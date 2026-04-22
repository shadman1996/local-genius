"""
Local Genius — Orchestrator

The central agentic loop that ties everything together.
Now supports continuous conversational loops and native file tools.
"""

import json
import logging
from typing import Any

from src.brain import Brain
from src.config import MAX_RETRIES
from src.gateway import Gateway, StatusReport
from src.memory import Memory
from src.safety_monitor import SafetyMonitor

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Manages the agentic feedback loop between Brain, SafetyMonitor,
    Gateway, and Memory.
    """

    def __init__(
        self,
        brain: Brain | None = None,
        safety: SafetyMonitor | None = None,
        gateway: Gateway | None = None,
        memory: Memory | None = None,
        max_retries: int | None = None,
    ):
        self.brain = brain or Brain()
        self.safety = safety or SafetyMonitor()
        self.gateway = gateway or Gateway()
        self.memory = memory or Memory()
        self.max_retries = max_retries or MAX_RETRIES

        logger.info(
            "Orchestrator initialized — max_retries=%d, safety_patterns=%d, memory_actions=%d",
            self.max_retries,
            self.safety.pattern_count,
            self.memory.total_actions,
        )

    # ------------------------------------------------------------------
    # Conversational Loop
    # ------------------------------------------------------------------

    def chat_turn(self, user_input: str, context_files: list[str] = None) -> dict[str, Any]:
        """
        Execute a single conversation turn through the agentic loop.
        Loops until the agent returns the 'reply' action.
        """
        logger.info("=" * 60)
        logger.info("NEW INPUT: %s", user_input)
        logger.info("=" * 60)

        steps: list[dict[str, Any]] = []

        # Prepare initial prompt
        prompt_parts = []
        
        # 1. Attach context files if any
        if context_files:
            prompt_parts.append("The user has attached the following files for context:")
            for cf in context_files:
                report = self.gateway.read_file(cf)
                if report.success:
                    prompt_parts.append(f"--- FILE: {cf} ---\n{report.output}\n--- END {cf} ---")
                else:
                    prompt_parts.append(f"--- FILE: {cf} ---\n(Failed to read: {report.error})\n--- END {cf} ---")
            prompt_parts.append("") # newline
            
        # 2. Inject memory context
        memory_context = self._build_memory_context(user_input)
        if memory_context:
            prompt_parts.append(memory_context)
            
        # 3. Add user input
        prompt_parts.append(f"USER: {user_input}")
        
        current_prompt = "\n".join(prompt_parts)

        for step_num in range(1, self.max_retries + 1):
            logger.info("--- Step %d/%d ---", step_num, self.max_retries)

            # 1. Ask the Brain
            action_block = self.brain.think(current_prompt)
            thought = action_block.get("thought", "")
            action = action_block.get("action", "reply")
            command = action_block.get("command", "")

            print(f"\n💭 Thought: {thought}")
            print(f"🎬 Action:  {action}")
            if command and action != "reply":
                print(f"📝 Command: {command}")

            step_record = {
                "step": step_num,
                "thought": thought,
                "action": action,
                "command": command,
                "result": None,
            }

            # 2. Handle parse errors
            if action == "error":
                print("⚠️  LLM returned an unparseable response. Retrying...")
                step_record["result"] = "Parse error — retrying"
                steps.append(step_record)
                current_prompt = (
                    "Your previous response was not valid JSON. "
                    "You MUST respond with a JSON object containing "
                    '"thought", "action", and "command" keys. Try again.'
                )
                continue

            # 3. Handle "reply" action (Goal / Turn Concluded)
            if action == "reply" or action == "done": # support legacy "done"
                print(f"💬 Reply: {command}")
                step_record["result"] = "Turn completed"
                steps.append(step_record)

                # Store in memory
                self.memory.store_action(
                    command=f"USER: {user_input}",
                    result=f"Completed in {step_num} steps. Reply: {command}",
                )
                return self._summary(steps, "completed", command)

            # 4. Handle System Commands
            if action == "bash_command":
                evaluation = self.safety.evaluate(command)

                if not evaluation.is_safe:
                    print(f"🛡️  BLOCKED: {evaluation.reason}")
                    step_record["result"] = evaluation.reason
                    steps.append(step_record)

                    self.memory.store_action(
                        command=command,
                        result=evaluation.reason,
                        was_blocked=True,
                    )

                    current_prompt = (
                        f"Your bash_command `{command}` was BLOCKED.\n"
                        f"Reason: {evaluation.reason}\n\n"
                        f"Analyze this error. Find a SAFE alternative approach."
                    )
                    continue

                print(f"⚡ Executing Bash: {command}")
                report = self.gateway.execute_command(command)
                feedback = report.to_feedback()

                print(feedback)
                step_record["result"] = feedback
                steps.append(step_record)

                self.memory.store_action(
                    command=command,
                    result=report.output if report.success else report.error,
                    was_blocked=False,
                )

                if report.success:
                    current_prompt = f"Command succeeded:\n{feedback}\n\nWhat is your next action?"
                else:
                    current_prompt = f"Command FAILED:\n{feedback}\n\nAnalyze the error and try a different approach."
                continue
                
            # 5. Handle File, Directory, Web, and Background Operations
            if action in ["read_file", "write_file", "replace_file_content", "list_directory", "web_search", "run_background"]:
                print(f"🔧 Tool Execution: {action}")
                
                try:
                    if action == "read_file":
                        report = self.gateway.read_file(command)
                    elif action == "list_directory":
                        report = self.gateway.list_directory(command)
                    elif action == "web_search":
                        report = self.gateway.web_search(command)
                    elif action == "run_background":
                        report = self.gateway.run_background(command)
                    else:
                        payload = json.loads(command)
                        path = payload.get("path", "")
                        if action == "write_file":
                            content = payload.get("content", "")
                            report = self.gateway.write_file(path, content)
                        elif action == "replace_file_content":
                            target = payload.get("target", "")
                            replacement = payload.get("replacement", "")
                            report = self.gateway.replace_file_content(path, target, replacement)
                except json.JSONDecodeError:
                    report = StatusReport(success=False, output="", error=f"Invalid JSON in command payload for {action}", channel="tool")
                except AttributeError:
                    report = StatusReport(success=False, output="", error=f"Missing required fields in payload for {action}", channel="tool")
                
                feedback = report.to_feedback()
                print(feedback)
                step_record["result"] = feedback
                steps.append(step_record)
                
                self.memory.store_action(
                    command=f"{action} on {command[:50]}...",
                    result=report.output if report.success else report.error,
                )
                
                current_prompt = f"{action} result:\n{feedback}\n\nWhat is your next action?"
                continue

            # 6. Handle MQTT actions
            if action == "mqtt_publish" and command:
                try:
                    payload = json.loads(command)
                    topic = payload.get("topic", "local-genius/command")
                    message = payload.get("message", command)
                except (json.JSONDecodeError, AttributeError):
                    topic = "local-genius/command"
                    message = command

                report = self.gateway.publish_mqtt(topic, message)
                feedback = report.to_feedback()
                print(feedback)
                step_record["result"] = feedback
                steps.append(step_record)

                self.memory.store_action(
                    command=f"MQTT:{topic} → {message}",
                    result=report.output if report.success else report.error,
                )

                current_prompt = f"MQTT publish result:\n{feedback}\n\nWhat is your next action?"
                continue

            # Fallback — unknown action
            print(f"❓ Unknown action: {action}")
            step_record["result"] = f"Unknown action type: {action}"
            steps.append(step_record)
            current_prompt = (
                f'Unknown action "{action}". Valid actions are: '
                f'"bash_command", "read_file", "write_file", "replace_file_content", "mqtt_publish", "reply". Try again.'
            )

        # Exhausted retries
        print(f"\n⛔ Max retries ({self.max_retries}) reached.")
        return self._summary(steps, "max_retries", "I reached the maximum number of internal steps before I could reply.")

    # ------------------------------------------------------------------
    # Context Builders
    # ------------------------------------------------------------------

    def _build_memory_context(self, goal: str) -> str:
        """Retrieve relevant past actions from memory."""
        recalled = self.memory.recall_similar(goal, n_results=3)
        if not recalled:
            return ""

        lines = ["Relevant past actions from memory:"]
        for item in recalled:
            meta = item.get("metadata", {})
            lines.append(
                f"  - [{meta.get('timestamp', '?')}] {item['document']}"
            )
        return "\n".join(lines)

    @staticmethod
    def _summary(
        steps: list[dict[str, Any]], status: str, reply_text: str
    ) -> dict[str, Any]:
        return {
            "steps": steps,
            "final_status": status,
            "total_steps": len(steps),
            "reply": reply_text
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Clean up all resources."""
        self.gateway.shutdown()
        logger.info("Orchestrator shutdown complete.")

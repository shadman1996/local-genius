"""
Local Genius — Orchestrator

The central agentic loop that ties everything together:

    User Goal → Brain (LLM) → Safety Monitor → Gateway (Execute) → Feedback → Brain

If a command is blocked or fails, the Orchestrator feeds the error back
into the Brain's context so it can self-correct. Memory is updated at
every step for persistent state.
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
    # Main Loop
    # ------------------------------------------------------------------

    def execute_goal(self, user_goal: str) -> dict[str, Any]:
        """
        Execute a user goal through the full agentic loop.

        Returns a summary dict with:
            - goal: The original user goal
            - steps: List of step dicts (thought, action, command, result)
            - final_status: "completed", "blocked", "max_retries", or "error"
            - total_steps: Number of loop iterations
        """
        logger.info("=" * 60)
        logger.info("NEW GOAL: %s", user_goal)
        logger.info("=" * 60)

        steps: list[dict[str, Any]] = []

        # Inject relevant memory context
        memory_context = self._build_memory_context(user_goal)
        initial_prompt = self._build_initial_prompt(user_goal, memory_context)

        current_prompt = initial_prompt

        for step_num in range(1, self.max_retries + 1):
            logger.info("--- Step %d/%d ---", step_num, self.max_retries)

            # 1. Ask the Brain
            action_block = self.brain.think(current_prompt)
            thought = action_block.get("thought", "")
            action = action_block.get("action", "done")
            command = action_block.get("command", "")

            print(f"\n💭 Thought: {thought}")
            print(f"🎬 Action:  {action}")
            if command:
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

            # 3. Handle "done" action
            if action == "done":
                print("✅ Task concluded by the Brain.")
                step_record["result"] = "Task completed"
                steps.append(step_record)

                # Store in memory
                self.memory.store_action(
                    command=f"GOAL: {user_goal}",
                    result=f"Completed in {step_num} steps. Final thought: {thought}",
                )
                return self._summary(user_goal, steps, "completed")

            # 4. Safety check
            if action == "bash_command" and command:
                evaluation = self.safety.evaluate(command)

                if not evaluation.is_safe:
                    print(f"🛡️  BLOCKED: {evaluation.reason}")
                    step_record["result"] = evaluation.reason
                    steps.append(step_record)

                    # Store blocked action in memory
                    self.memory.store_action(
                        command=command,
                        result=evaluation.reason,
                        was_blocked=True,
                    )

                    # Feed error back to LLM
                    current_prompt = (
                        f"Your previous command `{command}` was BLOCKED.\n"
                        f"Reason: {evaluation.reason}\n\n"
                        f"Analyze this error. Find a SAFE alternative approach "
                        f"to achieve the goal: {user_goal}\n"
                        f"Respond with a corrected JSON Action Block."
                    )
                    continue

                # 5. Execute the command via Gateway
                print(f"⚡ Executing: {command}")
                report: StatusReport = self.gateway.execute_command(command)
                feedback = report.to_feedback()

                print(feedback)
                step_record["result"] = feedback
                steps.append(step_record)

                # Store in memory
                self.memory.store_action(
                    command=command,
                    result=report.output if report.success else report.error,
                    was_blocked=False,
                )

                if report.success:
                    # Ask Brain if the goal is achieved or if more steps needed
                    current_prompt = (
                        f"Command executed successfully.\n{feedback}\n\n"
                        f"Original goal: {user_goal}\n"
                        f"Is the goal fully achieved? If yes, respond with "
                        f'action="done". If more steps are needed, provide '
                        f"the next command."
                    )
                else:
                    # Feed failure back
                    current_prompt = (
                        f"Command `{command}` FAILED.\n{feedback}\n\n"
                        f"Analyze the error and try a different approach "
                        f"to achieve: {user_goal}"
                    )
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

                current_prompt = (
                    f"MQTT publish result:\n{feedback}\n\n"
                    f"Original goal: {user_goal}\n"
                    f"Is the goal achieved? Respond accordingly."
                )
                continue

            # Fallback — unknown action
            print(f"❓ Unknown action: {action}")
            step_record["result"] = f"Unknown action type: {action}"
            steps.append(step_record)
            current_prompt = (
                f'Unknown action "{action}". Valid actions are: '
                f'"bash_command", "mqtt_publish", "done". Try again.'
            )

        # Exhausted retries
        print(f"\n⛔ Max retries ({self.max_retries}) reached.")
        return self._summary(user_goal, steps, "max_retries")

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
    def _build_initial_prompt(goal: str, memory_context: str) -> str:
        """Build the initial prompt for the Brain."""
        parts = [f"User Goal: {goal}"]
        if memory_context:
            parts.append(f"\n{memory_context}")
        parts.append(
            "\nProvide your JSON Action Block to begin working on this goal."
        )
        return "\n".join(parts)

    @staticmethod
    def _summary(
        goal: str, steps: list[dict[str, Any]], status: str
    ) -> dict[str, Any]:
        return {
            "goal": goal,
            "steps": steps,
            "final_status": status,
            "total_steps": len(steps),
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Clean up all resources."""
        self.gateway.shutdown()
        logger.info("Orchestrator shutdown complete.")

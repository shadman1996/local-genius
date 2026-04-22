"""
Local Genius — The Brain

Wraps the Ollama Python SDK to provide structured LLM inference.
The Brain receives a context (user goal + feedback history) and returns
a JSON Action Block that the Orchestrator can parse and execute.
"""

import json
import logging
from typing import Any

import ollama

from src.config import OLLAMA_HOST, OLLAMA_MODEL, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class Brain:
    """Interface to the local LLM via Ollama."""

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or OLLAMA_MODEL
        self.host = host or OLLAMA_HOST
        self.client = ollama.Client(host=self.host)
        self._conversation_history: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        logger.info("Brain initialized — model=%s host=%s", self.model, self.host)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def think(self, user_message: str) -> dict[str, Any]:
        """
        Send a message to the LLM and parse the structured JSON response.

        Args:
            user_message: The prompt (user goal, feedback, or context).

        Returns:
            Parsed dict with keys: thought, action, command.
            On parse failure returns a fallback dict with action="error".
        """
        self._conversation_history.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat(
                model=self.model,
                messages=self._conversation_history,
                options={"temperature": 0.2, "num_predict": 512},
            )
            raw_content: str = response["message"]["content"]
            logger.debug("Raw LLM response: %s", raw_content)

            # Append assistant response to history for multi-turn context
            self._conversation_history.append(
                {"role": "assistant", "content": raw_content}
            )

            return self._parse_response(raw_content)

        except ollama.ResponseError as exc:
            logger.error("Ollama API error: %s", exc)
            return self._error_block(f"Ollama API error: {exc}")

        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected Brain error: %s", exc)
            return self._error_block(f"Unexpected error: {exc}")

    def reset(self) -> None:
        """Clear conversation history (keeps the system prompt)."""
        self._conversation_history = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        logger.info("Brain conversation history reset.")

    def is_alive(self) -> bool:
        """Check if Ollama is reachable and the model is loaded."""
        try:
            models = self.client.list()
            model_names = [m.get("name", "") for m in models.get("models", [])]
            return any(self.model in name for name in model_names)
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> dict[str, Any]:
        """
        Extract JSON from the LLM response.

        The model sometimes wraps JSON in markdown code fences — we handle that.
        """
        text = raw.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            parsed = json.loads(text)
            # Validate required keys
            return {
                "thought": parsed.get("thought", ""),
                "action": parsed.get("action", "done"),
                "command": parsed.get("command", ""),
            }
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON — raw: %s", raw[:200])
            return {
                "thought": raw,
                "action": "error",
                "command": "",
                "parse_error": True,
            }

    @staticmethod
    def _error_block(message: str) -> dict[str, Any]:
        return {
            "thought": message,
            "action": "error",
            "command": "",
        }

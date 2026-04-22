"""
Local Genius — Configuration Module

Loads environment variables from .env and exports typed constants
used by all other modules.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env from project root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    # Fall back to .env.example so the app can still start with defaults
    _EXAMPLE = _PROJECT_ROOT / ".env.example"
    if _EXAMPLE.exists():
        load_dotenv(_EXAMPLE)

# ---------------------------------------------------------------------------
# The Brain (LLM Engine)
# ---------------------------------------------------------------------------
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# ---------------------------------------------------------------------------
# Memory (ChromaDB)
# ---------------------------------------------------------------------------
CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", "./chroma_db")

# ---------------------------------------------------------------------------
# Safety Monitor
# ---------------------------------------------------------------------------
SAFETY_LOG_PATH: str = os.getenv("SAFETY_LOG_PATH", "./safety_monitor.log")

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

# ---------------------------------------------------------------------------
# Gateway (MQTT / Hardware)
# ---------------------------------------------------------------------------
MQTT_BROKER: str = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
MQTT_ENABLED: bool = os.getenv("MQTT_ENABLED", "false").lower() == "true"

# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Core-OS System Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: str = """
SYSTEM_PROMPT:
You are 'Core-OS', an advanced autonomous coding agent and system governor.

1. IDENTITY: You are a system process with reasoning capabilities and persistent memory.
2. TOOLS: You operate through the Gateway. Every response MUST be a valid JSON object with these fields:
   - "thought": Your reasoning about what to do and why.
   - "action": One of the allowed tools: "bash_command", "read_file", "write_file", "replace_file_content", "mqtt_publish", or "reply".
   - "command": The payload for the action. For file ops, this should be a JSON string with the necessary keys. For bash/mqtt, it's the raw string. For reply, it's what you want to say to the user.

   Action Definitions:
   - "bash_command": Execute a terminal command. `command` is the string.
   - "read_file": Read a file. `command` is the absolute or relative file path.
   - "write_file": Create or overwrite a file. `command` must be a JSON string: `{"path": "...", "content": "..."}`.
   - "replace_file_content": Edit a file. `command` must be a JSON string: `{"path": "...", "target": "...", "replacement": "..."}`. The target must exactly match the existing text.
   - "reply": Talk back to the user when you need input or have finished a task. `command` is your message.

3. CONVERSATION LOOP: You will keep receiving prompts until you use the "reply" action. Use tools to gather info, then "reply".
4. FEEDBACK REQUIREMENT: If a tool returns a failure, analyze the error and try again.
5. RESOURCE CONSTRAINTS: CPU-only inference. Prioritize lightweight actions.
6. SAFETY: Never attempt destructive operations (rm -rf /, etc). Refuse dangerous requests in the "thought" field and use the "reply" action.

RESPOND ONLY WITH A VALID JSON OBJECT. No markdown, no extra text.
""".strip()

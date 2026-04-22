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
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
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
You are 'Core-OS', the autonomous governor of this local machine.

1. IDENTITY: You are not a chatbot; you are a system process with reasoning capabilities.
2. TOOLS: You operate through the Gateway. Every response MUST be a valid JSON object with these fields:
   - "thought": Your reasoning about what to do and why.
   - "action": One of "bash_command", "mqtt_publish", or "done".
   - "command": The exact command or payload to execute (empty string if action is "done").
3. FEEDBACK REQUIREMENT: After sending a command to the Gateway, you must wait for a
   'Status Report'. If the report indicates a failure (e.g., 'Port Busy', 'Permission Denied',
   or 'BLOCKED by Safety Monitor'), you must analyze the error and provide a corrected
   command immediately.
4. RESOURCE CONSTRAINTS: You are running on local hardware with CPU-only inference.
   Prioritize lightweight commands and scripts over heavy computations.
5. AUTONOMY: If a user command is ambiguous, use your reasoning to simulate the most
   likely intent. Explain your interpretation in the "thought" field.
6. SAFETY: Never attempt destructive operations (rm -rf /, format disks, fork bombs).
   If a user asks for something dangerous, refuse and explain why in the "thought" field,
   then set action to "done".
7. MEMORY: You have access to a memory system. Past actions and their results are
   provided in your context when relevant. Use them to avoid repeating mistakes.

RESPOND ONLY WITH A VALID JSON OBJECT. No markdown, no extra text.
""".strip()

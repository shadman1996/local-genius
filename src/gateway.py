"""
Local Genius — Gateway Module

The bridge between digital logic and the real world.
Handles two execution channels:

1. **System commands** — Executes shell commands via subprocess with
   timeout and output capture.
2. **MQTT** — Publishes/subscribes to an MQTT broker for hardware
   control (GPIO, sensors, actuators via Home Assistant or OpenClaw).
"""

import logging
import os
import subprocess
import threading
import urllib.request
import urllib.parse
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from src.config import MQTT_BROKER, MQTT_ENABLED, MQTT_PORT

logger = logging.getLogger(__name__)


@dataclass
class StatusReport:
    """Standardized result from a gateway operation."""

    success: bool
    output: str
    error: str = ""
    channel: str = "system"  # "system" or "mqtt"

    def to_feedback(self) -> str:
        """Format as a feedback string for the LLM."""
        if self.success:
            return f"[✅ SUCCESS via {self.channel}]\nOutput:\n{self.output}"
        return (
            f"[❌ FAILURE via {self.channel}]\n"
            f"Error: {self.error}\n"
            f"Output: {self.output}"
        )


class Gateway:
    """
    Execution gateway for system commands and MQTT hardware control.
    """

    def __init__(self, command_timeout: int = 30):
        self.command_timeout = command_timeout
        self._mqtt_client: Any | None = None
        self._mqtt_callbacks: dict[str, Callable] = {}

        if MQTT_ENABLED:
            self._init_mqtt()

    # ------------------------------------------------------------------
    # System Command Execution
    # ------------------------------------------------------------------

    def execute_command(self, command: str) -> StatusReport:
        """
        Execute a shell command via subprocess.

        Uses a timeout to prevent runaway processes. Captures both
        stdout and stderr for feedback to the LLM.
        """
        logger.info("Executing command: %s", command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
                cwd=None,  # Use current working directory
            )

            if result.returncode == 0:
                report = StatusReport(
                    success=True,
                    output=result.stdout.strip() or "(no output)",
                    channel="system",
                )
            else:
                report = StatusReport(
                    success=False,
                    output=result.stdout.strip(),
                    error=result.stderr.strip() or f"Exit code: {result.returncode}",
                    channel="system",
                )

        except subprocess.TimeoutExpired:
            report = StatusReport(
                success=False,
                output="",
                error=f"Command timed out after {self.command_timeout}s",
                channel="system",
            )

        except Exception as exc:  # noqa: BLE001
            report = StatusReport(
                success=False,
                output="",
                error=f"Execution error: {exc}",
                channel="system",
            )

        logger.info(
            "Command result: success=%s output_len=%d",
            report.success,
            len(report.output),
        )
        return report

    # ------------------------------------------------------------------
    # File Operations
    # ------------------------------------------------------------------

    def read_file(self, path: str) -> StatusReport:
        """Read a file's contents."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return StatusReport(success=True, output=content, channel="file")
        except Exception as exc:
            return StatusReport(success=False, output="", error=str(exc), channel="file")

    def write_file(self, path: str, content: str) -> StatusReport:
        """Create or overwrite a file."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return StatusReport(success=True, output=f"Successfully wrote to {path}", channel="file")
        except Exception as exc:
            return StatusReport(success=False, output="", error=str(exc), channel="file")

    def replace_file_content(self, path: str, target: str, replacement: str) -> StatusReport:
        """Replace an exact string in a file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if target not in content:
                return StatusReport(
                    success=False, 
                    output="", 
                    error=f"Target string not found in {path}. It must match exactly including whitespace.", 
                    channel="file"
                )
                
            new_content = content.replace(target, replacement)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
                
            return StatusReport(success=True, output=f"Successfully updated {path}", channel="file")
        except Exception as exc:
            return StatusReport(success=False, output="", error=str(exc), channel="file")

    def list_directory(self, path: str) -> StatusReport:
        """List contents of a directory."""
        try:
            entries = os.listdir(path)
            lines = []
            for entry in entries:
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    lines.append(f"[DIR]  {entry}/")
                else:
                    size = os.path.getsize(full_path)
                    lines.append(f"[FILE] {entry} ({size} bytes)")
            return StatusReport(success=True, output="\n".join(lines), channel="file")
        except Exception as exc:
            return StatusReport(success=False, output="", error=str(exc), channel="file")

    # ------------------------------------------------------------------
    # Web & Background Tasks
    # ------------------------------------------------------------------

    def web_search(self, query: str) -> StatusReport:
        """Search Wikipedia for information."""
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&utf8=&format=json"
            req = urllib.request.Request(url, headers={'User-Agent': 'LocalGenius/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                
            results = data.get('query', {}).get('search', [])
            if not results:
                return StatusReport(success=False, output="", error="No Wikipedia results found.", channel="web")
                
            snippets = []
            for r in results[:3]:
                clean_snippet = r['snippet'].replace('<span class="searchmatch">', '').replace('</span>', '').replace('&quot;', '"')
                snippets.append(f"Title: {r['title']}\nSnippet: {clean_snippet}\n")
                
            return StatusReport(success=True, output="\n".join(snippets), channel="web")
        except Exception as exc:
            return StatusReport(success=False, output="", error=str(exc), channel="web")

    def run_background(self, command: str) -> StatusReport:
        """Run a command in the background without blocking."""
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=None
            )
            return StatusReport(success=True, output=f"Background process started. PID: {process.pid}", channel="system")
        except Exception as exc:
            return StatusReport(success=False, output="", error=str(exc), channel="system")

    # ------------------------------------------------------------------
    # MQTT Hardware Gateway
    # ------------------------------------------------------------------

    def _init_mqtt(self) -> None:
        """Initialize MQTT client for hardware communication."""
        try:
            import paho.mqtt.client as mqtt_client

            self._mqtt_client = mqtt_client.Client(
                mqtt_client.CallbackAPIVersion.VERSION2,
                client_id="local-genius-gateway",
            )
            self._mqtt_client.on_connect = self._on_mqtt_connect
            self._mqtt_client.on_message = self._on_mqtt_message

            self._mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self._mqtt_client.loop_start()
            logger.info("MQTT connected to %s:%d", MQTT_BROKER, MQTT_PORT)

        except ImportError:
            logger.warning("paho-mqtt not installed — MQTT gateway disabled.")
            self._mqtt_client = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("MQTT connection failed: %s", exc)
            self._mqtt_client = None

    def _on_mqtt_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        logger.info("MQTT connected with result code %s", rc)
        # Re-subscribe to all registered topics
        for topic in self._mqtt_callbacks:
            client.subscribe(topic)

    def _on_mqtt_message(self, client: Any, userdata: Any, msg: Any) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        logger.debug("MQTT message: %s → %s", topic, payload[:100])

        if topic in self._mqtt_callbacks:
            self._mqtt_callbacks[topic](topic, payload)

    def publish_mqtt(self, topic: str, payload: str) -> StatusReport:
        """Publish a message to an MQTT topic."""
        if not self._mqtt_client:
            return StatusReport(
                success=False,
                output="",
                error="MQTT client not initialized. Set MQTT_ENABLED=true in .env",
                channel="mqtt",
            )

        try:
            result = self._mqtt_client.publish(topic, payload)
            result.wait_for_publish(timeout=5)
            return StatusReport(
                success=True,
                output=f"Published to {topic}: {payload}",
                channel="mqtt",
            )
        except Exception as exc:  # noqa: BLE001
            return StatusReport(
                success=False,
                output="",
                error=f"MQTT publish failed: {exc}",
                channel="mqtt",
            )

    def subscribe_mqtt(self, topic: str, callback: Callable) -> None:
        """Subscribe to an MQTT topic with a callback."""
        self._mqtt_callbacks[topic] = callback
        if self._mqtt_client:
            self._mqtt_client.subscribe(topic)
            logger.info("Subscribed to MQTT topic: %s", topic)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Clean up resources."""
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
            logger.info("MQTT client disconnected.")

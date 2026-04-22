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
import subprocess
import threading
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

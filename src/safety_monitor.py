"""
Local Genius — Safety Monitor

The gatekeeper between the LLM's intent and the actual system.
Every command proposed by the Brain passes through here before execution.
Dangerous commands are blocked, and the rejection reason is fed back
to the LLM so it can self-correct.

All decisions (approved and blocked) are logged for audit.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import ClassVar

from src.config import SAFETY_LOG_PATH

# ---------------------------------------------------------------------------
# Dedicated audit logger — writes to safety_monitor.log
# ---------------------------------------------------------------------------
audit_logger = logging.getLogger("safety_audit")
_audit_handler = logging.FileHandler(SAFETY_LOG_PATH)
_audit_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
)
audit_logger.addHandler(_audit_handler)
audit_logger.setLevel(logging.INFO)

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of evaluating a command against safety rules."""

    is_safe: bool
    reason: str
    matched_pattern: str = ""


@dataclass
class SafetyMonitor:
    """
    Regex-based command gatekeeper.

    Maintains a compiled list of dangerous patterns. Commands matching
    any pattern are blocked. All evaluations are logged.
    """

    # Class-level dangerous patterns — extend via add_pattern()
    DANGEROUS_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        # (pattern, human-readable description)
        (r"rm\s+-r[fF]?\s+/(?:\s|$)", "Recursive delete on root filesystem"),
        (r"rm\s+-r[fF]?\s+/\*", "Recursive delete on root glob"),
        (r"rm\s+-r[fF]?\s+\*", "Recursive delete on wildcard"),
        (r"rm\s+-r[fF]?\s+~/?$", "Recursive delete on home directory"),
        (r"mkfs\.", "Formatting a disk partition"),
        (r"dd\s+if=.*\s+of=/dev/", "Raw disk overwrite via dd"),
        (r"chmod\s+-R\s+777\s+/(?:\s|$)", "Recursive permissive chmod on root"),
        (r"chown\s+-R\s+.*\s+/(?:\s|$)", "Recursive chown on root"),
        (r">\s*/dev/sd[a-z]", "Redirection to raw disk device"),
        (r"wget\s+.*\|\s*(?:bash|sh)", "Download-and-execute via wget"),
        (r"curl\s+.*\|\s*(?:bash|sh)", "Download-and-execute via curl"),
        (r":\(\)\{\s*:\|:&\s*\};:", "Fork bomb"),
        (r"mv\s+.*\s+/dev/null", "Moving files to /dev/null"),
        (r"shutdown\s", "System shutdown"),
        (r"reboot\b", "System reboot"),
        (r"init\s+[06]", "System halt/reboot via init"),
        (r"systemctl\s+(halt|poweroff|reboot)", "Systemctl power command"),
        (r"echo\s+.*>\s*/etc/passwd", "Overwriting /etc/passwd"),
        (r"echo\s+.*>\s*/etc/shadow", "Overwriting /etc/shadow"),
        (r"python.*-c\s+.*import\s+os.*system", "Python shell escape attempt"),
    ]

    # Instance state
    _custom_patterns: list[tuple[str, str]] = field(default_factory=list)
    _compiled: list[tuple[re.Pattern, str]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile all patterns (class-level + custom) for performance."""
        all_patterns = self.DANGEROUS_PATTERNS + self._custom_patterns
        self._compiled = [
            (re.compile(pattern, re.IGNORECASE), desc)
            for pattern, desc in all_patterns
        ]
        logger.info("SafetyMonitor compiled %d patterns.", len(self._compiled))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, command: str) -> EvaluationResult:
        """
        Evaluate a command against all safety rules.

        Returns an EvaluationResult with is_safe, reason, and matched_pattern.
        """
        command = command.strip()

        if not command:
            result = EvaluationResult(
                is_safe=False, reason="Empty command — nothing to execute."
            )
            audit_logger.warning("BLOCKED | (empty) | %s", result.reason)
            return result

        for pattern, description in self._compiled:
            if pattern.search(command):
                result = EvaluationResult(
                    is_safe=False,
                    reason=f"BLOCKED by Safety Monitor: {description}",
                    matched_pattern=pattern.pattern,
                )
                audit_logger.warning(
                    "BLOCKED | %s | %s | pattern=%s",
                    command,
                    description,
                    pattern.pattern,
                )
                return result

        # Command passed all checks
        result = EvaluationResult(
            is_safe=True, reason="Command passed all safety checks."
        )
        audit_logger.info("APPROVED | %s", command)
        return result

    def add_pattern(self, pattern: str, description: str) -> None:
        """Add a custom dangerous pattern at runtime."""
        self._custom_patterns.append((pattern, description))
        self._compile_patterns()
        logger.info("Added custom safety pattern: %s (%s)", pattern, description)

    @property
    def pattern_count(self) -> int:
        return len(self._compiled)

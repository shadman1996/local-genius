"""
Tests for the Orchestrator module.

Uses mock objects to simulate the Brain (LLM) so tests run
without Ollama. Verifies the feedback loop, retry logic,
and safety integration.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Any

from src.orchestrator import Orchestrator
from src.safety_monitor import SafetyMonitor
from src.gateway import Gateway, StatusReport
from src.memory import Memory


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def mock_brain():
    """Mock Brain that returns predefined responses."""
    brain = MagicMock()
    brain.is_alive.return_value = True
    brain.reset.return_value = None
    return brain


@pytest.fixture
def safety():
    return SafetyMonitor()


@pytest.fixture
def mock_gateway():
    """Mock Gateway that simulates successful execution."""
    gw = MagicMock(spec=Gateway)
    gw.execute_command.return_value = StatusReport(
        success=True, output="command output", channel="system"
    )
    gw.shutdown.return_value = None
    return gw


@pytest.fixture
def tmp_memory(tmp_path):
    """Memory backed by a temporary ChromaDB directory."""
    return Memory(db_path=str(tmp_path / "test_chroma"))


@pytest.fixture
def orchestrator(mock_brain, safety, mock_gateway, tmp_memory):
    return Orchestrator(
        brain=mock_brain,
        safety=safety,
        gateway=mock_gateway,
        memory=tmp_memory,
        max_retries=3,
    )


# ======================================================================
# Happy path
# ======================================================================

class TestHappyPath:
    """Test successful goal execution."""

    def test_single_step_completion(self, orchestrator, mock_brain):
        """Brain immediately returns done — single-step completion."""
        mock_brain.think.return_value = {
            "thought": "Goal is already achieved.",
            "action": "reply",
            "command": "Done.",
        }

        result = orchestrator.chat_turn("Say hello")

        assert result["final_status"] == "completed"
        assert result["total_steps"] == 1
        mock_brain.think.assert_called_once()

    def test_command_then_done(self, orchestrator, mock_brain, mock_gateway):
        """Brain proposes a command, it succeeds, then Brain says done."""
        mock_brain.think.side_effect = [
            {
                "thought": "I need to list files.",
                "action": "bash_command",
                "command": "ls -la",
            },
            {
                "thought": "Files listed successfully. Goal achieved.",
                "action": "reply",
                "command": "Done.",
            },
        ]

        result = orchestrator.chat_turn("List files")

        assert result["final_status"] == "completed"
        assert result["total_steps"] == 2
        mock_gateway.execute_command.assert_called_once_with("ls -la")


# ======================================================================
# Feedback loop — blocked commands
# ======================================================================

class TestFeedbackLoop:
    """Test that blocked commands trigger a retry with feedback."""

    def test_blocked_command_retries(self, orchestrator, mock_brain):
        """
        Brain proposes a dangerous command → gets blocked →
        receives feedback → proposes a safe alternative → done.
        """
        mock_brain.think.side_effect = [
            # Step 1: Dangerous command
            {
                "thought": "I need to delete everything.",
                "action": "bash_command",
                "command": "rm -rf /",
            },
            # Step 2: Corrected (safe) command
            {
                "thought": "Previous was blocked. I'll clean only the temp dir.",
                "action": "bash_command",
                "command": "rm -rf ./tmp_cache/",
            },
            # Step 3: Done
            {
                "thought": "Goal achieved.",
                "action": "reply",
                "command": "Done.",
            },
        ]

        result = orchestrator.chat_turn("Clean up temporary files")

        assert result["final_status"] == "completed"
        assert result["total_steps"] == 3

        # Verify the first (dangerous) command was never executed
        calls = orchestrator.gateway.execute_command.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] == "rm -rf ./tmp_cache/"

    def test_max_retries_exhausted(self, orchestrator, mock_brain):
        """Brain keeps proposing dangerous commands — exhausts retries."""
        mock_brain.think.return_value = {
            "thought": "Must delete root.",
            "action": "bash_command",
            "command": "rm -rf /",
        }

        result = orchestrator.chat_turn("Delete everything")

        assert result["final_status"] == "max_retries"
        assert result["total_steps"] == 3  # max_retries = 3
        # Gateway should NEVER be called
        orchestrator.gateway.execute_command.assert_not_called()


# ======================================================================
# Error handling
# ======================================================================

class TestErrorHandling:
    """Test parse errors and execution failures."""

    def test_parse_error_retry(self, orchestrator, mock_brain):
        """LLM returns unparseable response → gets feedback → corrects."""
        mock_brain.think.side_effect = [
            # Step 1: Parse error
            {
                "thought": "Some gibberish",
                "action": "error",
                "command": "",
                "parse_error": True,
            },
            # Step 2: Corrected
            {
                "thought": "Now responding correctly.",
                "action": "reply",
                "command": "Done.",
            },
        ]

        result = orchestrator.chat_turn("Do something")
        assert result["final_status"] == "completed"
        assert result["total_steps"] == 2

    def test_execution_failure_feedback(self, orchestrator, mock_brain, mock_gateway):
        """Command execution fails → error fed back → Brain tries again."""
        mock_gateway.execute_command.side_effect = [
            StatusReport(success=False, output="", error="Permission denied", channel="system"),
            StatusReport(success=True, output="done", channel="system"),
        ]

        mock_brain.think.side_effect = [
            {
                "thought": "Running restricted command.",
                "action": "bash_command",
                "command": "cat /etc/shadow_backup",
            },
            {
                "thought": "Permission denied. Trying accessible file.",
                "action": "bash_command",
                "command": "cat /etc/hostname",
            },
            {
                "thought": "Got the hostname. Done.",
                "action": "reply",
                "command": "Done.",
            },
        ]

        result = orchestrator.chat_turn("Get system info")
        assert result["final_status"] == "completed"


# ======================================================================
# Memory integration
# ======================================================================

class TestMemoryIntegration:
    """Verify actions are stored in memory."""

    def test_blocked_action_stored(self, orchestrator, mock_brain, tmp_memory):
        """Blocked commands should be recorded in memory."""
        mock_brain.think.side_effect = [
            {"thought": "Deleting root.", "action": "bash_command", "command": "rm -rf /"},
            {"thought": "Done.", "action": "reply", "command": "Done."},
        ]

        orchestrator.chat_turn("Clean up")

        assert tmp_memory.total_actions >= 1
        recent = tmp_memory.recall_recent(n=5)
        blocked_actions = [
            a for a in recent if a["metadata"].get("was_blocked")
        ]
        assert len(blocked_actions) >= 1

    def test_successful_action_stored(self, orchestrator, mock_brain, tmp_memory):
        """Successful commands should be recorded in memory."""
        mock_brain.think.side_effect = [
            {"thought": "Listing files.", "action": "bash_command", "command": "ls"},
            {"thought": "Done.", "action": "reply", "command": "Done."},
        ]

        orchestrator.chat_turn("List files")

        assert tmp_memory.total_actions >= 1

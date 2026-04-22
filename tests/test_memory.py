"""
Tests for the Memory module.

Uses a temporary ChromaDB directory so tests don't pollute
the real database.
"""

import pytest

from src.memory import Memory


@pytest.fixture
def memory(tmp_path):
    """Fresh Memory instance backed by a temp directory."""
    return Memory(db_path=str(tmp_path / "test_chroma"))


# ======================================================================
# Store and retrieve
# ======================================================================

class TestStoreAndRetrieve:
    """Verify basic store → retrieve cycle."""

    def test_store_action(self, memory):
        doc_id = memory.store_action(
            command="ls -la",
            result="total 42\ndrwxr-xr-x ...",
        )
        assert doc_id.startswith("cmd_")
        assert memory.total_actions == 1

    def test_store_multiple_actions(self, memory):
        memory.store_action(command="ls", result="file1 file2")
        memory.store_action(command="pwd", result="/home/user")
        memory.store_action(command="date", result="2026-04-22")
        assert memory.total_actions == 3

    def test_recall_recent(self, memory):
        memory.store_action(command="echo hello", result="hello")
        memory.store_action(command="echo world", result="world")

        recent = memory.recall_recent(n=5)
        assert len(recent) == 2
        assert all("document" in item for item in recent)
        assert all("metadata" in item for item in recent)

    def test_store_blocked_action(self, memory):
        memory.store_action(
            command="rm -rf /",
            result="BLOCKED",
            was_blocked=True,
        )

        recent = memory.recall_recent(n=1)
        assert len(recent) == 1
        assert recent[0]["metadata"]["was_blocked"] is True


# ======================================================================
# Semantic recall
# ======================================================================

class TestSemanticRecall:
    """Verify semantic search over past actions."""

    def test_recall_similar(self, memory):
        memory.store_action(command="ls /var/log", result="syslog auth.log")
        memory.store_action(command="df -h", result="50% used")
        memory.store_action(command="cat /etc/hostname", result="my-server")

        results = memory.recall_similar("show me log files", n_results=2)
        assert len(results) <= 2
        assert all("document" in r for r in results)
        assert all("distance" in r for r in results)

    def test_recall_empty_memory(self, memory):
        results = memory.recall_similar("anything")
        assert results == []

    def test_recall_does_not_exceed_count(self, memory):
        memory.store_action(command="cmd1", result="r1")
        # Requesting more results than exist should not error
        results = memory.recall_similar("test", n_results=100)
        assert len(results) == 1


# ======================================================================
# Session summaries
# ======================================================================

class TestSessionSummaries:
    """Verify session summary storage."""

    def test_store_session_summary(self, memory):
        doc_id = memory.store_session_summary("User asked to list files. Completed.")
        assert doc_id.startswith("session_")


# ======================================================================
# Clear
# ======================================================================

class TestClear:
    """Verify memory can be wiped."""

    def test_clear_resets_count(self, memory):
        memory.store_action(command="test", result="ok")
        assert memory.total_actions == 1

        memory.clear()
        assert memory.total_actions == 0

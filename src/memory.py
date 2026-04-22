"""
Local Genius — Memory Module

Persistent vector memory backed by ChromaDB.
Stores every action the agent takes along with its result,
enabling semantic recall ("what did I do yesterday?") and
context injection into the LLM's prompt.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import chromadb

from src.config import CHROMA_DB_PATH

logger = logging.getLogger(__name__)


class Memory:
    """
    ChromaDB-backed persistent memory for the Local Genius agent.

    Collections:
        - command_history: Every command executed + its result.
        - session_context: High-level session summaries.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or CHROMA_DB_PATH
        self.client = chromadb.PersistentClient(path=self.db_path)

        # Create or open collections
        self.command_history = self.client.get_or_create_collection(
            name="command_history",
            metadata={"description": "Every command executed by the agent"},
        )
        self.session_context = self.client.get_or_create_collection(
            name="session_context",
            metadata={"description": "High-level session summaries"},
        )
        logger.info(
            "Memory initialized — path=%s, history_count=%d",
            self.db_path,
            self.command_history.count(),
        )

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store_action(
        self,
        command: str,
        result: str,
        was_blocked: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Record an action (command + result) in persistent memory.

        Returns the generated document ID.
        """
        now = datetime.now(timezone.utc)
        doc_id = f"cmd_{now.strftime('%Y%m%d_%H%M%S_%f')}"

        doc_text = f"Command: {command}\nResult: {result}"

        meta = {
            "command": command,
            "was_blocked": was_blocked,
            "timestamp": now.isoformat(),
            **(metadata or {}),
        }

        self.command_history.add(
            documents=[doc_text],
            metadatas=[meta],
            ids=[doc_id],
        )
        logger.debug("Stored action: %s → %s", doc_id, command[:80])
        return doc_id

    def store_session_summary(self, summary: str) -> str:
        """Store a high-level session summary."""
        now = datetime.now(timezone.utc)
        doc_id = f"session_{now.strftime('%Y%m%d_%H%M%S')}"

        self.session_context.add(
            documents=[summary],
            metadatas=[{"timestamp": now.isoformat()}],
            ids=[doc_id],
        )
        logger.debug("Stored session summary: %s", doc_id)
        return doc_id

    # ------------------------------------------------------------------
    # Recall
    # ------------------------------------------------------------------

    def recall_similar(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """
        Semantic search over past actions.

        Args:
            query: Natural language query (e.g., "what did I do yesterday?").
            n_results: Max results to return.

        Returns:
            List of dicts with keys: document, metadata, distance.
        """
        if self.command_history.count() == 0:
            return []

        # Don't request more results than exist
        actual_n = min(n_results, self.command_history.count())

        results = self.command_history.query(
            query_texts=[query],
            n_results=actual_n,
        )

        recalled = []
        if results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                recalled.append(
                    {"document": doc, "metadata": meta, "distance": dist}
                )

        logger.debug("Recalled %d results for query: %s", len(recalled), query[:60])
        return recalled

    def recall_recent(self, n: int = 10) -> list[dict[str, Any]]:
        """
        Retrieve the most recent actions (by insertion order).

        Returns list of dicts with keys: id, document, metadata.
        """
        if self.command_history.count() == 0:
            return []

        actual_n = min(n, self.command_history.count())
        results = self.command_history.peek(limit=actual_n)

        recent = []
        if results["documents"]:
            for doc_id, doc, meta in zip(
                results["ids"],
                results["documents"],
                results["metadatas"],
            ):
                recent.append({"id": doc_id, "document": doc, "metadata": meta})

        return recent

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @property
    def total_actions(self) -> int:
        return self.command_history.count()

    def clear(self) -> None:
        """Delete all collections and recreate them (use with caution)."""
        self.client.delete_collection("command_history")
        self.client.delete_collection("session_context")
        self.command_history = self.client.get_or_create_collection(
            name="command_history"
        )
        self.session_context = self.client.get_or_create_collection(
            name="session_context"
        )
        logger.warning("Memory cleared — all collections deleted and recreated.")

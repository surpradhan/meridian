"""
Query History Manager

Persists query history to SQLite so it survives process restarts.
Accessed via REST API and the Gradio UI sidebar.

Thread-safety: a single shared connection is used (SQLite supports
concurrent reads in WAL mode, and all writes are serialised through
``self._lock``).
"""

import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS query_history (
    id          TEXT PRIMARY KEY,
    question    TEXT NOT NULL,
    domain      TEXT,
    sql         TEXT,
    row_count   INTEGER,
    confidence  REAL,
    error       TEXT,
    conversation_id TEXT,
    created_at  TEXT NOT NULL
);
"""


class HistoryManager:
    """Persists query history to a SQLite database.

    Uses a single shared ``sqlite3.Connection`` (``check_same_thread=False``)
    protected by a ``threading.Lock`` so FastAPI worker threads don't race.
    """

    def __init__(self, db_path: str = "meridian.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_table()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        with self._lock:
            self._conn.execute(_CREATE_TABLE_SQL)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(
        self,
        question: str,
        result: Dict[str, Any],
        conversation_id: Optional[str] = None,
    ) -> str:
        """Persist a completed query and return its history ID."""
        history_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        row_count = result.get("row_count")
        if row_count is not None:
            try:
                row_count = int(row_count)
            except (TypeError, ValueError):
                row_count = None

        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO query_history
                        (id, question, domain, sql, row_count, confidence,
                         error, conversation_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        history_id,
                        question,
                        result.get("domain"),
                        result.get("sql"),
                        row_count,
                        result.get("confidence"),
                        result.get("error"),
                        conversation_id,
                        now,
                    ),
                )
                self._conn.commit()
            logger.debug(f"Saved query history: {history_id}")
        except Exception as e:
            logger.warning(f"HistoryManager.save failed: {e}")

        return history_id

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent queries, newest first."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM query_history ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"HistoryManager.list failed: {e}")
            return []

    def get(self, history_id: str) -> Optional[Dict[str, Any]]:
        """Return a single history entry by ID."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT * FROM query_history WHERE id = ?", (history_id,)
                ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.warning(f"HistoryManager.get failed: {e}")
            return None

    def delete(self, history_id: str) -> bool:
        """Delete a history entry. Returns True if a row was deleted."""
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "DELETE FROM query_history WHERE id = ?", (history_id,)
                )
                self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.warning(f"HistoryManager.delete failed: {e}")
            return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_history_manager: Optional[HistoryManager] = None


def get_history_manager() -> HistoryManager:
    """Return the process-wide HistoryManager singleton."""
    global _history_manager
    if _history_manager is None:
        try:
            from app.config import settings
            db_path = settings.database_url.replace("sqlite:///", "")
        except Exception:
            db_path = "meridian.db"
        _history_manager = HistoryManager(db_path)
    return _history_manager

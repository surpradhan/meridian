"""
Auth Store

SQLite-backed persistence for users and audit logs.
Follows the same sqlite3 pattern as HistoryManager for consistency.

Roles:
  admin   — full access to all domains; can manage users
  analyst — execute queries on allowed_domains
  viewer  — explore/list on allowed_domains, no query execution; sensitive fields masked
"""

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

_CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'viewer',
    allowed_domains TEXT NOT NULL DEFAULT '[]',
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);
"""

_CREATE_AUDIT_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    username    TEXT,
    action      TEXT NOT NULL,
    resource    TEXT NOT NULL,
    domain      TEXT,
    status_code INTEGER,
    client_ip   TEXT,
    created_at  TEXT NOT NULL
);
"""

_AUDIT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_audit_user_id  ON audit_log (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created  ON audit_log (created_at);
"""


@dataclass
class User:
    id: str
    username: str
    email: str
    password_hash: str
    role: str
    allowed_domains: List[str]
    is_active: bool
    created_at: str

    def can_access_domain(self, domain: str) -> bool:
        """Check domain access.

        - admin: always True.
        - analyst / viewer with empty allowed_domains: False (fail closed — no access
          until explicitly granted). Assign domains at registration time.
        - analyst / viewer with non-empty allowed_domains: True only if domain listed.
        """
        if self.role == "admin":
            return True
        return domain in self.allowed_domains

    def can_execute_queries(self) -> bool:
        return self.role in ("admin", "analyst")


@dataclass
class AuditEntry:
    id: str
    user_id: Optional[str]
    username: Optional[str]
    action: str
    resource: str
    domain: Optional[str]
    status_code: Optional[int]
    client_ip: Optional[str]
    created_at: str


class AuthStore:
    """Persists users and audit logs to SQLite.

    Thread-safe via a per-instance Lock (same pattern as HistoryManager).
    """

    def __init__(self, db_path: str = "meridian.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        with self._lock:
            self._conn.execute(_CREATE_USERS_SQL)
            self._conn.execute(_CREATE_AUDIT_SQL)
            for stmt in _AUDIT_INDEX_SQL.strip().split("\n"):
                if stmt.strip():
                    self._conn.execute(stmt)
            self._conn.commit()

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        role: str = "viewer",
        allowed_domains: Optional[List[str]] = None,
    ) -> User:
        user_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        domains_json = json.dumps(allowed_domains or [])

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO users (id, username, email, password_hash, role, allowed_domains, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (user_id, username, email, password_hash, role, domains_json, now),
            )
            self._conn.commit()

        return User(
            id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            allowed_domains=allowed_domains or [],
            is_active=True,
            created_at=now,
        )

    def get_user_by_username(self, username: str) -> Optional[User]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def user_exists(self, username: str = "", email: str = "") -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM users WHERE username = ? OR email = ?", (username, email)
            ).fetchone()
        return row is not None

    def count_users(self) -> int:
        """Return total number of registered users."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return row[0] if row else 0

    def _row_to_user(self, row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=row["role"],
            allowed_domains=json.loads(row["allowed_domains"] or "[]"),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def log_audit(
        self,
        action: str,
        resource: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        domain: Optional[str] = None,
        status_code: Optional[int] = None,
        client_ip: Optional[str] = None,
    ) -> None:
        entry_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO audit_log
                        (id, user_id, username, action, resource, domain, status_code, client_ip, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (entry_id, user_id, username, action, resource, domain, status_code, client_ip, now),
                )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"audit_log write failed: {e}")

    def list_audit(self, limit: int = 100) -> List[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"audit_log list failed: {e}")
            return []


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_auth_store: Optional[AuthStore] = None


def get_auth_store() -> AuthStore:
    """Return the process-wide AuthStore singleton."""
    global _auth_store
    if _auth_store is None:
        try:
            from app.config import settings
            db_path = settings.database_url.replace("sqlite:///", "")
        except Exception:
            db_path = "meridian.db"
        _auth_store = AuthStore(db_path)
    return _auth_store

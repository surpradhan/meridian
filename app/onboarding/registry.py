"""
Dynamic Domain Registry

Persists dynamically-registered domains to SQLite and exposes them
so the Orchestrator can load them alongside the built-in domains.
"""

import json
import logging
import sqlite3
import threading
from typing import Dict, List, Optional

from app.onboarding.models import DomainConfig

logger = logging.getLogger(__name__)

_BUILTIN_DOMAINS = {"sales", "finance", "operations"}


class DomainRegistry:
    """
    Thread-safe registry for dynamically-registered domains.

    Domains are persisted to the ``dynamic_domains`` table in the existing
    SQLite database so they survive process restarts.
    """

    def __init__(self, db_path: str = "meridian.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._cache: Dict[str, DomainConfig] = {}
        self._init_table()
        self._load_from_db()

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_table(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dynamic_domains (
                    name        TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    keywords    TEXT NOT NULL DEFAULT '[]',
                    view_names  TEXT NOT NULL DEFAULT '[]',
                    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()

    def _load_from_db(self) -> None:
        try:
            with self._conn() as conn:
                rows = conn.execute("SELECT * FROM dynamic_domains").fetchall()
            with self._lock:
                for row in rows:
                    config = DomainConfig(
                        name=row["name"],
                        description=row["description"],
                        keywords=json.loads(row["keywords"]),
                        view_names=json.loads(row["view_names"]),
                    )
                    self._cache[config.name] = config
        except Exception as e:
            logger.error(f"Failed to load dynamic domains: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, config: DomainConfig) -> DomainConfig:
        """Register a new dynamic domain.

        Raises:
            ValueError: if the name conflicts with a built-in domain
        """
        if config.name in _BUILTIN_DOMAINS:
            raise ValueError(
                f"Domain {config.name!r} conflicts with a built-in domain. "
                f"Choose a different name."
            )

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dynamic_domains (name, description, keywords, view_names)
                VALUES (?, ?, ?, ?)
                """,
                (
                    config.name,
                    config.description,
                    json.dumps(config.keywords),
                    json.dumps(config.view_names),
                ),
            )
            conn.commit()

        with self._lock:
            self._cache[config.name] = config

        logger.info(f"Registered dynamic domain: {config.name!r}")
        return config

    def list_domains(self) -> List[DomainConfig]:
        """Return all registered dynamic domains."""
        with self._lock:
            return list(self._cache.values())

    def get_domain(self, name: str) -> Optional[DomainConfig]:
        """Look up a dynamic domain by name."""
        with self._lock:
            return self._cache.get(name)

    def delete_domain(self, name: str) -> bool:
        """Remove a dynamic domain. Returns True if it existed."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM dynamic_domains WHERE name = ?", (name,))
            conn.commit()
            deleted = cursor.rowcount > 0

        with self._lock:
            self._cache.pop(name, None)

        if deleted:
            logger.info(f"Deleted dynamic domain: {name!r}")
        return deleted


# Module-level singleton
_registry: Optional[DomainRegistry] = None
_registry_lock = threading.Lock()


def get_domain_registry(db_path: str = "meridian.db") -> DomainRegistry:
    """Return the module-level DomainRegistry singleton."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = DomainRegistry(db_path=db_path)
    return _registry

"""Lead storage: SQLite table, mirrored to a JSON file."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.models import Lead

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    service TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
)
"""


class LeadStore:
    def __init__(self, db_path: Path, json_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path)
        self.json_path = Path(json_path) if json_path else None
        self._initialised = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        if not self._initialised:
            conn.execute(_SCHEMA)
            conn.commit()
            self._initialised = True
        return conn

    def save(self, lead: Lead) -> Lead:
        lead.created_at = lead.created_at or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO leads (session_id, name, email, service, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (lead.session_id, lead.name, lead.email, lead.service, lead.notes, lead.created_at),
            )
            lead.id = cur.lastrowid
        if self.json_path:
            self._mirror(lead)
        return lead

    def _mirror(self, lead: Lead) -> None:
        rows = []
        if self.json_path.exists():
            try:
                rows = json.loads(self.json_path.read_text(encoding="utf-8"))
            except Exception:
                rows = []
        rows.append(lead.to_dict())
        self.json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def all(self) -> List[Lead]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
        return [Lead(**dict(r)) for r in rows]

    def exists_for_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM leads WHERE session_id = ? LIMIT 1", (session_id,)).fetchone() is not None

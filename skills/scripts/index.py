"""Index manager — manages .doc-kit/index.json metadata cache.

Minimal version extracted from app/engine, used by the skills CLI.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json


@dataclass
class IndexEntry:
    """A single document entry in the index."""
    path: str
    doc_type: str
    module: str
    level: str
    version: str
    status: str = "active"
    depends_on: list[dict] = field(default_factory=list)
    mtime: str = ""

    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []


class IndexManager:
    """Manages .doc-kit/index.json with read and query capabilities."""

    def __init__(self, index_path: Path):
        self.index_path = index_path
        self._entries: dict[str, IndexEntry] = {}
        if index_path.exists():
            self._load()

    def _load(self):
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            for entry_data in data.get("documents", []):
                entry = IndexEntry(**entry_data)
                self._entries[entry.path] = entry
        except (json.JSONDecodeError, KeyError):
            self._entries = {}

    def get_entry(self, path: str) -> Optional[IndexEntry]:
        """Get entry by document path."""
        return self._entries.get(path)

    def add_entry(self, entry: IndexEntry):
        """Add or update a document entry."""
        self._entries[entry.path] = entry

    def remove_entry(self, path: str):
        """Remove a document entry by path."""
        self._entries.pop(path, None)

    def save(self):
        """Write index to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "documents": [asdict(e) for e in self._entries.values()],
        }
        self.index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_entries(self) -> list[IndexEntry]:
        """List all entries."""
        return list(self._entries.values())

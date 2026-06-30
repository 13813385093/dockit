"""Index manager — manages .doc-kit/index.json metadata cache.

Minimal version extracted from app/engine, only includes what mcp_server uses.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
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

    def list_entries(self) -> list[IndexEntry]:
        """List all entries."""
        return list(self._entries.values())

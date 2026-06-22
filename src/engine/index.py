"""Index manager - manages .doc-kit/index.json metadata cache."""
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


class IndexManager:
    """Manages .doc-kit/index.json with read, write, and rebuild capabilities."""

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

    def add_entry(self, entry: IndexEntry):
        """Add or update a document entry."""
        self._entries[entry.path] = entry

    def get_entry(self, path: str) -> Optional[IndexEntry]:
        """Get entry by document path."""
        return self._entries.get(path)

    def update_version(self, path: str, new_version: str):
        """Update the version of a specific document."""
        if path in self._entries:
            self._entries[path].version = new_version

    def remove_entry(self, path: str):
        """Remove a document entry by path."""
        self._entries.pop(path, None)

    def list_entries(self) -> list[IndexEntry]:
        """List all entries."""
        return list(self._entries.values())

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

    def rebuild(self, docs_root: Path) -> int:
        """Full scan of ProjectSpec/ to rebuild index from scratch.

        Returns the number of documents found.
        """
        self._entries = {}
        if not docs_root.exists():
            return 0

        from src.engine.frontmatter import FrontmatterParser

        count = 0
        for md_file in sorted(docs_root.rglob("*.md")):
            try:
                meta, _ = FrontmatterParser.read_file(md_file)
                rel_path = str(md_file.relative_to(docs_root.parent)).replace("\\", "/")
                entry = IndexEntry(
                    path=rel_path,
                    doc_type=meta.get("doc_type", "unknown"),
                    module=meta.get("module", ""),
                    level=meta.get("level", ""),
                    version=str(meta.get("version", "0.0.0")),
                    status=meta.get("status", "active"),
                    depends_on=meta.get("depends_on", []),
                    mtime=FrontmatterParser.now_iso(),
                )
                self._entries[rel_path] = entry
                count += 1
            except Exception:
                continue

        return count

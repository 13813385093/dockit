"""Index manager — manages .doc-kit/index.json metadata cache.

Minimal version extracted from app/engine, used by the skills CLI.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict, fields
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

    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []


#: 当前 schema 认识的条目字段。加载时据此丢弃旧版本遗留的键
#: （如已删除的 ``mtime``），避免 ``IndexEntry(**entry_data)`` 因未知键抛
#: TypeError 而炸掉整个 _load。
_ENTRY_FIELDS = {f.name for f in fields(IndexEntry)}


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
                entry = IndexEntry(**{k: v for k, v in entry_data.items() if k in _ENTRY_FIELDS})
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
        """Write index to disk.

        只写与内容有关的信息（version + documents）。刻意不写 ``built_at`` /
        ``mtime`` 这类"生成时刻"字段：它们会让**内容没变**的一次刷新（如桌面
        App 每次加载都 rebuild+save）也产生 diff，污染 git 提交。
        """
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "documents": [asdict(e) for e in self._entries.values()],
        }
        self.index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_entries(self) -> list[IndexEntry]:
        """List all entries."""
        return list(self._entries.values())

    def rebuild(self, docs_root: Path) -> int:
        """Full scan of ProjectSpec/ to rebuild index from scratch.

        Returns the number of documents found.

        与 App 侧 ``src/app/engine/index.py::IndexManager.rebuild`` 行为一致。
        纯 AI 流程（不启动桌面 App）没有别的角色会维护 index.json，故由 CLI
        的 doc reindex 命令承担同一职责：逐篇读取 frontmatter，把
        doc_type / module / level / version / status / depends_on 汇总进索引。
        单篇解析失败只跳过该篇，不中断整体重建。
        """
        self._entries = {}
        if not docs_root.exists():
            return 0

        from frontmatter import FrontmatterParser

        count = 0
        for md_file in sorted(docs_root.rglob("*.md")):
            try:
                meta, _ = FrontmatterParser.parse(md_file.read_text(encoding="utf-8"))
                rel_path = str(md_file.relative_to(docs_root.parent)).replace("\\", "/")
                entry = IndexEntry(
                    path=rel_path,
                    doc_type=meta.get("doc_type", "unknown"),
                    module=meta.get("module", ""),
                    level=meta.get("level", ""),
                    version=str(meta.get("version", "0.0.0")),
                    status=meta.get("status", "active"),
                    depends_on=meta.get("depends_on", []),
                )
                self._entries[rel_path] = entry
                count += 1
            except Exception:
                continue

        return count

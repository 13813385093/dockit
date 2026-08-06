"""doc-kit 软件元数据管理 — 统一存放于可执行文件同级的 .meta/ 目录。

打包态: <exe 所在目录>/.meta/
开发态: <仓库根>/.meta/

替代注册表（QSettings）保存最近项目等应用级数据。数据为 JSON 文件，
按主题分文件（如 projects.json），便于查看与备份。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def get_meta_dir() -> Path:
    """返回本软件元数据目录（与可执行文件同级 .meta/）。

    打包态：exe 所在目录 / .meta；
    开发态：仓库根 / .meta（模拟 exe 与仓库同级的语义）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / ".meta"
    return Path(__file__).resolve().parent.parent.parent / ".meta"


class AppMeta:
    """读写 .meta/ 下的元数据文件（JSON，按主题分文件）。"""

    def __init__(self, meta_dir: Path | None = None) -> None:
        self.meta_dir = meta_dir or get_meta_dir()
        self._cache: dict[str, dict] = {}

    def _path(self, name: str) -> Path:
        return self.meta_dir / f"{name}.json"

    def _load(self, name: str) -> dict:
        if name in self._cache:
            return self._cache[name]
        path = self._path(name)
        data: dict = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (json.JSONDecodeError, OSError):
                data = {}
        self._cache[name] = data
        return data

    def _save(self, name: str, data: dict) -> None:
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(name)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._cache[name] = data

    def get(self, name: str, key: str, default: Any = None) -> Any:
        """读取 <name>.json 中的 key，不存在时返回 default。"""
        return self._load(name).get(key, default)

    def set(self, name: str, key: str, value: Any) -> None:
        """写入 <name>.json 中的 key，立即落盘。"""
        data = self._load(name)
        data[key] = value
        self._save(name, data)

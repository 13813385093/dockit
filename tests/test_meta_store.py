"""AppMeta 元数据存储测试 — exe 同级 .meta/（JSON），替代注册表。"""
import json
from pathlib import Path

from src.app.meta_store import AppMeta, get_meta_dir


class TestAppMeta:
    """AppMeta 读写 .meta/<name>.json"""

    def test_get_set_roundtrip(self, tmp_path):
        """写入后重新实例化（模拟重启）数据仍在"""
        meta = AppMeta(meta_dir=tmp_path)
        meta.set("projects", "recent_projects", ["D:/a", "D:/b"])
        meta.set("projects", "last_project", "D:/a")
        meta2 = AppMeta(meta_dir=tmp_path)
        assert meta2.get("projects", "recent_projects") == ["D:/a", "D:/b"]
        assert meta2.get("projects", "last_project") == "D:/a"
        # 落盘文件为 JSON
        data = json.loads((tmp_path / "projects.json").read_text(encoding="utf-8"))
        assert data["last_project"] == "D:/a"

    def test_default_when_missing(self, tmp_path):
        """键不存在返回默认值"""
        meta = AppMeta(meta_dir=tmp_path)
        assert meta.get("projects", "recent_projects", []) == []
        assert meta.get("projects", "last_project") is None

    def test_corrupted_json_recovers(self, tmp_path):
        """损坏的 JSON 回退为空，且可继续写入"""
        (tmp_path / "projects.json").write_text("{broken", encoding="utf-8")
        meta = AppMeta(meta_dir=tmp_path)
        assert meta.get("projects", "recent_projects", []) == []
        meta.set("projects", "ok", True)
        assert meta.get("projects", "ok") is True

    def test_meta_dir_development(self):
        """开发态：仓库根/.meta（与可执行文件同级语义）"""
        d = get_meta_dir()
        assert d.name == ".meta"
        repo_root = Path(__file__).resolve().parents[1]
        assert d.parent == repo_root

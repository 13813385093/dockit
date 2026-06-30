"""pytest conftest — 将 src/ 加入 sys.path 以便测试代码导入。"""
import json
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import pytest


# ── 文件系统辅助函数 ──

def make_md(project: Path, rel_path: str, content: str) -> Path:
    """在项目中创建 .md 文件，自动创建父目录。"""
    fp = project / rel_path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return fp


def make_index(project: Path, documents: list[dict]) -> Path:
    """创建 index.json。"""
    index_path = project / ".doc-kit" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "built_at": "2026-01-01T00:00:00+00:00",
        "documents": documents,
    }
    index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return index_path


def make_spec(project: Path, sid: str, data: dict | None = None) -> Path:
    """在 SessionSpec/active/ 下创建 spec 文件。"""
    spec_path = project / "SessionSpec" / "active" / f"{sid}.spec.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    default = {
        "session_spec_id": sid,
        "project": "test",
        "scenario": "tech-ref",
        "related_doc_types": ["architecture"],
        "created_at": "2026-01-01T00:00:00+00:00",
        "resolutions": [],
        "pending_decisions": [],
        "next_steps": [],
        "status": "active",
        "closed_at": None,
        "closed_reason": None,
    }
    if data:
        default.update(data)
    spec_path.write_text(json.dumps(default, indent=2, ensure_ascii=False), encoding="utf-8")
    return spec_path


# ── pytest fixtures ──

@pytest.fixture
def tmp_project(tmp_path) -> Path:
    """创建一个包含 ProjectSpec/、.doc-kit/、SessionSpec/ 的临时项目目录。"""
    proj = tmp_path / "test-project"
    for sub in ["ProjectSpec", ".doc-kit", "SessionSpec/active", "SessionSpec/archive"]:
        (proj / sub).mkdir(parents=True, exist_ok=True)
    return proj


@pytest.fixture
def mcp_env(tmp_project):
    """初始化 MCP 全局状态指向临时项目，测试后恢复。"""
    import src.skill.mcp.mcp_server as mcp
    old_root = mcp._project_root
    old_session = mcp._current_session_id
    mcp._project_root = tmp_project
    mcp._current_session_id = None
    yield mcp
    mcp._project_root = old_root
    mcp._current_session_id = old_session

"""pytest conftest — skills CLI 测试基础设施。

将 skills/scripts/ 加入 sys.path，使测试可以直接 import spec_schema / docmodel / cli。
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO / "skills" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


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


def valid_spec(**overrides) -> dict:
    """构造一份合法的完整 spec dict。"""
    spec = {
        "session_spec_id": "test-001",
        "project": "test-project",
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
    spec.update(overrides)
    return spec


# ── pytest fixtures ──

@pytest.fixture
def tmp_project(tmp_path) -> Path:
    """创建一个包含 ProjectSpec/、.doc-kit/、SessionSpec/ 的临时项目目录。"""
    proj = tmp_path / "test-project"
    for sub in ["ProjectSpec", ".doc-kit", "SessionSpec/active", "SessionSpec/archive"]:
        (proj / sub).mkdir(parents=True, exist_ok=True)
    return proj


@pytest.fixture
def active_spec(tmp_project) -> Path:
    """在临时项目中创建一个活跃议题，返回 spec 文件路径。"""
    return make_spec(tmp_project, "test-001")


@pytest.fixture
def cli_env(tmp_project):
    """CLI 命令门面：将 cli.py 的 cmd_* 函数绑定到临时项目。

    方法名与原 MCP 工具一致（spec_write / spec_read / spec_archive /
    read_doc / update_section / add_section / doc_structure），
    使集成测试的调用方式不变。
    """
    from types import SimpleNamespace

    import cli  # noqa: F401

    root = tmp_project
    return SimpleNamespace(
        _root=root,
        spec_write=lambda spec_json: cli.cmd_spec_write(root, spec_json),
        spec_read=lambda: cli.cmd_spec_read(root),
        spec_archive=lambda: cli.cmd_spec_archive(root),
        read_doc=lambda path: cli.cmd_doc_read(root, path),
        update_section=lambda ref, content: cli.cmd_doc_update_section(root, ref, content),
        add_section=lambda ref, heading, content="", level="sibling": cli.cmd_doc_add_section(
            root, ref, heading, content, level),
        doc_structure=lambda: cli.cmd_doc_structure(root),
        # ── dev（spec-dev-loop）──
        dev_status=lambda: cli.cmd_dev_status(root),
        dev_plan_create=lambda scope, target, module=None, title=None, session=None: cli.cmd_dev_plan_create(
            root, scope, target, module, title, session),
        dev_plan_read=lambda: cli.cmd_dev_plan_read(root),
        dev_plan_update_section=lambda ref, content: cli.cmd_dev_plan_update_section(root, ref, content),
        dev_plan_add_section=lambda ref, heading, content="", level="sibling": cli.cmd_dev_plan_add_section(
            root, ref, heading, content, level),
        dev_task_list=lambda: cli.cmd_dev_task_list(root),
        dev_task_set=lambda tasks_json: cli.cmd_dev_task_set(root, tasks_json),
        dev_task_update=lambda tid, status, note="": cli.cmd_dev_task_update(root, tid, status, note),
        dev_task_annotate=lambda tid, note: cli.cmd_dev_task_annotate(root, tid, note),
        dev_align=lambda feature, module, status, note="": cli.cmd_dev_align(root, feature, module, status, note),
        dev_integrate=lambda module, status, note="": cli.cmd_dev_integrate(root, module, status, note),
        dev_notes_append=lambda content, section=None: cli.cmd_dev_notes_append(root, content, section),
        dev_report_write=lambda kind, name, content: cli.cmd_dev_report_write(root, kind, name, content),
        dev_close=lambda reason: cli.cmd_dev_close(root, reason),
        dev_abort=lambda reason: cli.cmd_dev_abort(root, reason),
        dev_archive=lambda: cli.cmd_dev_archive(root),
    )

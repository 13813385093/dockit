"""工具链版本与副本一致性测试（B10 方案 1）+ 旧版会话迁移测试（B10 方案 2）。

问题背景：`init` 把工具链**快照复制**进项目，此后仓库与项目各自演化。
「新技能 + 旧 CLI」时旧 CLI 会**静默丢弃**未知字段（命令仍报成功），
「CLI 升级 + 在途会话」会让旧状态无法迁移而卡死。本文件固定两条防线：

  1. 版本与副本一致性：`tool status` 能分辨 一致 / 版本落后 / 无清单 / 副本被改动或缺失；
  2. 旧状态映射：`in-progress/unit-green/fixing` 读取时映射为
     `implementing/tested/rejected`，一次写操作即落盘迁移，会话不再卡死。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "skills" / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "skills" / "scripts"))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import cli  # noqa: E402
from src.app.engine.commands.init_utils import init_project  # noqa: E402


def parse(result: str) -> dict:
    return json.loads(result)


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    init_project(root, project_name="toolchain-probe")
    return root


class TestVersionConstant:
    def test_version_format(self):
        assert re.match(r"^\d{4}\.\d{2}\.\d+$", cli.TOOLCHAIN_VERSION)

    def test_skills_declare_same_version(self):
        """9 份技能注入的版本必须来自 cli.py 的常量（单一事实源）。"""
        for md in sorted((REPO / "skills").glob("spec-*/SKILL.md")):
            text = md.read_text(encoding="utf-8")
            assert f"`{cli.TOOLCHAIN_VERSION}`" in text, md

    def test_generator_reads_constant(self):
        sys.path.insert(0, str(REPO / "tests"))
        import render_skill_preamble as R  # noqa: E402

        assert R.toolchain_version() == cli.TOOLCHAIN_VERSION


class TestVersionBumpGuard:
    """内容变 ⇒ 版本必须变（`tests/check_toolchain_version.py`）。

    否则 `tool status` 的"版本一致 + 副本哈希一致"会因为版本号没变而漏报
    「项目副本是旧版」——这正是引入版本号要防的静默错配。
    """

    def test_fingerprint_matches(self):
        sys.path.insert(0, str(REPO / "tests"))
        import check_toolchain_version as C  # noqa: E402

        problems = C.check()
        assert not problems, "工具链指纹不一致：" + "; ".join(problems)

    def test_fingerprint_covers_toolchain_sources(self):
        sys.path.insert(0, str(REPO / "tests"))
        import check_toolchain_version as C  # noqa: E402

        rels = {p.relative_to(REPO).as_posix() for p in C.toolchain_files()}
        # 会被复制进项目的四类文件都必须在指纹里
        assert "skills/scripts/cli.py" in rels
        assert "skills/_shared/preamble-dev.md" in rels
        assert "skills/guidance/doc-capabilities/_index.md" in rels
        assert "skills/spec-dev-loop/SKILL.md" in rels
        assert any(r.startswith("src/app/templates/") for r in rels)
        # 应用侧代码与仓库内文档/测试产物不进指纹
        assert not any(r.startswith("src/app/engine/") for r in rels)
        assert not any("__pycache__" in r for r in rels)
        assert not any(r.startswith("tests/") for r in rels)
        assert all(r.endswith((".py", ".md")) for r in rels)

    def test_content_change_is_detected_and_blocks_update_without_bump(self, monkeypatch):
        """反向验证：内容变了但版本没变 → 校验失败，且 --update 拒绝写入。"""
        sys.path.insert(0, str(REPO / "tests"))
        import check_toolchain_version as C  # noqa: E402

        monkeypatch.setattr(C, "fingerprint", lambda: ("0" * 64, 50))   # 模拟内容已变
        problems = C.check()
        assert problems and "TOOLCHAIN_VERSION" in problems[0]
        assert C.update() == 1, "版本未递增时 --update 必须拒绝"

    def test_update_accepts_when_version_bumped(self, monkeypatch, tmp_path):
        """正常工作流：内容变了 + 版本递增 → --update 写入新指纹。"""
        sys.path.insert(0, str(REPO / "tests"))
        import check_toolchain_version as C  # noqa: E402

        monkeypatch.setattr(C, "FINGERPRINT_FILE", tmp_path / "fp.json")
        C.FINGERPRINT_FILE.write_text(json.dumps(
            {"fingerprint": "old", "toolchain_version": "2000.01.1"}), encoding="utf-8")
        monkeypatch.setattr(C, "fingerprint", lambda: ("f" * 64, 50))
        monkeypatch.setattr(C, "toolchain_version", lambda: "2026.09.2")
        assert C.update() == 0
        data = json.loads(C.FINGERPRINT_FILE.read_text(encoding="utf-8"))
        assert data["fingerprint"] == "f" * 64
        assert data["toolchain_version"] == "2026.09.2"


class TestVersionHistory:
    """版本历史：让"该同步"有理由、有内容（`tool status` 据此算落后几版）。"""

    def history(self) -> list[dict]:
        sys.path.insert(0, str(REPO / "tests"))
        import check_toolchain_version as C  # noqa: E402

        return C.toolchain_history()

    def test_last_entry_is_current_version(self):
        history = self.history()
        assert history, "版本历史不能为空"
        assert history[-1]["version"] == cli.TOOLCHAIN_VERSION

    def test_entries_are_well_formed(self):
        for h in self.history():
            assert re.match(r"^\d{4}\.\d{2}\.\d+$", h["version"]), h
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", h["date"]), h
            assert h["note"].strip(), f"{h['version']} 缺变更说明"

    def test_versions_are_unique_and_monotonic(self):
        keys = [cli._version_key(h["version"]) for h in self.history()]
        assert keys == sorted(keys), "版本历史必须按旧→新排列"
        assert len(set(keys)) == len(keys), "版本号不得重复"

    def test_pending_changes_for_older_project(self, monkeypatch):
        history = self.history()
        older = history[0]["version"]
        behind, pending, known = cli.pending_toolchain_changes(older)
        assert known is True
        assert behind == len(history) - 1
        assert [p["version"] for p in pending] == [h["version"] for h in history[1:]]

    def test_pending_changes_for_current_project(self):
        behind, pending, known = cli.pending_toolchain_changes(cli.TOOLCHAIN_VERSION)
        assert (behind, pending, known) == (0, [], True)

    def test_unknown_version_is_flagged(self):
        behind, pending, known = cli.pending_toolchain_changes("1999.01.1")
        assert behind == -1 and known is False and pending

    def test_new_version_requires_note(self, monkeypatch, tmp_path):
        """新增版本必须带变更说明——否则用户同步时看不到"改了什么"。"""
        sys.path.insert(0, str(REPO / "tests"))
        import check_toolchain_version as C  # noqa: E402

        monkeypatch.setattr(C, "FINGERPRINT_FILE", tmp_path / "fp.json")
        C.FINGERPRINT_FILE.write_text(json.dumps(
            {"fingerprint": "same", "toolchain_version": "2000.01.1"}), encoding="utf-8")
        monkeypatch.setattr(C, "fingerprint", lambda: ("same", 50))
        monkeypatch.setattr(C, "toolchain_version", lambda: "2099.01.1")
        monkeypatch.setattr(C, "toolchain_history", lambda: [{"version": "2000.01.1", "date": "2000-01-01", "note": "x"}])
        written: list = []
        monkeypatch.setattr(C, "write_history", lambda h: written.append(h))

        assert C.update() == 1, "缺 --note 时必须拒绝"
        assert not written, "拒绝时不得写历史"
        assert C.update(note="一句说明") == 0
        assert written and written[0][-1]["note"] == "一句说明"


class TestManifest:
    def test_init_writes_manifest(self, project):
        manifest_path = project / ".doc-kit" / "toolchain.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["toolchain_version"] == cli.TOOLCHAIN_VERSION
        assert manifest["generated_at"]
        files = manifest["files"]
        assert files, "清单必须记录副本哈希"
        # CLI、技能、能力库、模板都在清单里
        assert ".doc-kit/cli/cli.py" in files
        assert ".doc-kit/skills/spec-dev-loop/SKILL.md" in files
        assert ".doc-kit/skills/guidance/doc-capabilities/_index.md" in files
        assert any(k.startswith(".doc-kit/templates/") for k in files)
        # 清单自身与 __pycache__ 不入清单
        assert ".doc-kit/toolchain.json" not in files
        assert not any("__pycache__" in k for k in files)


class TestToolStatus:
    def test_consistent_after_init(self, project):
        data = parse(cli.cmd_tool_status(project))["data"]
        assert data["consistent"] is True
        assert data["stale"] is False
        assert data["recorded_version"] == cli.TOOLCHAIN_VERSION
        assert data["checked"] > 0
        assert data["mismatched"] == [] and data["missing"] == []

    def test_missing_manifest_is_reported(self, tmp_path):
        """旧版 init 生成的项目（没有清单）必须被识别并给出同步指引。"""
        root = tmp_path / "legacy"
        (root / ".doc-kit" / "cli").mkdir(parents=True)
        out = parse(cli.cmd_tool_status(root))
        assert out["success"] is True
        assert out["data"]["reason"] == "no_manifest"
        assert out["data"]["consistent"] is False
        assert any("doc-kit init" in s for s in out["suggestions"])

    def test_tampered_copy_is_detected(self, project):
        target = project / ".doc-kit" / "skills" / "spec-load" / "SKILL.md"
        target.write_text(target.read_text(encoding="utf-8") + "\n# 本地改动\n", encoding="utf-8")
        out = parse(cli.cmd_tool_status(project))
        assert out["data"]["consistent"] is False
        assert ".doc-kit/skills/spec-load/SKILL.md" in out["data"]["mismatched"]
        assert any("被本地改动" in s for s in out["suggestions"])

    def test_missing_copy_is_detected(self, project):
        (project / ".doc-kit" / "cli" / "index.py").unlink()
        out = parse(cli.cmd_tool_status(project))
        assert out["data"]["consistent"] is False
        assert ".doc-kit/cli/index.py" in out["data"]["missing"]
        assert any("缺失" in s for s in out["suggestions"])

    def test_stale_version_is_detected_but_copies_consistent(self, project):
        """版本落后（技能/CLI 不同版）与副本被改动是两回事，要能分开报告。"""
        manifest_path = project / ".doc-kit" / "toolchain.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["toolchain_version"] = "1999.01.1"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        out = parse(cli.cmd_tool_status(project))
        assert out["data"]["stale"] is True
        assert out["data"]["mismatched"] == []          # 副本没被改
        assert any("不一致" in s and "静默丢弃" in s for s in out["suggestions"])

    def test_reinit_refreshes_copies(self, project):
        """重跑 init 是修复通道：刷新副本并保留用户内容。"""
        docs = project / "ProjectSpec" / "business-context.md"
        before = docs.read_bytes()
        target = project / ".doc-kit" / "cli" / "cli.py"
        target.write_text("# 被改坏的副本\n", encoding="utf-8")
        assert parse(cli.cmd_tool_status(project))["data"]["consistent"] is False

        init_project(project, project_name="toolchain-probe")
        assert parse(cli.cmd_tool_status(project))["data"]["consistent"] is True
        assert docs.read_bytes() == before, "init 不得改动 ProjectSpec 内容"


class TestLegacySessionMigration:
    """旧 CLI 写到一半的会话，在升级后必须能继续（否则在途循环死锁）。"""

    def _make_session(self, project, status: str) -> Path:
        project.joinpath("ProjectSpec/module-order/architecture.md").parent.mkdir(parents=True, exist_ok=True)
        project.joinpath("ProjectSpec/module-order/architecture.md").write_text(
            "---\ndoc_type: architecture\nmodule: order\nlevel: module\nversion: 0.1.0\nstatus: active\n---\n# 架构\n",
            encoding="utf-8")
        project.joinpath("ProjectSpec/module-order/features/f1/feature-design.md").parent.mkdir(parents=True, exist_ok=True)
        project.joinpath("ProjectSpec/module-order/features/f1/feature-design.md").write_text(
            "---\ndoc_type: feature_design\nmodule: order\nfeature: f1\nlevel: feature\nversion: 0.1.0\nstatus: active\n---\n# 功能设计\n",
            encoding="utf-8")
        assert parse(cli.cmd_dev_plan_create(project, "feature", "f1", "order"))["success"] is True
        session_dir = next(p for p in (project / "DevSpec" / "active").iterdir() if p.is_dir())
        (session_dir / "tasks.json").write_text(json.dumps({
            "version": 1,
            "tasks": [{"task_id": "T1", "title": "旧会话任务", "status": status,
                       "functions": [], "gwt_refs": [], "constraint_ids": []}],
        }, ensure_ascii=False), encoding="utf-8")
        return session_dir

    @pytest.mark.parametrize("legacy,expected", [
        ("in-progress", "implementing"),
        ("unit-green", "tested"),
        ("fixing", "rejected"),
    ])
    def test_legacy_status_is_mapped_on_read(self, project, legacy, expected):
        session_dir = self._make_session(project, legacy)
        tasks = cli._load_dev_tasks(session_dir)
        assert tasks[0]["status"] == expected

    def test_status_warns_and_suggests(self, project):
        self._make_session(project, "in-progress")
        out = parse(cli.cmd_dev_status(project))
        assert out["data"]["legacy_status_migrated"] == 1
        assert any("旧版状态" in s for s in out["suggestions"])
        # 旧会话缺 implemented_in，必须提示补齐（否则子代理无法派发）
        assert any("implemented_in" in s for s in out["suggestions"])

    def test_session_can_continue_after_upgrade(self, project):
        """复现原故障：旧状态 in-progress 在新 CLI 下曾无法推进。"""
        self._make_session(project, "in-progress")
        # 迁移前：in-progress → submitted 非法；迁移后：implementing → submitted 合法
        result = parse(cli.cmd_dev_task_update(project, "T1", "submitted"))
        assert result["success"] is True, result

    def test_migration_is_persisted_by_any_write(self, project):
        session_dir = self._make_session(project, "in-progress")
        assert parse(cli.cmd_dev_task_update(project, "T1", "submitted"))["success"] is True
        raw = json.loads((session_dir / "tasks.json").read_text(encoding="utf-8"))
        assert raw["tasks"][0]["status"] == "submitted"
        # 再次读取不再触发迁移提示
        assert cli._normalize_legacy_task_statuses(raw["tasks"]) == 0

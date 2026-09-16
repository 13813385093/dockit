"""review 评审锚点测试 —— 按分支记录，多分支并行评审互不覆盖。

背景（M3-P1-2）：原实现把锚点存成项目级单例（只有 last_reviewed_commit），
同时评审 main 与 feature 分支时后者会覆盖前者，下次比对范围错乱。
现在 state 增加 branches 映射，并保留旧字段兼容老 state 文件。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "skills" / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "skills" / "scripts"))

import cli  # noqa: E402


def _parse(result: str) -> dict:
    return json.loads(result)


def _git(root: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


@pytest.fixture
def git_project(tmp_path) -> Path:
    root = tmp_path / "proj"
    (root / ".doc-kit").mkdir(parents=True)
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / ".gitignore").write_text(".doc-kit/\n", encoding="utf-8")  # 工具状态不进版本控制
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


class TestCurrentBranch:
    def test_reads_head(self, git_project):
        assert cli._current_git_branch(git_project) in ("master", "main")

    def test_returns_empty_without_git(self, tmp_path):
        (tmp_path / ".doc-kit").mkdir()
        assert cli._current_git_branch(tmp_path) == ""

    def test_detached_head_returns_empty(self, git_project):
        _git(git_project, "checkout", "-q", "--detach", "HEAD")
        assert cli._current_git_branch(git_project) == ""


class TestPerBranchAnchors:
    def test_anchor_is_recorded_per_branch_and_isolated(self, git_project):
        base = _git(git_project, "rev-parse", "HEAD")
        branch_a = cli._current_git_branch(git_project)
        assert _parse(cli.cmd_review_anchor_set(git_project, base))["success"] is True

        _git(git_project, "checkout", "-q", "-b", "feature-x")
        (git_project / "b.txt").write_text("b\n", encoding="utf-8")
        _git(git_project, "add", "-A")
        _git(git_project, "commit", "-q", "-m", "feat-x")
        head_x = _git(git_project, "rev-parse", "HEAD")

        # feature-x 尚无专属锚点 → 回退到全局锚点并明确提示
        got = _parse(cli.cmd_review_anchor_get(git_project))
        assert got["data"]["branch"] == "feature-x"
        assert got["data"]["source"] == "global"
        assert got["data"]["last_reviewed_commit"] == base
        assert any("可能来自其它分支" in s for s in got["suggestions"])

        # feature-x 记录自己的锚点
        assert _parse(cli.cmd_review_anchor_set(git_project, head_x))["success"] is True
        got = _parse(cli.cmd_review_anchor_get(git_project))
        assert got["data"]["source"] == "branch"
        assert got["data"]["last_reviewed_commit"] == head_x

        # 切回 A：仍是 A 的锚点（未被 feature-x 覆盖）
        _git(git_project, "checkout", "-q", branch_a)
        got = _parse(cli.cmd_review_anchor_get(git_project))
        assert got["data"]["source"] == "branch"
        assert got["data"]["last_reviewed_commit"] == base
        assert set(got["data"]["branches"]) == {branch_a, "feature-x"}

    def test_explicit_branch_parameter(self, git_project):
        head = _git(git_project, "rev-parse", "HEAD")
        assert _parse(cli.cmd_review_anchor_set(git_project, head, "", "other-branch"))["success"] is True
        got = _parse(cli.cmd_review_anchor_get(git_project, "other-branch"))
        assert got["data"]["branch"] == "other-branch"
        assert got["data"]["last_reviewed_commit"] == head

    def test_no_anchor_at_all(self, git_project):
        got = _parse(cli.cmd_review_anchor_get(git_project))
        assert got["data"]["source"] == "none"
        assert got["data"]["last_reviewed_commit"] is None

    def test_legacy_state_without_branches_still_works(self, git_project):
        """兼容旧 state（只有 last_reviewed_commit 三个字段）。"""
        state_path = git_project / ".doc-kit" / "code-review-state.json"
        state_path.write_text(json.dumps({
            "last_reviewed_commit": "deadbeef",
            "last_reviewed_at": "2026-01-01T00:00:00+00:00",
            "review_history": [{"commit": "deadbeef", "time": "2026-01-01T00:00:00+00:00"}],
        }), encoding="utf-8")
        got = _parse(cli.cmd_review_anchor_get(git_project))
        assert got["data"]["last_reviewed_commit"] == "deadbeef"
        assert got["data"]["source"] == "global"
        # 写入后升级为按分支结构，旧字段仍保留
        assert _parse(cli.cmd_review_anchor_set(git_project, "cafe1234"))["success"] is True
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["last_reviewed_commit"] == "cafe1234"
        assert cli._current_git_branch(git_project) in state["branches"]

    def test_anchor_set_rejects_empty(self, git_project):
        assert _parse(cli.cmd_review_anchor_set(git_project, "  "))["success"] is False

"""模块三技能契约测试（spec-smart-git / spec-code-review）。

锁定《07-模块三评审》中经用户确认的修正：

  M3-P0-1 提交必须用 pathspec 形式（普通 git commit 会卷走其它分组的已暂存文件）
  M3-P1-1 评审锚点必须先校验有效性（rebase / force-push 后锚点会失效）
  M3-P1-2 锚点按分支记录（多分支并行评审互不覆盖）
  M3-P1-3 报告段落要求与 CLI 校验一致（必填 3 / 建议 3）
  M3-P2-* commit message 用 ASCII 冒号；不用按键式交互；
           dev 分支默认不推送；混合暂存限制有说明；写文档走能力库路由 + 用户确认
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
if str(REPO / "skills" / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "skills" / "scripts"))

import cli  # noqa: E402


@pytest.fixture(scope="module")
def smart_git() -> str:
    return (SKILLS / "spec-smart-git" / "SKILL.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code_review() -> str:
    return (SKILLS / "spec-code-review" / "SKILL.md").read_text(encoding="utf-8")


def git(root: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


# ── M3-P0-1：提交流程必须隔离分组 ──────────────────────────────

class TestCommitIsolation:
    def test_skill_prescribes_pathspec_commit(self, smart_git):
        """执行步骤必须用 pathspec 形式提交，并解释原因。"""
        assert "git commit" in smart_git
        assert re.search(r"git commit -m .*-- <file1> <file2>", smart_git, re.S), \
            "提交示例必须带 pathspec（-- <文件>）"
        assert "索引中的全部内容" in smart_git, "必须说明为什么不能用普通 git commit"

    def test_phase3_teaches_pathspec_only(self, smart_git):
        """Phase 3 必须把 pathspec 作为执行方式，且不复述"直接 commit"的旧写法。"""
        phase3 = smart_git.split("## Phase 3")[1].split("## Phase 4")[0]
        assert "pathspec" in phase3
        assert "-- <file1> <file2>" in phase3
        assert "必须使用" in phase3

    def test_staged_limit_documented(self, smart_git):
        assert "混合暂存" in smart_git, "必须说明同一文件混合暂存的限制"

    def test_pathspec_procedure_actually_isolates_groups(self, tmp_path):
        """把技能规定的流程真跑一遍：pathspec 提交不得卷入其它分组的已暂存文件。"""
        root = tmp_path / "repo"
        root.mkdir()
        git(root, "init", "-q", ".")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        for f in ("A.txt", "B.txt", "C.txt"):
            (root / f).write_text("base\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")

        (root / "A.txt").write_text("change-A\n", encoding="utf-8")
        (root / "B.txt").write_text("change-B\n", encoding="utf-8")
        (root / "C.txt").write_text("change-C\n", encoding="utf-8")
        git(root, "add", "A.txt", "B.txt")          # 用户手工暂存（属于其它分组）

        git(root, "add", "C.txt")
        git(root, "commit", "-q", "-m", "chore: only-C", "--", "C.txt")

        changed = git(root, "show", "--stat", "--oneline", "HEAD")
        assert "C.txt" in changed
        assert "A.txt" not in changed and "B.txt" not in changed, \
            "pathspec 提交不应卷入其它分组的已暂存文件"
        status = git(root, "status", "--porcelain")
        assert "M  A.txt" in status and "M  B.txt" in status, "用户暂存状态必须保留"


# ── smart-git 其它契约 ────────────────────────────────────────

class TestSmartGitContracts:
    def test_commit_message_uses_ascii_colon(self, smart_git):
        assert "<标签>: <简短标题>" in smart_git
        assert "<标签>：" not in smart_git, "COMMIT message 规范不得用中文冒号"

    def test_no_keypress_interaction(self, smart_git):
        for pattern in ("[Y/n]", "输入 confirm", "输入 abort", "输入 merge", "输入 skip"):
            assert pattern not in smart_git, f"不应要求按键式交互: {pattern}"
        assert "你可以直接说" in smart_git or "用自然语言" in smart_git

    def test_dev_branch_not_pushed_by_default(self, smart_git):
        assert "dev-loop/" in smart_git
        assert "默认不推送" in smart_git
        assert "git push -u" in smart_git, "首次推送需说明 upstream"

    def test_no_windows_redirect(self, smart_git):
        assert ">nul" not in smart_git
        assert ">/dev/null 2>&1" in smart_git


# ── M3-P1-1 / P1-2：锚点健壮性 ────────────────────────────────

class TestAnchorRobustness:
    def test_anchor_validated_before_use(self, code_review):
        assert "git cat-file -e" in code_review, "必须校验锚点是否仍存在"
        assert "rebase" in code_review and "force-push" in code_review, "必须说明失效原因"

    def test_fallback_source_is_handled(self, code_review):
        assert "source: global" in code_review, "必须处理跨分支回退的锚点"

    def test_branch_scoped_anchor_documented(self, code_review):
        assert "--branch" in code_review
        assert "按分支记录" in code_review or "互不覆盖" in code_review

    def test_cli_supports_branch_arguments(self):
        import argparse

        parser = cli.build_parser()
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        review = sub.choices["review"]
        rsub = next(a for a in review._actions if isinstance(a, argparse._SubParsersAction))
        get_args = {a.dest for a in rsub.choices["anchor-get"]._actions}
        set_args = {a.dest for a in rsub.choices["anchor-set"]._actions}
        assert "branch" in get_args and "branch" in set_args


# ── M3-P1-3：报告段落要求与 CLI 一致 ─────────────────────────

class TestReportSections:
    def test_skill_matches_cli_validation(self, code_review):
        required = [h for h, _ in cli.REVIEW_REPORT_SECTIONS["required"]]
        recommended = [h for h, _ in cli.REVIEW_REPORT_SECTIONS["recommended"]]
        assert "必填 3 段" in code_review and "建议 3 段" in code_review
        for h in required + recommended:
            assert h in code_review, f"报告模板缺少段落 {h}"
        # 不得再声称"所有段落必须包含"
        assert "所有段落必须包含" not in code_review


# ── M3-P2：其它契约 ──────────────────────────────────────────

class TestCodeReviewContracts:
    def test_empty_change_set_handled(self, code_review):
        assert "空变更处理" in code_review
        assert "无新增代码变更" in code_review

    def test_doc_write_requires_routing_and_confirmation(self, code_review):
        assert "必须走能力库路由" in code_review
        assert "_index.md" in code_review
        assert "交用户确认" in code_review or "经用户确认" in code_review
        assert "doc update-section" in code_review and "doc add-section" in code_review

    def test_exclusion_note_explains_mixed_commits(self, code_review):
        assert "同时改了文档与代码的提交仍会出现在清单" in code_review

    def test_spec_start_guidance_updated(self, code_review):
        assert "先确认本次要讨论的议程" in code_review

    def test_no_windows_redirect(self, code_review):
        assert ">nul" not in code_review

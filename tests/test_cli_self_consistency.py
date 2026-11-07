"""CLI 自身输出的自洽检具（阶段 0-3）。

背景：`_shared/output-convention.md` 要求 agent"读到建议后**直接按建议行动**"。
但 `cli.py` 自己给出的建议里存在**会被 CLI 自己拒绝**的引用：
`suggestions` 与 argparse `help` 曾写作 `'<plan.md>#2. 约束整合'`，
而 reference 校验只接受 `plan.md#<章节>` 字面量——照抄建议的 agent 会直接撞 `invalid_ref`。

**本检具只读"运行时渲染结果"，不扫源码文本**：
  - help 文本取自 `cli.build_parser()` 的 `action.help`；
  - suggestions 取自真实运行 `dev plan create` 的 JSON 输出。

这条区分是必要的：源码里出现 `<plan.md>` 只说明有人在**描述**这个坑
（解释性注释、版本历史里的变更说明），并不代表 agent 会把占位符当值抄走；
真正会被照抄的只有 help 与 suggestions 两处。早先版本的检具扫全文，
结果被自己的注释与变更说明误伤——那是检具的错，不是被检对象的错。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "scripts"))

import cli  # noqa: E402

CLI = REPO / "skills" / "scripts" / "cli.py"
PLACEHOLDER = "<plan.md>"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), "--root", str(root), *args],
        capture_output=True, text=True, cwd=str(root),
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """能被 CLI 识别的最小工程：`SessionSpec/` 标记项目根，`ProjectSpec/` 提供 feature 范围。"""
    (tmp_path / "SessionSpec").mkdir()
    (tmp_path / "ProjectSpec" / "module-m" / "features" / "demo").mkdir(parents=True)
    return tmp_path


def _iter_parsers(parser: argparse.ArgumentParser):
    yield parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                yield from _iter_parsers(sub)


def _rendered_helps() -> list[str]:
    """模型与用户实际会看到的帮助文本。"""
    helps: list[str] = []
    for parser in _iter_parsers(cli.build_parser()):
        for action in parser._actions:
            if action.help:
                helps.append(str(action.help))
    return helps


def _suggestions_from_create(project: Path) -> list[str]:
    created = _run(project, "dev", "plan", "create", "--scope", "feature", "--target", "demo", "--module", "m")
    assert created.stdout.lstrip().startswith("{"), created.stdout + created.stderr
    payload = json.loads(created.stdout)
    assert payload.get("success") is True, created.stdout + created.stderr
    return list(payload.get("suggestions", []))


def test_help_text_never_uses_the_plan_md_placeholder():
    """help 里给的是可以照抄的值，不得使用占位符形式。"""
    helps = _rendered_helps()
    assert helps, "未取到任何 help 文本，检具本身可能已失效"
    offenders = [text for text in helps if PLACEHOLDER in text]
    assert offenders == [], f"argparse help 文本仍使用 {PLACEHOLDER} 占位符：\n  " + "\n  ".join(offenders)


def test_suggestions_never_use_the_plan_md_placeholder(project: Path):
    """suggestions 同样是给 agent 照抄的。"""
    offenders = [text for text in _suggestions_from_create(project) if PLACEHOLDER in text]
    assert offenders == [], f"suggestions 仍使用 {PLACEHOLDER} 占位符：\n  " + "\n  ".join(offenders)


def test_suggested_plan_references_are_accepted_by_cli(project: Path):
    """CLI 建议的每条 plan 段落引用，都必须能被 CLI 自己接受（往返验证）。"""
    suggestions = _suggestions_from_create(project)
    references = sorted({
        match.group(1)
        for text in suggestions
        for match in re.finditer(r"plan update-section\s+'([^']+)'", text)
    })
    assert references, f"未能从 suggestions 抽到 plan 引用，抽取逻辑可能已失效：{suggestions}"

    failures: list[str] = []
    for reference in references:
        done = _run(project, "dev", "plan", "update-section", reference, "--content", "x")
        if done.returncode != 0:
            failures.append(f"{reference!r} → exit {done.returncode}：{' '.join(done.stdout.split())[:160]}")
    assert failures == [], "CLI 自己建议的引用无法被 CLI 自己接受：\n  " + "\n  ".join(failures)

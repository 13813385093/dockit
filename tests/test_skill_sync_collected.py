"""把 `check_skill_sync.py` 纳入 pytest 收集（阶段 0-1）。

背景：`check_skill_sync.py` 是**脚本**（文件名无 `test_` 前缀），pytest 不会收集它，
也没有任何测试 import 它。因此 `TODO.md` 第 5 步声称的
"`python -m pytest tests/` = 四个检具 + 全量测试" 对**它**不成立——
而"SKILL.md 引用的 CLI 命令是否真实存在"恰恰是技能与工具链之间最关键的那条耦合。

本文件复用它的两个检查函数，使 `pytest tests/` 成为真正的闸门。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import check_skill_sync as S  # noqa: E402


def test_all_referenced_commands_exist_in_cli():
    """SKILL.md 引用的每个命令都必须真实存在于 CLI 的 argparse 树。"""
    real = S.extract_commands()
    assert real, "未能从 cli.build_parser() 提取到任何命令，检具本身可能已失效"
    problems: list[str] = []
    for group, cmd in sorted(S.extract_skill_refs()):
        if group not in real:
            problems.append(f"cli.py {group}（命令组不存在）")
        elif cmd not in real[group]:
            problems.append(f"cli.py {group} {cmd}（该组可用：{sorted(real[group])}）")
    assert problems == [], "SKILL.md 引用了不存在的命令：\n  " + "\n  ".join(problems)


def test_reference_extraction_is_not_silently_empty():
    """守住上一条检查的前提：抽取正则被改坏时必须报错，而不是"零引用 ⇒ 零问题"。"""
    refs = S.extract_skill_refs()
    assert len(refs) >= 20, f"只抽到 {len(refs)} 个命令引用，抽取逻辑可能已失效"


def test_skill_names_use_hyphen_form():
    """技能名必须写作 `spec-start` 而非 `spec_start`（下划线形式会让 AI 找不到技能）。"""
    problems = S.check_skill_names()
    assert problems == [], "\n".join(problems)

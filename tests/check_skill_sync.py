#!/usr/bin/env python3
"""Skill 提示词回归检查 — 验证 SKILL.md 引用的 CLI 命令与 cli.py 实际定义一致。

用法:
    python tests/check_skill_sync.py

无第三方依赖，纯静态分析。返回 0 表示无差异，返回 1 表示发现不匹配。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO / "skills" / "scripts"
SKILL_DIR = REPO / "skills"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# CLI 命令分组（正则捕获组）。dev 组为两级子命令（如 `dev plan create`），
# 因此允许捕获至多两个单词，其余组为单级命令（如 `doc update-section`）。
# 仅匹配行内空格（[ \t]+），避免跨行误匹配。
GROUP_RE = re.compile(r"cli\.py[ \t]+(tool|spec|doc|review|dev)((?:[ \t]+[a-z][a-z-]*){1,2})")

# 技能名的下划线写法（spec_start）是 Python 函数名 / 旧 MCP 工具名的写法，
# 写进 SKILL.md 正文会让 AI 找不到对应技能。只匹配 10 个真实/历史技能名，避免误伤
# spec_write / spec_read 这类 CLI 命令名与代码符号。
SKILL_NAME_RE = re.compile(
    r"\bspec_(start|load|pause|close|abort|archive|dev_loop|smart_git|code_review|code_smell)\b"
)


def extract_commands() -> dict[str, set[str]]:
    """从 cli.py 的 argparse 定义提取 {group: set(完整命令路径)}。

    递归遍历嵌套 subparsers，叶子命令以「子组 命令」形式记录（如
    "plan create" / "status"），与 SKILL.md 中的调用形式一一对应。
    """
    import argparse

    import cli  # noqa: E402

    parser = cli.build_parser()
    sub_actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not sub_actions:
        return {}

    def walk(p, prefix: str) -> set[str]:
        leaves: set[str] = set()
        for action in p._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, subparser in action.choices.items():
                    sub_leaves = walk(subparser, prefix + name + " ")
                    if sub_leaves:
                        leaves.update(sub_leaves)
                    else:
                        leaves.add(prefix + name)
        return leaves

    result: dict[str, set[str]] = {}
    for gname, gparser in sub_actions[0].choices.items():
        result[gname] = walk(gparser, "")
    return result


def extract_skill_refs() -> set[tuple[str, str]]:
    """从 skill/*/SKILL.md 提取所有 `cli.py <group> <命令...>` 引用。"""
    refs: set[tuple[str, str]] = set()
    for md_file in sorted(SKILL_DIR.glob("**/SKILL.md")):
        text = md_file.read_text(encoding="utf-8")
        for m in GROUP_RE.finditer(text):
            refs.add((m.group(1), m.group(2).strip()))
    return refs


def check_skill_names() -> list[str]:
    """检查 SKILL.md 中的技能名是否统一用连字符形式（spec-start 而非 spec_start）。"""
    errors: list[str] = []
    for md_file in sorted(SKILL_DIR.glob("**/SKILL.md")):
        text = md_file.read_text(encoding="utf-8")
        for m in SKILL_NAME_RE.finditer(text):
            name = m.group(0)
            line_no = text[: m.start()].count("\n") + 1
            errors.append(
                f"⚠️  {md_file.relative_to(REPO)}:{line_no} 技能名写成下划线形式 `{name}`\n"
                f"   应写作 `{name.replace('_', '-')}`（目录名即技能名）"
            )
    return errors


def check() -> None:
    real = extract_commands()
    refs = extract_skill_refs()
    errors: list[str] = []

    for group, cmd in sorted(refs):
        if group not in real:
            errors.append(f"⚠️  Skill 中引用了不存在的命令分组: `cli.py {group}`")
            continue
        if cmd not in real[group]:
            errors.append(
                f"⚠️  Skill 中引用了不存在的命令: `cli.py {group} {cmd}`\n"
                f"   该分组可用命令: {sorted(real[group])}"
            )

    errors.extend(check_skill_names())

    if errors:
        print("!! Skill 同步检查发现以下问题：\n")
        for e in errors:
            print(e)
            print()
        sys.exit(1)
    else:
        print("OK Skill 同步检查通过")
        print(f"   CLI 命令: {sum(len(v) for v in real.values())} 个（分组 {len(real)} 个）")
        print(f"   Skill 引用: {len(refs)} 个命令")
        print(f"   技能名一致性: {len(list(SKILL_DIR.glob('**/SKILL.md')))} 个 SKILL.md 均使用连字符形式")


if __name__ == "__main__":
    check()

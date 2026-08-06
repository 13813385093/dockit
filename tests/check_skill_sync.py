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


def extract_commands() -> dict[str, set[str]]:
    """从 cli.py 的 argparse 定义提取 {group: set(command)}。"""
    import cli  # noqa: E402

    parser = cli.build_parser()
    group_parsers = parser._subparsers.choices  # type: ignore[attr-defined]
    result: dict[str, set[str]] = {}
    for gname, gparser in group_parsers.items():
        sub = getattr(gparser, "_subparsers", None)
        cmds: set[str] = set()
        if sub is not None:
            cmds.update(sub.choices.keys())  # type: ignore[attr-defined]
        result[gname] = cmds
    return result


def extract_skill_refs() -> set[tuple[str, str]]:
    """从 skill/*/SKILL.md 提取所有 `cli.py <group> <command>` 引用。"""
    refs: set[tuple[str, str]] = set()
    pattern = re.compile(r"cli\.py\s+(spec|doc|review)\s+([a-z][a-z-]*)")
    for md_file in sorted(SKILL_DIR.glob("**/SKILL.md")):
        text = md_file.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            refs.add((m.group(1), m.group(2)))
    return refs


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


if __name__ == "__main__":
    check()

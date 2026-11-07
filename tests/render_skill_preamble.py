#!/usr/bin/env python3
"""SKILL.md 前言生成器 / 校验器（共享前言的单一事实源）。

背景：8 份 SKILL.md 顶部那段"最高优先级"前言（CLI 纪律 / 能力库例外 / 三层边界 /
前置条件 / 工具清单 / 输出约定）原本各写一遍，已经漂移出 9 个版本——同一个坏命令
（`>nul 2>&1`）在两份技能里各留一份，输出约定的措辞有三种，工具清单靠人工对齐。

本脚本把前言变成**生成物**：

  1. 共性文字来自 `skills/_shared/preamble-<variant>.md`（三个变体：session / dev / git）
     与 `skills/_shared/output-convention.md`；
  2. **工具清单从技能正文实际用到的命令自动派生**——"声明 = 实用"由机制保证，
     不会再出现过期/多余的声明；
  3. 生成结果**内联**写回 SKILL.md（技能文件仍自包含，init/install 部署方式不变）。

用法：
    python tests/render_skill_preamble.py            # 重新生成全部 8 份
    python tests/render_skill_preamble.py --check    # 只校验（CI 用；有漂移返回 1）

正文里的特例可用注释标记：
    <!-- preamble-tools-extra: spec archive -->      额外声明一条命令
    <!-- preamble-tools-exclude: doc remove-section -->  排除正文提到但不调用的命令
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO / "skills"
SHARED = SKILLS_DIR / "_shared"

PREAMBLE_START = "# 最高优先级："
PREAMBLE_END_RE = re.compile(r"^# spec-", re.M)

# 技能 → 前言变体
VARIANTS = {
    "spec-start": "session",
    "spec-pause": "session",
    "spec-close": "session",
    "spec-archive": "session",
    "spec-dev-loop": "dev",
    "spec-smart-git": "git",
    "spec-code-review": "git",
    "spec-code-smell": "smell",
}

# 命令 → 规范用法行（单一事实源；新增命令必须在此登记，否则生成器报错）
USAGE: dict[str, str] = {
    "tool status": "python3 .doc-kit/cli/cli.py tool status",
    "spec status": "python3 .doc-kit/cli/cli.py spec status",
    "spec read": "python3 .doc-kit/cli/cli.py spec read",
    "spec schema": "python3 .doc-kit/cli/cli.py spec schema",
    "spec write": "python3 .doc-kit/cli/cli.py spec write [--json '<完整 spec JSON>']   # 省 --json 则从 stdin 读入",
    "spec archive": "python3 .doc-kit/cli/cli.py spec archive",
    "spec coverage": "python3 .doc-kit/cli/cli.py spec coverage [--verify] [--id <sid>]",
    "doc structure": "python3 .doc-kit/cli/cli.py doc structure",
    "doc read": "python3 .doc-kit/cli/cli.py doc read <path>",
    "doc update-section": "python3 .doc-kit/cli/cli.py doc update-section <reference> --content '<正文>'",
    "doc add-section": "python3 .doc-kit/cli/cli.py doc add-section <reference> '<标题>' [--content '<正文>'] [--level sibling|child]",
    "doc new": "python3 .doc-kit/cli/cli.py doc new <doc_type> [--module <模块名>] [--feature <功能名>] [--author <负责人>]",
    "doc reindex": "python3 .doc-kit/cli/cli.py doc reindex",
    "doc lint": "python3 .doc-kit/cli/cli.py doc lint [--baseline <file>] [--summary]",
    "review anchor-get": "python3 .doc-kit/cli/cli.py review anchor-get [--branch <分支名>]",
    "review anchor-set": "python3 .doc-kit/cli/cli.py review anchor-set <commit_hash> [--session <sid>] [--branch <分支名>]",
    "review report-write": "python3 .doc-kit/cli/cli.py review report-write [--content '<report_markdown>']   # 或 --file <path> / stdin",
    "dev status": "python3 .doc-kit/cli/cli.py dev status",
    "dev plan create": "python3 .doc-kit/cli/cli.py dev plan create --scope feature --target <功能名> --module <模块名> [--title <标题>]",
    "dev plan read": "python3 .doc-kit/cli/cli.py dev plan read",
    "dev plan update-section": "python3 .doc-kit/cli/cli.py dev plan update-section <reference> --content '<正文>'",
    "dev task list": "python3 .doc-kit/cli/cli.py dev task list",
    "dev task set": "python3 .doc-kit/cli/cli.py dev task set --json '<tasks 数组>'",
    "dev task patch": "python3 .doc-kit/cli/cli.py dev task patch <task_id> --json '<字段子集>'",
    "dev task update": "python3 .doc-kit/cli/cli.py dev task update <task_id> --status <状态> [--note '<备注>']",
    "dev task annotate": "python3 .doc-kit/cli/cli.py dev task annotate <task_id> --note '<备注>'",
    "dev branch set": "python3 .doc-kit/cli/cli.py dev branch set <branch>",
    "dev align": "python3 .doc-kit/cli/cli.py dev align --feature <功能名> --module <模块名> --status <aligned|done> [--note '<备注>'] [--allow-branch-mismatch --reason '<原因>']",
    "dev integrate": "python3 .doc-kit/cli/cli.py dev integrate --module <模块名> --status <integrated|documented|done> [--note '<备注>'] [--allow-branch-mismatch --reason '<原因>']",
    "dev notes append": "python3 .doc-kit/cli/cli.py dev notes append --content '<md>' [--section <章节名>]",
    "dev report-write": "python3 .doc-kit/cli/cli.py dev report-write --kind <feature|module> --name <目标> --content '<md>'",
    "dev close": "python3 .doc-kit/cli/cli.py dev close --reason '<原因>'",
    "dev abort": "python3 .doc-kit/cli/cli.py dev abort --reason '<原因>'",
    "dev archive": "python3 .doc-kit/cli/cli.py dev archive",
}

# 工具清单的呈现顺序（按 CLI 分组与常用度）
ORDER = list(USAGE)

# 每份技能都会声明的工具（工具链自检，不属于各技能正文的调用）
ALWAYS_TOOLS = ["tool status"]


def toolchain_version() -> str:
    """从 cli.py 读取工具链版本（单一事实源）。"""
    m = re.search(r'^TOOLCHAIN_VERSION\s*=\s*["\']([^"\']+)["\']',
                  (SKILLS_DIR / "scripts" / "cli.py").read_text(encoding="utf-8"), re.M)
    if not m:
        raise ValueError("cli.py 中找不到 TOOLCHAIN_VERSION")
    return m.group(1)

# 全写形式：python3 .doc-kit/cli/cli.py dev task update ...
COMMAND_RE = re.compile(r"cli\.py[ \t]+((?:tool|spec|doc|review|dev)(?:[ \t]+[a-z][a-z-]*){1,2})")
# 简写形式：正文里的 `dev task update` / `doc read`（判定"该技能会用到哪些命令"时同样计入，
# 纯引用（如"`doc remove-section` 不在本技能职责内"）用 preamble-tools-exclude 标记排除）
SHORTHAND_RE = re.compile(r"`((?:tool|spec|doc|review|dev)[ \t]+[a-z][a-z-]*(?:[ \t]+[a-z][a-z-]*)?)")
EXTRA_RE = re.compile(r"<!--\s*preamble-tools-extra:\s*([^>]+?)\s*-->")
EXCLUDE_RE = re.compile(r"<!--\s*preamble-tools-exclude:\s*([^>]+?)\s*-->")


def split_skill(text: str) -> tuple[str, str, str]:
    """拆成 (frontmatter+前言之前, 旧前言, 正文)。"""
    m = PREAMBLE_END_RE.search(text)
    if not m:
        raise ValueError("找不到正文 H1（# spec-...）")
    head = text[: m.start()]
    start = head.find(PREAMBLE_START)
    if start == -1:
        raise ValueError(f"找不到前言起点 {PREAMBLE_START!r}")
    body = text[m.start():]
    # 去掉前言与正文之间的分隔线（---），生成时会重新补上
    preamble = head[start:].rstrip()
    if preamble.endswith("---"):
        preamble = preamble[:-3].rstrip()
    return text[:start], preamble, body


def normalize(cmd: str) -> str:
    return " ".join(cmd.split())


def derive_tools(prefix: str, body: str) -> list[str]:
    """从正文派生工具清单（声明 = 实用）。"""
    used = {normalize(m.group(1)) for m in COMMAND_RE.finditer(body)}
    for m in SHORTHAND_RE.finditer(body):
        cand = normalize(m.group(1))
        if cand in USAGE:
            used.add(cand)
    for m in EXTRA_RE.finditer(prefix + body):
        used.add(normalize(m.group(1)))
    for m in EXCLUDE_RE.finditer(prefix + body):
        used.discard(normalize(m.group(1)))
    unknown = sorted(c for c in used if c not in USAGE)
    if unknown:
        raise ValueError(f"正文使用了未在 USAGE 中登记的命令: {unknown}")
    return [c for c in ORDER if c in used]


def render(name: str, text: str) -> str:
    prefix, _old, body = split_skill(text)
    variant = VARIANTS[name]
    frag = (SHARED / f"preamble-{variant}.md").read_text(encoding="utf-8").rstrip()
    convention = (SHARED / "output-convention.md").read_text(encoding="utf-8").rstrip()
    tools = ALWAYS_TOOLS + [c for c in derive_tools(prefix, body) if c not in ALWAYS_TOOLS]
    tool_block = "```bash\ncd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录\n" + \
        "\n".join(USAGE[c] for c in tools) + "\n```"
    preamble = (
        frag.replace("{{TOOLS}}", tool_block)
        .replace("{{OUTPUT_CONVENTION}}", convention)
        .replace("{{TOOLCHAIN_VERSION}}", toolchain_version())
    )
    return f"{prefix}{preamble}\n---\n\n{body}"


def targets() -> list[tuple[str, Path]]:
    return [(n, SKILLS_DIR / n / "SKILL.md") for n in VARIANTS]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    changed, failed = [], []
    for name, path in targets():
        original = path.read_text(encoding="utf-8")
        try:
            rendered = render(name, original)
        except ValueError as e:
            failed.append(f"{name}: {e}")
            continue
        if rendered != original:
            changed.append(name)
            if not check:
                path.write_text(rendered, encoding="utf-8")
    if failed:
        print("!! 前言生成失败：")
        for f in failed:
            print("  -", f)
        return 1
    if check and changed:
        print("!! 以下 SKILL.md 的前言与共享片段不一致（请运行 python tests/render_skill_preamble.py）：")
        for c in changed:
            print("  -", c)
        return 1
    action = "校验" if check else "生成"
    print(f"OK 前言{action}通过：{len(VARIANTS)} 份 SKILL.md"
          + (f"（{len(changed)} 份需更新）" if check else f"（更新 {len(changed)} 份）"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

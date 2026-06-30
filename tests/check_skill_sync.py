#!/usr/bin/env python3
"""Skill 提示词回归检查 — 验证 .md Skill 描述与实际工具签名一致。

用法:
    python tests/check_skill_sync.py

无依赖，纯静态分析。返回 0 表示无差异，返回 1 表示发现不匹配。
"""

import ast
import re
import sys
from pathlib import Path

# 确保 stdout 支持 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / "src" / "skill" / "skills"
MCP_SERVER = REPO / "src" / "skill" / "mcp" / "mcp_server.py"
SPEC_SCHEMA = REPO / "src" / "skill" / "mcp" / "spec_schema.py"

# 已知的非工具函数名（内部函数，不暴露为 MCP 工具），检查时忽略
NON_TOOL_NAMES = {"validate", "render_summary", "new_spec", "close_spec", "abort_spec"}

errors: list[str] = []


# ═══════════════════════════════════════════════════════════════
#  1. 提取真实工具签名
# ═══════════════════════════════════════════════════════════════

def extract_tool_signatures() -> dict[str, list[str]]:
    """从 mcp_server.py 提取 @mcp.tool() 装饰的函数的名称和参数名列表。"""
    source = MCP_SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)

    tools: dict[str, list[str]] = {}
    in_tool = False

    for node in ast.walk(tree):
        # 检测 @mcp.tool() 装饰器
        if isinstance(node, ast.FunctionDef):
            # 检查上一个语句或装饰器
            for deco in node.decorator_list:
                if (isinstance(deco, ast.Call) and
                    getattr(deco.func, 'attr', None) == 'tool'):
                    params = [arg.arg for arg in node.args.args
                              if arg.arg != 'self']
                    tools[node.name] = params
                    break

    return tools


# ═══════════════════════════════════════════════════════════════
#  2. 提取 Skill 中的工具引用
# ═══════════════════════════════════════════════════════════════

def extract_skill_refs() -> dict[str, set[str]]:
    """从 skill/*.md 提取所有 `函数名(...)` 调用模式，返回 {工具名: set(参数名)}。"""
    skill_refs: dict[str, set[str]] = {}

    for md_file in sorted(SKILL_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        # 匹配 `funcName(arg1, arg2, ...)` 或 `funcName(arg1=val, arg2=val)`
        pattern = r'`([a-zA-Z_]\w*)\s*\(([^)]*)\)`'
        for match in re.finditer(pattern, text):
            func_name = match.group(1)
            args_str = match.group(2)
            # 提取参数名（支持 name=val 和 name: type 两种写法）
            args = set()
            for arg in args_str.split(","):
                arg = arg.strip()
                # name=val → name
                if "=" in arg:
                    arg = arg.split("=")[0].strip()
                # name: type → name
                if ":" in arg:
                    arg = arg.split(":")[0].strip()
                if arg:
                    args.add(arg)
            skill_refs.setdefault(func_name, set()).update(args)

    return skill_refs


# ═══════════════════════════════════════════════════════════════
#  3. 提取 spec_pause 的 data 字段定义
# ═══════════════════════════════════════════════════════════════

def extract_pause_data_keys_from_code() -> set[str]:
    """从 apply_pause() 解析它读取的 data dict 的顶层 key。"""
    source = SPEC_SCHEMA.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "apply_pause":
            data_keys: set[str] = set()
            for sub in ast.walk(node):
                # 匹配 data.get("xxx", []) — 仅限变量名为 data 的 .get 调用
                if (isinstance(sub, ast.Call) and
                    isinstance(sub.func, ast.Attribute) and
                    sub.func.attr == "get" and
                    isinstance(sub.func.value, ast.Name) and
                    sub.func.value.id == "data" and
                    len(sub.args) >= 1 and
                    isinstance(sub.args[0], ast.Constant) and
                    isinstance(sub.args[0].value, str)):
                    data_keys.add(sub.args[0].value)
            return data_keys

    return set()


def extract_pause_data_keys_from_skill() -> set[str]:
    """从 spec-pause.md 提取 spec_pause JSON 的顶层字段名。"""
    skill_file = SKILL_DIR / "spec-pause.md"
    text = skill_file.read_text(encoding="utf-8")

    keys: set[str] = set()
    in_json = False
    for line in text.split("\n"):
        if "```" in line and "json" in line:
            in_json = True
            continue
        if line.strip().startswith("```"):
            in_json = False
            continue
        if in_json:
            # 只匹配顶层 key（不在缩进的 { 内部）
            # 缩进 ≤ 2 个空格 + "key": 开头
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent <= 2 and stripped.startswith('"') and ": " in stripped:
                m = re.match(r'"(\w+)":', stripped)
                if m:
                    keys.add(m.group(1))

    return keys


# ═══════════════════════════════════════════════════════════════
#  检查
# ═══════════════════════════════════════════════════════════════

def check():
    real_tools = extract_tool_signatures()
    skill_refs = extract_skill_refs()

    # ── 4a: 工具名称匹配 ──
    # 构建反向映射：camelCase → snake_case
    def snake_to_camel(name: str) -> str:
        parts = name.split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    real_by_camel = {snake_to_camel(k): k for k in real_tools}
    # 也保留原样（部分工具本身不含下划线）
    for k in real_tools:
        real_by_camel.setdefault(k, k)

    for skill_name in skill_refs:
        if skill_name in NON_TOOL_NAMES:
            continue
        if skill_name not in real_by_camel and skill_name not in real_tools:
            errors.append(
                f"⚠️  Skill 中引用了不存在的工具: `{skill_name}()`\n"
                f"   可能名称: {[n for n in real_tools if n.replace('_','').lower() == skill_name.lower()]}"
            )

    # ── 4b: spec_pause data 字段一致性 ──
    code_keys = extract_pause_data_keys_from_code()
    skill_keys = extract_pause_data_keys_from_skill()

    only_in_code = code_keys - skill_keys
    only_in_skill = skill_keys - code_keys

    if only_in_code:
        errors.append(
            f"⚠️  spec-pause.md 缺少以下字段（代码中有但文档未描述）:\n"
            f"   {sorted(only_in_code)}"
        )
    if only_in_skill:
        errors.append(
            f"⚠️  spec-pause.md 多出以下字段（文档中有但代码不处理）:\n"
            f"   {sorted(only_in_skill)}"
        )

    # ── 输出 ──
    if errors:
        print("!! Skill 同步检查发现以下问题：\n")
        for e in errors:
            print(e)
            print()
        sys.exit(1)
    else:
        print("OK Skill 同步检查通过")
        print(f"   工具签名: {len(real_tools)} 个")
        print(f"   Skill 引用: {len(skill_refs)} 个工具")
        print(f"   spec-pause data 字段: {code_keys} (代码) ↔ {skill_keys} (文档)")


if __name__ == "__main__":
    check()

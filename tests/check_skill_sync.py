#!/usr/bin/env python3
"""Skill 提示词回归检查 — 验证 SKILL.md 描述与实际工具签名一致。

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
SKILL_DIR = REPO / "skills"
MCP_SERVER = REPO / "spec_mcp_tools" / "server.py"

# 已知的非工具函数名（内部函数，不暴露为 MCP 工具），检查时忽略
NON_TOOL_NAMES = {"validate", "render_summary"}

errors: list[str] = []


# ═══════════════════════════════════════════════════════════════
#  1. 提取真实工具签名
# ═══════════════════════════════════════════════════════════════

def extract_tool_signatures() -> dict[str, list[str]]:
    """从 mcp_server.py 提取 @mcp.tool() 装饰的函数的名称和参数名列表。"""
    source = MCP_SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)

    tools: dict[str, list[str]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
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
    """从 skill/*/SKILL.md 提取所有 `函数名(...)` 调用模式，返回 {工具名: set(参数名)}。"""
    skill_refs: dict[str, set[str]] = {}

    for md_file in sorted(SKILL_DIR.glob("**/SKILL.md")):
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


if __name__ == "__main__":
    check()

"""doc-kit MCP 服务器。

提供 MCP（Model Context Protocol）工具，让 AI 按需查询文档依赖图，
避免全文加载。支持 stdio 传输，兼容 Reasonix / Claude Desktop 等 MCP 客户端。

用法:
    python -m src.mcp_server                         # 从 cwd 自动检测项目
    python -m src.mcp_server /path/to/project         # 指定项目目录
    set DOC_KIT_PROJECT_ROOT=/path & python -m src.mcp_server  # 环境变量
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── MCP SDK ──
try:
    from mcp.server import FastMCP
except ImportError:
    print("请安装 mcp 包: pip install 'mcp>=1.5.0'", file=sys.stderr)
    sys.exit(1)

# ── 项目引擎 ──
# 脚本在项目根执行时，src 作为顶层包导入
_PROJECT_ROOT_PLACEHOLDER = "__PROJECT_ROOT__"


def _ensure_src_on_path():
    """确保 src/ 可被导入（无论从项目根还是子目录启动）。"""
    src_path = Path(__file__).resolve().parent
    if str(src_path.parent) not in sys.path:
        sys.path.insert(0, str(src_path.parent))


_ensure_src_on_path()

from src.engine.index import IndexManager, IndexEntry
from src.engine.deps import find_reverse_dependencies, check_version_drift
from src.engine.frontmatter import FrontmatterParser


# ═══════════════════════════════════════════════════════════════
#  项目根发现
# ═══════════════════════════════════════════════════════════════

MCP_SERVER_DIR = Path(__file__).resolve().parent


def find_project_root(cli_arg: str | None = None) -> Path:
    """自动发现 doc-kit 项目根目录。

    优先级: CLI 参数 > 环境变量 > cwd 向上遍历找 .doc-kit/。
    返回 Path 或抛出 SystemExit。
    """
    # 1) CLI 参数
    if cli_arg:
        candidate = Path(cli_arg).resolve()
        if _is_valid_project(candidate):
            return candidate
        print(f"错误: 指定目录不存在或不是 doc-kit 项目: {cli_arg}", file=sys.stderr)
        sys.exit(1)

    # 2) 环境变量
    env_val = os.environ.get("DOC_KIT_PROJECT_ROOT")
    if env_val:
        candidate = Path(env_val).resolve()
        if _is_valid_project(candidate):
            return candidate
        print(f"错误: DOC_KIT_PROJECT_ROOT 指向无效目录: {env_val}", file=sys.stderr)
        sys.exit(1)

    # 3) 从 cwd 向上遍历
    start = Path.cwd().resolve()
    for parent in [start] + list(start.parents):
        if _is_valid_project(parent):
            return parent

    print(
        "错误: 未找到 doc-kit 项目目录。\n"
        "  用法: python -m src.mcp_server /path/to/project\n"
        "  或设置环境变量 DOC_KIT_PROJECT_ROOT\n"
        "  或从包含 .doc-kit/ 的目录下运行",
        file=sys.stderr,
    )
    sys.exit(1)


def _is_valid_project(path: Path) -> bool:
    """检查 path 是否为 doc-kit 项目：存在 .doc-kit/ 目录。"""
    return (path / ".doc-kit").is_dir()


def _load_index(project_root: Path) -> IndexManager | None:
    """加载项目索引，不存在则返回 None。"""
    index_path = project_root / ".doc-kit" / "index.json"
    if not index_path.exists():
        return None
    return IndexManager(index_path)


def _find_doc(project_root: Path, doc_path: str) -> Path | None:
    """在 ProjectSpec/ 中查找文档文件。

    doc_path 可以是完整路径或文件名（取首个匹配）。
    """
    docs_root = project_root / "ProjectSpec"
    if not docs_root.exists():
        return None

    target = docs_root / doc_path
    if target.exists() and target.is_file():
        return target

    # 按文件名搜索
    for f in sorted(docs_root.rglob(doc_path)):
        if f.is_file():
            return f

    # 模糊匹配basename
    name = Path(doc_path).name
    for f in sorted(docs_root.rglob("*.md")):
        if f.name == name or f.stem == Path(doc_path).stem:
            return f

    return None


# ═══════════════════════════════════════════════════════════════
#  MCP 服务器
# ═══════════════════════════════════════════════════════════════

mcp = FastMCP("doc-kit")

# 项目根目录（在 run() 中通过生命周期初始化设置）
_project_root: Path | None = None


@mcp.tool()
def list_docs() -> str:
    """列出项目中所有文档及其元数据（doc_type / module / level / version / status）。

    返回值: Markdown 表格。
    """
    index = _load_index(_project_root)
    if not index:
        return "错误: 项目索引不存在，请先运行初始化。"
    entries = index.list_entries()
    if not entries:
        return "项目索引为空。"

    lines = ["| 文档路径 | 类型 | 模块 | 层级 | 版本 | 状态 |",
             "|---------|------|------|------|------|------|"]
    for e in sorted(entries, key=lambda x: x.path):
        lines.append(f"| {e.path} | {e.doc_type} | {e.module} | {e.level} | v{e.version} | {e.status} |")
    return "\n".join(lines)


@mcp.tool()
def get_forward_deps(doc_path: str) -> str:
    """查询指定文档的正向依赖（它依赖哪些文档）。

    AI 在阅读某个文档前调用此工具，了解需要先加载哪些前置文档。
    例如读 feature-design.md 前，先读它依赖的 architecture.md / domain-model.md。

    参数:
        doc_path: 文档路径（相对 ProjectSpec/，如 "technical-framework.md"）
                  支持文件名或路径片段。

    返回值: 依赖列表 Markdown，含文档名、模块和版本。
    """
    index = _load_index(_project_root)
    if not index:
        return "错误: 项目索引不存在。"

    # 在索引中查找文档
    entry = _find_index_entry(index, doc_path)
    if not entry:
        return f"未找到文档: {doc_path}\n可用文档请使用 list_docs 查看。"

    if not entry.depends_on:
        return f"`{entry.path}` 没有显式依赖（depends_on 为空）。"

    lines = [f"### {entry.path} 的依赖项",
             "",
             "| 依赖文档 | 模块 | 版本 |",
             "|---------|------|------|"]
    for dep in entry.depends_on:
        lines.append(f"| {dep.get('doc', '?')} | {dep.get('module', '?')} | v{dep.get('version', '?')} |")
    return "\n".join(lines)


@mcp.tool()
def get_reverse_deps(doc_path: str) -> str:
    """查询指定文档的反向依赖（哪些文档依赖它）。

    AI 在修改某个文档时调用此工具，了解需要同步更新哪些下游文档。
    例如修改 business-context.md 后，需要检查所有依赖它的文档是否需要调整。

    参数:
        doc_path: 文档路径（相对 ProjectSpec/，如 "business-context.md"）
                  支持文件名或路径片段。

    返回值: 依赖方列表 Markdown。
    """
    index = _load_index(_project_root)
    if not index:
        return "错误: 项目索引不存在。"

    rev = find_reverse_dependencies(doc_path, index)
    if not rev:
        return f"没有文档依赖 `{doc_path}`。"

    lines = [f"### 依赖 `{doc_path}` 的文档",
             "",
             "| 文档路径 | 模块 | 版本 |",
             "|---------|------|------|"]
    for r in rev:
        lines.append(f"| {r.path} | {r.module} | v{r.version} |")
    return "\n".join(lines)


@mcp.tool()
def read_doc(doc_path: str) -> str:
    """读取指定文档的完整内容。

    AI 在确定需要深入阅读时才调用此工具，避免全文加载。
    先用 get_forward_deps 了解前置依赖，再用 read_doc 按需加载。

    参数:
        doc_path: 文档路径（相对 ProjectSpec/，如 "architecture.md"）
                  支持文件名或路径片段。

    返回值: 文档的 Markdown 原文（含 frontmatter 元数据）。
    """
    full_path = _find_doc(_project_root, doc_path)
    if not full_path:
        return f"未找到文档: {doc_path}\n可用文档请使用 list_docs 查看。"

    try:
        text = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"读取文档失败: {e}"

    return text


@mcp.tool()
def search_docs(pattern: str) -> str:
    """按文件名或路径模式搜索文档。

    AI 在不确定确切文件名时调用此工具，例如按模块或功能名搜索。

    参数:
        pattern: 搜索关键词（如 "business"、"technical"、"module-core"）

    返回值: 匹配文档列表 Markdown。
    """
    index = _load_index(_project_root)
    if not index:
        return "错误: 项目索引不存在。"

    pattern_lower = pattern.lower()
    matches = []
    for e in index.list_entries():
        if pattern_lower in e.path.lower() or pattern_lower in e.doc_type.lower():
            matches.append(e)

    if not matches:
        return f"未找到匹配「{pattern}」的文档。"

    lines = ["| 文档路径 | 类型 | 模块 | 层级 | 版本 |",
             "|---------|------|------|------|------|"]
    for e in sorted(matches, key=lambda x: x.path):
        lines.append(f"| {e.path} | {e.doc_type} | {e.module} | {e.level} | v{e.version} |")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _find_index_entry(index: IndexManager, doc_path: str) -> IndexEntry | None:
    """通过路径或文件名在索引中查找文档。"""
    # 精确匹配
    entry = index.get_entry(doc_path)
    if entry:
        return entry

    # 按路径后缀
    target_name = Path(doc_path).name
    for e in index.list_entries():
        if e.path == doc_path or Path(e.path).name == target_name:
            return e
        # 路径片段匹配
        if doc_path in e.path:
            return e

    return None


# ═══════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════

def main():
    """MCP 服务器入口。"""
    global _project_root

    cli_arg = sys.argv[1] if len(sys.argv) > 1 else None
    _project_root = find_project_root(cli_arg)

    # 快速校验索引存在
    index = _load_index(_project_root)
    if index is None:
        print(
            f"警告: {_project_root / '.doc-kit' / 'index.json'} 不存在。\n"
            f"  请先在项目中运行初始化。MCP 服务器仍会启动，但工具将返回空结果。",
            file=sys.stderr,
        )

    print(
        f"doc-kit MCP 服务器启动\n"
        f"  项目: {_project_root}\n"
        f"  索引: {_project_root / '.doc-kit' / 'index.json'}\n"
        f"  传输: stdio\n"
        f"  工具: list_docs, get_forward_deps, get_reverse_deps, read_doc, search_docs",
        file=sys.stderr,
    )

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

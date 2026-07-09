"""doc-kit MCP 服务器。

提供 MCP（Model Context Protocol）工具，让 AI 按需查询文档与议题。
自包含模块，所有依赖在同目录下。

用法:
    python -m mcp_tools.server                        # 从 cwd 自动检测项目
    python -m mcp_tools.server /path/to/project        # 指定项目目录
    set DOC_KIT_PROJECT_ROOT=/path & python -m mcp_tools.server  # 环境变量
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── MCP SDK ──
try:
    from mcp.server import FastMCP
except ImportError:
    print("请安装 mcp 包: pip install 'mcp>=1.5.0'", file=sys.stderr)
    sys.exit(1)

# ── 本地依赖（同一目录）──
import sys
from pathlib import Path
_PKG_DIR = Path(__file__).resolve().parent
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

from frontmatter import FrontmatterParser
from index_manager import IndexManager, IndexEntry
from spec_schema import (
    validate as validate_spec,
    render_summary,
    get_schema_metadata,
)


# ═══════════════════════════════════════════════════════════════
#  项目根发现
# ═══════════════════════════════════════════════════════════════


def find_project_root(cli_arg: str | None = None) -> Path:
    """获取 doc-kit 项目根目录。

    优先级: CLI 参数 > DOC_KIT_PROJECT_ROOT 环境变量。
    均未提供或指向无效目录时，打印引导信息并退出。

    各 IDE/MCP 客户端应在 MCP 配置中通过 args 或 env 传入项目路径。
    """
    if cli_arg:
        candidate = Path(cli_arg).resolve()
        if _is_valid_project(candidate):
            return candidate
        print(
            f"错误: 指定目录不存在或不是 doc-kit 项目: {cli_arg}\n"
            f"  项目目录必须包含 .doc-kit/ 或 SessionSpec/ 目录。",
            file=sys.stderr,
        )
        sys.exit(1)

    env_val = os.environ.get("DOC_KIT_PROJECT_ROOT")
    if env_val:
        candidate = Path(env_val).resolve()
        if _is_valid_project(candidate):
            return candidate
        print(
            f"错误: DOC_KIT_PROJECT_ROOT 指向无效目录: {env_val}\n"
            f"  该目录必须包含 .doc-kit/ 或 SessionSpec/ 目录。",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        "错误: 未指定 doc-kit 项目目录。\n"
        "\n"
        "请在 MCP 客户端配置中传入项目根路径。常见配置方式：\n"
        "\n"
        "  VS Code (.vscode/mcp.json):\n"
        '    {\n'
        '      "doc-kit": {\n'
        '        "command": "python",\n'
        '        "args": ["-m", "mcp_tools.server", "D:/dockit"],\n'
        '        "cwd": "D:/dockit"\n'
        '      }\n'
        '    }\n'
        "\n"
        "  或设置环境变量:\n"
        '    set DOC_KIT_PROJECT_ROOT=D:/dockit\n'
        "\n"
        "  项目目录必须包含 .doc-kit/ 或 SessionSpec/ 目录。",
        file=sys.stderr,
    )
    sys.exit(1)


def _is_valid_project(path: Path) -> bool:
    """检查 path 是否为 doc-kit 项目：存在 .doc-kit/ 或 SessionSpec/ 目录。"""
    return (path / ".doc-kit").is_dir() or (path / "SessionSpec").is_dir()


def _load_index(project_root: Path) -> IndexManager | None:
    """加载项目索引，不存在则返回 None。"""
    index_path = project_root / ".doc-kit" / "index.json"
    if not index_path.exists():
        return None
    return IndexManager(index_path)


def safe_join(root: Path, sub_path: str) -> Path | None:
    """安全拼接路径，防止路径遍历逃逸。"""
    full = (root / sub_path).resolve()
    root_resolved = root.resolve()
    if not str(full).startswith(str(root_resolved)):
        return None
    return full


def _find_doc(project_root: Path, doc_path: str) -> Path | None:
    """在 ProjectSpec/ 中查找文档文件。

    doc_path 可带 ProjectSpec/ 前缀（如 "ProjectSpec/business-context.md"），
    也可不带（如 "business-context.md"），两种形式均可；
    可以是路径片段（module-Xxx/arch.md）或文件名（取首个匹配）。
    """
    docs_root = project_root / "ProjectSpec"
    if not docs_root.exists():
        return None

    # 统一去除 ProjectSpec/ 前缀（如有），避免 docs_root 拼接后双重路径
    search_path = doc_path
    if search_path.startswith("ProjectSpec/"):
        search_path = search_path[len("ProjectSpec/"):]

    target = safe_join(docs_root, search_path)
    if target and target.exists() and target.is_file():
        return target

    for f in sorted(docs_root.rglob(search_path)):
        if f.is_file():
            return f

    name = Path(search_path).name
    for f in sorted(docs_root.rglob("*.md")):
        if f.name == name or f.stem == Path(search_path).stem:
            return f

    return None


# ═══════════════════════════════════════════════════════════════
#  SessionSpec 路径与状态管理
# ═══════════════════════════════════════════════════════════════

_current_session_id: str | None = None


def _spec_path(project_root: Path, session_spec_id: str) -> Path:
    return project_root / "SessionSpec" / "active" / f"{session_spec_id}.spec.json"


def _archive_path(project_root: Path, session_spec_id: str) -> Path:
    return project_root / "SessionSpec" / "archive" / f"{session_spec_id}.spec.json"


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _detect_active_session(project_root: Path) -> str | None:
    active_dir = project_root / "SessionSpec" / "active"
    if not active_dir.is_dir():
        return None
    specs = sorted(active_dir.glob("*.spec.json"))
    if len(specs) == 0:
        return None
    if len(specs) == 1:
        return specs[0].stem.replace(".spec", "")
    raise ValueError(f"存在多个活跃 SessionSpec（{len(specs)} 个），违反了串行约束。")


def _read_spec_file(session_spec_id: str) -> dict | None:
    if _project_root is None:
        return None
    path = _spec_path(_project_root, session_spec_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_spec_file(spec: dict) -> None:
    if _project_root is None:
        raise RuntimeError("项目根目录未初始化")
    sid = spec["session_spec_id"]
    path = _spec_path(_project_root, sid)
    _ensure_dir(path)
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")


def _generate_spec_id(topic: str) -> str:
    today = datetime.now().strftime("%Y%m%d")
    clean = re.sub(r'[^a-zA-Z0-9\-]', '-', topic)
    clean = re.sub(r'-+', '-', clean).strip('-').lower()
    return f"{today}-{clean}"


# ═══════════════════════════════════════════════════════════════
#  MCP 服务器
# ═══════════════════════════════════════════════════════════════

mcp = FastMCP("doc-kit")
_project_root: Path | None = None


# ═══════════════════════════════════════════════════════════════
#  文档结构模型
# ═══════════════════════════════════════════════════════════════


@dataclass
class DocMeta:
    """文档元数据（不包含路径/名称等标识信息）。"""
    doc_type: str
    module: str
    level: str
    version: str
    status: str
    mtime: str

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "module": self.module,
            "level": self.level,
            "version": self.version,
            "status": self.status,
            "mtime": self.mtime,
        }


@dataclass
class DocNode:
    """文档节点 — 路径标识 + 元数据 + 标题 + 依赖。"""
    path: str
    name: str
    meta: DocMeta
    section: list[str]
    depends_on: list[str]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "section": self.section,
            "depends_on": self.depends_on,
            "level": self.meta.level,
        }


@dataclass
class Section:
    """文档段落 — 拍平层级段落。"""
    level: int
    heading: str
    reference: str
    content: str


class DocContent:
    """文档内容模型 — 通过 from_body() 构建，to_dict() 序列化，to_markdown() 回写。"""

    def __init__(
        self,
        path: str,
        meta: DocMeta,
        sections: list[Section],
        raw_frontmatter: dict | None = None,
        h1_heading: str = "",
    ) -> None:
        self.path = path
        self.meta = meta
        self.sections = sections
        self._raw_frontmatter = raw_frontmatter or {}
        self._h1 = h1_heading

    @classmethod
    def from_body(
        cls,
        path: str,
        meta: DocMeta,
        body: str,
        raw_frontmatter: dict | None = None,
    ) -> DocContent:
        h1 = ""
        lines = body.split("\n", 1)
        first_line = lines[0].strip() if lines else ""
        if first_line.startswith("# ") and not first_line.startswith("## "):
            h1 = first_line[2:].strip()
        sections = _parse_sections(body, path)
        return cls(path=path, meta=meta, sections=sections, raw_frontmatter=raw_frontmatter, h1_heading=h1)

    def get_section(self, reference: str) -> Section | None:
        for s in self.sections:
            if s.reference == reference:
                return s
        return None

    def find_by_heading(self, keyword: str) -> list[Section]:
        return [s for s in self.sections if keyword in s.heading]

    def insert_section(self, reference: str, heading: str, content: str, level_offset: int = 0) -> Section:
        """在reference段落后插入新段落。

        Args:
            reference: 锚点段落的reference
            heading: 新段落标题
            content: 正文
            level_offset: 相对于reference的层级偏移。
                          0（默认）= 同级插入
                          1 = 子级插入
        """
        target = self.get_section(reference)
        if target:
            level = target.level + level_offset
            target_idx = self.sections.index(target)
            insert_idx = target_idx + 1
            for i in range(target_idx + 1, len(self.sections)):
                if self.sections[i].level > target.level:
                    insert_idx = i + 1
                else:
                    break
            if level_offset == 0:
                # 同级插入：reference 取锚点的父路径 + 新标题
                last_hash = target.reference.rfind("#")
                if last_hash != -1:
                    new_ref = target.reference[:last_hash] + "#" + heading
                else:
                    new_ref = target.reference + "#" + heading
            else:
                # 子级插入：reference 取锚点 reference + 新标题
                new_ref = target.reference + "#" + heading
        else:
            level = 1
            insert_idx = len(self.sections)
            file_path = reference.split("#")[0]
            new_ref = file_path + "#" + heading

        new_section = Section(level=level, heading=heading, reference=new_ref, content=content)
        # 查重：同一 reference 不应重复插入
        if self.get_section(new_ref) is not None:
            raise ValueError(f"段落已存在: {new_ref}，不允许重复创建")
        self.sections.insert(insert_idx, new_section)
        return new_section

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "meta": self.meta.to_dict(),
            "sections": [asdict(s) for s in self.sections],
        }

    def to_markdown(self) -> str:
        body_parts: list[str] = []
        if self._h1:
            body_parts.append(f"# {self._h1}")
        for s in self.sections:
            heading_marker = "#" * (s.level + 1)
            block = f"{heading_marker} {s.heading}"
            if s.content:
                block += f"\n\n{s.content}"
            body_parts.append(block)
        body = "\n\n".join(body_parts)
        if not body.endswith("\n"):
            body += "\n"
        if self._raw_frontmatter:
            return FrontmatterParser.dump(self._raw_frontmatter, body)
        return body


class DocStructure:
    """完整的文档结构模型 — 构建后通过 to_dict() 输出 JSON 数据。"""

    def __init__(self, project_root: Path | None, entries: list[IndexEntry]) -> None:
        self._project_root = project_root
        self._entries = entries
        self.doc_map: dict[str, DocNode] = {}
        self._build()

    def _build(self) -> None:
        for entry in sorted(self._entries, key=lambda x: x.path):
            headings = _scan_level2_headings(self._project_root, entry.path)
            deps = _simplify_depends_on(entry.depends_on)
            meta = DocMeta(
                doc_type=entry.doc_type,
                module=entry.module,
                level=entry.level,
                version=entry.version,
                status=entry.status,
                mtime=entry.mtime,
            )
            self.doc_map[entry.path] = DocNode(
                path=entry.path,
                name=Path(entry.path).name,
                meta=meta,
                section=headings,
                depends_on=deps,
            )

    def find_by_module(self, module: str) -> list[DocNode]:
        return [n for n in self.doc_map.values() if n.meta.module == module]

    def find_by_doc_type(self, doc_type: str) -> list[DocNode]:
        return [n for n in self.doc_map.values() if n.meta.doc_type == doc_type]

    def find_by_level(self, level: str) -> list[DocNode]:
        return [n for n in self.doc_map.values() if n.meta.level == level]

    def get_dependency_chain(self, path: str) -> list[str]:
        seen: set[str] = set()
        chain: list[str] = []
        def _walk(p: str):
            if p in seen:
                return
            seen.add(p)
            node = self.doc_map.get(p)
            if node:
                for dep in node.depends_on:
                    if dep not in seen:
                        _walk(dep)
                        chain.append(dep)
        _walk(path)
        return chain

    def to_dict(self) -> dict:
        doc_map_dict = {k: v.to_dict() for k, v in self.doc_map.items()}
        tree = self._build_tree(doc_map_dict)
        return {"tree": tree, "doc_map": doc_map_dict}

    def _build_tree(self, doc_map_dict: dict[str, dict]) -> dict:
        root = {"name": "ProjectSpec", "type": "directory", "children": []}
        for path in sorted(doc_map_dict.keys()):
            parts = Path(path).parts
            if len(parts) < 2 or parts[0] != "ProjectSpec":
                continue
            current = root
            for i, part in enumerate(parts[1:], start=1):
                if i == len(parts) - 1:
                    info = doc_map_dict[path]
                    current["children"].append({"type": "file", "path": path, **info})
                else:
                    found = None
                    for child in current.get("children", []):
                        if child.get("type") == "directory" and child.get("name") == part:
                            found = child
                            break
                    if found is None:
                        found = {"name": part, "type": "directory", "children": []}
                        current["children"].append(found)
                    current = found
        return root


# ═══════════════════════════════════════════════════════════════
#  MCP 工具函数
# ═══════════════════════════════════════════════════════════════


@mcp.tool(name="read_doc", description="""
根据文件路径读取项目规格文档的完整内容，它是`add_section`和`update_section`的前置工具
""")
def read_doc(doc_path: str) -> str:
    """读取指定文档的完整内容，按段落层级拍平成 JSON。"""
    full_path = _find_doc(_project_root, doc_path)
    if not full_path:
        return json.dumps(
            {"success": False, "data": None, "suggestions": [f"未找到文档: {doc_path}，可用 doc_structure() 查看所有文档路径"]},
            indent=2, ensure_ascii=False,
        )
    try:
        raw_text = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return json.dumps(
            {"success": False, "data": None, "suggestions": [f"读取文档失败: {e}"]},
            indent=2, ensure_ascii=False,
        )
    try:
        meta_dict, body = FrontmatterParser.parse(raw_text)
    except Exception:
        meta_dict, body = {}, raw_text

    rel_path = str(full_path.relative_to(_project_root).as_posix()) if _project_root else str(full_path)

    # 从 index 中补充 mtime 和 depends_on
    index = _load_index(_project_root)
    index_depends_on: list[str] = []
    index_mtime = ""
    if index:
        entry = index.get_entry(rel_path)
        if entry:
            index_mtime = entry.mtime
            index_depends_on = _simplify_depends_on(entry.depends_on)

    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""),
        module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""),
        version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"),
        mtime=index_mtime,
    )
    content = DocContent.from_body(rel_path, doc_meta, body, raw_frontmatter=meta_dict)
    data = content.to_dict()
    data["depends_on"] = index_depends_on

    suggestions = [
        "如需修改某个段落，请调用 update_section(reference, content)",
        "如需新增段落，请调用 add_section(reference, heading, content)",
    ]
    if index_depends_on:
        dep_list = "、".join(index_depends_on)
        suggestions.append(
            f"该文档依赖: {dep_list}，可调用 read_doc() 查看依赖文档了解上下文"
        )

    result = {
        "success": True, "data": data,
        "suggestions": suggestions,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(name="update_section", description="""
路径加段落(reference)定位后写入正文内容(content)，并更新规格化文档，它适合作为文档更新的首选
""")
def update_section(reference: str, content: str) -> str:
    """更新文档中指定段落的正文内容，自动写回文件。"""
    if not _project_root:
        return json.dumps({"success": False, "data": None, "suggestions": ["项目根目录未初始化"]}, indent=2, ensure_ascii=False)
    file_rel = reference.split("#")[0]
    # 确保以 ProjectSpec/ 开头以便 safe_join 拼接（向后兼容裸路径）
    doc_rel = file_rel if file_rel.startswith("ProjectSpec/") else f"ProjectSpec/{file_rel}"
    safe_path = safe_join(_project_root, doc_rel)
    if safe_path is None:
        return json.dumps({"success": False, "data": None, "suggestions": [f"非法的路径: {file_rel}"]}, indent=2, ensure_ascii=False)
    full_path = safe_path
    if not full_path.exists():
        return json.dumps({"success": False, "data": None, "suggestions": [f"文件不存在: {file_rel}"]}, indent=2, ensure_ascii=False)
    try:
        raw_text = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return json.dumps({"success": False, "data": None, "suggestions": [f"读取文件失败: {e}"]}, indent=2, ensure_ascii=False)
    try:
        meta_dict, body = FrontmatterParser.parse(raw_text)
    except Exception:
        meta_dict, body = {}, raw_text
    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""), module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""), version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"), mtime="",
    )
    doc_content = DocContent.from_body(file_rel, doc_meta, body, raw_frontmatter=meta_dict)
    section = doc_content.get_section(reference)
    if section is None:
        return json.dumps({"success": False, "data": None, "suggestions": [f"未找到段落: {reference}，可用 read_doc() 查看所有段落 reference"]}, indent=2, ensure_ascii=False)
    old_content = section.content
    section.content = content
    try:
        new_markdown = doc_content.to_markdown()
        full_path.write_text(new_markdown, encoding="utf-8")
    except Exception as e:
        section.content = old_content
        return json.dumps({"success": False, "data": None, "suggestions": [f"写回文件失败: {e}"]}, indent=2, ensure_ascii=False)
    return json.dumps({"success": True, "suggestions": ["段落已更新，可通过 read_doc() 读取最新文档内容验证"]}, indent=2, ensure_ascii=False)


@mcp.tool(name="add_section", description="""
在文档中新增一个段落，写回文件。
    Args:
        reference: 锚点段落的 reference 路径
        heading: 新段落标题
        content: 正文
        level: 层级关系，"sibling"（默认）— 在锚点段落后追加同级段落；
               "child" — 在锚点段落内添加子段落
""")
def add_section(reference: str, heading: str, content: str = "", level: str = "sibling") -> str:
    """在文档中新增一个段落，自动写回文件。

    Args:
        reference: 锚点段落的 reference 路径
        heading: 新段落标题
        content: 正文（可选）
        level: 层级关系，"sibling"（默认）— 在锚点段落后追加同级段落；
               "child" — 在锚点段落内追加子段落
    """
    if not _project_root:
        return json.dumps({"success": False, "data": None, "suggestions": ["项目根目录未初始化"]}, indent=2, ensure_ascii=False)
    file_rel = reference.split("#")[0]
    # 确保以 ProjectSpec/ 开头以便 safe_join 拼接（向后兼容裸路径）
    doc_rel = file_rel if file_rel.startswith("ProjectSpec/") else f"ProjectSpec/{file_rel}"
    safe_path = safe_join(_project_root, doc_rel)
    if safe_path is None:
        return json.dumps({"success": False, "data": None, "suggestions": [f"非法的路径: {file_rel}"]}, indent=2, ensure_ascii=False)
    full_path = safe_path
    if not full_path.exists():
        return json.dumps({"success": False, "data": None, "suggestions": [f"文件不存在: {file_rel}"]}, indent=2, ensure_ascii=False)
    if not heading.strip():
        return json.dumps({"success": False, "data": None, "suggestions": ["heading 不能为空"]}, indent=2, ensure_ascii=False)
    try:
        raw_text = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return json.dumps({"success": False, "data": None, "suggestions": [f"读取文件失败: {e}"]}, indent=2, ensure_ascii=False)
    try:
        meta_dict, body = FrontmatterParser.parse(raw_text)
    except Exception:
        meta_dict, body = {}, raw_text
    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""), module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""), version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"), mtime="",
    )
    if level not in ("sibling", "child"):
        return json.dumps({"success": False, "data": None, "suggestions": ["level 参数仅支持 'sibling' 或 'child'"]}, indent=2, ensure_ascii=False)
    doc_content = DocContent.from_body(file_rel, doc_meta, body, raw_frontmatter=meta_dict)
    level_offset = 1 if level == "child" else 0
    try:
        new_section = doc_content.insert_section(reference, heading.strip(), content.strip(), level_offset=level_offset)
    except ValueError as e:
        return json.dumps({"success": False, "data": None, "suggestions": [str(e)]}, indent=2, ensure_ascii=False)
    try:
        new_markdown = doc_content.to_markdown()
        full_path.write_text(new_markdown, encoding="utf-8")
    except Exception as e:
        doc_content.sections = [s for s in doc_content.sections if s.reference != new_section.reference]
        return json.dumps({"success": False, "data": None, "suggestions": [f"写回文件失败: {e}"]}, indent=2, ensure_ascii=False)
    return json.dumps({"success": True, "suggestions": [f"段落「{heading}」已新增，可通过 read_doc() 读取最新文档内容验证"]}, indent=2, ensure_ascii=False)


def _parse_sections(body: str, file_path: str) -> list[dict]:
    """将 Markdown 正文按标题层级解析为拍平的段落列表。

    规则:
      - 每个标题节点只包含独立属于自身的正文内容（不含子标题的标题行和内容）
      - 某标题下无独立内容 → content = ""
    """
    import re
    lines = body.split("\n")
    heading_re = re.compile(r"^(#{2,6})\s+(.+)$")
    headings: list[tuple[int, str, int]] = []
    for i, line in enumerate(lines):
        m = heading_re.match(line)
        if m:
            level = len(m.group(1)) - 1
            h_text = m.group(2).strip()
            headings.append((level, h_text, i))
    if not headings:
        return [Section(level=0, heading="", reference=file_path, content=body.strip())]
    sections: list[Section] = []
    stack: list[tuple[int, str, int]] = []
    for level, heading, line_idx in headings:
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading, line_idx))
        next_boundary = len(lines)
        for h_level, _, h_line in headings:
            if h_line > line_idx and h_level <= level:
                next_boundary = h_line
                break
        child_end = None
        for h_level, _, h_line in headings:
            if h_line > line_idx and h_level == level + 1 and h_line < next_boundary:
                child_end = h_line
                break
        if child_end is not None:
            content_lines = lines[line_idx + 1 : child_end]
        else:
            content_lines = lines[line_idx + 1 : next_boundary]
        content = "\n".join(content_lines).strip()
        ref = file_path + "#" + "#".join(h[1] for h in stack)
        sections.append(Section(level=level, heading=heading, reference=ref, content=content))
    return sections


# ═══════════════════════════════════════════════════════════════
#  doc_structure
# ═══════════════════════════════════════════════════════════════


@mcp.tool(name="doc_structure", description="""
读取项目规格化文档的文档结构和大纲，作为文档速查表
""")
def doc_structure() -> str:
    """扫描 ProjectSpec/ 下所有文档，返回 JSON 格式的文档结构树和查找表。"""
    index = _load_index(_project_root)
    if not index:
        return json.dumps({"success": False, "data": None, "suggestions": ["项目索引不存在，请先运行初始化。"]}, indent=2, ensure_ascii=False)
    entries = index.list_entries()
    if not entries:
        return json.dumps({"success": True, "data": {"doc_map": {}}, "suggestions": []}, indent=2, ensure_ascii=False)
    structure = DocStructure(_project_root, entries)
    doc_map_dict = {k: v.to_dict() for k, v in structure.doc_map.items()}
    return json.dumps({
        "success": True, "data": {"doc_map": doc_map_dict},
        "suggestions": ["获取文档完整内容请调用 read_doc(doc_map中的path值)，如 read_doc(\"ProjectSpec/business-context.md\")"],
    }, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
#  SessionSpec 工具
# ═══════════════════════════════════════════════════════════════


@mcp.tool(name="spec_schema", description="""
会议模板及完整字段定义，包括类型、允许值、长度约束等
""")
def spec_schema() -> str:
    """返回 SpecStruct 的完整字段定义，包括类型、允许值、长度约束等。

    Skills 通过此工具获取数据结构模板，替代硬编码的 JSON 示例。
    返回 JSON 格式的字段元数据。"""
    if _project_root is None:
        return "错误: 项目根目录未初始化"
    metadata = get_schema_metadata()
    return json.dumps(metadata, indent=2, ensure_ascii=False)


@mcp.tool(name="spec_status", description="""
检查当前议题状态并给出下一步操作指引。
    状态路由：
    - 未初始化 → 自动创建 SessionSpec/ 目录，提示开启新议题
    - 无活跃议题 → 提示参考 spec-start 流程
    - 有活跃议题 → 提示调 spec_read() 读取
    - 有已关闭未归档 → 提示调 spec_archive() 归档
""")
def spec_status() -> str:
    """检查当前议题状态并给出下一步操作指引。

    状态路由：
    - 未初始化 → 自动创建 SessionSpec/ 目录，提示开启新议题
    - 无活跃议题 → 提示参考 spec-start 流程
    - 有活跃议题 → 提示调 spec_read() 读取
    - 有已关闭未归档 → 提示调 spec_archive() 归档"""
    if _project_root is None:
        return "错误: 项目根目录未初始化"

    # 自动初始化 SessionSpec 目录
    active_dir = _project_root / "SessionSpec" / "active"
    archive_dir = _project_root / "SessionSpec" / "archive"
    if not active_dir.is_dir() or not archive_dir.is_dir():
        active_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        return "✅ 项目已初始化，SessionSpec/ 目录已就绪。当前无活跃议题，可参考 spec-start 流程开启新议题。"

    try:
        sid = _detect_active_session(_project_root)
    except ValueError as e:
        return f"错误: {e}"

    if sid is None:
        return "当前没有活跃议题。可参考 spec-start 流程开启新议题。"

    spec = _read_spec_file(sid)
    if spec is None:
        return "当前会话已失效（文件不存在）。可参考 spec-start 流程开启新议题。"

    status = spec.get("status", "active")
    if status == "active":
        return f"当前有活跃议题：**{sid}**。请调用 spec_read() 读取完整内容。"
    if status == "closed":
        return f"当前有已关闭但未归档的议题：**{sid}**。请调用 spec_archive() 归档。"
    if status == "abandoned":
        return f"当前有已作废但未归档的议题：**{sid}**。请调用 spec_archive() 归档。"

    return f"当前文件状态异常: {sid} (status={status})"


@mcp.tool(name="spec_read", description="""
读取当前活跃议题的完整内容。返回完整会议记录
""")
def spec_read() -> str:
    """读取当前活跃议题的完整内容。

    返回完整的 SpecStruct JSON，包含 resolutions、pending_decisions、next_steps 等。
    如需了解各字段的定义和约束，请先调用 spec_schema()。"""
    if _project_root is None:
        return "错误: 项目根目录未初始化"
    try:
        sid = _detect_active_session(_project_root)
    except ValueError as e:
        return f"错误: {e}"
    if sid is None:
        return "当前没有活跃议题。可参考 spec-start 流程开启新议题。"

    spec = _read_spec_file(sid)
    if spec is None:
        return "错误: 文件不存在"
    return json.dumps(spec, indent=2, ensure_ascii=False)


@mcp.tool(name="spec_write", description="""
写入完整的议题数据（全量替换模式）。 传入完整的 SpecStruct JSON，建议先调 `spec_schema`或`spec_read` 获取信息
""")
def spec_write(spec_json: str) -> str:
    """写入完整的议题数据（全量替换模式）。

    传入完整的 SpecStruct JSON，服务端会校验字段合法性并执行业务规则检查：
    - 新创建：自动填充 project、created_at，默认为空决议/待定/计划
    - 更新：校验只读字段不可改、状态转移合法、关闭必填原因

    建议先调 spec_schema() 获取字段定义。"""
    global _current_session_id
    if _project_root is None:
        return "错误: 项目根目录未初始化"

    # 1) 解析 JSON
    if len(spec_json) > 1_000_000:
        return "错误: 数据量过大（超过 1MB），请精简后再试"
    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError as e:
        return f"错误: 不是合法 JSON: {e}"
    if not isinstance(data, dict):
        return "错误: 必须是一个 JSON 对象"

    # 必填字段检查
    for field in ("session_spec_id", "scenario", "status"):
        if field not in data:
            return f"错误: 缺少必填字段 '{field}'"

    sid = data["session_spec_id"]
    spec_path = _spec_path(_project_root, sid)
    existing = None
    if spec_path.exists():
        try:
            existing = json.loads(spec_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # 2) 新创建 vs 更新
    if existing is None:
        # ——— 新创建 ———
        # 检查 ProjectSpec/ 是否存在
        docs_root = _project_root / "ProjectSpec"
        if not docs_root.is_dir() or not list(docs_root.rglob("*.md")):
            return "错误: 未找到 ProjectSpec/ 或项目规格文档。请先创建项目规格文档后再开启议题。"
        try:
            recovered = _detect_active_session(_project_root)
            if recovered:
                return f"SessionSpec/active/ 下存在残留文件，请先处理后再创建新议题。"
        except ValueError as e:
            return f"检测活跃会话失败: {e}"
        if spec_path.exists():
            return f"错误: session_spec_id '{sid}' 已存在，请使用其他名称。"

        # 自动填充
        data.setdefault("project", _project_root.name)
        data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        data.setdefault("related_doc_types", [])
        data.setdefault("resolutions", [])
        data.setdefault("pending_decisions", [])
        data.setdefault("next_steps", [])
        data.setdefault("closed_at", None)
        data.setdefault("closed_reason", None)
    else:
        # ——— 更新 ———
        # 只读字段一致检查
        for fld in ("session_spec_id", "project", "created_at"):
            if fld in data and data[fld] != existing.get(fld):
                return (
                    f"错误: 字段 '{fld}' 不可修改（只读）。"
                    f" 已有值: '{existing.get(fld)}'，提交值: '{data[fld]}'"
                )

        # 状态转移校验
        old_status = existing.get("status", "active")
        new_status = data.get("status", old_status)
        if old_status != new_status:
            allowed = {"active": {"closed", "abandoned"}, "closed": set(), "abandoned": set()}
            if new_status not in allowed.get(old_status, set()):
                return (
                    f"错误: 状态 {old_status} → {new_status} 不合法。"
                    f" active 可转为 closed 或 abandoned；closed/abandoned 不可再变更。"
                )

        # 关闭/作废必须提供原因
        if new_status in ("closed", "abandoned") and not data.get("closed_reason"):
            labels = {"closed": "关闭", "abandoned": "作废"}
            return f"错误: status 为 {new_status} 时必须提供 {labels[new_status]}原因（closed_reason）。"

        # 从已有数据补充缺失字段（全量替换模式下 LLM 可能漏传）
        for fld in ("project", "created_at", "related_doc_types"):
            if fld not in data:
                data[fld] = existing.get(fld, "")

    # 3) Schema 校验
    errors = validate_spec(data)
    if errors:
        # 增强错误提示
        enhanced = []
        for e in errors:
            if "最小 150 字符" in e:
                enhanced.append(f"  - {e} — 建议补充决策理由、约束条件或影响范围。")
            elif "不在允许范围内" in e:
                enhanced.append(f"  - {e} — 请检查是否拼写错误。")
            else:
                enhanced.append(f"  - {e}")
        return "Schema 校验失败:\n" + "\n".join(enhanced)

    # 4) 写入
    _write_spec_file(data)
    _current_session_id = sid

    summary = render_summary(data)
    result = f"## ✅ 议题已保存\n\n{summary}"

    # 空决议覆盖警告（仅更新场景）
    if existing is not None:
        existing_res = existing.get("resolutions", [])
        new_res = data.get("resolutions", [])
        if existing_res and not new_res:
            result += f"\n\n⚠️ **注意**：提交的 resolutions 为空，但该议题原有 {len(existing_res)} 条决议。如果是有意清空请忽略此提示。"

    # 状态特定后续建议
    if data.get("status") == "closed":
        result += "\n\n**下一步建议**：调用 spec_archive() 归档已关闭的议题。"
    elif data.get("status") == "abandoned":
        result += "\n\n**下一步建议**：调用 spec_archive() 归档已作废的议题。"
    else:
        result += "\n\n**下一步建议**：调用 doc_structure() 查看文档结构，将决议写入对应文档。"
    return result


@mcp.tool(name="spec_archive", description="""
归档已关闭或已作废的议题（从 active 移至 archive）
""")
def spec_archive() -> str:
    """归档已关闭或已作废的议题（从 active 移至 archive）。"""
    if _project_root is None:
        return "错误: 项目根目录未初始化"
    try:
        sid = _detect_active_session(_project_root)
    except ValueError as e:
        return f"错误: {e}"
    if sid is None:
        return "当前没有可归档的议题（active 目录为空）。"
    spec = _read_spec_file(sid)
    if spec is None:
        return "错误: 文件不存在"
    status = spec.get("status")
    if status not in ("closed", "abandoned"):
        return f"议题 {sid} 状态为 {status}，只有 closed 或 abandoned 的议题才能归档。请先通过 spec_write() 设置正确状态。"
    src = _spec_path(_project_root, sid)
    dst = _archive_path(_project_root, sid)
    _ensure_dir(dst)
    src.replace(dst)
    global _current_session_id
    if _current_session_id == sid:
        _current_session_id = None
    return f"## ✅ 议题已归档\n\n**议题**: {sid}\n\n已移至 SessionSpec/archive/。"


# ═══════════════════════════════════════════════════════════════
#  Code Review 状态管理
# ═══════════════════════════════════════════════════════════════


def _review_state_path() -> Path | None:
    """返回 code-review-state.json 的路径，项目未初始化时返回 None。"""
    if _project_root is None:
        return None
    return _project_root / ".doc-kit" / "code-review-state.json"


REVIEW_STATE_DEFAULTS = {
    "last_reviewed_commit": None,
    "last_reviewed_at": None,
    "review_history": [],
}


def _read_review_state() -> dict:
    """读取 code-review-state.json，不存在则返回默认结构。"""
    path = _review_state_path()
    if path is None or not path.exists():
        return dict(REVIEW_STATE_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # 补全缺失字段
        for k, v in REVIEW_STATE_DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, OSError):
        return dict(REVIEW_STATE_DEFAULTS)


def _write_review_state(state: dict) -> None:
    """写入 code-review-state.json。"""
    path = _review_state_path()
    if path is None:
        raise RuntimeError("项目根目录未初始化")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


@mcp.tool(name="get_git_history", description="""
获取上一次 code review 的 git 提交锚点。 返回上次评审时的 commit hash，以及评审历史列表。 首次使用（无锚点）时返回空状态，提示从头开始评审。
""")
def get_git_history() -> str:
    """获取上一次 code review 的 git 提交锚点。

    返回上次评审时的 commit hash，以及评审历史列表。
    首次使用（无锚点）时返回空状态，提示从头开始评审。"""
    state = _read_review_state()
    commit = state.get("last_reviewed_commit")
    if not commit:
        return json.dumps({
            "success": True,
            "data": {"last_reviewed_commit": None, "last_reviewed_at": None, "review_history": []},
            "suggestions": ["尚无评审记录，将从头开始评审所有提交。"],
        }, indent=2, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "data": {
            "last_reviewed_commit": commit,
            "last_reviewed_at": state.get("last_reviewed_at"),
            "review_history": state.get("review_history", []),
        },
        "suggestions": [
            f"上次评审锚点: {commit}",
            f"可用 git log {commit}..HEAD --oneline 查看新增提交。",
        ],
    }, indent=2, ensure_ascii=False)


@mcp.tool(name="add_git_history", description="""
保存本次 code review 的 git 提交锚点。 Args: commit_hash: 本次评审到的 commit hash（完整 hash） session_spec_id: 关联的议题 ID（可选，便于追溯）
""")
def add_git_history(commit_hash: str, session_spec_id: str = "") -> str:
    """保存本次 code review 的 git 提交锚点。

    Args:
        commit_hash: 本次评审到的 commit hash（完整 hash）
        session_spec_id: 关联的议题 ID（可选，便于追溯）
    """
    if not commit_hash or not commit_hash.strip():
        return json.dumps({"success": False, "data": None, "suggestions": ["commit_hash 不能为空"]}, indent=2, ensure_ascii=False)

    commit_hash = commit_hash.strip()
    state = _read_review_state()

    # 更新锚点
    state["last_reviewed_commit"] = commit_hash
    state["last_reviewed_at"] = datetime.now(timezone.utc).isoformat()

    # 追加评审记录
    record = {
        "commit": commit_hash,
        "time": state["last_reviewed_at"],
    }
    if session_spec_id:
        record["session"] = session_spec_id
    state.setdefault("review_history", []).append(record)

    _write_review_state(state)

    return json.dumps({
        "success": True,
        "data": {"last_reviewed_commit": commit_hash, "last_reviewed_at": state["last_reviewed_at"]},
        "suggestions": [f"评审锚点已更新为 {commit_hash}。下次 code review 将从此 commit 开始。"],
    }, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
#  Code Review 报告管理
# ═══════════════════════════════════════════════════════════════


REVIEW_REPORT_SECTIONS = {
    "required": [
        ("# ", "报告标题"),
        ("## 基本信息", "基本信息段"),
        ("## 评审热点", "热点区域段"),
    ],
    "recommended": [
        ("## 深入确认项", "确认项段"),
        ("## 未深入比对项", "未深入比对项段"),
        ("## 后续动作", "后续动作段"),
    ],
}
"""评审报告必须/推荐的 Markdown 段落。"""


def _validate_review_report(markdown: str) -> list[str]:
    """校验评审报告的段落结构，返回缺失段落警告列表（空列表 = 通过）。"""
    warnings = []
    for heading, label in REVIEW_REPORT_SECTIONS["required"]:
        if heading not in markdown:
            warnings.append(f"缺少必填段落: {label} (以 '{heading}' 开头)")
    for heading, label in REVIEW_REPORT_SECTIONS["recommended"]:
        if heading not in markdown:
            warnings.append(f"建议补充段落: {label} (以 '{heading}' 开头)")
    return warnings


@mcp.tool(name="write_review_report", description="""
将代码评审报告写入文件。 报告需包含以下 Markdown 段落结构： # {报告标题} ## 基本信息 — 评审日期、关注范围、变更文件清单 ## 评审热点 — AI 标注的潜在偏差区域 ## 深入确认项 — 经用户确认的差异及其判定（推荐） ## 未深入比对项 — 标注但未深入处理的热点（推荐） ## 后续动作 — 基于评审结果的可选后续步骤（推荐） 服务端校验必填段落，缺失时返回警告但仍写入文件。
""")
def write_review_report(report_markdown: str) -> str:
    """将代码评审报告写入 ReviewSpec/ 目录。

    报告需包含以下 Markdown 段落结构：
      # {报告标题}
      ## 基本信息    — 评审日期、关注范围、变更文件清单
      ## 评审热点    — AI 标注的潜在偏差区域
      ## 深入确认项  — 经用户确认的差异及其判定（推荐）
      ## 未深入比对项 — 标注但未深入处理的热点（推荐）
      ## 后续动作    — 基于评审结果的可选后续步骤（推荐）

    服务端校验必填段落，缺失时返回警告但仍写入文件。
    文件名格式：code-review-{YYYYMMDD-HHMMSS}.md
    """
    if _project_root is None:
        return json.dumps({"success": False, "data": None, "suggestions": ["项目根目录未初始化"]}, indent=2, ensure_ascii=False)

    if not report_markdown or not report_markdown.strip():
        return json.dumps({"success": False, "data": None, "suggestions": ["report_markdown 不能为空"]}, indent=2, ensure_ascii=False)

    # 校验段落结构
    warnings = _validate_review_report(report_markdown)

    # 生成文件名
    now = datetime.now()
    filename = f"code-review-{now.strftime('%Y%m%d-%H%M%S')}.md"
    reviews_dir = _project_root / "ReviewSpec"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    file_path = reviews_dir / filename

    # 写入文件
    file_path.write_text(report_markdown.strip() + "\n", encoding="utf-8")

    result = {
        "success": True,
        "data": {
            "file": filename,
            "path": str(file_path.relative_to(_project_root)),
        },
        "suggestions": [],
    }

    if warnings:
        result["warnings"] = warnings
        result["suggestions"].append(f"报告已写入但格式有 {len(warnings)} 个提示，详见 warnings 字段")
    else:
        result["suggestions"].append("报告格式完整，已写入 ReviewSpec/")

    return json.dumps(result, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════


def _scan_level2_headings(project_root: Path | None, doc_rel_path: str) -> list[str]:
    if project_root is None:
        return []
    full_path = project_root / doc_rel_path
    if not full_path.exists():
        return []
    try:
        text = full_path.read_text(encoding="utf-8")
    except Exception:
        return []
    headings: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("###"):
            headings.append(stripped[3:].strip())
    return headings


def _simplify_depends_on(depends_on: list[dict]) -> list[str]:
    if depends_on is None:
        return []
    result: list[str] = []
    for dep in depends_on:
        if isinstance(dep, dict):
            doc_path = dep.get("doc", "")
            if doc_path:
                result.append(doc_path)
        elif isinstance(dep, str):
            result.append(dep)
    return result


def main():
    """MCP 服务器入口。"""
    global _project_root, _current_session_id
    cli_arg = sys.argv[1] if len(sys.argv) > 1 else None
    _project_root = find_project_root(cli_arg)
    index = _load_index(_project_root)
    if index is None:
        print(f"警告: {_project_root / '.doc-kit' / 'index.json'} 不存在。\n  请先在项目中运行初始化。MCP 服务器仍将启动，但部分工具将返回空结果。", file=sys.stderr)
    try:
        recovered = _detect_active_session(_project_root)
        if recovered:
            spec = _read_spec_file(recovered)
            if spec and spec.get("status") == "active":
                _current_session_id = recovered
    except ValueError as e:
        print(f"  警告: {e}", file=sys.stderr)
    session_status = f"active ({_current_session_id})" if _current_session_id else "idle"
    print(
        f"doc-kit MCP 服务器启动\n"
        f"  项目: {_project_root}\n"
        f"  索引: {_project_root / '.doc-kit' / 'index.json'}\n"
        f"  会话: {session_status}\n"
        f"  传输: stdio\n"
        f"  工具: read_doc, doc_structure, update_section, add_section, "
        f"spec_schema, spec_status, spec_read, spec_write, spec_archive, "
        f"get_git_history, add_git_history, write_review_report",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

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
    new_spec,
    apply_pause,
    close_spec,
    abort_spec,
    render_summary,
    generate_template,
)


# ═══════════════════════════════════════════════════════════════
#  项目根发现
# ═══════════════════════════════════════════════════════════════


def find_project_root(cli_arg: str | None = None) -> Path:
    """自动发现 doc-kit 项目根目录。

    优先级: CLI 参数 > 环境变量 > cwd 向上遍历找 .doc-kit/。
    返回 Path 或抛出 SystemExit。
    """
    if cli_arg:
        candidate = Path(cli_arg).resolve()
        if _is_valid_project(candidate):
            return candidate
        print(f"错误: 指定目录不存在或不是 doc-kit 项目: {cli_arg}", file=sys.stderr)
        sys.exit(1)

    env_val = os.environ.get("DOC_KIT_PROJECT_ROOT")
    if env_val:
        candidate = Path(env_val).resolve()
        if _is_valid_project(candidate):
            return candidate
        print(f"错误: DOC_KIT_PROJECT_ROOT 指向无效目录: {env_val}", file=sys.stderr)
        sys.exit(1)

    start = Path.cwd().resolve()
    for parent in [start] + list(start.parents):
        if _is_valid_project(parent):
            return parent

    print(
        "错误: 未找到 doc-kit 项目目录。\n"
        "  用法: python -m mcp_tools.server /path/to/project\n"
        "  或设置环境变量 DOC_KIT_PROJECT_ROOT\n"
        "  或从包含 .doc-kit/ 的目录下运行",
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

    doc_path 可以是完整路径或文件名（取首个匹配）。
    """
    docs_root = project_root / "ProjectSpec"
    if not docs_root.exists():
        return None

    target = safe_join(docs_root, doc_path)
    if target and target.exists() and target.is_file():
        return target

    for f in sorted(docs_root.rglob(doc_path)):
        if f.is_file():
            return f

    name = Path(doc_path).name
    for f in sorted(docs_root.rglob("*.md")):
        if f.name == name or f.stem == Path(doc_path).stem:
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


def _check_active() -> str | None:
    return _current_session_id


def _require_active() -> str:
    sid = _check_active()
    if sid is None:
        raise RuntimeError("当前没有活跃议题，请先调用 specStart。")
    return sid


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
            "doc_type": self.meta.doc_type,
            "module": self.meta.module,
            "level": self.meta.level,
            "version": self.meta.version,
            "status": self.meta.status,
            "mtime": self.meta.mtime,
            "section": self.section,
            "depends_on": self.depends_on,
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

    def insert_section(self, parent_reference: str, heading: str, content: str) -> Section:
        parent = self.get_section(parent_reference)
        if parent:
            level = parent.level + 1
            parent_idx = self.sections.index(parent)
            insert_idx = parent_idx + 1
            for i in range(parent_idx + 1, len(self.sections)):
                if self.sections[i].level > parent.level:
                    insert_idx = i + 1
                else:
                    break
            new_ref = parent.reference + "#" + heading
        else:
            level = 1
            insert_idx = len(self.sections)
            file_path = parent_reference.split("#")[0]
            new_ref = file_path + "#" + heading

        new_section = Section(level=level, heading=heading, reference=new_ref, content=content)
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
                block += f"\n{s.content}"
            body_parts.append(block)
        body = "\n\n".join(body_parts)
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


@mcp.tool()
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
    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""),
        module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""),
        version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"),
        mtime="",
    )
    rel_path = str(full_path.relative_to(_project_root).as_posix()) if _project_root else str(full_path)
    content = DocContent.from_body(rel_path, doc_meta, body, raw_frontmatter=meta_dict)
    data = content.to_dict()
    result = {
        "success": True, "data": data,
        "suggestions": [
            "如需修改某个段落，请调用 update_section(reference, content)",
            "如需新增段落，请调用 add_section(reference, heading, content)",
        ],
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def update_section(reference: str, content: str) -> str:
    """更新文档中指定段落的正文内容，自动写回文件。"""
    if not _project_root:
        return json.dumps({"success": False, "data": None, "suggestions": ["项目根目录未初始化"]}, indent=2, ensure_ascii=False)
    file_rel = reference.split("#")[0]
    safe_path = safe_join(_project_root, file_rel)
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


@mcp.tool()
def add_section(reference: str, heading: str, content: str = "") -> str:
    """在文档中新增一个段落，自动写回文件。"""
    if not _project_root:
        return json.dumps({"success": False, "data": None, "suggestions": ["项目根目录未初始化"]}, indent=2, ensure_ascii=False)
    file_rel = reference.split("#")[0]
    safe_path = safe_join(_project_root, file_rel)
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
    doc_content = DocContent.from_body(file_rel, doc_meta, body, raw_frontmatter=meta_dict)
    parent = doc_content.get_section(reference)
    if parent:
        new_ref = parent.reference + "#" + heading.strip()
    else:
        new_ref = file_rel + "#" + heading.strip()
    if doc_content.get_section(new_ref) is not None:
        return json.dumps({"success": False, "data": None, "suggestions": [f"段落已存在: {new_ref}，不允许重复创建"]}, indent=2, ensure_ascii=False)
    new_section = doc_content.insert_section(reference, heading.strip(), content.strip())
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


@mcp.tool()
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


@mcp.tool()
def spec_start(topic: str, scenario: str, session_spec_id: str | None = None) -> str:
    """开启新议题。"""
    global _current_session_id
    if _current_session_id is not None:
        return f"当前已有活跃议题 {_current_session_id}，请先 specClose 或 specAbort 后再开启新议题。"
    if _project_root is None:
        return "错误: 项目根目录未初始化"
    try:
        recovered = _detect_active_session(_project_root)
        if recovered:
            return f"SessionSpec/active/ 下存在残留文件 {recovered}.spec.json，请先 specClose、specAbort 或 specArchive 处理后重试。"
    except ValueError as e:
        return f"检测活跃会话失败: {e}"
    sid = session_spec_id or _generate_spec_id(topic)
    if _spec_path(_project_root, sid).exists():
        return f"错误: session_spec_id '{sid}' 已存在，请手动指定其他名称。"
    spec = new_spec(session_spec_id=sid, project=_project_root.name, scenario=scenario, created_at=datetime.now(timezone.utc).isoformat())
    errors = validate_spec(spec)
    if errors:
        return "Schema 校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
    _write_spec_file(spec)
    _current_session_id = sid
    return f"## ✅ 议题已创建\n\n{render_summary(spec)}\n\n可以开始讨论了。"


@mcp.tool()
def spec_status() -> str:
    """查看当前议题状态。"""
    global _current_session_id
    sid = _check_active()
    if sid is None:
        if _project_root is not None:
            try:
                recovered = _detect_active_session(_project_root)
                if recovered:
                    spec = _read_spec_file(recovered)
                    if spec and spec.get("status") == "active":
                        _current_session_id = recovered
                        return render_summary(spec)
            except ValueError as e:
                return f"检测活跃会话失败: {e}"
        return "当前没有活跃议题。如需开启新议题，请调用 specStart。"
    spec = _read_spec_file(sid)
    if spec is None:
        _current_session_id = None
        return "当前会话已失效（文件不存在），请调用 specStart 开启新议题。"
    return render_summary(spec)


@mcp.tool()
def spec_pause(spec_json: str) -> str:
    """保存当前议题进度，不改变状态。"""
    sid = _require_active()
    spec = _read_spec_file(sid)
    if spec is None:
        _current_session_id = None
        return f"错误: 会话 {sid} 的文件已不存在"
    if len(spec_json) > 1_000_000:
        return "错误: spec_json 数据量过大（超过 1MB），请精简后再试"
    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError as e:
        return f"错误: spec_json 不是合法 JSON: {e}"
    if not isinstance(data, dict):
        return "错误: spec_json 必须是一个 JSON 对象"
    errors = apply_pause(spec, data)
    if errors:
        return "数据处理错误:\n" + "\n".join(f"  - {e}" for e in errors)
    errors = validate_spec(spec)
    if errors:
        return "Schema 校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
    _write_spec_file(spec)
    return f"## ✅ 进度已保存\n\n{render_summary(spec)}\n\n**下一步建议**：调用 doc_structure() 查看 ProjectSpec/ 文档结构，根据文档 section 将决议内容写入对应段落。写入时可使用 read_doc() 查看目标文档当前内容，再调 update_section() 或 add_section() 操作。"


@mcp.tool()
def spec_close(reason: str, force: bool = False) -> str:
    """关闭当前议题。"""
    global _current_session_id
    sid = _require_active()
    spec = _read_spec_file(sid)
    if spec is None:
        _current_session_id = None
        return f"错误: 会话 {sid} 的文件已不存在"
    pending = spec.get("pending_decisions", [])
    unresolved = [p for p in pending if p.get("status") != "resolved"]
    if unresolved and not force:
        topics = "\n".join(f"  - {p['topic']} [{p['status']}]: {p['note']}" for p in unresolved)
        return f"⚠️ 仍有 {len(unresolved)} 项待定决议未解决：\n{topics}\n\n建议先讨论解决后再关闭。如需强行关闭，请再次调用 specClose(reason='{reason}', force=True)，未解决项将被自动清除。"
    if force and unresolved:
        spec["pending_decisions"] = [p for p in pending if p.get("status") == "resolved"]
    close_spec(spec, reason, datetime.now(timezone.utc).isoformat())
    errors = validate_spec(spec)
    if errors:
        return "Schema 校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
    _write_spec_file(spec)
    _current_session_id = None
    cleared_note = ""
    if force and unresolved:
        cleared_note = f"\n（已自动清除 {len(unresolved)} 项未解决的待定决议）"
    doc_sync_note = "\n\n**⚠️ 请确认**：关闭前应先调 doc_structure() 查看文档结构，确认所有决议已通过 update_section() / add_section() 同步到 ProjectSpec/ 对应文档中。未同步的决议不会自动写入文档。"
    return f"## ✅ 议题已关闭\n\n**议题**: {sid}\n**关闭原因**: {reason}{cleared_note}{doc_sync_note}\n\n{render_summary(spec)}\n\n如需开启新议题，请调用 specStart。"


@mcp.tool()
def spec_abort(reason: str, confirm: bool = False) -> str:
    """作废当前议题。"""
    global _current_session_id
    if not confirm:
        return f"⚠️ 作废不可撤销。请确认要将议题 {_current_session_id} 作废（原因: {reason}）。如确认，请再次调用 specAbort 并设置 confirm=True。"
    sid = _require_active()
    spec = _read_spec_file(sid)
    if spec is None:
        _current_session_id = None
        return f"错误: 会话 {sid} 的文件已不存在"
    abort_spec(spec, reason, datetime.now(timezone.utc).isoformat())
    errors = validate_spec(spec)
    if errors:
        return "Schema 校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
    _write_spec_file(spec)
    src = _spec_path(_project_root, sid)
    dst = _archive_path(_project_root, sid)
    _ensure_dir(dst)
    src.replace(dst)
    _current_session_id = None
    return f"## 🚫 议题已作废并归档\n\n**议题**: {sid}\n**作废原因**: {reason}\n\n如需开启新议题，请调用 specStart。"


@mcp.tool()
def spec_archive() -> str:
    """归档已关闭的议题（从 active 移至 archive）。仅当议题状态为 closed 时有效。"""
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
    if status != "closed":
        return f"议题 {sid} 状态为 {status}，只有 closed 的议题才能归档。请先调用 specClose。"
    src = _spec_path(_project_root, sid)
    dst = _archive_path(_project_root, sid)
    _ensure_dir(dst)
    src.replace(dst)
    global _current_session_id
    if _current_session_id == sid:
        _current_session_id = None
    return f"## ✅ 议题已归档\n\n**议题**: {sid}\n\n已移至 SessionSpec/archive/。"


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
    template_path = _project_root / ".reasonix" / "spec-template.json"
    try:
        template = generate_template()
        template_path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"  警告: spec-template.json 写入失败: {e}", file=sys.stderr)
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
        f"spec_start, spec_status, spec_pause, spec_close, spec_abort, spec_archive",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

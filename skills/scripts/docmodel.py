"""Document models for the skills CLI — 文档模型与 section 解析逻辑。

DocMeta / DocNode / Section / DocContent / DocStructure plus the section
parsing and path-resolution helpers. Pure logic, no MCP dependency.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from frontmatter import FrontmatterParser
from index import IndexEntry


def safe_join(root: Path, sub_path: str) -> Path | None:
    """Safely join a sub path onto root, rejecting path traversal escapes.

    按**路径段**判定归属，而不是裸字符串前缀：`<root>-evil/x.md` 与 `<root>`
    前缀相同，但它不是 root 的子路径，裸 `startswith` 会放行。该函数同时是
    读与写的边界（`doc read` 的候选兜底、`doc *-section` 的写目标、spec 的
    目标文档路径校验），放行即等于把写入引到 ProjectSpec/ 之外。
    """
    full = (root / sub_path).resolve()
    root_resolved = root.resolve()
    if full != root_resolved and root_resolved not in full.parents:
        return None
    return full


#: 文档解析命中方式（对外暴露为 ``data.resolved_via``，让调用方判断"这次是不是靠猜"）
RESOLVED_VIA_EXACT = "exact"
RESOLVED_VIA_SUFFIX_ADDED = "suffix_added"
RESOLVED_VIA_PATH_SUFFIX = "path_suffix"
RESOLVED_VIA_BASENAME = "basename"


@dataclass
class DocResolution:
    """一次 ``doc read <path>`` 的解析结果。

    三态互斥，由 ``cmd_doc_read`` 翻译成不同错误码：

    - ``path`` 非空 → 命中，``via`` 说明命中方式；
    - ``candidates`` 非空 → 多候选，**绝不静默取首个**（R1-b）；
    - 两者皆空 → 无候选（``invalid`` / ``is_dir`` 给出更具体的失败原因）。
    """
    path: Path | None = None
    via: str = ""
    candidates: list[Path] = field(default_factory=list)
    invalid: bool = False
    is_dir: bool = False


def _md_files_under(docs_root: Path) -> list[Path]:
    return [f for f in docs_root.rglob("*.md") if f.is_file()]


def resolve_doc(project_root: Path, doc_path: str) -> DocResolution:
    """把调用方给的路径片段解析成 ProjectSpec/ 下的唯一文档。

    解析顺序（R1-a，前一步命中即返回）：

    1. ``exact``        —— 原样路径精确命中；
    2. ``suffix_added`` —— 未带 ``.md`` 时补后缀再精确命中（本次修复的核心：
       以前缺这一步，合法的"省略后缀"写法必然掉进按文件名兜底）；
    3. ``path_suffix``  —— 含 ``/`` 的片段按**路径段**后缀匹配唯一文件；
    4. ``basename``     —— 裸文件名，仅当全库同名唯一时兜底。

    任何一步出现多个候选一律返回候选清单，由调用方报 ``doc_read.ambiguous``。
    **丢弃目录信息去猜**（旧实现的第 3 步）是本次缺陷的根因，已彻底移除：
    含 ``/`` 的片段在第 3 步之后不会退化到 ``basename``，否则
    ``module-context/architecture`` 会再次静默解析到别的模块。
    """
    docs_root = project_root / "ProjectSpec"
    if not docs_root.is_dir():
        return DocResolution()

    search = (doc_path or "").strip().replace("\\", "/")
    if search.startswith("ProjectSpec/"):
        search = search[len("ProjectSpec/"):]
    search = search.lstrip("/")
    if search.startswith("./"):
        search = search[2:]
    if not search or search.endswith("/"):
        return DocResolution(invalid=not search, is_dir=bool(search))

    target = safe_join(docs_root, search)
    if target is None:
        # 路径逃出 ProjectSpec/：不再走任何兜底（旧实现会靠 basename 捞回来）
        return DocResolution(invalid=True)
    if target.is_file():
        return DocResolution(path=target, via=RESOLVED_VIA_EXACT)
    if target.is_dir():
        # 目录不是文档。显式报错，避免后缀匹配把整个目录的子文档匹配成"多候选"
        return DocResolution(is_dir=True)

    has_suffix = search.endswith(".md")
    if not has_suffix:
        with_suffix = safe_join(docs_root, search + ".md")
        if with_suffix is not None and with_suffix.is_file():
            return DocResolution(path=with_suffix, via=RESOLVED_VIA_SUFFIX_ADDED)

    needle = (search[:-3] if has_suffix else search).strip("/")
    if not needle:
        return DocResolution()

    files = sorted(_md_files_under(docs_root))
    if "/" in needle:
        # 路径段对齐的后缀匹配：「/a/b」不会误中「x/a/b-notes」
        marker = "/" + needle
        candidates = [
            f for f in files
            if ("/" + f.relative_to(docs_root).as_posix()[:-3]).endswith(marker)
        ]
        via = RESOLVED_VIA_PATH_SUFFIX
    else:
        candidates = [f for f in files if f.name == needle + ".md"]
        via = RESOLVED_VIA_BASENAME

    if len(candidates) == 1:
        return DocResolution(path=candidates[0], via=via)
    if candidates:
        return DocResolution(candidates=candidates)
    return DocResolution()


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


def _simplify_depends_on(depends_on: list[dict] | None) -> list[str]:
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


@dataclass
class DocMeta:
    """Document metadata (excluding path/name identifiers)."""
    doc_type: str
    module: str
    level: str
    version: str
    status: str

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "module": self.module,
            "level": self.level,
            "version": self.version,
            "status": self.status,
        }


@dataclass
class DocNode:
    """Document node — path + metadata + title + dependencies."""
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
    """Document section — flattened heading levels."""
    level: int
    heading: str
    reference: str
    content: str


class DocContent:
    """Document content model — built via from_body(), serialized via
    to_dict() / to_markdown()."""

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
        """Insert a new section after the reference section.

        Args:
            reference: anchor section reference
            heading: new section heading
            content: body text
            level_offset: 0 (default) = sibling, 1 = child
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
                # Sibling insert: reference = anchor parent path + new heading
                last_hash = target.reference.rfind("#")
                if last_hash != -1:
                    new_ref = target.reference[:last_hash] + "#" + heading
                else:
                    new_ref = target.reference + "#" + heading
            else:
                # Child insert: reference = anchor reference + new heading
                new_ref = target.reference + "#" + heading
        else:
            level = 1
            insert_idx = len(self.sections)
            file_path = reference.split("#")[0]
            new_ref = file_path + "#" + heading

        new_section = Section(level=level, heading=heading, reference=new_ref, content=content)
        if self.get_section(new_ref) is not None:
            raise ValueError(f"段落已存在: {new_ref}，不允许重复创建")
        self.sections.insert(insert_idx, new_section)
        return new_section

    def remove_section(self, reference: str) -> list[Section]:
        """Remove a section and all of its descendant sections.

        Returns the list of removed Section objects (in document order).
        Raises ValueError if the reference does not exist.
        """
        target = self.get_section(reference)
        if target is None:
            raise ValueError(f"段落不存在: {reference}")
        idx = self.sections.index(target)
        end = idx + 1
        while end < len(self.sections) and self.sections[end].level > target.level:
            end += 1
        removed = self.sections[idx:end]
        del self.sections[idx:end]
        return removed

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


def _parse_sections(body: str, file_path: str) -> list[Section]:
    """Parse Markdown body into a flattened section list.

    Rules:
      - Each heading node owns only its own body text (not children's).
      - A heading with no own content gets content = "".
    """
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
            content_lines = lines[line_idx + 1: child_end]
        else:
            content_lines = lines[line_idx + 1: next_boundary]
        content = "\n".join(content_lines).strip()
        ref = file_path + "#" + "#".join(h[1] for h in stack)
        sections.append(Section(level=level, heading=heading, reference=ref, content=content))
    return sections


class DocStructure:
    """Full document structure model — built from index entries."""

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

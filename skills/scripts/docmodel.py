"""Document models for the skills CLI — 文档模型与 section 解析逻辑。

DocMeta / DocNode / Section / DocContent / DocStructure plus the section
parsing and path-resolution helpers. Pure logic, no MCP dependency.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from frontmatter import FrontmatterParser
from index import IndexEntry


def safe_join(root: Path, sub_path: str) -> Path | None:
    """Safely join a sub path onto root, rejecting path traversal escapes."""
    full = (root / sub_path).resolve()
    root_resolved = root.resolve()
    if not str(full).startswith(str(root_resolved)):
        return None
    return full


def _find_doc(project_root: Path, doc_path: str) -> Path | None:
    """Locate a document under ProjectSpec/.

    doc_path may carry a "ProjectSpec/" prefix or not; it may be a path
    fragment (module-Xxx/arch.md) or a bare file name (first match wins).
    """
    docs_root = project_root / "ProjectSpec"
    if not docs_root.exists():
        return None

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

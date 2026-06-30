"""mcp_server 纯函数单元测试。

测试目标（无文件IO）：
  - safe_join              —— 路径安全拼接
  - _simplify_depends_on   —— 依赖路径简化
  - _parse_sections        —— Markdown → Section 列表
  - _generate_spec_id      —— 议题 ID 生成
  - DocMeta / DocNode      —— 数据类序列化
  - DocContent             —— 查询 / 变更 / 序列化
  - DocStructure           —— 查询方法
"""

import pytest
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
#  safe_join
# ═══════════════════════════════════════════════════════════════

class TestSafeJoin:
    """safe_join(root: Path, sub_path: str) -> Path | None"""

    def test_normal_join(self):
        from skill.mcp.mcp_server import safe_join
        root = Path.cwd()
        result = safe_join(root, "tests/conftest.py")
        assert result is not None
        assert result.exists()

    def test_traversal_blocked(self):
        from skill.mcp.mcp_server import safe_join
        root = Path.cwd()
        result = safe_join(root, "../etc/passwd")
        assert result is None

    def test_deep_traversal_blocked(self):
        from skill.mcp.mcp_server import safe_join
        root = Path.cwd()
        result = safe_join(root, "docs/../../etc/passwd")
        assert result is None

    def test_same_directory(self):
        from skill.mcp.mcp_server import safe_join
        root = Path.cwd()
        result = safe_join(root, ".")
        assert result is not None
        assert result == root.resolve()

    def test_subdirectory(self):
        from skill.mcp.mcp_server import safe_join
        root = Path.cwd()
        result = safe_join(root, "tests")
        assert result is not None
        assert str(result).endswith("tests")


# ═══════════════════════════════════════════════════════════════
#  _simplify_depends_on
# ═══════════════════════════════════════════════════════════════

class TestSimplifyDependsOn:
    """_simplify_depends_on(depends_on: list[dict]) -> list[str]"""

    def test_dict_items(self):
        from skill.mcp.mcp_server import _simplify_depends_on
        deps = [
            {"doc": "a.md", "module": "m1", "version": "1.0"},
            {"doc": "b.md", "module": "m2", "version": "2.0"},
        ]
        result = _simplify_depends_on(deps)
        assert result == ["a.md", "b.md"]

    def test_empty_list(self):
        from skill.mcp.mcp_server import _simplify_depends_on
        assert _simplify_depends_on([]) == []

    def test_missing_doc_key(self):
        from skill.mcp.mcp_server import _simplify_depends_on
        deps = [{"module": "m1"}, {"doc": "b.md"}]
        result = _simplify_depends_on(deps)
        assert result == ["b.md"]


# ═══════════════════════════════════════════════════════════════
#  _generate_spec_id
# ═══════════════════════════════════════════════════════════════

class TestGenerateSpecId:
    """_generate_spec_id(topic: str) -> str"""

    def test_basic_topic(self):
        from skill.mcp.mcp_server import _generate_spec_id
        sid = _generate_spec_id("tech-ref")
        # 格式: {YYYYMMDD}-{topic}
        parts = sid.split("-", 1)
        assert len(parts[0]) == 8  # 日期部分
        assert parts[0].isdigit()
        assert parts[1] == "tech-ref"

    def test_special_chars_replaced(self):
        from skill.mcp.mcp_server import _generate_spec_id
        sid = _generate_spec_id("Feature/Design v2!")
        parts = sid.split("-", 1)
        assert "/" not in parts[1]
        assert "!" not in parts[1]


# ═══════════════════════════════════════════════════════════════
#  DocMeta
# ═══════════════════════════════════════════════════════════════

class TestDocMeta:
    """DocMeta dataclass + to_dict()"""

    def test_to_dict(self):
        from skill.mcp.mcp_server import DocMeta
        meta = DocMeta(doc_type="arch", module="core", level="top",
                       version="1.0", status="active", mtime="2026-01-01")
        d = meta.to_dict()
        assert d["doc_type"] == "arch"
        assert d["module"] == "core"
        assert d["level"] == "top"
        assert d["version"] == "1.0"
        assert d["status"] == "active"
        assert d["mtime"] == "2026-01-01"


# ═══════════════════════════════════════════════════════════════
#  DocNode
# ═══════════════════════════════════════════════════════════════

class TestDocNode:
    """DocNode dataclass + to_dict()"""

    def test_to_dict(self):
        from skill.mcp.mcp_server import DocMeta, DocNode
        meta = DocMeta("arch", "core", "top", "1.0", "active", "")
        node = DocNode(path="p.md", name="p.md", meta=meta,
                       section=["H1", "H2"], depends_on=["a.md"])
        d = node.to_dict()
        assert d["name"] == "p.md"
        assert d["doc_type"] == "arch"
        assert d["module"] == "core"
        assert d["section"] == ["H1", "H2"]
        assert d["depends_on"] == ["a.md"]


# ═══════════════════════════════════════════════════════════════
#  Section + DocContent
# ═══════════════════════════════════════════════════════════════

class TestDocContent:
    """DocContent — from_body, get_section, find_by_heading, insert_section, to_dict, to_markdown"""

    @pytest.fixture
    def content(self):
        from skill.mcp.mcp_server import DocMeta, DocContent
        meta = DocMeta("test", "m", "top", "1.0", "active", "")
        body = "# Title\n\n## H1\ncontent1\n\n### H2\ncontent2\n\n## H3\ncontent3"
        return DocContent.from_body("doc.md", meta, body)

    def test_get_section_found(self, content):
        section = content.get_section("doc.md#H1")
        assert section is not None
        assert section.heading == "H1"
        assert "content1" in section.content

    def test_get_section_nested(self, content):
        section = content.get_section("doc.md#H1#H2")
        assert section is not None
        assert section.heading == "H2"
        assert "content2" in section.content

    def test_get_section_not_found(self, content):
        assert content.get_section("doc.md#NONEXIST") is None

    def test_find_by_heading(self, content):
        results = content.find_by_heading("H")
        assert len(results) == 3  # H1, H2, H3 all match

    def test_find_by_heading_partial(self, content):
        results = content.find_by_heading("H1")
        assert len(results) == 1
        assert results[0].heading == "H1"

    def test_insert_section_under_parent(self, content):
        new_s = content.insert_section("doc.md#H1", "H1sub", "sub content")
        assert new_s.level == 2
        assert new_s.reference == "doc.md#H1#H1sub"
        # 应在 H1 的子段落后（H2 之前）
        h1_idx = content.sections.index(content.get_section("doc.md#H1"))
        new_idx = content.sections.index(new_s)
        assert new_idx > h1_idx

    def test_insert_section_no_parent(self, content):
        new_s = content.insert_section("doc.md#NONEXIST", "NewTop", "new content")
        assert new_s.level == 1
        assert new_s.reference == "doc.md#NewTop"
        # 应追加到末尾
        assert content.sections[-1] == new_s

    def test_to_dict_structure(self, content):
        d = content.to_dict()
        assert "path" in d
        assert "meta" in d
        assert "sections" in d
        assert d["path"] == "doc.md"
        assert len(d["sections"]) == 3

    def test_to_markdown_reconstruction(self, content):
        md = content.to_markdown()
        assert "# Title" in md
        assert "## H1" in md
        assert "content1" in md
        assert "### H2" in md
        assert "content2" in md
        assert "## H3" in md
        assert "content3" in md

    def test_to_markdown_with_frontmatter(self, content):
        """给 DocContent 设置 raw_frontmatter 后 to_markdown 应包含 frontmatter"""
        content._raw_frontmatter = {"doc_type": "test"}
        md = content.to_markdown()
        assert "---" in md
        assert "doc_type: test" in md


# ═══════════════════════════════════════════════════════════════
#  _parse_sections
# ═══════════════════════════════════════════════════════════════

class TestParseSections:
    """_parse_sections(body: str, file_path: str) -> list[Section]"""

    def test_empty_body(self):
        from skill.mcp.mcp_server import _parse_sections
        result = _parse_sections("", "doc.md")
        assert len(result) == 1
        assert result[0].level == 0

    def test_basic_headings(self):
        from skill.mcp.mcp_server import _parse_sections
        body = "## A\na-content\n\n## B\nb-content"
        result = _parse_sections(body, "doc.md")
        assert len(result) == 2
        assert result[0].heading == "A"
        assert "a-content" in result[0].content
        assert result[1].heading == "B"
        assert "b-content" in result[1].content

    def test_nested_exclusive_content(self):
        """父段落不包含子段落内容"""
        from skill.mcp.mcp_server import _parse_sections
        body = "## Parent\nparent-only\n\n### Child\nchild-only\n"
        result = _parse_sections(body, "doc.md")
        assert len(result) == 2
        assert result[0].heading == "Parent"
        assert "parent-only" in result[0].content
        assert "child-only" not in result[0].content
        assert result[1].heading == "Child"
        assert "child-only" in result[1].content

    def test_reference_chain(self):
        from skill.mcp.mcp_server import _parse_sections
        body = "## L1\nt1\n### L2\nt2\n#### L3\nt3"
        result = _parse_sections(body, "f.md")
        assert result[0].reference == "f.md#L1"
        assert result[1].reference == "f.md#L1#L2"
        assert result[2].reference == "f.md#L1#L2#L3"

    def test_sibling_reset(self):
        """同级别标题后 reference 链正确重置，B 不应包含 A 的前缀"""
        from skill.mcp.mcp_server import _parse_sections
        body = "## A\na\n### A1\na1\n## B\nb"
        result = _parse_sections(body, "f.md")
        assert result[0].reference == "f.md#A"      # A
        assert result[1].reference == "f.md#A#A1"   # A1
        assert result[2].reference == "f.md#B"      # B（不包含 A）

    def test_empty_content_preserved(self):
        """无独立内容的段落 content = \"\""""
        from skill.mcp.mcp_server import _parse_sections
        body = "## H1\n### H2\nh2-only\n"
        result = _parse_sections(body, "f.md")
        assert result[0].heading == "H1"
        assert result[0].content == ""  # 无直接内容
        assert result[1].content == "h2-only"


# ═══════════════════════════════════════════════════════════════
#  DocStructure
# ═══════════════════════════════════════════════════════════════

class TestDocStructure:
    """DocStructure — find_by_module/find_by_doc_type/find_by_level/get_dependency_chain"""

    @pytest.fixture
    def structure(self):
        from skill.mcp.mcp_server import DocMeta, DocNode, DocStructure
        # 模拟 DocStructure，直接构造 doc_map
        import types
        ds = object.__new__(DocStructure)
        ds._project_root = None
        ds._entries = []
        ds.doc_map = {}
        for p, dt, mod, lvl in [
            ("a.md", "arch", "core", "top"),
            ("b.md", "domain_model", "core", "top"),
            ("c.md", "arch", "modX", "module"),
            ("d.md", "feature_design", "modX", "feature"),
        ]:
            meta = DocMeta(dt, mod, lvl, "1.0", "active", "")
            ds.doc_map[p] = DocNode(p, Path(p).name, meta, [], [])
        return ds

    def test_find_by_module(self, structure):
        results = structure.find_by_module("core")
        assert len(results) == 2

    def test_find_by_doc_type(self, structure):
        results = structure.find_by_doc_type("arch")
        assert len(results) == 2

    def test_find_by_level(self, structure):
        results = structure.find_by_level("top")
        assert len(results) == 2

    def test_get_dependency_chain_simple(self, structure):
        from skill.mcp.mcp_server import DocMeta, DocNode
        meta = DocMeta("arch", "core", "top", "1.0", "active", "")
        structure.doc_map["e.md"] = DocNode(
            "e.md", "e.md", meta, [], ["a.md", "b.md"])
        chain = structure.get_dependency_chain("e.md")
        assert "a.md" in chain
        assert "b.md" in chain

    def test_get_dependency_chain_no_deps(self, structure):
        chain = structure.get_dependency_chain("a.md")
        assert chain == []

    def test_get_dependency_chain_dedup(self, structure):
        """共享依赖不应重复"""
        from skill.mcp.mcp_server import DocMeta, DocNode
        meta = DocMeta("arch", "core", "top", "1.0", "active", "")
        # e -> a, b; f -> a (共享 a)
        structure.doc_map["e.md"] = DocNode("e.md", "e.md", meta, [], ["a.md"])
        structure.doc_map["f.md"] = DocNode("f.md", "f.md", meta, [], ["a.md"])
        # f 依赖 e, e 依赖 a → a 应只出现一次
        structure.doc_map["g.md"] = DocNode("g.md", "g.md", meta, [], ["f.md", "e.md"])
        chain = structure.get_dependency_chain("g.md")
        assert len(chain) == len(set(chain))  # 无重复

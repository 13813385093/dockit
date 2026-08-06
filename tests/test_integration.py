"""文件系统集成测试 — 验证 MCP 工具读写安全。

测试策略：每个测试在 tmp_path 创建的隔离目录中操作，互不干扰。
使用 cli_env fixture 重置 MCP 全局状态指向临时项目。
"""

import json

from conftest import make_md, make_index, make_spec


# ═══════════════════════════════════════════════════════════════
#  文件读取正确性
# ═══════════════════════════════════════════════════════════════

class TestReadDoc:
    """read_doc 不会读错文件"""

    def test_read_by_full_path(self, tmp_project, cli_env):
        """按全路径读取应返回正确内容"""
        make_md(tmp_project, "ProjectSpec/a.md",
                "---\ndoc_type: test\n---\n# A\n\n## Section\ncontent-a")
        result = json.loads(cli_env.read_doc("a.md"))
        assert result["success"] is True
        # path 带 ProjectSpec/ 前缀，与 doc_structure 的 doc_map key 一致
        assert result["data"]["path"] == "ProjectSpec/a.md"
        sections = result["data"]["sections"]
        assert any(s["heading"] == "Section" and "content-a" in s["content"] for s in sections)

    def test_read_by_filename(self, tmp_project, cli_env):
        """按文件名（模糊匹配）应找到正确文件"""
        make_md(tmp_project, "ProjectSpec/a.md",
                "---\ndoc_type: test\n---\n# A\n\n## Title\na-content")
        make_md(tmp_project, "ProjectSpec/b.md",
                "---\ndoc_type: test\n---\n# B\n\n## Title\nb-content")
        # 按文件名 b.md 读取
        result = json.loads(cli_env.read_doc("b.md"))
        assert result["success"] is True
        assert "b.md" in result["data"]["path"]
        assert any("b-content" in s["content"] for s in result["data"]["sections"])

    def test_read_nonexistent(self, tmp_project, cli_env):
        """不存在的文件应返回 success: false"""
        result = json.loads(cli_env.read_doc("nonexistent.md"))
        assert result["success"] is False

    def test_read_no_frontmatter(self, tmp_project, cli_env):
        """没有 frontmatter 的纯 Markdown 也应正常读取"""
        make_md(tmp_project, "ProjectSpec/plain.md",
                "# 纯标题\n\n## 段落\n纯文本内容")
        result = json.loads(cli_env.read_doc("plain.md"))
        assert result["success"] is True
        assert len(result["data"]["sections"]) > 0

    def test_read_empty_file(self, tmp_project, cli_env):
        """空文件应返回空 sections"""
        make_md(tmp_project, "ProjectSpec/empty.md", "")
        result = json.loads(cli_env.read_doc("empty.md"))
        assert result["success"] is True
        # 空文件解析后 sections 应存在（可能为空列表或一个空白段）


class TestDocStructure:
    """doc_structure 正确读取 index.json"""

    def test_returns_all_docs(self, tmp_project, cli_env):
        """应返回 index.json 中所有文档"""
        make_md(tmp_project, "ProjectSpec/a.md", "---\ndoc_type: a\n---\n# A")
        make_md(tmp_project, "ProjectSpec/b.md", "---\ndoc_type: b\n---\n# B")
        make_index(tmp_project, [
            {"path": "a.md", "doc_type": "a", "module": "m",
             "level": "top", "version": "1.0", "status": "active",
             "depends_on": [], "mtime": "2026-01-01T00:00:00+00:00"},
            {"path": "b.md", "doc_type": "b", "module": "m",
             "level": "top", "version": "1.0", "status": "active",
             "depends_on": [], "mtime": "2026-01-01T00:00:00+00:00"},
        ])
        result = json.loads(cli_env.doc_structure())
        assert result["success"] is True
        assert len(result["data"]["doc_map"]) == 2

    def test_missing_index(self, cli_env):
        """index.json 不存在时返回 success: false"""
        # cli_env 的 tmp_project 没有 index.json
        result = json.loads(cli_env.doc_structure())
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════
#  路径穿越安全
# ═══════════════════════════════════════════════════════════════

class TestPathTraversal:
    """MCP 工具应拒绝路径穿越"""

    def test_read_doc_traversal(self, cli_env):
        """read_doc 拒绝 ../ 路径"""
        result = json.loads(cli_env.read_doc("../../../etc/passwd"))
        assert result["success"] is False

    def test_update_section_traversal(self, cli_env):
        """update_section 拒绝 reference 中的 ../ 路径"""
        result = json.loads(cli_env.update_section("../etc/passwd#x", "hack"))
        assert result["success"] is False

    def test_add_section_traversal(self, cli_env):
        """add_section 拒绝 reference 中的 ../ 路径"""
        result = json.loads(cli_env.add_section("../etc/passwd#x", "hack", "data"))
        assert result["success"] is False

    def test_deep_traversal(self, cli_env):
        """深层 ../ 路径也拒绝"""
        result = json.loads(cli_env.read_doc("../../windows/system32/config"))
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════
#  文件写入正确性
# ═══════════════════════════════════════════════════════════════

class TestUpdateSection:
    """update_section 写入正确文件、正确段落"""

    def test_update_correct_file(self, tmp_project, cli_env):
        """更新只影响目标文件，不影响其他文件"""
        make_md(tmp_project, "ProjectSpec/doc1.md",
                "---\ndoc_type: test\n---\n# D1\n\n## X\noriginal-x\n\n## Y\noriginal-y")
        make_md(tmp_project, "ProjectSpec/doc2.md",
                "---\ndoc_type: test\n---\n# D2\n\n## X\nother-x")
        result = json.loads(cli_env.update_section(
            "doc1.md#X", "updated-x"))
        assert result["success"] is True
        # 验证 doc1 已更新
        r1 = json.loads(cli_env.read_doc("doc1.md"))
        s_x = next(s for s in r1["data"]["sections"] if s["heading"] == "X")
        assert "updated-x" in s_x["content"]
        s_y = next(s for s in r1["data"]["sections"] if s["heading"] == "Y")
        assert "original-y" in s_y["content"]  # 未改变
        # 验证 doc2 不变
        r2 = json.loads(cli_env.read_doc("doc2.md"))
        s_x2 = next(s for s in r2["data"]["sections"] if s["heading"] == "X")
        assert "other-x" in s_x2["content"]

    def test_update_nonexistent_section(self, tmp_project, cli_env):
        """不存在的 reference 应拒绝写入，文件不变"""
        make_md(tmp_project, "ProjectSpec/doc.md",
                "---\ndoc_type: test\n---\n# Doc\n\n## X\ncontent")
        original = (tmp_project / "ProjectSpec" / "doc.md").read_text(encoding="utf-8")
        result = json.loads(cli_env.update_section(
            "doc.md#NONEXIST", "new"))
        assert result["success"] is False
        # 文件未改变
        assert (tmp_project / "ProjectSpec" / "doc.md").read_text(encoding="utf-8") == original

    def test_update_writes_frontmatter(self, tmp_project, cli_env):
        """写入后 frontmatter 应完整保留"""
        make_md(tmp_project, "ProjectSpec/doc.md",
                "---\ndoc_type: arch\nmodule: core\nversion: 1.0\n---\n# Doc\n\n## X\nold")
        cli_env.update_section("doc.md#X", "new")
        content = (tmp_project / "ProjectSpec" / "doc.md").read_text(encoding="utf-8")
        assert "doc_type: arch" in content
        assert "module: core" in content
        assert "version: 1.0" in content


class TestAddSection:
    """add_section 写入正确位置"""

    def test_add_under_existing_parent(self, tmp_project, cli_env):
        """在存在的父段落下新增"""
        make_md(tmp_project, "ProjectSpec/doc.md",
                "---\ndoc_type: test\n---\n# Doc\n\n## X\nx-content\n\n## Z\nz-content")
        result = json.loads(cli_env.add_section(
            "doc.md#X", "Y", "y-content"))
        assert result["success"] is True
        # 验证 Y 出现在 X 之后、Z 之前
        r = json.loads(cli_env.read_doc("doc.md"))
        sections = r["data"]["sections"]
        idx_x = next(i for i, s in enumerate(sections) if s["heading"] == "X")
        idx_y = next(i for i, s in enumerate(sections) if s["heading"] == "Y")
        idx_z = next(i for i, s in enumerate(sections) if s["heading"] == "Z")
        assert idx_x < idx_y < idx_z  # 顺序正确

    def test_add_nonexistent_parent(self, tmp_project, cli_env):
        """父段落不存在时追加到末尾"""
        make_md(tmp_project, "ProjectSpec/doc.md",
                "---\ndoc_type: test\n---\n# Doc\n\n## X\nx-content")
        result = json.loads(cli_env.add_section(
            "doc.md#NONEXIST", "Y", "y-content"))
        assert result["success"] is True
        r = json.loads(cli_env.read_doc("doc.md"))
        sections = r["data"]["sections"]
        assert sections[-1]["heading"] == "Y"

    def test_add_duplicate_reference(self, tmp_project, cli_env):
        """重复的 reference 应拒绝"""
        make_md(tmp_project, "ProjectSpec/doc.md",
                "---\ndoc_type: test\n---\n# Doc\n\n## X\nx-content")
        cli_env.add_section("doc.md#X", "Y", "y-content")
        result = json.loads(cli_env.add_section(
            "doc.md#X", "Y", "duplicate"))
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════
#  SessionSpec 文件操作
# ═══════════════════════════════════════════════════════════════

class TestSpecWrite:
    """spec_write 创建和更新文件"""

    def test_creates_spec_file(self, tmp_project, cli_env):
        """spec_write 应在 SessionSpec/active/ 下创建 spec.json"""
        import json
        make_md(tmp_project, "ProjectSpec/doc.md",
                "---\ndoc_type: test\n---\n# Doc\n\n## X\ncontent")
        data = json.dumps({
            "session_spec_id": "integration-test-001",
            "scenario": "tech-ref",
            "status": "active",
            "resolutions": [],
            "pending_decisions": [],
            "next_steps": [],
        })
        result = cli_env.spec_write(data)
        assert "✅" in result
        spec_file = tmp_project / "SessionSpec" / "active" / "integration-test-001.spec.json"
        assert spec_file.exists()
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        assert spec["session_spec_id"] == "integration-test-001"
        assert spec["scenario"] == "tech-ref"
        assert spec["status"] == "active"
        assert spec["project"] == "test-project"  # 自动填充

    def test_rejects_when_active_exists(self, tmp_project, cli_env):
        """有活跃议题时应拒绝创建新议题"""
        import json
        make_md(tmp_project, "ProjectSpec/doc.md",
                "---\ndoc_type: test\n---\n# Doc\n\n## X\ncontent")
        make_spec(tmp_project, "existing-session", {"status": "active"})
        data = json.dumps({
            "session_spec_id": "new-session",
            "scenario": "tech-ref",
            "status": "active",
            "resolutions": [],
            "pending_decisions": [],
            "next_steps": [],
        })
        result = cli_env.spec_write(data)
        assert "残留" in result or "请先处理" in result


class TestSpecAbort:
    """通过 spec_write + spec_archive 实现作废"""

    def test_abort_via_write_and_archive(self, tmp_project, cli_env):
        """作废：spec_write 设 abandoned → spec_archive 移至 archive"""
        import json
        make_md(tmp_project, "ProjectSpec/doc.md",
                "---\ndoc_type: test\n---\n# Doc\n\n## X\ncontent")
        # 先创建
        create = json.dumps({
            "session_spec_id": "abort-001",
            "scenario": "tech-ref",
            "status": "active",
            "resolutions": [],
            "pending_decisions": [],
            "next_steps": [],
        })
        cli_env.spec_write(create)
        active_file = tmp_project / "SessionSpec" / "active" / "abort-001.spec.json"
        assert active_file.exists()

        # 设 abandoned
        abandon = json.dumps({
            "session_spec_id": "abort-001",
            "scenario": "tech-ref",
            "status": "abandoned",
            "closed_at": "2026-01-02T00:00:00+00:00",
            "closed_reason": "测试作废",
            "resolutions": [],
            "pending_decisions": [],
            "next_steps": [],
        })
        result = cli_env.spec_write(abandon)
        assert "✅" in result

        # 归档
        cli_env.spec_archive()
        assert not active_file.exists()
        archive_file = tmp_project / "SessionSpec" / "archive" / "abort-001.spec.json"
        assert archive_file.exists()
        spec = json.loads(archive_file.read_text(encoding="utf-8"))
        assert spec["status"] == "abandoned"


class TestSpecArchive:
    """spec_archive 仅允许 closed/abandoned 状态归档"""

    def test_rejects_active(self, tmp_project, cli_env):
        """active 状态的议题不能归档"""
        make_spec(tmp_project, "active-session", {"status": "active"})
        result = cli_env.spec_archive()
        assert "closed" in result or "abandoned" in result or "不能" in result

    def test_accepts_closed(self, tmp_project, cli_env):
        """closed 状态的议题可以归档"""
        make_spec(tmp_project, "closed-session", {"status": "closed"})
        result = cli_env.spec_archive()
        assert "✅" in result
        archive_file = tmp_project / "SessionSpec" / "archive" / "closed-session.spec.json"
        assert archive_file.exists()
        assert not (tmp_project / "SessionSpec" / "active" / "closed-session.spec.json").exists()

    def test_accepts_abandoned(self, tmp_project, cli_env):
        """abandoned 状态的议题也可以归档"""
        make_spec(tmp_project, "abandoned-session", {"status": "abandoned"})
        result = cli_env.spec_archive()
        assert "✅" in result
        archive_file = tmp_project / "SessionSpec" / "archive" / "abandoned-session.spec.json"
        assert archive_file.exists()

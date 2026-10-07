"""状态机闭环测试 — 模拟完整的 SessionSpec 生命周期。

测试链路:
  spec_write(创建) → spec_write(新增决议) → spec_read(验证) →
  read_doc+update_section → spec_write(关闭) → spec_archive
"""

import json

from conftest import make_md, make_index


def test_full_session_lifecycle(tmp_project, cli_env):
    """完整的"开议题→决议→暂停→写文档→关闭→归档"链路"""

    # ── 准备：创建项目文档和索引 ──
    make_md(tmp_project, "ProjectSpec/business-context.md",
            "---\ndoc_type: business_context\nmodule: project-charter\nlevel: top\n"
            "version: 0.1.0\nstatus: active\n---\n"
            "# 业务背景\n\n## 项目动因\n\n原始项目动因内容\n")
    make_index(tmp_project, [
        {"path": "business-context.md",
         "doc_type": "business_context", "module": "project-charter",
         "level": "top", "version": "0.1.0", "status": "active",
         "depends_on": []},
    ])
    detail_150 = "话" * 150  # 满足 ≥150 字要求

    # ═══════════════════════════════════
    # Step 1: spec_write — 创建新议题
    # ═══════════════════════════════════
    create_data = json.dumps({
        "session_spec_id": "e2e-001",
        "scenario": "spec-scribe",
        "status": "active",
        "resolutions": [],
        "pending_decisions": [],
        "next_steps": [],
    }, ensure_ascii=False)
    result1 = cli_env.spec_write(create_data)
    assert "✅" in result1, f"spec_write (创建) failed: {result1}"
    assert json.loads(result1)["data"]["session_spec_id"] == "e2e-001"
    spec_file = tmp_project / "SessionSpec" / "active" / "e2e-001.spec.json"
    assert spec_file.exists()

    # ═══════════════════════════════════
    # Step 2: spec_write — 新增决议（全量替换）
    # ═══════════════════════════════════
    update_data = json.dumps({
        "session_spec_id": "e2e-001",
        "scenario": "spec-scribe",
        "status": "active",
        "resolutions": [
            {"topic": "项目目标确认",
             "decision": "明确项目核心目标为辅助个人投资者决策",
             "detail": detail_150},
        ],
        "pending_decisions": [],
        "next_steps": [],
        "related_doc_types": [],
    }, ensure_ascii=False)
    result2 = cli_env.spec_write(update_data)
    assert "✅" in result2, f"spec_write (更新) failed: {result2}"

    # ═══════════════════════════════════
    # Step 3: spec_read — 验证决议已写入
    # ═══════════════════════════════════
    result3 = cli_env.spec_read()
    spec = json.loads(result3)
    assert spec["session_spec_id"] == "e2e-001"
    assert len(spec["resolutions"]) == 1
    assert spec["resolutions"][0]["topic"] == "项目目标确认"

    # ═══════════════════════════════════
    # Step 4: read_doc → update_section
    # ═══════════════════════════════════
    # 4a. 读取文档，获取 section reference
    result4 = json.loads(cli_env.read_doc("business-context.md"))
    assert result4["success"] is True
    sections = result4["data"]["sections"]
    ref = None
    for s in sections:
        if s["heading"] == "项目动因":
            ref = s["reference"]
            break
    assert ref is not None, "未找到段落: 项目动因"

    # 4b. 更新段落内容
    new_content = "- 辅助个人投资者做出理智交易决策\n- 提供量价技术分析信号\n- 降低量化交易门槛"
    result4b = json.loads(cli_env.update_section(ref, new_content))
    assert result4b["success"] is True

    # 4c. 验证文件已更新
    updated = (tmp_project / "ProjectSpec" / "business-context.md").read_text(encoding="utf-8")
    assert "辅助个人投资者" in updated
    assert "原始项目动因内容" not in updated  # 旧内容已被替换

    # ═══════════════════════════════════
    # Step 5: spec_write 关闭 + spec_archive
    # ═══════════════════════════════════
    close_data = json.dumps({
        "session_spec_id": "e2e-001",
        "scenario": "spec-scribe",
        "status": "closed",
        "closed_at": "2026-01-02T00:00:00+00:00",
        "closed_reason": "验证完成",
        "resolutions": [
            {"topic": "项目目标确认",
             "decision": "明确项目核心目标为辅助个人投资者决策",
             "detail": detail_150},
        ],
        "pending_decisions": [],
        "next_steps": [],
        "related_doc_types": [],
    }, ensure_ascii=False)
    result5 = cli_env.spec_write(close_data)
    assert "✅" in result5, f"spec_write (关闭) failed: {result5}"

    # 磁盘文件状态已更新
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    assert spec["status"] == "closed"
    assert spec["closed_reason"] == "验证完成"

    # Step 6: spec_archive
    result6 = cli_env.spec_archive()
    assert "✅" in result6, f"spec_archive failed: {result6}"
    assert not spec_file.exists()  # 已移至 archive
    archive_file = tmp_project / "SessionSpec" / "archive" / "e2e-001.spec.json"
    assert archive_file.exists()

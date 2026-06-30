"""状态机闭环测试 — 模拟完整的 SessionSpec 生命周期。

测试链路:
  spec_start → spec_pause → spec_status → read_doc(+update_section) → spec_close
"""

import json

from conftest import make_md, make_index


def test_full_session_lifecycle(tmp_project, mcp_env):
    """完整的"开议题→决议→暂停→写文档→关闭"链路"""

    # ── 准备：创建项目文档和索引 ──
    make_md(tmp_project, "ProjectSpec/business-context.md",
            "---\ndoc_type: business_context\nmodule: project-charter\nlevel: top\n"
            "version: 0.1.0\nstatus: active\n---\n"
            "# 业务背景\n\n## 项目动因\n\n原始项目动因内容\n")
    make_index(tmp_project, [
        {"path": "ProjectSpec/business-context.md",
         "doc_type": "business_context", "module": "project-charter",
         "level": "top", "version": "0.1.0", "status": "active",
         "depends_on": [], "mtime": "2026-01-01T00:00:00+00:00"},
    ])
    detail_150 = "话" * 150  # 满足 ≥150 字要求

    # ═══════════════════════════════════
    # Step 1: spec_start
    # ═══════════════════════════════════
    result1 = mcp_env.spec_start("e2e-test", "spec-scribe", "e2e-001")
    assert "✅" in result1, f"spec_start failed: {result1}"
    assert mcp_env._current_session_id == "e2e-001"
    spec_file = tmp_project / "SessionSpec" / "active" / "e2e-001.spec.json"
    assert spec_file.exists()

    # ═══════════════════════════════════
    # Step 2: spec_pause — 新增决议
    # ═══════════════════════════════════
    pause_data = json.dumps({
        "new_resolutions": [
            {"topic": "项目目标确认",
             "decision": "明确项目核心目标为辅助个人投资者决策",
             "detail": detail_150},
        ],
    }, ensure_ascii=False)
    result2 = mcp_env.spec_pause(pause_data)
    assert "✅" in result2, f"spec_pause failed: {result2}"

    # ═══════════════════════════════════
    # Step 3: spec_status — 验证决议已写入
    # ═══════════════════════════════════
    result3 = mcp_env.spec_status()
    assert "e2e-001" in result3
    assert "项目目标确认" in result3, f"spec_status missing resolution: {result3}"

    # ═══════════════════════════════════
    # Step 4: read_doc → update_section
    # ═══════════════════════════════════
    # 4a. 读取文档，获取 section reference
    result4 = json.loads(mcp_env.read_doc("ProjectSpec/business-context.md"))
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
    result4b = json.loads(mcp_env.update_section(ref, new_content))
    assert result4b["success"] is True

    # 4c. 验证文件已更新
    updated = (tmp_project / "ProjectSpec" / "business-context.md").read_text(encoding="utf-8")
    assert "辅助个人投资者" in updated
    assert "原始项目动因内容" not in updated  # 旧内容已被替换

    # ═══════════════════════════════════
    # Step 5: spec_close — 关闭议题
    # ═══════════════════════════════════
    result5 = mcp_env.spec_close("验证完成", force=False)
    assert "✅" in result5, f"spec_close failed: {result5}"
    # 全局状态已清空
    assert mcp_env._current_session_id is None

    # 磁盘文件状态已更新
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    assert spec["status"] == "closed"
    assert spec["closed_reason"] == "验证完成"

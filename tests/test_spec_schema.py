"""spec_schema 纯函数单元测试。

测试目标（无文件IO）：
  - validate()               —— SpecStruct 校验逻辑
  - get_schema_metadata()    —— Schema 元数据生成
  - render_summary()         —— 摘要渲染
"""

import pytest
from spec_mcp_tools.spec_schema import (
    validate,
    render_summary,
    get_schema_metadata,
)


def _make_spec(**overrides) -> dict:
    """构造一份合法的完整 spec。"""
    spec = {
        "session_spec_id": "test-001",
        "project": "test-project",
        "scenario": "tech-ref",
        "related_doc_types": ["architecture"],
        "created_at": "2026-01-01T00:00:00+00:00",
        "resolutions": [],
        "pending_decisions": [],
        "next_steps": [],
        "status": "active",
        "closed_at": None,
        "closed_reason": None,
    }
    spec.update(overrides)
    return spec


# ═══════════════════════════════════════════════════════════════
#  validate
# ═══════════════════════════════════════════════════════════════

class TestValidate:
    """validate(spec: dict) -> list[str]"""

    def test_valid_spec(self):
        """合法 spec 返回空错误列表"""
        spec = _make_spec()
        assert validate(spec) == []

    def test_missing_required_fields(self):
        """缺少必填字段"""
        spec = {}
        errors = validate(spec)
        assert len(errors) >= 5  # 多个必填字段
        assert any("缺少必填字段" in e for e in errors)

    def test_invalid_scenario(self):
        """非法的 scenario 值"""
        spec = _make_spec(scenario="invalid-scenario")
        errors = validate(spec)
        assert any("scenario" in e and "不在允许范围内" in e for e in errors)

    def test_wrong_type(self):
        """字段类型错误（status 应为 str）"""
        spec = _make_spec(status=123)
        errors = validate(spec)
        assert any("status" in e and "类型应为" in e for e in errors)

    def test_detail_too_short(self):
        """决议 detail 不足 150 字"""
        spec = _make_spec(resolutions=[
            {"topic": "测试决议", "decision": "采用方案A",
             "detail": "太短了"},
        ])
        errors = validate(spec)
        assert any("长度不足" in e and "最少 150" in e for e in errors)

    def test_detail_exactly_150(self):
        """detail 恰好 150 字（边界测试）"""
        detail = "话" * 150
        spec = _make_spec(resolutions=[
            {"topic": "边界测试", "decision": "通过", "detail": detail},
        ])
        assert validate(spec) == []

    def test_detail_149(self):
        """detail 149 字应被拒绝"""
        detail = "话" * 149
        spec = _make_spec(resolutions=[
            {"topic": "边界测试", "decision": "拒绝", "detail": detail},
        ])
        errors = validate(spec)
        assert any("长度不足" in e for e in errors)

    def test_invalid_pending_status(self):
        """待定决议的状态值非法"""
        spec = _make_spec(pending_decisions=[
            {"topic": "缓存方案", "status": "invalid_status", "note": "测试"},
        ])
        errors = validate(spec)
        assert any("不在允许范围内" in e for e in errors)

    def test_empty_resolutions(self):
        """空决议列表应合法"""
        spec = _make_spec(resolutions=[])
        assert validate(spec) == []


# ═══════════════════════════════════════════════════════════════
#  get_schema_metadata
# ═══════════════════════════════════════════════════════════════

class TestGetSchemaMetadata:
    """get_schema_metadata() -> dict"""

    def test_returns_top_level_keys(self):
        meta = get_schema_metadata()
        assert "description" in meta
        assert "valid_status_transitions" in meta
        assert "fields" in meta

    def test_fields_cover_all_spec_fields(self):
        meta = get_schema_metadata()
        fields = meta["fields"]
        for name in ("session_spec_id", "project", "scenario",
                      "created_at", "status", "resolutions",
                      "pending_decisions", "next_steps",
                      "closed_at", "closed_reason"):
            assert name in fields, f"缺少字段: {name}"

    def test_readonly_fields_marked(self):
        meta = get_schema_metadata()
        fields = meta["fields"]
        assert fields["session_spec_id"].get("readonly") is True
        assert fields["project"].get("readonly") is True
        assert fields["created_at"].get("readonly") is True

    def test_allowed_values_present(self):
        meta = get_schema_metadata()
        scenario = meta["fields"]["scenario"]
        assert "allowed_values" in scenario
        assert "spec-scribe" in scenario["allowed_values"]

        status = meta["fields"]["status"]
        assert "allowed_values" in status
        assert "active" in status["allowed_values"]

    def test_nested_item_fields(self):
        meta = get_schema_metadata()
        res = meta["fields"]["resolutions"]
        assert "items" in res
        assert "topic" in res["items"]
        assert "decision" in res["items"]
        assert "detail" in res["items"]
        assert res["items"]["detail"].get("min_length") == 150

        pending = meta["fields"]["pending_decisions"]
        assert "items" in pending
        assert "status" in pending["items"]
        assert "allowed_values" in pending["items"]["status"]

    def test_valid_status_transitions(self):
        meta = get_schema_metadata()
        transitions = meta["valid_status_transitions"]
        assert "active" in transitions
        assert "closed" in transitions["active"]
        assert "abandoned" in transitions["active"]


# ═══════════════════════════════════════════════════════════════
#  render_summary
# ═══════════════════════════════════════════════════════════════

class TestRenderSummary:
    """render_summary(spec: dict) -> str"""

    def test_returns_string_with_key_info(self):
        spec = _make_spec(
            resolutions=[{
                "topic": "架构",
                "decision": "微服务",
                "detail": "d" * 150,
            }],
        )
        summary = render_summary(spec)
        assert isinstance(summary, str)
        assert "test-001" in summary
        assert "微服务" in summary
        assert "已完成决议" in summary

    def test_empty_spec(self):
        spec = _make_spec()
        summary = render_summary(spec)
        assert isinstance(summary, str)
        assert "test-001" in summary
        # 无决议、待定、计划时不应有对应的 section 标题
        assert "已完成决议" not in summary
        assert "待定决议" not in summary
        assert "后续计划" not in summary

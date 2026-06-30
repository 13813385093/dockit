"""spec_schema 纯函数单元测试。

测试目标（无文件IO）：
  - validate()     —— SpecStruct 校验逻辑
  - apply_pause()  —— 状态机暂停/保存逻辑
"""

import pytest
from spec_mcp_tools.spec_schema import (
    validate,
    new_spec,
    apply_pause,
    close_spec,
    abort_spec,
    render_summary,
)


# ═══════════════════════════════════════════════════════════════
#  validate
# ═══════════════════════════════════════════════════════════════

class TestValidate:
    """validate(spec: dict) -> list[str]"""

    def _valid_spec(self, **overrides) -> dict:
        """构造一份合法的最小 spec。"""
        spec = new_spec(
            session_spec_id="test-001",
            project="test-project",
            scenario="tech-ref",
            created_at="2026-01-01T00:00:00+00:00",
        )
        spec.update(overrides)
        return spec

    def test_valid_spec(self):
        """合法 spec 返回空错误列表"""
        spec = self._valid_spec()
        assert validate(spec) == []

    def test_missing_required_fields(self):
        """缺少必填字段"""
        spec = {}
        errors = validate(spec)
        assert len(errors) >= 5  # 多个必填字段
        assert any("缺少必填字段" in e for e in errors)

    def test_invalid_scenario(self):
        """非法的 scenario 值"""
        spec = self._valid_spec(scenario="invalid-scenario")
        errors = validate(spec)
        assert any("scenario" in e and "不在允许范围内" in e for e in errors)

    def test_wrong_type(self):
        """字段类型错误（status 应为 str）"""
        spec = self._valid_spec(status=123)
        errors = validate(spec)
        assert any("status" in e and "类型应为" in e for e in errors)

    def test_detail_too_short(self):
        """决议 detail 不足 150 字"""
        spec = self._valid_spec(resolutions=[
            {"topic": "测试决议", "decision": "采用方案A",
             "detail": "太短了"},
        ])
        errors = validate(spec)
        assert any("长度不足" in e and "最少 150" in e for e in errors)

    def test_detail_exactly_150(self):
        """detail 恰好 150 字（边界测试）"""
        detail = "话" * 150
        spec = self._valid_spec(resolutions=[
            {"topic": "边界测试", "decision": "通过", "detail": detail},
        ])
        assert validate(spec) == []

    def test_detail_149(self):
        """detail 149 字应被拒绝"""
        detail = "话" * 149
        spec = self._valid_spec(resolutions=[
            {"topic": "边界测试", "decision": "拒绝", "detail": detail},
        ])
        errors = validate(spec)
        assert any("长度不足" in e for e in errors)

    def test_invalid_pending_status(self):
        """待定决议的状态值非法"""
        spec = self._valid_spec(pending_decisions=[
            {"topic": "缓存方案", "status": "invalid_status", "note": "测试"},
        ])
        errors = validate(spec)
        assert any("不在允许范围内" in e for e in errors)

    def test_empty_resolutions(self):
        """空决议列表应合法"""
        spec = self._valid_spec(resolutions=[])
        assert validate(spec) == []


# ═══════════════════════════════════════════════════════════════
#  apply_pause
# ═══════════════════════════════════════════════════════════════

class TestApplyPause:
    """apply_pause(spec: dict, data: dict) -> list[str]"""

    def _make_spec(self) -> dict:
        return new_spec(
            session_spec_id="pause-test",
            project="test",
            scenario="spec-scribe",
            created_at="2026-01-01T00:00:00+00:00",
        )

    def test_add_resolution(self):
        """新增决议应追加到 resolutions 列表末尾"""
        spec = self._make_spec()
        data = {
            "new_resolutions": [
                {"topic": "认证方式", "decision": "采用 OAuth2",
                 "detail": "选择 OAuth2 是为了满足第三方系统安全接入要求，同时已有团队基础设施支持。授权模型采用 RBAC。传输加密使用 TLS 1.3。涉及模块：API 网关、用户服务。"},
            ],
        }
        errors = apply_pause(spec, data)
        assert errors == []
        assert len(spec["resolutions"]) == 1
        assert spec["resolutions"][0]["topic"] == "认证方式"
        assert spec["resolutions"][0]["decision"] == "采用 OAuth2"

    def test_add_multiple_resolutions(self):
        """多次新增决议"""
        spec = self._make_spec()
        apply_pause(spec, {"new_resolutions": [
            {"topic": "A", "decision": "方案A", "detail": "d" * 150},
        ]})
        apply_pause(spec, {"new_resolutions": [
            {"topic": "B", "decision": "方案B", "detail": "d" * 150},
        ]})
        assert len(spec["resolutions"]) == 2
        assert spec["resolutions"][1]["topic"] == "B"

    def test_change_pending_status(self):
        """修改待定决议的状态（needs_discussion → resolved）"""
        spec = self._make_spec()
        spec["pending_decisions"] = [
            {"topic": "缓存方案", "status": "needs_discussion", "note": "待讨论"},
        ]
        data = {
            "pending_status_changes": [
                {"topic": "缓存方案", "status": "resolved"},
            ],
        }
        errors = apply_pause(spec, data)
        assert errors == []
        assert spec["pending_decisions"][0]["status"] == "resolved"

    def test_change_invalid_status(self):
        """修改为非法状态应报错"""
        spec = self._make_spec()
        spec["pending_decisions"] = [
            {"topic": "日志方案", "status": "needs_discussion", "note": "待定"},
        ]
        data = {
            "pending_status_changes": [
                {"topic": "日志方案", "status": "invalid_status"},
            ],
        }
        errors = apply_pause(spec, data)
        assert len(errors) == 1
        assert "不合法" in errors[0]

    def test_add_new_pending(self):
        """新增待定决议"""
        spec = self._make_spec()
        data = {
            "new_pending": [
                {"topic": "ELK vs Loki", "note": "调研两种日志方案的优劣"},
            ],
        }
        errors = apply_pause(spec, data)
        assert errors == []
        assert len(spec["pending_decisions"]) == 1
        assert spec["pending_decisions"][0]["topic"] == "ELK vs Loki"
        assert spec["pending_decisions"][0]["status"] == "needs_discussion"

    def test_add_next_steps(self):
        """新增后续计划"""
        spec = self._make_spec()
        data = {"new_next_steps": ["调研 ELK", "写 PoC"]}
        errors = apply_pause(spec, data)
        assert errors == []
        assert spec["next_steps"] == ["调研 ELK", "写 PoC"]

    def test_remove_next_steps(self):
        """删除后续计划（精确匹配）"""
        spec = self._make_spec()
        spec["next_steps"] = ["调研 ELK", "写 PoC", "上线部署"]
        data = {"remove_next_steps": ["写 PoC"]}
        errors = apply_pause(spec, data)
        assert errors == []
        assert spec["next_steps"] == ["调研 ELK", "上线部署"]

    def test_empty_data(self):
        """空变更数据不应报错"""
        spec = self._make_spec()
        errors = apply_pause(spec, {})
        assert errors == []

    def test_invalid_resolution_format(self):
        """决议格式错误应报错（缺少 topic）"""
        spec = self._make_spec()
        data = {"new_resolutions": [{"decision": "不完整决议"}]}
        errors = apply_pause(spec, data)
        assert len(errors) == 1
        assert "格式错误" in errors[0]
        assert len(spec["resolutions"]) == 0  # 未追加


# ═══════════════════════════════════════════════════════════════
#  close_spec / abort_spec
# ═══════════════════════════════════════════════════════════════

class TestStateTransitions:
    """close_spec / abort_spec / render_summary 基本验证"""

    def test_close_spec(self):
        spec = new_spec("close-test", "test", "spec-scribe", "2026-01-01T00:00:00+00:00")
        close_spec(spec, "讨论完成", "2026-01-02T00:00:00+00:00")
        assert spec["status"] == "closed"
        assert spec["closed_reason"] == "讨论完成"

    def test_abort_spec(self):
        spec = new_spec("abort-test", "test", "spec-scribe", "2026-01-01T00:00:00+00:00")
        abort_spec(spec, "方向变更", "2026-01-02T00:00:00+00:00")
        assert spec["status"] == "abandoned"
        assert spec["closed_reason"] == "方向变更"

    def test_render_summary(self):
        """render_summary 返回字符串且包含关键信息"""
        spec = new_spec("sum-test", "test", "tech-ref", "2026-01-01T00:00:00+00:00")
        spec["resolutions"].append({
            "topic": "架构",
            "decision": "微服务",
            "detail": "d" * 150,
        })
        summary = render_summary(spec)
        assert isinstance(summary, str)
        assert "sum-test" in summary
        assert "微服务" in summary
        assert "已完成决议" in summary


# ═══════════════════════════════════════════════════════════════
#  new_spec
# ═══════════════════════════════════════════════════════════════

class TestNewSpec:
    """new_spec(...) -> dict"""

    def test_creates_active_spec(self):
        spec = new_spec("test-001", "my-project", "tech-ref", "2026-06-01T00:00:00+00:00")
        assert spec["session_spec_id"] == "test-001"
        assert spec["project"] == "my-project"
        assert spec["scenario"] == "tech-ref"
        assert spec["status"] == "active"
        assert spec["resolutions"] == []
        assert spec["pending_decisions"] == []

    def test_related_doc_types_by_scenario(self):
        spec_s = new_spec("s", "p", "spec-scribe", "")
        assert "business_context" in spec_s["related_doc_types"]

        spec_t = new_spec("t", "p", "tech-ref", "")
        assert "technical_framework" in spec_t["related_doc_types"]

        spec_f = new_spec("f", "p", "feature-dev", "")
        assert "feature_design" in spec_f["related_doc_types"]

    def test_unknown_scenario_empty_related(self):
        spec = new_spec("x", "p", "unknown", "")
        assert spec["related_doc_types"] == []


# ═══════════════════════════════════════════════════════════════
#  generate_template
# ═══════════════════════════════════════════════════════════════

class TestGenerateTemplate:
    """generate_template() -> dict"""

    def test_returns_dict(self):
        from spec_mcp_tools.spec_schema import generate_template
        template = generate_template()
        assert isinstance(template, dict)
        assert "session_spec_id" in template
        assert "scenario" in template
        assert "resolutions" in template
        assert "status" in template
        assert template["status"] == "active"
        assert template["closed_at"] is None

    def test_resolution_has_detail_placeholder(self):
        from spec_mcp_tools.spec_schema import generate_template
        template = generate_template()
        assert len(template["resolutions"]) == 1
        r = template["resolutions"][0]
        assert "detail" in r
        assert "150" in r["detail"]  # 提示最少150字

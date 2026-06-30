"""
doc-kit SpecStruct — 统一的 Schema 定义与校验。

本文件是 SpecStruct 的**唯一权威来源**。
MCP Server 通过 `validate(spec)` 校验写入数据。
Skills 通过引用本文件获取字段定义和合法取值。

使用方法：
    from spec_schema import validate, SPEC_SCHEMA
    errors = validate(spec_dict)
    if errors:
        print(f"校验失败: {errors}")
"""

from typing import Any

# ═══════════════════════════════════════════════════════════════
#  Scenario → 文档类型映射
# ═══════════════════════════════════════════════════════════════

SCENARIO_DOC_TYPES = {
    "spec-scribe": [
        "business_context",
        "stakeholders",
        # 精简模式复合类型
        "charter",
    ],
    "tech-ref": [
        "technical_framework",
        "technical_constraints",
        "global_policies",
        "inter_module_contract",
        "architecture",
        "domain_model",
        "module_manifest",
        # 可选
        "integration",
        # 精简模式复合类型
        "module_design",
    ],
    "feature-dev": [
        "feature_design",
        "decision_log",
        "unit_test",
        "acceptance_test",
        # 精简模式复合类型
        "feature_package",
    ],
}
"""scenario 到文档类型（doc_type）的映射表。

spec-scribe → 业务需求类文档
tech-ref    → 技术架构类文档
feature-dev → 功能规格+测试类文档
"""


# ═══════════════════════════════════════════════════════════════
#  Schema 定义
# ═══════════════════════════════════════════════════════════════

SPEC_SCHEMA = {
    "session_spec_id": {
        "type": str,
        "required": True,
        "description": "人类可读的唯一标识，如 'ss-tech-ref-module-A-001'",
    },
    "project": {
        "type": str,
        "required": True,
        "description": "项目名称",
    },
    "scenario": {
        "type": str,
        "required": True,
        "allowed": ["spec-scribe", "tech-ref", "feature-dev"],
        "description": "场景类型：spec-scribe（需求讨论）、tech-ref（技术评审）、feature-dev（功能设计）",
    },
    "related_doc_types": {
        "type": list,
        "required": True,
        "description": "本议题关联的文档类型列表，由 scenario 自动推导",
        "item_schema": {"type": str, "required": True},
    },
    "created_at": {
        "type": str,
        "required": True,
        "description": "ISO 8601 创建时间，如 '2026-06-17T20:38:00+08:00'",
    },
    "resolutions": {
        "type": list,
        "required": True,
        "description": "已明确的决议列表",
        "item_schema": {
            "topic": {"type": str, "required": True},
            "decision": {"type": str, "required": True},
            "detail": {"type": str, "required": True, "min_length": 150},
        },
    },
    "pending_decisions": {
        "type": list,
        "required": True,
        "description": "待定决议列表",
        "item_schema": {
            "topic": {"type": str, "required": True},
            "status": {
                "type": str,
                "required": True,
                "allowed": ["needs_discussion", "deferred", "blocked", "resolved"],
            },
            "note": {"type": str, "required": True},
        },
    },
    "next_steps": {
        "type": list,
        "required": True,
        "description": "后续计划列表",
        "item_schema": {"type": str, "required": True},
    },
    "status": {
        "type": str,
        "required": True,
        "allowed": ["active", "closed", "abandoned"],
        "description": "会话状态",
    },
    "closed_at": {
        "type": (str, type(None)),
        "required": False,
        "description": "关闭/作废时间，ISO 8601",
    },
    "closed_reason": {
        "type": (str, type(None)),
        "required": False,
        "description": "关闭/作废原因",
    },
}


# ═══════════════════════════════════════════════════════════════
#  校验函数
# ═══════════════════════════════════════════════════════════════


def _type_name(t: Any) -> str:
    """获取类型的可读名称。"""
    if isinstance(t, tuple):
        return " | ".join(_type_name(tt) for tt in t)
    return t.__name__


def validate(spec: dict) -> list[str]:
    """校验 spec 是否符合 SPEC_SCHEMA，返回错误列表（空 = 合法）。"""
    errors = []

    for field_name, field_schema in SPEC_SCHEMA.items():
        value = spec.get(field_name)

        # 必填检查
        if field_schema.get("required") and value is None:
            errors.append(f"缺少必填字段: {field_name}")
            continue

        if value is None:
            continue

        # 类型检查
        expected_type = field_schema["type"]
        if not isinstance(value, expected_type):
            errors.append(
                f"{field_name}: 类型应为 {_type_name(expected_type)}，"
                f"收到 {type(value).__name__}"
            )
            continue

        # 最小长度检查（字符串字段）
        min_len = field_schema.get("min_length")
        if min_len is not None and isinstance(value, str) and len(value) < min_len:
            errors.append(
                f"{field_name}: 长度不足，最少 {min_len} 字符，当前 {len(value)} 字符"
            )

        # 允许值检查
        allowed = field_schema.get("allowed")
        if allowed is not None and value not in allowed:
            errors.append(
                f"{field_name}: 值 '{value}' 不在允许范围内 {allowed}"
            )

        # 列表项检查
        if isinstance(value, list) and "item_schema" in field_schema:
            item_schema = field_schema["item_schema"]
            for i, item in enumerate(value):
                if not isinstance(item, dict) and item_schema.get("type") == str and isinstance(item, str):
                    continue  # 简单字符串列表，不需要进一步校验
                if isinstance(item, dict):
                    for item_field, item_field_schema in item_schema.items():
                        item_value = item.get(item_field)
                        if item_field_schema.get("required") and item_value is None:
                            errors.append(
                                f"{field_name}[{i}].{item_field}: 缺少必填字段"
                            )
                            continue
                        if item_value is not None:
                            if not isinstance(item_value, item_field_schema["type"]):
                                errors.append(
                                    f"{field_name}[{i}].{item_field}: "
                                    f"类型应为 {_type_name(item_field_schema['type'])}，"
                                    f"收到 {type(item_value).__name__}"
                                )
                            # 列表项字段的最小长度检查
                            item_min_len = item_field_schema.get("min_length")
                            if item_min_len is not None and isinstance(item_value, str) and len(item_value) < item_min_len:
                                errors.append(
                                    f"{field_name}[{i}].{item_field}: "
                                    f"长度不足，最少 {item_min_len} 字符，当前 {len(item_value)} 字符"
                                )
                            item_allowed = item_field_schema.get("allowed")
                            if item_allowed is not None and item_value not in item_allowed:
                                errors.append(
                                    f"{field_name}[{i}].{item_field}: "
                                    f"值 '{item_value}' 不在允许范围内 {item_allowed}"
                                )

    return errors


# ═══════════════════════════════════════════════════════════════
#  模板生成（给 Skills 引用，MCP 启动时自动刷新）
# ═══════════════════════════════════════════════════════════════


def generate_template() -> dict:
    """返回一个完整的 SpecStruct 骨架，字段值用占位符填充。

    Skills 通过 `read_file("spec-template.json")` 引用此结构。
    不允许任何内联硬编码的 JSON 模板。
    """
    return {
        "session_spec_id": "{唯一标识，如 ss-tech-ref-module-A-001}",
        "project": "{项目名}",
        "scenario": "{场景: spec-scribe | tech-ref | feature-dev}",
        "related_doc_types": ["{根据 scenario 自动填充的文档类型列表}"],
        "created_at": "{ISO 8601 时间}",
        "resolutions": [
            {
                "topic": "{决议主题（简洁明了）}",
                "decision": "{决议内容}",
                "detail": "{决议理由与补充说明（必填，≥150 字，供后续写入文档用）}",
            }
        ],
        "pending_decisions": [
            {
                "topic": "{待定决议主题}",
                "status": "{状态: needs_discussion | deferred | blocked | resolved}",
                "note": "{说明}",
            }
        ],
        "next_steps": ["{后续计划项}"],
        "status": "active",
        "closed_at": None,
        "closed_reason": None,
    }


# ═══════════════════════════════════════════════════════════════
#  SpecStruct 工厂函数
# ═══════════════════════════════════════════════════════════════


def new_spec(
    session_spec_id: str,
    project: str,
    scenario: str,
    created_at: str,
) -> dict:
    """创建一个初始的 SpecStruct（空决议/待定/计划）。"""
    related = SCENARIO_DOC_TYPES.get(scenario, [])
    return {
        "session_spec_id": session_spec_id,
        "project": project,
        "scenario": scenario,
        "related_doc_types": related,
        "created_at": created_at,
        "resolutions": [],
        "pending_decisions": [],
        "next_steps": [],
        "status": "active",
        "closed_at": None,
        "closed_reason": None,
    }


# ═══════════════════════════════════════════════════════════════
#  状态转移函数
# ═══════════════════════════════════════════════════════════════


def apply_pause(spec: dict, data: dict) -> list[str]:
    """对 spec 应用 specPause 变更，返回执行错误（空=成功）。"""
    errors = []

    # 1) 新增决议
    for r in data.get("new_resolutions", []):
        if not isinstance(r, dict) or "topic" not in r or "decision" not in r:
            errors.append(f"决议格式错误: {r}")
            continue
        spec["resolutions"].append({
            "topic": r["topic"],
            "decision": r["decision"],
            "detail": r.get("detail", ""),
        })

    # 2) 待定决议状态变更（按 topic 匹配）
    status_topics = {c["topic"] for c in data.get("pending_status_changes", [])
                     if isinstance(c, dict) and "topic" in c and "status" in c}
    for pd in spec["pending_decisions"]:
        if pd["topic"] in status_topics:
            match = [c for c in data["pending_status_changes"]
                     if c["topic"] == pd["topic"]]
            if match:
                new_status = match[0]["status"]
                if new_status in ("needs_discussion", "deferred", "blocked", "resolved"):
                    pd["status"] = new_status
                else:
                    errors.append(f"待定决议 '{pd['topic']}' 的状态 '{new_status}' 不合法")

    # 3) 新增待定决议
    for p in data.get("new_pending", []):
        if not isinstance(p, dict) or "topic" not in p or "note" not in p:
            errors.append(f"待定决议格式错误: {p}")
            continue
        spec["pending_decisions"].append({
            "topic": p["topic"],
            "status": "needs_discussion",
            "note": p["note"],
        })

    # 4) 新增后续计划
    for step in data.get("new_next_steps", []):
        if isinstance(step, str) and step.strip():
            spec["next_steps"].append(step.strip())

    # 5) 删除后续计划（按文本精确匹配）
    remove_set = set(data.get("remove_next_steps", []))
    spec["next_steps"] = [s for s in spec["next_steps"] if s not in remove_set]

    return errors


def close_spec(spec: dict, reason: str, closed_at: str) -> None:
    """标记 SpecStruct 为 closed。"""
    spec["status"] = "closed"
    spec["closed_at"] = closed_at
    spec["closed_reason"] = reason


def abort_spec(spec: dict, reason: str, closed_at: str) -> None:
    """标记 SpecStruct 为 abandoned。"""
    spec["status"] = "abandoned"
    spec["closed_at"] = closed_at
    spec["closed_reason"] = reason


# ═══════════════════════════════════════════════════════════════
#  摘要渲染
# ═══════════════════════════════════════════════════════════════


def render_summary(spec: dict) -> str:
    """将 SpecStruct 渲染为 Markdown 摘要，供 Agent 直接使用。"""
    lines = []
    sid = spec.get("session_spec_id", "?")
    scenario = spec.get("scenario", "?")
    status = spec.get("status", "?")
    scenario_label = {
        "spec-scribe": "需求讨论",
        "tech-ref": "技术评审",
        "feature-dev": "功能设计",
    }.get(scenario, scenario)

    lines.append(f"**议题**: {sid}  **场景**: {scenario_label}  **状态**: {status}")

    res = spec.get("resolutions", [])
    if res:
        lines.append(f"\n### ✅ 已完成决议（{len(res)} 项）")
        for r in res:
            lines.append(f"- {r['topic']}：{r['decision']}")

    pd = spec.get("pending_decisions", [])
    active_pd = [p for p in pd if p.get("status") != "resolved"]
    if active_pd:
        lines.append(f"\n### ❓ 待定决议（{len(active_pd)} 项）")
        for p in active_pd:
            lines.append(f"- {p['topic']} [{p['status']}]：{p['note']}")

    ns = spec.get("next_steps", [])
    if ns:
        lines.append(f"\n### 📌 后续计划（{len(ns)} 项）")
        for i, s in enumerate(ns, 1):
            lines.append(f"{i}. {s}")

    return "\n".join(lines)

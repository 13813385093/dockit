"""
doc-kit SpecStruct — 统一的 Schema 定义与校验。

本文件是 SpecStruct 的**唯一权威来源**。
MCP Server 通过 `validate(spec)` 校验写入数据。
`get_schema_metadata()` 通过共享 CLI（`python skills/scripts/cli.py spec schema`）暴露给 Skills。"""

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
        "non_functional_constraints",
        "global_policies",
        "inter_module_contract",
        "release_policy",
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
#  Schema 元数据（给 LLM 读取，替代 spec-template.json）
# ═══════════════════════════════════════════════════════════════


def get_schema_metadata() -> dict:
    """从 SPEC_SCHEMA 生成 LLM 友好的字段定义。

    Skills 运行 `python skills/scripts/cli.py spec schema` 获取此结构，了解各字段的类型、约束和允许值。
    是字段定义的**唯一公开来源**，skill 中不应硬编码任何 JSON 模板。
    """
    result = {}
    for name, schema in SPEC_SCHEMA.items():
        entry = {
            "type": _type_name(schema["type"]),
            "required": schema.get("required", False),
            "description": schema.get("description", ""),
        }
        allowed = schema.get("allowed")
        if allowed is not None:
            entry["allowed_values"] = list(allowed)
        min_len = schema.get("min_length")
        if min_len is not None:
            entry["min_length"] = min_len
        # 标记只读字段
        if name in ("session_spec_id", "project", "created_at"):
            entry["readonly"] = True
            entry["auto_filled"] = True

        item_schema = schema.get("item_schema")
        if item_schema is not None and isinstance(item_schema, dict):
            if "type" in item_schema:
                # 简单列表，如 next_steps: list[str]
                entry["item_type"] = _type_name(item_schema["type"])
            else:
                # 嵌套对象列表，如 resolutions: list[{topic, decision, detail}]
                entry["items"] = {}
                for fname, fschema in item_schema.items():
                    fentry = {
                        "type": _type_name(fschema["type"]),
                        "required": fschema.get("required", False),
                        "description": fschema.get("description", ""),
                    }
                    f_min_len = fschema.get("min_length")
                    if f_min_len is not None:
                        fentry["min_length"] = f_min_len
                    f_allowed = fschema.get("allowed")
                    if f_allowed is not None:
                        fentry["allowed_values"] = list(f_allowed)
                    entry["items"][fname] = fentry

        result[name] = entry

    return {
        "description": "SpecStruct — 议题会话的数据结构。全量替换模式：调用 spec write 时必须传入完整的 spec JSON，缺失的字段会被视为清空。",
        "valid_status_transitions": {
            "active": ["closed", "abandoned"],
            "closed": [],
            "abandoned": [],
        },
        "fields": result,
    }


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

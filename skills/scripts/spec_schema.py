"""
doc-kit SpecStruct — 统一的 Schema 定义与校验。

本文件是 SpecStruct 的**唯一权威来源**。
共享 CLI 的 `spec write` 通过 `validate(spec)` 校验写入数据。
`get_schema_metadata()` 通过共享 CLI（`python .doc-kit/cli/cli.py spec schema`）暴露给 Skills。"""

from typing import Any

# ═══════════════════════════════════════════════════════════════
#  Scenario → 文档类型映射
# ═══════════════════════════════════════════════════════════════

SCENARIO_DOC_TYPES = {
    "spec-scribe": [
        "business_context",
        "stakeholders",
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
    ],
    "feature-dev": [
        "feature_design",
        "decision_log",
        "unit_test",
        "acceptance_test",
    ],
}
"""scenario 到文档类型（doc_type）的映射表。

spec-scribe → 业务需求类文档
tech-ref    → 技术架构类文档
feature-dev → 功能规格+测试类文档
"""


# ═══════════════════════════════════════════════════════════════
#  决议的文档归宿（targets[]）—— 动作枚举与字段契约
# ═══════════════════════════════════════════════════════════════

RESOLUTION_TARGET_ACTIONS = ("doc_new", "doc_update_section", "doc_add_section", "doc_skip")
"""一条决议对某个目标文档的动作，与 CLI 子命令一一对应。

- ``doc_new``            → ``doc new``
- ``doc_update_section`` → ``doc update-section``
- ``doc_add_section``    → ``doc add-section``
- ``doc_skip``           → 本议题不写文档，必须给 ``reason``；它不是逃生舱——关闭时
  该条以 ``skipped`` 出现在覆盖表里，必须被人看到
"""

RESOLUTION_TARGET_SCHEMA = {
    "doc": {
        "type": str,
        "required": True,
        "description": "目标文档，`ProjectSpec/` 相对路径且必须带 `.md`，如 `module-order/architecture.md`",
    },
    "section": {
        "type": str,
        "required": False,
        "description": (
            "目标段落，形如 `架构设计#组件划分`（同 `doc read` 的 section reference）。"
            "`action=doc_new` 时可为空；用带父级的引用，避免同名标题歧义"
        ),
    },
    "action": {
        "type": str,
        "required": True,
        "allowed": list(RESOLUTION_TARGET_ACTIONS),
        "description": "doc_new 新建文档 / doc_update_section 改写已有段落 / doc_add_section 新增段落 / doc_skip 不落文档",
    },
    "reason": {
        "type": str,
        "required": False,
        "description": "`action=doc_skip` 时必填（≥10 字）：为何不落文档、建议归属层级",
    },
}
"""单个 target 的字段契约 —— schema 渲染与 CLI 业务校验共用这一份定义。"""


# ═══════════════════════════════════════════════════════════════
#  Schema 定义
# ═══════════════════════════════════════════════════════════════

SPEC_SCHEMA = {
    "session_spec_id": {
        "type": str,
        "required": True,
        "description": "人类可读的唯一标识，格式 '{当天日期}-{topic-kebab}'，如 '20260618-cert-auth'",
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
            "detail": {
                "type": str,
                "required": True,
                "min_length": 150,
                "description": (
                    "决议全文。必须自含：引用的清单、约束编号、条文原样写进本字段，"
                    "禁止「上述第 N 项」「见前一议题」这类指代（归档后指代目标失效）。150 字是下限，不是目标"
                ),
            },
            "targets": {
                "type": list,
                "required": False,
                "description": (
                    "本决议的文档归宿，可有多处（1:N）。active 时可留空；"
                    "closed 时每条决议必须有（由 spec write 校验）"
                ),
                "item_schema": RESOLUTION_TARGET_SCHEMA,
            },
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
    "coverage": {
        "type": (dict, type(None)),
        "required": False,
        "description": (
            "关闭时由 CLI **按磁盘重算**写入的落盘覆盖快照（verified_at / ok / missing / empty / "
            "ambiguous / rows）。调用方传入的值会被忽略：快照用来审计「已落盘」声明，不能由被审计方自填"
        ),
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


def _is_object_schema(schema: dict) -> bool:
    """区分 `item_schema` 的两种形态。

    - ``{"type": str}``                → 标量元素列表（如 `next_steps: list[str]`）
    - ``{"topic": {...}, "doc": {...}}`` → 对象字段定义（如 `resolutions: list[{...}]`）
    """
    return bool(schema) and all(isinstance(v, dict) for v in schema.values())


def _check_value(path: str, value: Any, schema: dict, errors: list[str]) -> None:
    """校验单个值：类型 → 最小长度 → 允许值 → （列表时）逐项递归。

    ``path`` 是报错前缀，如 ``resolutions[0].targets[1].action``。
    """
    expected_type = schema["type"]
    if not isinstance(value, expected_type):
        errors.append(
            f"{path}: 类型应为 {_type_name(expected_type)}，"
            f"收到 {type(value).__name__}"
        )
        return

    min_len = schema.get("min_length")
    if min_len is not None and isinstance(value, str) and len(value) < min_len:
        errors.append(f"{path}: 长度不足，最少 {min_len} 字符，当前 {len(value)} 字符")

    allowed = schema.get("allowed")
    if allowed is not None and value not in allowed:
        errors.append(f"{path}: 值 '{value}' 不在允许范围内 {allowed}")

    item_schema = schema.get("item_schema")
    if isinstance(value, list) and isinstance(item_schema, dict) and _is_object_schema(item_schema):
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                errors.append(f"{path}[{i}]: 类型应为 dict，收到 {type(item).__name__}")
                continue
            _check_object(f"{path}[{i}].", item, item_schema, errors)


def _check_object(prefix: str, obj: dict, schema: dict, errors: list[str]) -> None:
    """校验一个对象：逐字段必填 / 类型 / 约束；``prefix`` 为空表示顶层。"""
    for name, field_schema in schema.items():
        value = obj.get(name)
        if field_schema.get("required") and value is None:
            # 顶层沿用历史文案「缺少必填字段: x」，嵌套沿用「x.y: 缺少必填字段」
            errors.append(
                f"缺少必填字段: {name}" if not prefix else f"{prefix}{name}: 缺少必填字段"
            )
            continue
        if value is None:
            continue
        _check_value(f"{prefix}{name}", value, field_schema, errors)


def validate(spec: dict) -> list[str]:
    """校验 spec 是否符合 SPEC_SCHEMA，返回错误列表（空 = 合法）。

    支持两层嵌套（``resolutions[].targets[].*``）。为什么必须递归：schema 从「对象列表」
    演进为「对象列表里的对象列表」后，不递归就等于对最内层放行——非法枚举
    （``action: "bogus"``）与错拼字段都会被 success 回执吞掉，而这正是 2026.09.8 加
    ``unknown_keys`` 要防的失败模式。只做到两层，够用即可，不做通用递归框架。
    """
    errors: list[str] = []
    _check_object("", spec, SPEC_SCHEMA, errors)
    return errors


# ═══════════════════════════════════════════════════════════════
#  Schema 元数据（给 LLM 读取，替代 spec-template.json）
# ═══════════════════════════════════════════════════════════════


def _unknown_in_items(items: list, item_schema: dict, path: str, out: list[str]) -> None:
    """递归找出对象列表条目内的未知字段（支持一层嵌套，如 `resolutions[].targets[]`）。"""
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key not in item_schema:
                out.append(f"{path}[{index}].{key}")
                continue
            child_schema = item_schema[key]
            sub_items = child_schema.get("item_schema")
            if (
                isinstance(value, list)
                and isinstance(sub_items, dict)
                and _is_object_schema(sub_items)
            ):
                _unknown_in_items(value, sub_items, f"{path}[{index}].{key}", out)


def unknown_keys(spec: dict) -> list[str]:
    """返回 spec 中不在 SPEC_SCHEMA 里的字段路径（含嵌套条目内的字段）。

    为什么需要：`validate()` 只遍历 schema **定义过的**字段，从不反问"你给我的键里
    有没有我不认识的"。于是把 `pending_decisions` 拼成 `pendng_decisions`、或混进一个
    拼错的键，CLI 会回 success 并**原样写盘**——那个字段永远不会被读到，而用户以为记下了。
    `dev task set` 对此是拒绝的（见 cli.py 的 TASK_ALLOWED_KEYS 校验），本函数让两者对齐。

    列表字段按 `item_schema` 递归检查条目内的键（两层：``resolutions[].targets[]``）；
    标量元素列表（如 `next_steps`）无键可查。
    """
    unknown = [key for key in spec if key not in SPEC_SCHEMA]
    for field_name, field_schema in SPEC_SCHEMA.items():
        item_schema = field_schema.get("item_schema")
        # 标量元素的 item_schema 形如 {"type": str, "required": True}——值不是字段定义
        if not isinstance(item_schema, dict) or not _is_object_schema(item_schema):
            continue
        value = spec.get(field_name)
        if not isinstance(value, list):
            continue
        _unknown_in_items(value, item_schema, field_name, unknown)
    return unknown


def _render_field(schema: dict) -> dict:
    """把一个字段定义渲染为 LLM 可读的元数据（递归，支持两层嵌套）。"""
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
    item_schema = schema.get("item_schema")
    if isinstance(item_schema, dict):
        if _is_object_schema(item_schema):
            # 嵌套对象列表：resolutions[].targets[] 的内层字段也在这里展开，
            # 否则 agent 只能从描述里猜字段名（猜错会被 unknown_keys 拒绝）
            entry["items"] = {name: _render_field(fs) for name, fs in item_schema.items()}
        else:
            # 简单列表，如 next_steps: list[str]
            entry["item_type"] = _type_name(item_schema["type"])
    return entry


def get_schema_metadata() -> dict:
    """从 SPEC_SCHEMA 生成 LLM 友好的字段定义。

    Skills 运行 `python .doc-kit/cli/cli.py spec schema` 获取此结构，了解各字段的类型、约束和允许值。
    是字段定义的**唯一公开来源**，skill 中不应硬编码任何 JSON 模板。
    """
    result = {}
    for name, schema in SPEC_SCHEMA.items():
        entry = _render_field(schema)
        # 标记只读字段
        if name in ("session_spec_id", "project", "created_at"):
            entry["readonly"] = True
            entry["auto_filled"] = True
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

"""Document type registry - manages doc_type definitions and templates."""
from __future__ import annotations
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional

import yaml

# Built-in default registry with all 15 document types
DEFAULT_TYPES = [
    # Level 0 - Top
    {"doc_type": "business_context", "level": "top", "template": "business-context.md", "description": "业务背景"},
    {"doc_type": "technical_framework", "level": "top", "template": "technical-framework.md", "description": "技术框架"},
    {"doc_type": "non_functional_constraints", "level": "top", "template": "non-functional-constraints.md", "description": "非功能性约束"},
    {"doc_type": "global_policies", "level": "top", "template": "global-policies.md", "description": "全局策略"},
    {"doc_type": "inter_module_contract", "level": "top", "template": "inter-module-contracts.md", "description": "模块间接口契约"},
    {"doc_type": "stakeholders", "level": "top", "template": "stakeholders.md", "description": "干系人分析"},
    {"doc_type": "release_policy", "level": "top", "template": "release-policy.md", "description": "发布策略"},
    # Level 1 - Module
    {"doc_type": "architecture", "level": "module", "template": "architecture.md", "description": "模块架构设计"},
    {"doc_type": "domain_model", "level": "module", "template": "domain-model.md", "description": "领域模型"},
    {"doc_type": "module_manifest", "level": "module", "template": "module-manifest.md", "description": "模块清单"},
    {"doc_type": "integration", "level": "module", "template": "integration.md", "description": "外部集成"},
    # Level 2 - Feature
    {"doc_type": "feature_design", "level": "feature", "template": "feature-design.md", "description": "功能设计"},
    {"doc_type": "decision_log", "level": "feature", "template": "decision-log.md", "description": "设计决策"},
    {"doc_type": "unit_test", "level": "feature", "template": "unit-tests.md", "description": "单元测试"},
    {"doc_type": "acceptance_test", "level": "feature", "template": "acceptance-tests.md", "description": "验收测试"},
]


@dataclass
class DocTypeDef:
    """Definition of a single document type."""
    doc_type: str
    level: str
    template: str
    description: str = ""
    required_fields: list[str] = field(default_factory=list)


# DocTypeDef 认识的字段集合，用于过滤旧 registry.yaml 中的未知键（如 composite: true）
_DOC_TYPE_FIELDS = {f.name for f in fields(DocTypeDef)}

# 构造 DocTypeDef 时必需、且必须为真值的字段。只有 doc_type 的残缺条目会缺
# 这些键，若直接 DocTypeDef(**kwargs) 会抛 TypeError 崩溃，故加载时跳过。
_REQUIRED_TYPE_FIELDS = ("level", "template")


class Registry:
    """Document type registry.

    Loads type definitions from a registry.yaml file,
    falling back to built-in defaults if the file doesn't exist.
    """

    def __init__(self, registry_path: Optional[Path] = None):
        self._types: dict[str, DocTypeDef] = {}
        if registry_path and registry_path.exists():
            self._load_from_file(registry_path)
        else:
            self._load_defaults()

    def _load_from_file(self, path: Path):
        """从 registry.yaml 加载类型定义。

        防线（针对手改 / 截断 / 结构非法的 registry.yaml）：
        - 解析失败或结构非法（顶层非映射/列表、types 非列表）→ 回退内置默认；
        - 顶层直接是 list（裸列表格式）时，把该列表本身当作条目列表解析；
          dict 时取 types 键；
        - 忽略 DocTypeDef 不认识的字段（如 composite: true），避免 TypeError 崩溃；
        - 缺 level/template 必需键（或值为空）的条目不参与构造、直接跳过，
          同样避免缺键 TypeError 崩溃；
        - 结果为空 → 回退内置默认。

        设计说明：这里**刻意不**按名字过滤「已下线的文档类型」。项目内的
        .doc-kit/registry.yaml 陈旧（如仍是重构前的 18 种）时，让旧类型照原样
        显示，作为「该项目需要重跑 init 同步」的可见信号；由此产生的副作用
        （旧项目上仍可创建旧类型文档）由人工重跑 init 消除，而不是在代码里按
        名字写死黑名单——黑名单只作用于看板这份已安装程序，反而会掩盖「项目内
        旧 CLI / 旧能力库 / 旧模板仍然在位」这个真正的异常。
        """
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            self._load_defaults()
            return
        if isinstance(raw, dict):
            entries = raw.get("types")
        elif isinstance(raw, list):
            # 顶层裸列表：重构前即支持的格式，继续接受
            entries = raw
        else:
            self._load_defaults()
            return
        if not isinstance(entries, list):
            self._load_defaults()
            return
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("doc_type"):
                continue
            if not all(entry.get(k) for k in _REQUIRED_TYPE_FIELDS):
                continue
            kwargs = {k: v for k, v in entry.items() if k in _DOC_TYPE_FIELDS}
            dt = DocTypeDef(**kwargs)
            self._types[dt.doc_type] = dt
        if not self._types:
            self._load_defaults()

    def _load_defaults(self):
        for entry in DEFAULT_TYPES:
            dt = DocTypeDef(**entry)
            self._types[dt.doc_type] = dt

    def get(self, doc_type: str) -> Optional[DocTypeDef]:
        """Look up a document type by identifier."""
        return self._types.get(doc_type)

    def list_by_level(self, level: str) -> list[DocTypeDef]:
        """List all types at a given level."""
        return [t for t in self._types.values() if t.level == level]

    def list_all(self) -> list[DocTypeDef]:
        """List all registered document types."""
        return list(self._types.values())

    @staticmethod
    def get_default_registry_yaml() -> str:
        """Return the built-in registry as a YAML string."""
        data = {"types": DEFAULT_TYPES}
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

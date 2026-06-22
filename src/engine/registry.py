"""Document type registry - manages doc_type definitions and templates."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# Built-in default registry with all 17 document types
DEFAULT_TYPES = [
    # Level 0 - Top
    {"doc_type": "business_context", "level": "top", "template": "business-context.md", "description": "业务背景"},
    {"doc_type": "technical_framework", "level": "top", "template": "technical-framework.md", "description": "技术框架"},
    {"doc_type": "technical_constraints", "level": "top", "template": "technical-constraints.md", "description": "技术约束"},
    {"doc_type": "global_policies", "level": "top", "template": "global-policies.md", "description": "全局策略"},
    {"doc_type": "inter_module_contract", "level": "top", "template": "inter-module-contracts.md", "description": "模块间接口契约"},
    {"doc_type": "stakeholders", "level": "top", "template": "stakeholders.md", "description": "干系人分析"},
    # Level 0 - Composite
    {"doc_type": "charter", "level": "top", "template": "charter.md", "description": "项目宪章（复合类型）"},
    # Level 1 - Module
    {"doc_type": "architecture", "level": "module", "template": "architecture.md", "description": "模块架构设计"},
    {"doc_type": "domain_model", "level": "module", "template": "domain-model.md", "description": "领域模型"},
    {"doc_type": "module_manifest", "level": "module", "template": "module-manifest.md", "description": "模块清单"},
    {"doc_type": "integration", "level": "module", "template": "integration.md", "description": "外部集成"},
    # Level 1 - Composite
    {"doc_type": "module_design", "level": "module", "template": "module-design.md", "description": "模块设计（复合类型）"},
    # Level 2 - Feature
    {"doc_type": "feature_design", "level": "feature", "template": "feature-design.md", "description": "功能设计"},
    {"doc_type": "decision_log", "level": "feature", "template": "decision-log.md", "description": "设计决策"},
    {"doc_type": "unit_test", "level": "feature", "template": "unit-tests.md", "description": "单元测试"},
    {"doc_type": "acceptance_test", "level": "feature", "template": "acceptance-tests.md", "description": "验收测试"},
    # Level 2 - Composite
    {"doc_type": "feature_package", "level": "feature", "template": "feature-package.md", "description": "功能包（复合类型）"},
]


@dataclass
class DocTypeDef:
    """Definition of a single document type."""
    doc_type: str
    level: str
    template: str
    description: str = ""
    required_fields: list[str] = field(default_factory=list)

    @property
    def is_composite(self) -> bool:
        return self.doc_type in {"charter", "module_design", "feature_package"}


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
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries = raw.get("types", []) if isinstance(raw, dict) else raw
        for entry in entries:
            dt = DocTypeDef(**entry)
            self._types[dt.doc_type] = dt

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

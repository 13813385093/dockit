"""文档类型注册表 / 旧复合类型下线 的回归测试。

覆盖 15 种注册类型的边界，以及 charter / module_design / feature_package
三个旧复合类型彻底下线的回归护栏：

    - 默认注册表恰好 15 种，且不含旧类型；
    - init_project() 只创建 7 个顶层基础文档；
    - doc new 创建模块级/功能级文档时自动创建目录；
    - doc new 传旧类型名时返回未知类型错误，且不落盘；
    - SCENARIO_DOC_TYPES 不含旧类型；
    - 源码树（模板/能力库/对话框）不再残留旧类型。

关于取舍（项目决策，非遗漏）：

本次重构明确**不做任何向后兼容**——复合类型从未被真实使用过，因此
「旧 registry.yaml 的旧类型过滤」与「旧复合文档的迁移/备份（含陈旧索引
清理、迁移幂等）」被显式否决。原套件里描述这两类行为的两个测试类随之
删除，本文件**不设**对应护栏：写进去必然失败，且会把已被否决的行为
固化成契约。本文件只保留「现状即正确」的护栏：注册表 15 种、模板/能力库
同步、init 只建 7 份顶层文档、doc new 拒绝旧类型名。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

# 已下线的复合类型与其模板文件名（本次重构移除，不得以任何形式回流）
LEGACY_DOC_TYPES = {"charter", "module_design", "feature_package"}
LEGACY_FILENAMES = {
    "charter.md",
    "module-design.md",
    "module_design.md",
    "feature-package.md",
    "feature_package.md",
}

# init_project() 落地到 ProjectSpec/ 根目录的 7 份顶层文档
TOP_LEVEL_TEMPLATES = {
    "business-context.md",
    "technical-framework.md",
    "non-functional-constraints.md",
    "global-policies.md",
    "inter-module-contracts.md",
    "stakeholders.md",
    "release-policy.md",
}

EXPECTED_TOTAL = 15
EXPECTED_TOP = 7
EXPECTED_MODULE = 4
EXPECTED_FEATURE = 4


def _registry():
    from src.app.engine.registry import Registry

    return Registry()


def _init_project(root: Path, name: str = "proj") -> str:
    from src.app.engine.commands.init_utils import init_project

    return init_project(root, project_name=name)


# 说明：蓝图里另有 _write_registry_yaml / _default_entries / _legacy_entries
# 三个辅助器，其唯一消费者是被否决的「旧 registry.yaml 过滤」测试类。
# 该行为按项目决策不做，辅助器随之删除，避免留下无调用方的死代码。


# ═══════════════════════════════════════════════════════════════
#  默认注册表
# ═══════════════════════════════════════════════════════════════

class TestDefaultRegistry:
    """默认注册表恰好 15 种类型"""

    def test_default_types_has_exactly_15_entries(self):
        from src.app.engine.registry import DEFAULT_TYPES

        assert len(DEFAULT_TYPES) == EXPECTED_TOTAL

    def test_registry_loads_exactly_15_types(self):
        reg = _registry()
        assert len(reg.list_all()) == EXPECTED_TOTAL
        assert len({t.doc_type for t in reg.list_all()}) == EXPECTED_TOTAL

    def test_level_distribution_is_7_4_4(self):
        reg = _registry()
        assert len(reg.list_by_level("top")) == EXPECTED_TOP
        assert len(reg.list_by_level("module")) == EXPECTED_MODULE
        assert len(reg.list_by_level("feature")) == EXPECTED_FEATURE

    def test_no_legacy_type_registered(self):
        reg = _registry()
        assert not ({t.doc_type for t in reg.list_all()} & LEGACY_DOC_TYPES)
        for legacy in LEGACY_DOC_TYPES:
            assert reg.get(legacy) is None

    def test_top_level_templates_match_expected_set(self):
        reg = _registry()
        assert {t.template for t in reg.list_by_level("top")} == TOP_LEVEL_TEMPLATES

    def test_default_registry_yaml_roundtrip_has_15(self):
        from src.app.engine.registry import Registry

        data = yaml.safe_load(Registry.get_default_registry_yaml())
        assert len(data["types"]) == EXPECTED_TOTAL
        assert not ({e["doc_type"] for e in data["types"]} & LEGACY_DOC_TYPES)

    def test_cli_registry_matches_app_registry(self):
        """cli.py 的 DOC_TYPE_REGISTRY 与 app 端 DEFAULT_TYPES 为两份独立定义，必须一致。"""
        import cli
        from src.app.engine.registry import DEFAULT_TYPES

        app_map = {t["doc_type"]: (t["level"], t["template"]) for t in DEFAULT_TYPES}
        cli_map = {t["doc_type"]: (t["level"], t["template"]) for t in cli.DOC_TYPE_REGISTRY}
        assert len(cli_map) == EXPECTED_TOTAL
        assert cli_map == app_map

    def test_registered_templates_all_exist_on_disk(self):
        reg = _registry()
        templates_dir = REPO / "src" / "app" / "templates"
        for t in reg.list_all():
            assert (templates_dir / t.template).is_file(), f"模板缺失: {t.template}"


# ═══════════════════════════════════════════════════════════════
#  init_project
# ═══════════════════════════════════════════════════════════════

class TestInitProject:
    """init_project() 只创建 7 个顶层基础文档"""

    @pytest.fixture
    def initialized(self, tmp_path) -> Path:
        proj = tmp_path / "proj"
        proj.mkdir()
        _init_project(proj)
        return proj

    def test_creates_exactly_7_top_level_docs(self, initialized):
        docs = sorted((initialized / "ProjectSpec").glob("*.md"))
        assert len(docs) == EXPECTED_TOP
        assert {d.name for d in docs} == TOP_LEVEL_TEMPLATES

    def test_no_subdirectories_created_for_baseline(self, initialized):
        """顶层骨架不创建模块/功能目录。"""
        subdirs = [p for p in (initialized / "ProjectSpec").iterdir() if p.is_dir()]
        assert subdirs == []

    def test_top_level_docs_carry_registered_doc_types(self, initialized):
        reg = _registry()
        registered = {t.doc_type for t in reg.list_all()}
        from src.app.engine.frontmatter import FrontmatterParser

        for md in sorted((initialized / "ProjectSpec").glob("*.md")):
            meta, _ = FrontmatterParser.read_file(md)
            assert meta.get("doc_type") in registered, f"{md.name} 的 doc_type 未注册"
            assert meta.get("level") == "top"

    def test_doc_kit_templates_are_exactly_15(self, initialized):
        tmpl = initialized / ".doc-kit" / "templates"
        files = sorted(p.name for p in tmpl.glob("*.md"))
        assert len(files) == EXPECTED_TOTAL
        assert not (set(files) & LEGACY_FILENAMES)

    def test_doc_kit_guidance_has_no_legacy(self, initialized):
        caps = initialized / ".doc-kit" / "skills" / "guidance" / "doc-capabilities"
        files = sorted(p.name for p in caps.glob("*.md"))
        assert len(files) == EXPECTED_TOTAL + 1
        assert not (set(files) & LEGACY_FILENAMES)
        assert all(p.read_text(encoding="utf-8").strip() for p in caps.glob("*.md"))

    def test_registry_yaml_written_has_15_types(self, initialized):
        data = yaml.safe_load(
            (initialized / ".doc-kit" / "registry.yaml").read_text(encoding="utf-8")
        )
        assert len(data["types"]) == EXPECTED_TOTAL
        assert not ({e["doc_type"] for e in data["types"]} & LEGACY_DOC_TYPES)

    def test_index_contains_only_registered_types(self, initialized):
        idx = json.loads(
            (initialized / ".doc-kit" / "index.json").read_text(encoding="utf-8")
        )
        doc_types = {d["doc_type"] for d in idx["documents"]}
        assert len(idx["documents"]) == EXPECTED_TOP
        assert not (doc_types & LEGACY_DOC_TYPES)


# ═══════════════════════════════════════════════════════════════
#  doc new
# ═══════════════════════════════════════════════════════════════

class TestDocNew:
    """doc new 自动创建模块/功能目录，并拒绝旧类型"""

    @pytest.fixture
    def proj(self, tmp_path) -> Path:
        root = tmp_path / "proj"
        root.mkdir()
        _init_project(root)
        return root

    def test_module_level_doc_creates_module_dir(self, proj):
        import cli

        out = json.loads(cli.cmd_doc_new(proj, "architecture", module="order"))
        assert out["success"] is True, out
        target = proj / "ProjectSpec" / "module-order" / "architecture.md"
        assert target.is_file()
        assert out["data"]["path"] == "ProjectSpec/module-order/architecture.md"

    def test_feature_level_doc_creates_feature_dir(self, proj):
        import cli

        out = json.loads(
            cli.cmd_doc_new(proj, "feature_design", module="order", feature="checkout")
        )
        assert out["success"] is True, out
        target = (
            proj / "ProjectSpec" / "module-order" / "features" / "checkout" / "feature-design.md"
        )
        assert target.is_file()
        assert out["data"]["path"] == "ProjectSpec/module-order/features/checkout/feature-design.md"

    def test_module_dir_not_required_beforehand(self, proj):
        """模块目录此前不存在也必须被自动创建。"""
        assert not (proj / "ProjectSpec" / "module-order").exists()
        import cli

        cli.cmd_doc_new(proj, "architecture", module="order")
        assert (proj / "ProjectSpec" / "module-order").is_dir()

    def test_submodule_doc_uses_sub_modules_path(self, proj):
        import cli

        out = json.loads(cli.cmd_doc_new(proj, "architecture", module="order.core"))
        assert out["success"] is True, out
        assert (
            proj / "ProjectSpec" / "module-order" / "sub-modules" / "core" / "architecture.md"
        ).is_file()

    @pytest.mark.parametrize("legacy", sorted(LEGACY_DOC_TYPES))
    def test_legacy_doc_type_is_rejected_as_unknown(self, proj, legacy):
        import cli

        out = json.loads(
            cli.cmd_doc_new(proj, legacy, module="order", feature="checkout")
        )
        assert out["success"] is False
        assert "未知的文档类型" in out["suggestions"][0]
        assert legacy in out["suggestions"][0]

    @pytest.mark.parametrize("legacy", sorted(LEGACY_DOC_TYPES))
    def test_rejected_legacy_type_writes_nothing(self, proj, legacy):
        import cli

        before = {p.relative_to(proj) for p in proj.rglob("*")}
        cli.cmd_doc_new(proj, legacy, module="order", feature="checkout")
        after = {p.relative_to(proj) for p in proj.rglob("*")}
        assert after == before, f"{legacy} 被拒绝却产生了副作用"

    def test_unknown_type_error_lists_only_registered_candidates(self, proj):
        import cli

        out = json.loads(cli.cmd_doc_new(proj, "no_such_type"))
        msg = out["suggestions"][0]
        assert out["success"] is False
        for dt in _registry().list_all():
            assert dt.doc_type in msg
        for legacy in LEGACY_DOC_TYPES:
            assert legacy not in msg

    def test_new_module_doc_is_indexed(self, proj):
        import cli

        cli.cmd_doc_new(proj, "architecture", module="order")
        idx = json.loads(
            (proj / ".doc-kit" / "index.json").read_text(encoding="utf-8")
        )
        paths = {d["path"] for d in idx["documents"]}
        assert "ProjectSpec/module-order/architecture.md" in paths


# ═══════════════════════════════════════════════════════════════
#  场景类型表
# ═══════════════════════════════════════════════════════════════

class TestScenarioDocTypes:
    """SCENARIO_DOC_TYPES 不含复合类型，且全部为注册类型"""

    def test_no_legacy_types(self):
        from spec_schema import SCENARIO_DOC_TYPES

        flat = {dt for dts in SCENARIO_DOC_TYPES.values() for dt in dts}
        assert not (flat & LEGACY_DOC_TYPES)

    def test_all_scenario_types_are_registered(self):
        from spec_schema import SCENARIO_DOC_TYPES

        registered = {t.doc_type for t in _registry().list_all()}
        for scenario, doc_types in SCENARIO_DOC_TYPES.items():
            unknown = set(doc_types) - registered
            assert not unknown, f"{scenario} 含未注册类型: {unknown}"

    def test_derived_related_doc_types_from_scenario(self, tmp_path):
        """cli 由 scenario 推导 related_doc_types，结果不得含旧类型。"""
        import cli
        from spec_schema import SCENARIO_DOC_TYPES

        proj = tmp_path / "proj"
        proj.mkdir()
        _init_project(proj)

        spec = {
            "session_spec_id": "ss-test-001",
            "project": "proj",
            "scenario": "tech-ref",
            "created_at": "2026-01-01T00:00:00+00:00",
            "resolutions": [],
            "pending_decisions": [],
            "next_steps": [],
            "status": "active",
            "closed_at": None,
            "closed_reason": None,
        }
        out = json.loads(cli.cmd_spec_write(proj, json.dumps(spec)))
        assert out["success"] is True, out

        written = json.loads(
            (proj / "SessionSpec" / "active" / "ss-test-001.spec.json").read_text(
                encoding="utf-8"
            )
        )
        assert not (set(written["related_doc_types"]) & LEGACY_DOC_TYPES)
        assert set(written["related_doc_types"]) == set(SCENARIO_DOC_TYPES["tech-ref"])


# ═══════════════════════════════════════════════════════════════
#  源码树残留
# ═══════════════════════════════════════════════════════════════

class TestSourceTreeHasNoLegacy:
    """源码树不再残留旧类型文件与引用"""

    def test_templates_dir_matches_registry_exactly(self):
        reg = _registry()
        registered = {t.template for t in reg.list_all()}
        on_disk = {p.name for p in (REPO / "src" / "app" / "templates").glob("*.md")}
        assert on_disk == registered

    def test_capability_files_match_registry_exactly(self):
        reg = _registry()
        expected = {f"{t.doc_type}.md" for t in reg.list_all()} | {"_index.md"}
        caps = REPO / "skills" / "guidance" / "doc-capabilities"
        assert {p.name for p in caps.glob("*.md")} == expected

    def test_no_empty_capability_file(self):
        caps = REPO / "skills" / "guidance" / "doc-capabilities"
        empties = [
            p.name for p in sorted(caps.glob("*.md"))
            if not p.read_text(encoding="utf-8").strip()
        ]
        assert empties == []

    def test_no_legacy_template_files_on_disk(self):
        templates = REPO / "src" / "app" / "templates"
        assert not ({p.name for p in templates.glob("*.md")} & LEGACY_FILENAMES)

    def test_no_stale_section_refs_in_templates_or_capabilities(self):
        """unit-tests.md / release_policy.md 曾误引 §3.9（现为 §3.8）。"""
        for base in (
            REPO / "src" / "app" / "templates",
            REPO / "skills" / "guidance" / "doc-capabilities",
        ):
            for path in sorted(base.glob("*.md")):
                assert "§3.9" not in path.read_text(encoding="utf-8"), (
                    f"{path.name} 残留旧章节号 §3.9"
                )

    @pytest.mark.parametrize("dialog", [
        "src/app/dialogs/new_module_dialog.py",
        "src/app/dialogs/new_feature_dialog.py",
        "src/app/dialogs/new_doc.py",
        "src/app/dialogs/init_dialog.py",
    ])
    def test_dialogs_reference_no_legacy_type(self, dialog):
        """新建模块/功能对话框不再出现复合类型（PySide6 缺失，故为源码级断言）。"""
        text = (REPO / dialog).read_text(encoding="utf-8")
        for legacy in LEGACY_DOC_TYPES:
            assert f'"{legacy}"' not in text, f"{dialog} 仍引用旧类型 {legacy}"

    @pytest.mark.parametrize("dialog", [
        "src/app/dialogs/new_module_dialog.py",
        "src/app/dialogs/new_feature_dialog.py",
    ])
    def test_dialog_type_choices_are_registered(self, dialog):
        registered = {t.doc_type for t in _registry().list_all()}
        text = (REPO / dialog).read_text(encoding="utf-8")
        chosen = set(re.findall(r'types\.append\("([a-z_]+)"\)', text))
        assert chosen, f"{dialog} 未找到 types.append(...) 调用"
        assert chosen <= registered, f"{dialog} 含未注册类型: {chosen - registered}"

    def test_packaging_spec_excludes_legacy_files(self):
        """doc_kit.spec 必须显式排除旧复合文档，避免进入安装包。"""
        spec = (REPO / "src" / "app" / "doc_kit.spec").read_text(encoding="utf-8")
        assert "LEGACY_DOC_FILES" in spec
        assert "charter.md" in spec
        assert "_datas_tree" in spec


# ═══════════════════════════════════════════════════════════════
#  静态一致性检查器
# ═══════════════════════════════════════════════════════════════

class TestStaticConsistency:
    """tests/check_doc_consistency.py 的全部检查项必须无报错"""

    def test_consistency_check_reports_no_errors(self):
        import check_doc_consistency

        errors = check_doc_consistency.check()
        assert errors == [], (
            "文档一致性检查未通过:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

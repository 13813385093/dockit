"""文档类型注册表 / 旧复合类型下线 的回归测试。

覆盖 15 种注册类型的边界，以及 charter / module_design / feature_package
三个旧复合类型彻底下线的回归护栏：

    - 默认注册表恰好 15 种，且不含旧类型；
    - init_project() 只创建 7 个顶层基础文档；
    - doc new 创建模块级/功能级文档时自动创建目录；
    - 干净项目上 doc new 传旧类型名时返回未知类型错误，且不落盘；
    - SCENARIO_DOC_TYPES 不含旧类型；
    - 源码树（模板/能力库/对话框）不再残留旧类型；
    - init_project() 会把旧项目副本里的旧能力文件/模板清掉，用户自定义文件保留。

关于取舍（项目决策，非遗漏）：

1. **刻意不按名字写死过滤「已下线的文档类型」**（app 端 src/app/engine/registry.py
   与 CLI 端 skills/scripts/cli.py 的注册表加载点都不再过滤）。项目内那份
   .doc-kit/registry.yaml 陈旧（仍是重构前的 18 种）时应照原样加载，让异常保持
   可见，作为「该项目需要重跑 init 同步」的信号：静默过滤只作用于看板这份已安装
   程序，反而掩盖了项目内旧 CLI / 旧能力库 / 旧模板仍在的真正的异常；按名字写死
   三个类型的黑名单也属于针对遗留数据的特例兼容。由此产生的副作用（旧项目上仍可
   创建旧类型文档）由人工重跑 init 消除，而不是靠代码掩盖。故本文件不再为该过滤
   行为设护栏。
2. 同样按决策**不做**存量复合文档的迁移/备份（含陈旧索引清理、迁移幂等）。复合
   类型从未被真实使用过，不为其写迁移逻辑；写进去必然失败，且会把已被否决的行为
   固化成契约。本文件只保留「现状即正确」的护栏。
3. **已做且设护栏的泛化配置校验**（防的不是「旧数据」，而是任何手改/截断/结构非法
   的 registry.yaml 让工具崩溃或不可用）：忽略未知键（如 composite: true）、跳过
   缺 level/template 的残缺条目、结构非法或结果为空时回退内置 15 种；app 端继续
   接受顶层裸列表，CLI 端因迷你解析器所限一律返回 None 回退内置。对应护栏为
   TestIncompleteAndBareRegistry。
4. **重跑 init 会清理项目副本里的旧模板/旧能力文件**（TestLegacyCopyCleanup）：
   这是所有者已批准的行为，与注册表加载无关。
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


def _write_registry(root: Path, data) -> Path:
    """把 registry.yaml 写进 root/.doc-kit/ 并返回其路径。

    data 可以是 {"types": [...]} 映射，也可以是顶层裸列表（后者用于验证
    app 端对裸列表格式的兼容）。
    """
    kit = root / ".doc-kit"
    kit.mkdir(parents=True, exist_ok=True)
    path = kit / "registry.yaml"
    path.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def _default_entries() -> list[dict]:
    """15 个正规类型条目（与内置默认注册表同源的一份拷贝）。"""
    from src.app.engine.registry import DEFAULT_TYPES

    return [dict(t) for t in DEFAULT_TYPES]


def _legacy_entries(with_composite_key: bool = False) -> list[dict]:
    """旧版工具写入的 3 个复合类型条目。

    with_composite_key=True 时补上旧格式独有的 `composite: true` 未知键，
    用于验证加载器忽略未知键（历史 bug：直接构造 DocTypeDef 会 TypeError）。
    """
    entries = [
        {"doc_type": "charter", "level": "top", "template": "charter.md"},
        {"doc_type": "module_design", "level": "module", "template": "module-design.md"},
        {"doc_type": "feature_package", "level": "feature", "template": "feature-package.md"},
    ]
    if with_composite_key:
        for entry in entries:
            entry["composite"] = True
    return entries


def _registry_from(path: Path):
    """按 app 端真实调用方式从 registry.yaml 构造 Registry。"""
    from src.app.engine.registry import Registry

    return Registry(path)


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
#  残缺条目 / 裸列表 / 结构非法
# ═══════════════════════════════════════════════════════════════

class TestIncompleteAndBareRegistry:
    """残缺条目不屏蔽注册表；app 端接受顶层裸列表；结构非法回退内置"""

    INCOMPLETE = {"doc_type": "half_baked", "composite": True}

    def test_app_skips_incomplete_entry_without_crash(self, tmp_path):
        """缺 level/template 的残缺条目被跳过，不抛 TypeError，也不影响其它条目。"""
        path = _write_registry(tmp_path, {"types": _default_entries() + [dict(self.INCOMPLETE)]})
        reg = _registry_from(path)

        assert len(reg.list_all()) == EXPECTED_TOTAL
        assert reg.get("half_baked") is None
        assert reg.get("architecture") is not None

    def test_app_skips_entry_missing_only_template(self, tmp_path):
        """只有 level、缺 template 的条目同样被跳过。"""
        path = _write_registry(
            tmp_path,
            {"types": _default_entries() + [{"doc_type": "no_template", "level": "module"}]},
        )
        reg = _registry_from(path)

        assert len(reg.list_all()) == EXPECTED_TOTAL
        assert reg.get("no_template") is None

    def test_cli_skips_incomplete_entry_without_masking_registry(self, tmp_path):
        """CLI 端残缺条目不顶替内置注册表，返回的 15 种里不含它。"""
        import cli

        _write_registry(tmp_path, {"types": _default_entries() + [dict(self.INCOMPLETE)]})
        loaded = cli._load_registry(tmp_path)

        assert loaded is not None
        assert len(loaded) == EXPECTED_TOTAL
        assert "half_baked" not in loaded

    def test_cli_registry_not_masked_so_doc_new_still_works(self, tmp_path):
        """注册表未被残缺条目顶替：doc new architecture 仍成功。"""
        import cli

        proj = tmp_path / "proj"
        proj.mkdir()
        _init_project(proj)
        _write_registry(proj, {"types": _default_entries() + [dict(self.INCOMPLETE)]})

        out = json.loads(cli.cmd_doc_new(proj, "architecture", module="order"))
        assert out["success"] is True, out
        assert out["data"]["path"] == "ProjectSpec/module-order/architecture.md"

    def test_app_accepts_bare_list_registry(self, tmp_path):
        """顶层直接是 list（无 types 键）时 app 端仍解析：15 + 1 自定义 = 16。"""
        bare = _default_entries() + [
            {"doc_type": "my_custom", "level": "module", "template": "my-custom.md",
             "description": "自定义类型"}
        ]
        path = _write_registry(tmp_path, bare)
        reg = _registry_from(path)

        assert len(reg.list_all()) == EXPECTED_TOTAL + 1
        custom = reg.get("my_custom")
        assert custom is not None
        assert custom.level == "module"
        assert custom.template == "my-custom.md"
        assert custom.description == "自定义类型"

    def test_app_bare_list_parses_entries_as_is(self, tmp_path):
        """裸列表被原样解析：15 正规 + 3 旧类型 → 18 种，旧类型保持可见（不做过滤）。

        旧格式独有的 `composite: true` 未知键同时被忽略，不得 TypeError 崩溃。
        """
        path = _write_registry(
            tmp_path, _default_entries() + _legacy_entries(with_composite_key=True)
        )
        reg = _registry_from(path)
        types = reg.list_all()

        assert len(types) == EXPECTED_TOTAL + 3
        assert {t.doc_type for t in types} >= {"charter", "module_design", "feature_package"}
        assert reg.get("architecture") is not None

    def test_app_falls_back_to_defaults_on_scalar_document(self, tmp_path):
        """顶层是字符串等标量 → 回退内置 15 种，不崩溃。"""
        kit = tmp_path / ".doc-kit"
        kit.mkdir(parents=True, exist_ok=True)
        path = kit / "registry.yaml"
        path.write_text("就是一个字符串", encoding="utf-8")

        assert len(_registry_from(path).list_all()) == EXPECTED_TOTAL

    def test_app_falls_back_to_defaults_on_non_list_types_key(self, tmp_path):
        """types 是字符串 → 回退内置 15 种，不崩溃。"""
        path = _write_registry(tmp_path, {"types": "not-a-list"})

        assert len(_registry_from(path).list_all()) == EXPECTED_TOTAL

    def test_cli_returns_none_on_non_list_types_key(self, tmp_path):
        """CLI 端 types 非列表 → None（回退内置注册表）。"""
        import cli

        _write_registry(tmp_path, {"types": "not-a-list"})

        assert cli._load_registry(tmp_path) is None

    def test_cli_returns_none_on_scalar_document(self, tmp_path):
        """CLI 端顶层是标量 → None（回退内置注册表）。"""
        import cli

        kit = tmp_path / ".doc-kit"
        kit.mkdir(parents=True, exist_ok=True)
        (kit / "registry.yaml").write_text("就是一个字符串", encoding="utf-8")

        assert cli._load_registry(tmp_path) is None

    def test_cli_returns_none_on_bare_list_registry(self, tmp_path):
        """CLI 端刻意不支持顶层裸列表：返回 None 回退内置（迷你解析器无法处理）。"""
        import cli

        _write_registry(tmp_path, _default_entries())

        assert cli._load_registry(tmp_path) is None

    def test_cli_falls_back_to_builtin_and_still_creates_docs(self, tmp_path):
        """仅含残缺条目的 registry.yaml → 回退内置，doc new 仍可用。"""
        import cli

        proj = tmp_path / "proj"
        proj.mkdir()
        _init_project(proj)
        reg_path = proj / ".doc-kit" / "registry.yaml"
        reg_path.write_text("types:\n- doc_type: half_baked\n", encoding="utf-8")

        assert cli._load_registry(proj) is None
        out = json.loads(cli.cmd_doc_new(proj, "domain_model", module="pay"))
        assert out["success"] is True, out


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

    def test_doc_kit_smell_capabilities_copied(self, initialized):
        """init 必须把 smell-capabilities 一并复制（spec-code-smell 的运行前提）。"""
        caps = initialized / ".doc-kit" / "skills" / "guidance" / "smell-capabilities"
        files = sorted(p.name for p in caps.glob("*.md"))
        assert "_index.md" in files
        assert len(files) == 9  # _index + 8 个能力文件
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
#  init_project 副本清理（旧能力文件 / 旧模板）
# ═══════════════════════════════════════════════════════════════

class TestLegacyCopyCleanup:
    """init_project() 清理副本目录里的旧能力文件/模板，用户自定义文件保留"""

    CUSTOM_CAPABILITY = "my-custom-capability.md"
    CUSTOM_TEMPLATE = "my-custom-template.md"

    @pytest.fixture
    def proj(self, tmp_path) -> Path:
        proj = tmp_path / "proj"
        proj.mkdir()
        _init_project(proj)
        return proj

    @staticmethod
    def _capabilities_dir(proj: Path) -> Path:
        return proj / ".doc-kit" / "skills" / "guidance" / "doc-capabilities"

    @staticmethod
    def _templates_dir(proj: Path) -> Path:
        return proj / ".doc-kit" / "templates"

    @staticmethod
    def _names(directory: Path) -> set[str]:
        return {p.name for p in directory.glob("*.md")}

    def test_legacy_capability_files_removed_and_custom_kept(self, proj):
        """预置 3 个旧能力文件 + 1 个自定义文件 → 旧的全消失，自定义保留。"""
        from src.app.engine.commands.init_utils import LEGACY_CAPABILITY_FILES

        caps = self._capabilities_dir(proj)
        for name in LEGACY_CAPABILITY_FILES:
            (caps / name).write_text("旧复合类型能力说明\n", encoding="utf-8")
        custom = caps / self.CUSTOM_CAPABILITY
        custom.write_text("用户自定义能力说明\n", encoding="utf-8")
        assert len(self._names(caps)) == EXPECTED_TOTAL + 1 + len(LEGACY_CAPABILITY_FILES) + 1

        _init_project(proj)

        names = self._names(caps)
        assert not (names & set(LEGACY_CAPABILITY_FILES))
        assert self.CUSTOM_CAPABILITY in names
        assert custom.read_text(encoding="utf-8") == "用户自定义能力说明\n"
        assert len(names) == EXPECTED_TOTAL + 1 + 1  # 15 类型 + _index.md + 自定义

    def test_legacy_template_files_removed_and_custom_kept(self, proj):
        """预置 3 个旧模板 + 1 个自定义模板 → 旧的全消失，自定义保留。"""
        from src.app.engine.commands.init_utils import LEGACY_TEMPLATE_FILES

        tmpl = self._templates_dir(proj)
        for name in LEGACY_TEMPLATE_FILES:
            (tmpl / name).write_text("# 旧复合类型模板\n", encoding="utf-8")
        custom = tmpl / self.CUSTOM_TEMPLATE
        custom.write_text("# 用户自定义模板\n", encoding="utf-8")
        assert len(self._names(tmpl)) == EXPECTED_TOTAL + len(LEGACY_TEMPLATE_FILES) + 1

        _init_project(proj)

        names = self._names(tmpl)
        assert not (names & set(LEGACY_TEMPLATE_FILES))
        assert self.CUSTOM_TEMPLATE in names
        assert custom.read_text(encoding="utf-8") == "# 用户自定义模板\n"
        assert len(names) == EXPECTED_TOTAL + 1

    def test_copy_functions_clean_legacy_directly(self, proj):
        """直接调用 copy_guidance/copy_templates 也执行同一份清单的清理。"""
        from src.app.engine.commands.init_utils import (
            LEGACY_CAPABILITY_FILES,
            LEGACY_TEMPLATE_FILES,
            copy_guidance,
            copy_templates,
        )

        caps = self._capabilities_dir(proj)
        tmpl = self._templates_dir(proj)
        for name in LEGACY_CAPABILITY_FILES:
            (caps / name).write_text("旧能力\n", encoding="utf-8")
        for name in LEGACY_TEMPLATE_FILES:
            (tmpl / name).write_text("# 旧模板\n", encoding="utf-8")

        copy_guidance(proj)
        copy_templates(proj)

        assert not (self._names(caps) & set(LEGACY_CAPABILITY_FILES))
        assert not (self._names(tmpl) & set(LEGACY_TEMPLATE_FILES))

    def test_cleanup_is_idempotent(self, proj):
        """连续两次 init_project() 结果一致（幂等，可重复调用）。"""
        from src.app.engine.commands.init_utils import (
            LEGACY_CAPABILITY_FILES,
            LEGACY_TEMPLATE_FILES,
        )

        caps = self._capabilities_dir(proj)
        tmpl = self._templates_dir(proj)
        for name in LEGACY_CAPABILITY_FILES:
            (caps / name).write_text("旧能力\n", encoding="utf-8")
        for name in LEGACY_TEMPLATE_FILES:
            (tmpl / name).write_text("# 旧模板\n", encoding="utf-8")
        (caps / self.CUSTOM_CAPABILITY).write_text("自定义\n", encoding="utf-8")
        (tmpl / self.CUSTOM_TEMPLATE).write_text("自定义\n", encoding="utf-8")

        _init_project(proj)
        first = (sorted(self._names(caps)), sorted(self._names(tmpl)))
        _init_project(proj)
        second = (sorted(self._names(caps)), sorted(self._names(tmpl)))

        assert first == second
        assert not (set(first[0]) & set(LEGACY_CAPABILITY_FILES))
        assert not (set(first[1]) & set(LEGACY_TEMPLATE_FILES))
        assert self.CUSTOM_CAPABILITY in first[0]
        assert self.CUSTOM_TEMPLATE in first[1]

    def test_clean_project_has_exact_counts(self, proj):
        """无残留的干净项目：能力库 16 个（15 + _index.md）、模板 15 个。"""
        from src.app.engine.commands.init_utils import (
            LEGACY_CAPABILITY_FILES,
            LEGACY_TEMPLATE_FILES,
        )

        caps = self._names(self._capabilities_dir(proj))
        tmpl = self._names(self._templates_dir(proj))

        assert len(caps) == EXPECTED_TOTAL + 1
        assert len(tmpl) == EXPECTED_TOTAL
        assert not (caps & LEGACY_FILENAMES)
        assert not (tmpl & LEGACY_FILENAMES)
        assert not (caps & set(LEGACY_CAPABILITY_FILES))
        assert not (tmpl & set(LEGACY_TEMPLATE_FILES))


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

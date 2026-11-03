"""`doc read` 路径解析契约 —— R1 缺陷的回归测试。

背景（2026.10.5 的缺陷）：`doc read module-context/architecture` 会静默解析到
`ProjectSpec/module-behavior-log/architecture.md` 并返回 `success: true`——
目录信息在兜底步骤被整个丢弃，多候选时取排序首个。调用方（尤其 AI）通常只
消费 `sections`/`content`、不核对 `data.path`，于是拿另一模块的内容做判断。

本文件锁住修复后的四段解析顺序与三态失败语义：

  1. exact        —— 原样路径精确命中
  2. suffix_added —— 未带 .md 时补后缀再精确命中
  3. path_suffix  —— 含 `/` 的片段按**路径段**后缀匹配唯一文件
  4. basename     —— 裸文件名，仅当全库同名唯一时兜底
  多候选 → `doc_read.ambiguous`（列出全部候选，退出码 1）；无候选 →
  `doc_read.not_found`（含原文输入与 .md 提示）。
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from conftest import make_md  # noqa: E402


# ═══════════════════════════════════════════════════════════════
#  夹具：复刻 memctx 的"三篇同名 architecture.md"现场
# ═══════════════════════════════════════════════════════════════

def _frontmatter(doc_type: str, module: str, title: str, body: str) -> str:
    return (
        "---\n"
        f"doc_type: {doc_type}\n"
        f"module: {module}\n"
        "level: module\n"
        "version: 1.0.0\n"
        "last_updated: 2026-01-01\n"
        "status: active\n"
        "---\n"
        f"# {title}\n\n"
        f"{body}\n"
    )


def _build_project(project: Path) -> Path:
    """三篇同名 architecture.md + 两组同名 feature-design.md + 顶层平铺文档。

    与 memctx 的真实布局同构：同名文件分属不同模块，靠目录区分。
    """
    make_md(project, "ProjectSpec/business-context.md",
            _frontmatter("business_context", "", "业务背景", "## 动因\n顶层平铺文档。"))
    for module, marker in (
        ("module-behavior-log", "behavior-log-content"),
        ("module-context", "context-content"),
        ("module-memory", "memory-content"),
    ):
        make_md(project, f"ProjectSpec/{module}/architecture.md",
                _frontmatter("architecture", module, f"{module} 架构",
                             f"## 概述\n{marker}"))
    for feature, marker in (
        ("filter-chain", "filter-chain-content"),
        ("store-schema", "store-schema-content"),
    ):
        make_md(
            project,
            f"ProjectSpec/module-behavior-log/features/{feature}/feature-design.md",
            _frontmatter("feature_design", "module-behavior-log", f"{feature} 设计",
                         f"## 概述\n{marker}"),
        )
    # 嵌套且全库唯一 → 只有裸名输入才会用到第 4 步（basename）兜底
    make_md(project, "ProjectSpec/module-memory/domain-model.md",
            _frontmatter("domain_model", "module-memory", "记忆模块领域模型",
                         "## 实体\n记忆实体说明"))
    return project


def _run_cli(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "skills" / "scripts" / "cli.py"),
         "--root", str(project), *args],
        capture_output=True, text=True, cwd=str(project),
    )


def _read(cli_env, path: str) -> dict:
    return json.loads(cli_env.read_doc(path))


def _section_text(payload: dict) -> str:
    return "\n".join(s.get("content", "") for s in payload["data"]["sections"])


# ═══════════════════════════════════════════════════════════════
#  需求表 1.1 的 7 个用例（逐行锁定）
# ═══════════════════════════════════════════════════════════════

class TestSpecTableCases:
    """1.5 验收 1：需求表 7 个用例全部符合「期望」列。"""

    def test_suffix_omitted_picks_same_module(self, tmp_project, cli_env):
        """R1 的核心：省略 .md 也要命中**同模块**，不能掉进按文件名兜底。"""
        _build_project(tmp_project)
        payload = _read(cli_env, "module-context/architecture")
        assert payload["success"] is True
        assert payload["data"]["path"] == "ProjectSpec/module-context/architecture.md"
        assert "context-content" in _section_text(payload)
        assert payload["data"]["resolved_via"] == "suffix_added"

    def test_prefix_without_suffix(self, tmp_project, cli_env):
        """带 ProjectSpec/ 前缀 + 省略 .md：同样按目录命中。"""
        _build_project(tmp_project)
        payload = _read(cli_env, "ProjectSpec/module-context/architecture")
        assert payload["success"] is True
        assert payload["data"]["path"] == "ProjectSpec/module-context/architecture.md"

    def test_nested_feature_path_omits_suffix(self, tmp_project, cli_env):
        """feature 级嵌套路径省略 .md：命中 store-schema 而非 filter-chain。

        这条片段相对 ProjectSpec/ 是完整路径，故由第 2 步（补后缀）命中；
        只写 `features/store-schema/...` 的片段才落到第 3 步（见下一条用例）。
        """
        _build_project(tmp_project)
        payload = _read(
            cli_env, "module-behavior-log/features/store-schema/feature-design")
        assert payload["success"] is True
        assert payload["data"]["path"] == (
            "ProjectSpec/module-behavior-log/features/store-schema/feature-design.md")
        assert "store-schema-content" in _section_text(payload)
        assert payload["data"]["resolved_via"] == "suffix_added"

    def test_bare_name_with_duplicates_is_ambiguous(self, tmp_project, cli_env):
        """裸文件名有 3 个同名候选：必须报歧义，不许静默取首个。"""
        _build_project(tmp_project)
        payload = _read(cli_env, "architecture")
        assert payload["success"] is False
        assert "doc_read.ambiguous" in payload["message"]
        candidates = payload["data"]["candidates"]
        assert len(candidates) == 3
        assert candidates == sorted(candidates)
        assert "ProjectSpec/module-behavior-log/architecture.md" in candidates
        assert "ProjectSpec/module-context/architecture.md" in candidates
        assert "ProjectSpec/module-memory/architecture.md" in candidates

    def test_full_path_with_suffix(self, tmp_project, cli_env):
        _build_project(tmp_project)
        payload = _read(cli_env, "module-context/architecture.md")
        assert payload["data"]["path"] == "ProjectSpec/module-context/architecture.md"
        assert payload["data"]["resolved_via"] == "exact"

    def test_prefixed_full_path(self, tmp_project, cli_env):
        _build_project(tmp_project)
        payload = _read(cli_env, "ProjectSpec/module-context/architecture.md")
        assert payload["data"]["path"] == "ProjectSpec/module-context/architecture.md"

    def test_feature_full_path(self, tmp_project, cli_env):
        _build_project(tmp_project)
        payload = _read(cli_env, "features/store-schema/feature-design.md")
        assert payload["data"]["path"] == (
            "ProjectSpec/module-behavior-log/features/store-schema/feature-design.md")
        assert payload["data"]["resolved_via"] == "path_suffix"


# ═══════════════════════════════════════════════════════════════
#  解析顺序与"绝不靠猜"
# ═══════════════════════════════════════════════════════════════

def test_missing_dir_fragment_never_falls_back_to_basename(tmp_project, cli_env):
    """含 `/` 的片段找不到时不许退化到按文件名兜底（否则就是原缺陷）。"""
    _build_project(tmp_project)
    # module-typo 不存在，但 architecture.md 在别处存在
    payload = _read(cli_env, "module-typo/architecture")
    assert payload["success"] is False
    assert "doc_read.not_found" in payload["message"]
    assert payload["data"]["input"] == "module-typo/architecture"


def test_path_suffix_match_is_path_segment_aligned(tmp_project, cli_env):
    """路径段对齐：`feature-design` 不得命中 `feature-design-draft.md`。"""
    _build_project(tmp_project)
    make_md(tmp_project, "ProjectSpec/module-behavior-log/features/filter-chain/"
                         "feature-design-draft.md",
            _frontmatter("feature_design", "module-behavior-log", "草稿", "## 草稿\n草稿内容"))
    payload = _read(cli_env, "features/filter-chain/feature-design")
    assert payload["data"]["path"].endswith("features/filter-chain/feature-design.md")
    assert "filter-chain-content" in _section_text(payload)


def test_root_level_doc_suffix_added(tmp_project, cli_env):
    """顶层平铺文档省略 .md：由第 2 步命中（不经过 basename 兜底）。"""
    _build_project(tmp_project)
    payload = _read(cli_env, "business-context")
    assert payload["success"] is True
    assert payload["data"]["path"] == "ProjectSpec/business-context.md"
    assert payload["data"]["resolved_via"] == "suffix_added"


def test_unique_basename_still_works_and_hints_full_path(tmp_project, cli_env):
    """裸名唯一时保持旧行为（兼容），但必须回报 via=basename 并提示用全路径。"""
    _build_project(tmp_project)
    payload = _read(cli_env, "domain-model")
    assert payload["success"] is True
    assert payload["data"]["resolved_via"] == "basename"
    assert payload["data"]["path"] == "ProjectSpec/module-memory/domain-model.md"
    assert any("完整路径" in s for s in payload["suggestions"])


def test_unique_basename_with_suffix(tmp_project, cli_env):
    _build_project(tmp_project)
    payload = _read(cli_env, "domain-model.md")
    assert payload["data"]["resolved_via"] == "basename"
    assert payload["data"]["path"] == "ProjectSpec/module-memory/domain-model.md"


def test_duplicate_basename_reports_all_candidates(tmp_project, cli_env):
    """domain-model 在 3 个模块各有一份 → 裸名歧义，列出 3 个候选。"""
    _build_project(tmp_project)
    for module in ("module-behavior-log", "module-context"):
        make_md(tmp_project, f"ProjectSpec/{module}/domain-model.md",
                _frontmatter("domain_model", module, "领域模型", "## 实体\n实体说明"))
    payload = _read(cli_env, "domain-model")
    assert payload["success"] is False
    assert "doc_read.ambiguous" in payload["message"]
    assert len(payload["data"]["candidates"]) == 3


# ═══════════════════════════════════════════════════════════════
#  失败语义（1.5 验收 4）
# ═══════════════════════════════════════════════════════════════

def test_not_found_keeps_input_and_md_hint(tmp_project, cli_env):
    payload = _read(cli_env, "module-context/architecture-typo")
    assert payload["success"] is False
    message = payload["message"]
    assert "doc_read.not_found" in message
    assert "module-context/architecture-typo" in message      # 原文输入
    assert ".md" in message                                    # 后缀提示


def test_traversal_is_rejected(tmp_project, cli_env):
    (tmp_project / "outside.md").write_text("# 外部文档\n", encoding="utf-8")
    payload = _read(cli_env, "../outside.md")
    assert payload["success"] is False
    assert "doc_read.invalid_path" in payload["message"]


def test_directory_input_reports_is_directory(tmp_project, cli_env):
    _build_project(tmp_project)
    payload = _read(cli_env, "module-context")
    assert payload["success"] is False
    assert "doc_read.is_directory" in payload["message"]


# ═══════════════════════════════════════════════════════════════
#  退出码（R1-b：多候选 exit 1）
# ═══════════════════════════════════════════════════════════════

def test_ambiguous_exits_one(tmp_project):
    _build_project(tmp_project)
    done = _run_cli(tmp_project, "doc", "read", "architecture")
    assert done.returncode == 1
    payload = json.loads(done.stdout)
    assert payload["success"] is False
    assert "doc_read.ambiguous" in payload["message"]


def test_resolved_exits_zero(tmp_project):
    _build_project(tmp_project)
    done = _run_cli(tmp_project, "doc", "read", "module-context/architecture")
    assert done.returncode == 0
    payload = json.loads(done.stdout)
    assert payload["data"]["path"] == "ProjectSpec/module-context/architecture.md"


# ═══════════════════════════════════════════════════════════════
#  与写命令的边界：读允许省略，写要求完整路径（不得写错文件）
# ═══════════════════════════════════════════════════════════════

def test_write_commands_still_refuse_short_paths(tmp_project, cli_env):
    """写命令保持精确路径语义：短路径报错而不是写到别的同名文档。"""
    _build_project(tmp_project)
    before = (tmp_project / "ProjectSpec/module-context/architecture.md").read_text(
        encoding="utf-8")
    result = json.loads(
        cli_env.update_section("module-context/architecture#概述", "被改写的内容"))
    assert result["success"] is False
    assert "not_found" in result["message"]
    assert (tmp_project / "ProjectSpec/module-context/architecture.md").read_text(
        encoding="utf-8") == before, "写命令不得改动任何文件"

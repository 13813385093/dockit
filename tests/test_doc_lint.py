"""`doc lint` 规格完整性门禁（v1）的回归测试。

覆盖 R1/R3/R4/R5/R7/R8/R9/R10/R11/R12、代码块/注释屏蔽、配置（severity 覆盖）、
baseline 吸收、只读性，以及"模板占位符 token 全部被 R7 覆盖"。

设计原则（与交接件一致）：
  - 夹具为合成样本，**不引用 luca**（下游客户项目）；
  - 硬门禁零误报：代码块/HTML 注释里的示例不得触发任何规则。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "skills" / "scripts" / "cli.py"
TEMPLATES = REPO / "src" / "app" / "templates"

import cli  # noqa: E402

#: 模板文件名 → doc_type（合成夹具据此补全 frontmatter）
_NAME_TO_TYPE = {
    "business-context.md": "business_context",
    "technical-framework.md": "technical_framework",
    "non-functional-constraints.md": "non_functional_constraints",
    "global-policies.md": "global_policies",
    "inter-module-contracts.md": "inter_module_contract",
    "stakeholders.md": "stakeholders",
    "release-policy.md": "release_policy",
    "architecture.md": "architecture",
    "domain-model.md": "domain_model",
    "module-manifest.md": "module_manifest",
    "integration.md": "integration",
    "feature-design.md": "feature_design",
    "decision-log.md": "decision_log",
    "unit-tests.md": "unit_test",
    "acceptance-tests.md": "acceptance_test",
}


# ── 夹具辅助 ────────────────────────────────────────────────

def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "ProjectSpec").mkdir(parents=True)
    (proj / ".doc-kit").mkdir(parents=True)
    (proj / "SessionSpec").mkdir(parents=True)
    return proj


def _write(proj: Path, rel: str, text: str) -> Path:
    p = proj / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _frontmatter(
    doc_type: str,
    *,
    module: str = "project-charter",
    level: str = "top",
    feature: str | None = None,
    version: str = "1.0.0",
    last_updated: str = "2026-01-01",
    status: str = "active",
    author: str = "tester",
    depends_on_lines: list[str] | None = None,
) -> str:
    lines = [f"doc_type: {doc_type}", f"module: {module}"]
    if feature is not None:
        lines.append(f"feature: {feature}")
    lines += [
        f"level: {level}",
        f"version: {version}",
        f"last_updated: {last_updated}",
        f"status: {status}",
        f"author: {author}",
    ]
    if depends_on_lines:
        lines.append("depends_on:")
        lines.extend(depends_on_lines)
    else:
        lines.append("depends_on: []")
    return "---\n" + "\n".join(lines) + "\n---\n"


def _doc(proj: Path, rel: str, body: str = "", doc_type: str | None = None, **fm) -> Path:
    if doc_type is None:
        doc_type = _NAME_TO_TYPE[Path(rel).name]
    return _write(proj, rel, _frontmatter(doc_type, **fm) + "\n" + body + "\n")


def _lint(proj: Path, *args: str) -> dict:
    return json.loads(cli.cmd_doc_lint(proj, *args))


def _rules(payload: dict, bucket: str) -> list[str]:
    return sorted(e["rule"] for e in payload["data"][bucket])


def _run_cli(proj: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), "--root", str(proj), *args],
        capture_output=True, text=True, cwd=str(proj),
    )


# ── 干净样本 / R11 ──────────────────────────────────────────

def test_clean_minimal_doc_has_no_errors(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "业务背景。")
    payload = _lint(proj)
    assert payload["success"] is True, payload
    assert payload["data"]["errors"] == []


def test_r11_unparseable_frontmatter_is_error(tmp_path):
    proj = _project(tmp_path)
    _write(proj, "ProjectSpec/business-context.md", "# 无 frontmatter\n\n正文\n")
    payload = _lint(proj)
    assert payload["success"] is False
    assert "R11" in _rules(payload, "errors")


def test_missing_projectspec_fails(tmp_path):
    proj = tmp_path / "empty"
    (proj / "SessionSpec").mkdir(parents=True)
    payload = _lint(proj)
    assert payload["success"] is False
    assert "lint.no_docs" in payload["message"]


# ── R1 / R10 ───────────────────────────────────────────────

def test_r1_missing_required_field_is_warning(tmp_path):
    proj = _project(tmp_path)
    _write(proj, "ProjectSpec/business-context.md",
           _frontmatter("business_context", last_updated="") + "\n正文\n")
    payload = _lint(proj)
    assert payload["success"] is True
    assert "R1" in _rules(payload, "warnings")


def test_r10_reports_missing_required_top_doc(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "只有一篇必选顶层文档。")
    idx = proj / ".doc-kit" / "skills" / "guidance" / "doc-capabilities" / "_index.md"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(
        "| doc_type | 文件名 | 必选 |\n"
        "|---|---|---|\n"
        "| `business_context` | business-context.md | ✅ | 业务 |\n"
        "| `global_policies` | global-policies.md | ✅ | 策略 |\n",
        encoding="utf-8",
    )
    payload = _lint(proj)
    r10 = [w for w in payload["data"]["warnings"] if w["rule"] == "R10"]
    assert len(r10) == 1
    assert "global_policies" in r10[0]["message"]


# ── R3 ─────────────────────────────────────────────────────

def test_r3_unresolved_qualified_ref_is_error(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md",
         "见 global-policies@project-charter:C-999 的说明。")
    payload = _lint(proj)
    assert payload["success"] is False
    assert "R3" in _rules(payload, "errors")


def test_r3_resolves_when_target_defines_id(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/global-policies.md",
         "| 约束 ID | 策略 | 级别 | 说明 |\n|---|---|---|---|\n"
         "| {#C-999}C-999 | 统一日志 | [MUST] | 见下 |\n")
    _doc(proj, "ProjectSpec/business-context.md",
         "见 global-policies@project-charter:C-999。")
    payload = _lint(proj)
    assert "R3" not in _rules(payload, "errors")
    assert payload["data"]["metrics"]["qualified_refs"] == 1


def test_r3_feature_scope_resolves(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/module-order/features/checkout/feature-design.md",
         "| 约束 ID | 约束 | 级别 | 目标 | 说明 |\n|---|---|---|---|---|\n"
         "| C-101 | 超时 | [MUST] | 1s | — |\n",
         doc_type="feature_design", module="order", level="feature", feature="checkout")
    _doc(proj, "ProjectSpec/module-order/architecture.md",
         "见 feature-design@order.checkout:C-101。",
         doc_type="architecture", module="order", level="module")
    payload = _lint(proj)
    assert "R3" not in _rules(payload, "errors")


# ── R5 / R9 / R12 ──────────────────────────────────────────

def test_r5_duplicate_id_is_error(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/global-policies.md",
         "| 约束 ID | 策略 |\n|---|---|\n| C-101 | a |\n| C-101 | b |\n")
    payload = _lint(proj)
    assert "R5" in _rules(payload, "errors")


def test_r9_anchor_mismatch_is_error(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/global-policies.md",
         "| {#C-101}S-101 | 错位 |\n")
    payload = _lint(proj)
    assert "R9" in _rules(payload, "errors")


def test_r12_table_blank_line_is_error(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/global-policies.md",
         "| a | b |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 |\n")
    payload = _lint(proj)
    assert "R12" in _rules(payload, "errors")


# ── R7 ─────────────────────────────────────────────────────

def test_r7_frontmatter_placeholder_is_error(tmp_path):
    proj = _project(tmp_path)
    _write(proj, "ProjectSpec/business-context.md",
           _frontmatter("business_context", author="<替代文档>") + "\n正文\n")
    payload = _lint(proj)
    assert "R7" in _rules(payload, "errors")


def test_r7_dollar_var_is_error(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "负责人 $author 待填。")
    payload = _lint(proj)
    assert "R7" in _rules(payload, "errors")


def test_every_template_frontmatter_placeholder_is_covered(tmp_path):
    """每个模板 frontmatter 里的 `<...>` 占位符 token 都必须被 R7 命中。"""
    proj = _project(tmp_path)
    tokens: set[str] = set()
    import re
    for tmpl in sorted(TEMPLATES.glob("*.md")):
        fm = re.match(r"^---\s*\n(.*?)\n---", tmpl.read_text(encoding="utf-8"), re.DOTALL)
        if fm:
            tokens.update(re.findall(r"<[^<>\n]{1,40}>", fm.group(1)))
    assert tokens, "模板 frontmatter 中未取到占位符 token，检具本身可能已失效"
    for token in sorted(tokens):
        _write(proj, "ProjectSpec/business-context.md",
               _frontmatter("business_context", author=token) + "\n正文\n")
        payload = _lint(proj)
        msgs = " ".join(e["message"] for e in payload["data"]["errors"])
        assert token in msgs, f"占位符 {token!r} 未被 R7 命中"


# ── R8 ─────────────────────────────────────────────────────

def test_r8_depends_on_version_mismatch_is_error(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/global-policies.md", "策略。", version="1.0.0")
    _doc(proj, "ProjectSpec/business-context.md", "背景。",
         depends_on_lines=["  - doc: ProjectSpec/global-policies.md", "    version: 9.9.9"])
    payload = _lint(proj)
    assert "R8" in _rules(payload, "errors")


def test_r8_is_consistent_when_versions_match(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/global-policies.md", "策略。", version="1.2.3")
    _doc(proj, "ProjectSpec/business-context.md", "背景。",
         depends_on_lines=["  - doc: ProjectSpec/global-policies.md", "    version: 1.2.3"])
    payload = _lint(proj)
    assert "R8" not in _rules(payload, "errors")


# ── R4 ─────────────────────────────────────────────────────

def test_r4_bare_id_is_warning(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "参见 C-101 与 C-101（重复出现）。")
    payload = _lint(proj)
    assert payload["success"] is True  # warning 不阻断
    assert _rules(payload, "warnings") == ["R4"]
    # findings 按 (file, id) 去重；metric 计出现次数
    assert len([w for w in payload["data"]["warnings"] if w["rule"] == "R4"]) == 1
    assert payload["data"]["metrics"]["bare_id_suspects"] == 2


def test_r4_qualified_ref_not_flagged(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/global-policies.md", "自身定义见下。",
         )  # no ids
    _doc(proj, "ProjectSpec/business-context.md",
         "参见 global-policies@project-charter:C-101。")
    payload = _lint(proj)
    assert [w for w in payload["data"]["warnings"] if w["rule"] == "R4"] == []


def test_r4_same_feature_is_same_package(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/module-order/features/checkout/feature-design.md",
         "| C-101 | 约束 | [MUST] | x |\n", doc_type="feature_design",
         module="order", level="feature", feature="checkout")
    _doc(proj, "ProjectSpec/module-order/features/checkout/unit-tests.md",
         "覆盖 C-101。\n", doc_type="unit_test",
         module="order", level="feature", feature="checkout")
    payload = _lint(proj)
    assert [w for w in payload["data"]["warnings"] if w["rule"] == "R4"] == []


# ── 屏蔽代码块 / 注释 ──────────────────────────────────────

def test_code_fence_and_comment_are_masked(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md",
         "```\n| a |\n\n| b |\nC-999 <替代文档>\n```\n"
         "<!-- 表格示例：| x |\n\n| y |\nglobal-policies@project-charter:C-777 -->\n"
         "正文。\n")
    payload = _lint(proj)
    # 代码块/注释内的 R12/R7/R3/R4 都不应触发
    assert "R12" not in _rules(payload, "errors")
    assert "R7" not in _rules(payload, "errors")
    assert "R3" not in _rules(payload, "errors")
    assert [w for w in payload["data"]["warnings"] if w["rule"] == "R4"] == []


# ── 配置 / baseline / 只读 ─────────────────────────────────

def _write_lint_yaml(proj: Path, text: str) -> None:
    (proj / ".doc-kit" / "lint.yaml").write_text(text, encoding="utf-8")


def test_severity_downgrade_is_applied_and_shown(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "见 global-policies@project-charter:C-999。")
    _write_lint_yaml(proj, "lint_rules:\n  - rule: R3\n    level: warning\n")
    payload = _lint(proj)
    assert payload["success"] is True
    assert "R3" in _rules(payload, "warnings")
    applied = [o for o in payload["data"]["overrides_applied"] if o["rule"] == "R3"]
    assert applied and applied[0]["applied"] is True


def test_r11_cannot_be_downgraded(tmp_path):
    proj = _project(tmp_path)
    _write(proj, "ProjectSpec/business-context.md", "# no frontmatter\n")
    _write_lint_yaml(proj, "lint_rules:\n  - rule: R11\n    level: warning\n")
    payload = _lint(proj)
    assert payload["success"] is False
    assert "R11" in _rules(payload, "errors")
    overridden = [o for o in payload["data"]["overrides_applied"] if o["rule"] == "R11"]
    assert overridden and overridden[0]["applied"] is False


def test_upgrade_is_rejected(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "参见 C-101。")
    _write_lint_yaml(proj, "lint_rules:\n  - rule: R4\n    level: error\n")
    payload = _lint(proj)
    overridden = [o for o in payload["data"]["overrides_applied"] if o["rule"] == "R4"]
    assert overridden and overridden[0]["applied"] is False
    assert "R4" in _rules(payload, "warnings")


def test_lint_disabled(tmp_path):
    proj = _project(tmp_path)
    _write(proj, "ProjectSpec/business-context.md", "# no frontmatter\n")
    _write_lint_yaml(proj, "lint_enabled: false\n")
    payload = _lint(proj)
    assert payload["success"] is True
    assert payload["data"]["errors"] == []


def test_baseline_absorbs_existing_and_reports_new(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "参见 C-101 与 C-102。")
    (proj / ".doc-kit" / "lint-baseline.json").write_text(json.dumps({
        "entries": [
            {"rule": "R4", "file": "ProjectSpec/business-context.md", "key": "C-101"},
        ]
    }), encoding="utf-8")
    payload = _lint(proj)
    assert payload["success"] is True
    remaining = [w for w in payload["data"]["warnings"] if w["rule"] == "R4"]
    assert [w["key"] for w in remaining] == ["C-102"]
    assert payload["data"]["metrics"]["baselined"] == 1


def test_configured_missing_baseline_warns(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "正文。")
    _write_lint_yaml(proj, "lint_baseline: .doc-kit/nope.json\n")
    payload = _lint(proj)
    assert payload["data"]["baseline"]["missing"] is True
    assert any(w["rule"] == "config" for w in payload["data"]["warnings"])


def test_lint_is_read_only(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "参见 C-101。")
    before = {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()}
    _lint(proj)
    after = {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()}
    assert before == after, "doc lint 产生了写副作用"
    assert not (proj / ".doc-kit" / "index.json").exists()


def test_exit_code_one_on_error(tmp_path):
    proj = _project(tmp_path)
    _write(proj, "ProjectSpec/business-context.md", "# no frontmatter\n")
    done = _run_cli(proj, "doc", "lint")
    assert done.returncode == 1
    assert json.loads(done.stdout)["success"] is False


def test_exit_code_zero_on_warnings_only(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "参见 C-101。")
    done = _run_cli(proj, "doc", "lint")
    assert done.returncode == 0
    assert json.loads(done.stdout)["success"] is True


# ── --summary 精简输出 ─────────────────────────────────────

def test_summary_omits_warnings_detail(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "参见 C-101。")
    payload = _lint(proj, None, True)
    assert payload["success"] is True
    data = payload["data"]
    assert "warnings" not in data, "summary 模式不应带 warnings 明细"
    assert data["metrics"]["warnings"] == 1
    assert data["errors"] == []


def test_summary_reports_errors_with_messages(tmp_path):
    proj = _project(tmp_path)
    _write(proj, "ProjectSpec/business-context.md", "# no frontmatter\n")
    payload = _lint(proj, None, True)
    assert payload["success"] is False
    assert payload["data"]["errors"] and "message" in payload["data"]["errors"][0]
    assert "warnings" not in payload["data"]


def test_summary_truncates_errors_to_20(tmp_path):
    proj = _project(tmp_path)
    for i in range(25):
        _write(proj, f"ProjectSpec/module-m{i}/architecture.md", "# no frontmatter\n")
    payload = _lint(proj, None, True)
    assert payload["success"] is False
    assert payload["data"]["metrics"]["errors"] == 25
    assert len(payload["data"]["errors"]) == 20
    assert payload["data"].get("errors_truncated") is True


def test_default_output_keeps_warnings_detail(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "参见 C-101。")
    payload = _lint(proj)
    assert payload["data"]["warnings"], "默认输出必须保留 warnings 明细"


# ── reindex 回报 skipped ───────────────────────────────────

def test_reindex_reports_skipped(tmp_path):
    proj = _project(tmp_path)
    _doc(proj, "ProjectSpec/business-context.md", "正文。")
    _write(proj, "ProjectSpec/global-policies.md", "# 无 frontmatter\n")
    payload = json.loads(cli.cmd_doc_reindex(proj))
    assert payload["success"] is True
    assert "ProjectSpec/global-policies.md" in payload["data"]["skipped"]

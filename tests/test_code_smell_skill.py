"""spec-code-smell 内容契约测试（v0.5 骨架）。

覆盖用户确认的关键规则：
  - 独立 skill / 与 spec-code-review 的边界；
  - 显式范围，不读不写 review 锚点；
  - 源码按扩展名 + 排除规则识别，**不绑定 src/**；
  - 范围摘要、快速/深入双模式、测试默认排除、已知例外、上限；
  - 只读：不写报告、不改代码、不改 ProjectSpec。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "spec-code-smell" / "SKILL.md"
CAPS = REPO / "skills" / "guidance" / "smell-capabilities"
INDEX = CAPS / "_index.md"
REVIEW = REPO / "skills" / "spec-code-review" / "SKILL.md"

QUICK = ("duplicated-code", "long-parameter-list", "speculative-generality", "message-chains")
DEEP = ("mysterious-name", "primitive-obsession", "data-clumps", "shotgun-surgery")


def _frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md 缺少 frontmatter"
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def test_frontmatter_and_description_budget():
    text = SKILL.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm["name"] == "spec-code-smell"
    desc = fm["description"]
    assert len(desc) <= 200, f"description 超过 200 字符：{len(desc)}"
    assert "提交 PR 前" in desc
    assert "不适用于" in desc or "不适用" in desc


def test_boundary_with_code_review():
    text = SKILL.read_text(encoding="utf-8")
    assert "spec-code-review" in text
    assert "代码形态" in text and "文档一致性" in text


def test_explicit_range_and_no_anchor_io():
    text = SKILL.read_text(encoding="utf-8")
    assert "不读、不写 `review` 锚点" in text
    assert "git cat-file -e" in text
    assert "空 diff" in text
    # 执行路径不能出现写锚点/写报告/改文档命令
    assert "review anchor-set" not in text
    assert "review report-write" not in text
    assert "doc update-section" not in text


def test_source_discovery_is_not_src_bound():
    text = INDEX.read_text(encoding="utf-8")
    assert "不绑定 `src/`" in text
    assert "源文件发现" in text
    assert "范围摘要" in text
    assert "扩展名" in text
    for token in ("include/", "cmd/", "internal/", "packages/", "lib/", "bin/", "tools/", "utils/"):
        assert token in text, f"源文件发现缺布局示例：{token}"
    assert "默认只扫 `src/`" not in text


def test_tests_are_excluded_by_default_but_can_be_enabled():
    text = SKILL.read_text(encoding="utf-8")
    assert "测试默认不扫" in text
    assert "包含 tests" in text
    assert "测试豁免" in text


def test_scope_summary_and_user_override():
    text = SKILL.read_text(encoding="utf-8")
    assert "范围摘要" in text
    assert "用户指令" in text or "以用户指令为准" in text
    assert "未识别" in text
    assert "DevSpec" in text and "ProjectSpec" in text


def test_two_modes_and_capability_list():
    text = SKILL.read_text(encoding="utf-8")
    assert "快速" in text and "深入" in text
    for name in QUICK + DEEP:
        assert f"{name}.md" in text, f"SKILL 未引用能力文件：{name}.md"
    for name in QUICK + DEEP:
        assert (CAPS / f"{name}.md").is_file(), f"缺少能力文件：{name}.md"


def test_limits_and_output_contract():
    text = SKILL.read_text(encoding="utf-8")
    assert "最多 10 条" in text
    assert "1,200" in text or "1200" in text
    assert "80KB" in text
    assert "为什么可能是误报" in text
    assert "零发现" in text
    assert "同一根因只报一次" in text


def test_known_exceptions_sources():
    text = SKILL.read_text(encoding="utf-8")
    assert "已知例外" in text
    assert "code-notes.md" in text
    assert "ReviewSpec" in text
    assert "domain-model" in text


def test_read_only_non_goals():
    text = SKILL.read_text(encoding="utf-8")
    assert "不写 ReviewSpec/ProjectSpec" in text
    assert "不改锚点" in text
    assert "不自动改代码" in text
    assert "不新增 CLI 命令" in text


def test_capability_index_lists_all_files():
    text = INDEX.read_text(encoding="utf-8")
    for name in QUICK + DEEP:
        assert f"`{name}.md`" in text, f"_index.md 未列出 {name}.md"
    assert "启动时批量加载" not in text
    assert "按需加载" in text


def test_review_handoff_carries_explicit_range():
    text = REVIEW.read_text(encoding="utf-8")
    assert "review_from" in text
    assert "review_to" in text
    assert "/spec-code-smell <review_from>..<review_to>" in text

"""smell-capabilities 内容契约测试。

固定能力文件的结构、模式归属、误报排除与索引一致性，防止后续演进时
出现“索引有、文件没有”或“能力文件退化成空壳”。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAPS = REPO / "skills" / "guidance" / "smell-capabilities"
INDEX = CAPS / "_index.md"
SKILL = REPO / "skills" / "spec-code-smell" / "SKILL.md"

QUICK = ("duplicated-code", "long-parameter-list", "speculative-generality", "message-chains")
DEEP = ("mysterious-name", "primitive-obsession", "data-clumps", "shotgun-surgery")
REQUIRED_SECTIONS = (
    "## 识别症状",
    "## 最小证据门槛",
    "## 误报排除",
    "## 修复方向",
    "## 何时不问",
)


def _frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "能力文件缺少 frontmatter"
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _cap_files() -> list[Path]:
    return sorted(p for p in CAPS.glob("*.md") if p.name != "_index.md")


def test_exactly_eight_capability_files():
    names = [p.stem for p in _cap_files()]
    assert names == sorted(QUICK + DEEP), names


def test_all_capabilities_have_frontmatter_and_mode():
    for path in _cap_files():
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        assert fm.get("smell") == path.stem, path
        assert fm.get("mode") in ("quick", "deep"), path
        assert fm.get("evidence_scope"), path
        assert fm.get("default_confidence") in ("high", "medium", "low"), path


def test_quick_deep_membership():
    for path in _cap_files():
        text = path.read_text(encoding="utf-8")
        fm = _frontmatter(text)
        expected = "quick" if path.stem in QUICK else "deep"
        assert fm["mode"] == expected, f"{path.name} 模式应为 {expected}"


def test_required_sections_and_non_empty():
    for path in _cap_files():
        text = path.read_text(encoding="utf-8")
        assert text.strip(), f"{path.name} 为空"
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{path.name} 缺段落 {section}"
        assert "TODO" not in text, f"{path.name} 残留 TODO"
        assert "## repo override" not in text, f"{path.name} 不应重复 override 段"


def test_each_capability_has_examples_and_false_positives():
    for path in _cap_files():
        text = path.read_text(encoding="utf-8")
        assert text.count("```") >= 2, f"{path.name} 缺代码示例"
        fp = text.split("## 误报排除", 1)[1].split("## 修复方向", 1)[0]
        numbered = re.findall(r"^\d+\.\s", fp, re.M)
        assert len(numbered) >= 2, f"{path.name} 误报排除少于 2 条"


def test_runtime_docs_have_no_internal_iteration_labels():
    """运行期文档不应出现 v0.5/v0.4/本轮 这类设计阶段口径。"""
    for path in [SKILL, INDEX, *_cap_files()]:
        text = path.read_text(encoding="utf-8")
        assert "v0.5" not in text, path
        assert "v0.4" not in text, path
        assert "本轮" not in text, path


def test_index_lists_modes_and_source_discovery():
    text = INDEX.read_text(encoding="utf-8")
    assert "快速" in text and "深入" in text
    assert "不绑定 `src/`" in text
    assert "范围摘要" in text
    assert "按需加载" in text
    assert "已知例外" in text
    for name in QUICK + DEEP:
        assert f"`{name}.md`" in text, f"索引未列 {name}.md"


def test_index_marks_mode_for_each_capability():
    text = INDEX.read_text(encoding="utf-8")
    for name in QUICK:
        row = next((l for l in text.splitlines() if f"`{name}.md`" in l and l.strip().startswith("|")), "")
        assert "quick" in row, f"{name} 索引行未标 quick：{row}"
    for name in DEEP:
        row = next((l for l in text.splitlines() if f"`{name}.md`" in l and l.strip().startswith("|")), "")
        assert "deep" in row, f"{name} 索引行未标 deep：{row}"

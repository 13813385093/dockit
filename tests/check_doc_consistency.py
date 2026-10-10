"""文档体系一致性静态检查 — 校验注册表 / 模板 / 能力库 / 索引 / 指南 五者不漂移。

用法:
    python tests/check_doc_consistency.py

无第三方依赖（registry 之外只用标准库），纯静态分析。
返回 0 表示一致，返回 1 表示发现不一致。

校验项：
    1. doc-capabilities/_index.md §1 的 doc_type 集合 == 注册表注册集合；
    2. _index.md §3 引用的章节名，能在目标能力文件（或模板）中找到；
    3. src/app/templates/ 中不存在未注册模板，且注册模板均已就位；
    4. skills/guidance/doc-capabilities/ 中不存在空文件或未注册能力文件；
    5. 上述两目录中不残留已下线类型的文件；
    6. 模板与能力文件中不残留旧章节号引用（§3.9 系）；
    7. 指南中不存在重复的小节编号（如两个 §3.8.1）；
    8. _index.md 含「权威分层与引用纪律」节（文档模型第三级：谁拥有哪类事实、指针方向）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO / "src" / "app" / "templates"
CAPS_DIR = REPO / "skills" / "guidance" / "doc-capabilities"
INDEX_MD = CAPS_DIR / "_index.md"
GUIDE = REPO / "面向AI时代的新型项目文档体系设计与实施指南.md"

# 已下线的复合类型（本次重构把 18 种类型收敛为 15 种正规类型）
LEGACY_DOC_TYPES = {"charter", "module_design", "feature_package"}
LEGACY_FILENAMES = {
    "charter.md", "module-design.md", "module_design.md",
    "feature-package.md", "feature_package.md",
}

# 模板与能力文件中不得再出现的旧章节号（原 §3.9 已重编号为 §3.8）
STALE_SECTION_REFS = ("§3.9",)

_SECTION_TOKEN_RE = re.compile(r"§([^\s/、|]+)")


def _load_registry_types() -> dict[str, dict]:
    """从 app 端注册表加载 {doc_type: {level, template}}。"""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from src.app.engine.registry import Registry

    return {
        t.doc_type: {"level": t.level, "template": t.template} for t in Registry().list_all()
    }


def _index_section1_types() -> dict[str, str]:
    """解析 _index.md §1 的表格，返回 {doc_type: 文件名}。"""
    found: dict[str, str] = {}
    for line in INDEX_MD.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*`([a-z_]+)`\s*\|\s*([a-z0-9\-]+\.md)\s*\|", line)
        if not m:
            continue
        found[m.group(1)] = m.group(2)
    return found


def _index_section3_rows() -> list[tuple[str, str, list[str]]]:
    """解析 _index.md §3 路由表，返回 [(doc_type, 原始文本, [章节名])]。"""
    rows: list[tuple[str, str, list[str]]] = []
    in_s3 = False
    for line in INDEX_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("## 3."):
            in_s3 = True
            continue
        if in_s3 and line.startswith("## "):
            return rows
        if not (in_s3 and line.startswith("|")):
            continue
        m = re.match(r"\|([^|]*)\|\s*`([a-z_]+)`\s*\|([^|]*)\|", line)
        if not m:
            continue
        doc_type, sections = m.group(2), m.group(3)
        tokens = [t.strip() for t in _SECTION_TOKEN_RE.findall(sections)]
        if not tokens:
            continue
        rows.append((doc_type, sections.strip(), tokens))
    return rows


def _normalize_heading(title: str) -> str:
    """归一化章节标题：去掉前导 §、去掉「— 说明」后缀。"""
    title = title.strip().lstrip("§").strip()
    for sep in (" — ", " - ", "——"):
        if sep in title:
            title = title.split(sep, 1)[0].strip()
    return title


def _capability_fixed_sections(doc_type: str) -> list[str]:
    """能力文件中声明的固定章节（形如 `### §模块概述`）。"""
    path = CAPS_DIR / f"{doc_type}.md"
    if not path.exists():
        return []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+(§.+)$", line)
        if not m:
            continue
        names.append(_normalize_heading(m.group(1)))
    return names


def _template_sections(template: str) -> list[str]:
    """模板中的二级标题（占位符 $feature 等不计）。"""
    path = TEMPLATES_DIR / template
    if not path.exists():
        return []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if not m:
            continue
        name = m.group(1).strip()
        if "$" in name:
            continue
        names.append(_normalize_heading(name))
    return names


def check() -> list[str]:
    """执行全部检查，返回错误信息列表（空 = 通过）。"""
    errors: list[str] = []
    registry = _load_registry_types()

    # ── 1. _index.md §1 的 doc_type 集合 == 注册表 ──
    index_types = _index_section1_types()
    if set(index_types) != set(registry):
        missing = sorted(set(registry) - set(index_types))
        extra = sorted(set(index_types) - set(registry))
        if missing:
            errors.append(f"_index.md §1 缺少注册类型: {missing}")
        if extra:
            errors.append(f"_index.md §1 含未注册类型: {extra}")
    for doc_type, fname in sorted(index_types.items()):
        expected = registry.get(doc_type, {}).get("template")
        if expected and fname != expected:
            errors.append(
                f"_index.md §1 文件名不一致: {doc_type} 标注 {fname}，注册表为 {expected}"
            )

    # ── 2. §3 路由表引用的章节名必须落在能力文件（或模板）中 ──
    for doc_type, raw, tokens in _index_section3_rows():
        if doc_type not in registry:
            errors.append(f"_index.md §3 引用了未注册类型: {doc_type}")
            continue
        known = set(_capability_fixed_sections(doc_type))
        source = "能力文件"
        if not known:
            known = set(_template_sections(registry[doc_type]["template"]))
            source = "模板"
        unknown = [t for t in tokens if t not in known]
        if unknown:
            errors.append(
                f"_index.md §3 中 {doc_type} 的章节名在{source}中不存在: {unknown}"
                f"（{source}实际章节: {sorted(known)}）"
            )

    # ── 3. templates 目录与注册表恰好互为镜像 ──
    registered_templates = {t["template"] for t in registry.values()}
    on_disk = {p.name for p in TEMPLATES_DIR.glob("*.md")}
    unregistered = sorted(on_disk - registered_templates)
    absent = sorted(registered_templates - on_disk)
    if unregistered:
        errors.append(f"src/app/templates/ 存在未注册模板: {unregistered}")
    if absent:
        errors.append(f"src/app/templates/ 缺少注册模板: {absent}")

    # ── 4. 能力库文件与注册表恰好互为镜像，且无空文件 ──
    cap_files = {p.name for p in CAPS_DIR.glob("*.md")}
    expected_caps = {f"{dt}.md" for dt in registry} | {"_index.md"}
    cap_unregistered = sorted(cap_files - expected_caps)
    cap_absent = sorted(expected_caps - cap_files)
    if cap_unregistered:
        errors.append(f"doc-capabilities/ 存在未注册能力文件: {cap_unregistered}")
    if cap_absent:
        errors.append(f"doc-capabilities/ 缺少能力文件: {cap_absent}")
    for path in sorted(CAPS_DIR.glob("*.md")):
        if not path.read_text(encoding="utf-8").strip():
            errors.append(f"doc-capabilities/{path.name} 是空文件（疑似残留占位）")

    # ── 5. 两个目录都不残留已下线类型的文件 ──
    for base in (TEMPLATES_DIR, CAPS_DIR):
        for path in sorted(base.glob("*.md")):
            if path.name in LEGACY_FILENAMES:
                errors.append(f"{base.name}/ 残留已下线类型文件: {path.name}")

    # ── 6. 模板与能力文件不残留旧章节号引用 ──
    for base in (TEMPLATES_DIR, CAPS_DIR):
        for path in sorted(base.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for ref in STALE_SECTION_REFS:
                if ref in text:
                    errors.append(f"{base.name}/{path.name} 残留旧章节号引用: {ref}")

    # ── 7. 指南不存在重复的小节编号 ──
    if GUIDE.exists():
        seen: dict[str, int] = {}
        for line in GUIDE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^#{3,4}\s+(\d+\.\d+(?:\.\d+)?)\s", line)
            if not m:
                continue
            seen[m.group(1)] = seen.get(m.group(1), 0) + 1
        dups = sorted(n for n, c in seen.items() if c > 1)
        if dups:
            errors.append(f"指南存在重复小节编号: {dups}")
    else:
        errors.append(f"未找到指南文件: {GUIDE.name}")

    # ── 8. _index.md 必须含「权威分层与引用纪律」节（文档模型第三级）──
    index_text = INDEX_MD.read_text(encoding="utf-8")
    if "权威分层与引用纪律" not in index_text:
        errors.append("_index.md 缺少「权威分层与引用纪律」节（文档模型第三级）")
    elif "禁止反向" not in index_text:
        errors.append("_index.md 的权威分层节缺少指针方向规则（feature → module → top，禁止反向）")

    return errors


def main() -> None:
    errors = check()
    if errors:
        print("!! 文档一致性检查发现以下问题：\n")
        for e in errors:
            print(f"  - {e}")
        print()
        sys.exit(1)

    registry = _load_registry_types()
    print("OK 文档一致性检查通过")
    print(f"   注册类型: {len(registry)} 种")
    print(f"   模板文件: {len(list(TEMPLATES_DIR.glob('*.md')))} 个")
    print(f"   能力文件: {len(list(CAPS_DIR.glob('*.md')))} 个（含 _index.md）")
    print(f"   路由章节: {len(_index_section3_rows())} 行已校验")


if __name__ == "__main__":
    main()

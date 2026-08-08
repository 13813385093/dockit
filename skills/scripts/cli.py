#!/usr/bin/env python3
"""doc-kit skills CLI — 议题与文档管理命令行工具（取代原 MCP 服务器）。

Stdlib-only command line interface for skills. Each subcommand mirrors the
behaviour of the former MCP tools with identical validation logic.

用法:
    python .doc-kit/cli/cli.py [--root <项目目录>] spec status
    python .doc-kit/cli/cli.py [--root <项目目录>] spec read
    python .doc-kit/cli/cli.py [--root <项目目录>] spec write --json '<spec_json>'   # 或从 stdin 读入
    python .doc-kit/cli/cli.py [--root <项目目录>] spec archive
    python .doc-kit/cli/cli.py [--root <项目目录>] spec schema
    python .doc-kit/cli/cli.py [--root <项目目录>] doc structure
    python .doc-kit/cli/cli.py [--root <项目目录>] doc read <path>
    python .doc-kit/cli/cli.py [--root <项目目录>] doc update-section <reference> --content '<text>'
    python .doc-kit/cli/cli.py [--root <项目目录>] doc add-section <reference> '<heading>' [--content '<text>'] [--level sibling|child]
    python .doc-kit/cli/cli.py [--root <项目目录>] doc new <doc_type> [--module <模块名>] [--feature <功能名>] [--author <负责人>]
    python .doc-kit/cli/cli.py [--root <项目目录>] doc remove-section <reference>
    python .doc-kit/cli/cli.py [--root <项目目录>] review anchor-get
    python .doc-kit/cli/cli.py [--root <项目目录>] review anchor-set <commit_hash> [--session <sid>]
    python .doc-kit/cli/cli.py [--root <项目目录>] review report-write [--content '<md>'] [--file <path>]

项目目录解析优先级: --root > DOC_KIT_PROJECT_ROOT 环境变量 > 从 cwd 向上查找
（含 .doc-kit/ 或 SessionSpec/ 的最近祖先目录）。

退出码: 0 = 成功（含业务拒绝时输出 success=false 的 JSON）；1 = 参数或运行时错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from docmodel import (  # noqa: E402
    DocContent,
    DocMeta,
    DocStructure,
    _find_doc,
    _simplify_depends_on,
    safe_join,
)
from frontmatter import FrontmatterParser, _parse_yaml_block  # noqa: E402
from index import IndexEntry, IndexManager  # noqa: E402
from spec_schema import (  # noqa: E402
    SCENARIO_DOC_TYPES,
    get_schema_metadata,
    render_summary,
    validate as validate_spec,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
#  项目根发现
# ═══════════════════════════════════════════════════════════════


def _is_valid_project(path: Path) -> bool:
    """doc-kit 项目：存在 .doc-kit/ 或 SessionSpec/ 目录。"""
    return (path / ".doc-kit").is_dir() or (path / "SessionSpec").is_dir()


def find_project_root(cli_arg: str | None = None) -> Path:
    """解析项目根目录：--root > DOC_KIT_PROJECT_ROOT > cwd 向上查找。"""
    candidates: list[Path] = []
    if cli_arg:
        candidates.append(Path(cli_arg).resolve())
    env_val = os.environ.get("DOC_KIT_PROJECT_ROOT")
    if env_val:
        candidates.append(Path(env_val).resolve())
    candidates.append(Path.cwd().resolve())

    for cand in candidates:
        if _is_valid_project(cand):
            return cand

    # 从 cwd 向上查找（候选本身无效时）
    current = Path.cwd().resolve()
    for parent in (current, *current.parents):
        if _is_valid_project(parent):
            return parent

    raise RuntimeError(
        "未找到 doc-kit 项目目录。请通过 --root <路径> 指定，或设置 DOC_KIT_PROJECT_ROOT 环境变量。\n"
        "项目目录必须包含 .doc-kit/ 或 SessionSpec/ 目录。"
    )


def _load_index(project_root: Path) -> IndexManager | None:
    index_path = project_root / ".doc-kit" / "index.json"
    if not index_path.exists():
        return None
    return IndexManager(index_path)


# ═══════════════════════════════════════════════════════════════
#  SessionSpec 路径与状态
# ═══════════════════════════════════════════════════════════════


def _spec_path(project_root: Path, session_spec_id: str) -> Path:
    return project_root / "SessionSpec" / "active" / f"{session_spec_id}.spec.json"


def _archive_path(project_root: Path, session_spec_id: str) -> Path:
    return project_root / "SessionSpec" / "archive" / f"{session_spec_id}.spec.json"


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _detect_active_session(project_root: Path) -> str | None:
    active_dir = project_root / "SessionSpec" / "active"
    if not active_dir.is_dir():
        return None
    specs = sorted(active_dir.glob("*.spec.json"))
    if len(specs) == 0:
        return None
    if len(specs) == 1:
        return specs[0].stem.replace(".spec", "")
    raise ValueError(f"存在多个活跃 SessionSpec（{len(specs)} 个），违反了串行约束。")


def _read_spec_file(project_root: Path, session_spec_id: str) -> dict | None:
    path = _spec_path(project_root, session_spec_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_spec_file(project_root: Path, spec: dict) -> None:
    sid = spec["session_spec_id"]
    path = _spec_path(project_root, sid)
    _ensure_dir(path)
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")


def _generate_spec_id(topic: str) -> str:
    today = datetime.now().strftime("%Y%m%d")
    clean = re.sub(r"[^a-zA-Z0-9\-]", "-", topic)
    clean = re.sub(r"-+", "-", clean).strip("-").lower()
    return f"{today}-{clean}"


# ═══════════════════════════════════════════════════════════════
#  spec 子命令（对应原 spec_status / spec_schema / spec_read /
#  spec_write / spec_archive）
# ═══════════════════════════════════════════════════════════════


def cmd_spec_status(project_root: Path) -> str:
    """检查当前议题状态并给出下一步操作指引。返回纯文本。"""
    active_dir = project_root / "SessionSpec" / "active"
    archive_dir = project_root / "SessionSpec" / "archive"
    if not active_dir.is_dir() or not archive_dir.is_dir():
        active_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        return "✅ 项目已初始化，SessionSpec/ 目录已就绪。当前无活跃议题，可参考 spec-start 流程开启新议题。"

    try:
        sid = _detect_active_session(project_root)
    except ValueError as e:
        return f"错误: {e}"

    if sid is None:
        return "当前没有活跃议题。可参考 spec-start 流程开启新议题。"

    spec = _read_spec_file(project_root, sid)
    if spec is None:
        return "当前会话已失效（文件不存在）。可参考 spec-start 流程开启新议题。"

    status = spec.get("status", "active")
    if status == "active":
        return f"当前有活跃议题：**{sid}**。请调用 spec read 读取完整内容。"
    if status == "closed":
        return f"当前有已关闭但未归档的议题：**{sid}**。请调用 spec archive 归档。"
    if status == "abandoned":
        return f"当前有已作废但未归档的议题：**{sid}**。请调用 spec archive 归档。"

    return f"当前文件状态异常: {sid} (status={status})"


def cmd_spec_schema(project_root: Path) -> str:
    """返回 SpecStruct 的完整字段定义（JSON 文本）。"""
    metadata = get_schema_metadata()
    return json.dumps(metadata, indent=2, ensure_ascii=False)


def cmd_spec_read(project_root: Path) -> str:
    """读取当前活跃议题的完整内容（JSON 文本）。"""
    try:
        sid = _detect_active_session(project_root)
    except ValueError as e:
        return f"错误: {e}"
    if sid is None:
        return "当前没有活跃议题。可参考 spec-start 流程开启新议题。"

    spec = _read_spec_file(project_root, sid)
    if spec is None:
        return "错误: 文件不存在"
    return json.dumps(spec, indent=2, ensure_ascii=False)


def cmd_spec_write(project_root: Path, spec_json: str) -> str:
    """写入完整的议题数据（全量替换模式）。返回 JSON 包装文本。"""
    if len(spec_json) > 1_000_000:
        return _fail("数据量过大（超过 1MB），请精简后再试")
    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError as e:
        return _fail(f"不是合法 JSON: {e}")
    if not isinstance(data, dict):
        return _fail("必须是一个 JSON 对象")

    for field in ("session_spec_id", "scenario", "status"):
        if field not in data:
            return _fail(f"缺少必填字段 '{field}'")

    sid = data["session_spec_id"]
    spec_path = _spec_path(project_root, sid)
    existing = None
    if spec_path.exists():
        try:
            existing = json.loads(spec_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    if existing is None:
        # ——— 新创建 ———
        docs_root = project_root / "ProjectSpec"
        if not docs_root.is_dir() or not list(docs_root.rglob("*.md")):
            return _fail("未找到 ProjectSpec/ 或项目规格文档。请先创建项目规格文档后再开启议题。")
        try:
            recovered = _detect_active_session(project_root)
            if recovered:
                return _fail(f"SessionSpec/active/ 下存在残留文件，请先处理后再创建新议题。")
        except ValueError as e:
            return _fail(f"检测活跃会话失败: {e}")
        if spec_path.exists():
            return _fail(f"session_spec_id '{sid}' 已存在，请使用其他名称。")

        data.setdefault("project", project_root.name)
        data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        # related_doc_types 由 scenario 自动推导（spec_schema.SCENARIO_DOC_TYPES），与能力库 _index §2 路由同源
        data["related_doc_types"] = SCENARIO_DOC_TYPES.get(data.get("scenario", ""), [])
        data.setdefault("resolutions", [])
        data.setdefault("pending_decisions", [])
        data.setdefault("next_steps", [])
        data.setdefault("closed_at", None)
        data.setdefault("closed_reason", None)
    else:
        # ——— 更新 ———
        for fld in ("session_spec_id", "project", "created_at"):
            if fld in data and data[fld] != existing.get(fld):
                return _fail(
                    f"字段 '{fld}' 不可修改（只读）。"
                    f" 已有值: '{existing.get(fld)}'，提交值: '{data[fld]}'"
                )

        old_status = existing.get("status", "active")
        new_status = data.get("status", old_status)
        if old_status != new_status:
            allowed = {"active": {"closed", "abandoned"}, "closed": set(), "abandoned": set()}
            if new_status not in allowed.get(old_status, set()):
                return _fail(
                    f"状态 {old_status} → {new_status} 不合法。"
                    f" active 可转为 closed 或 abandoned；closed/abandoned 不可再变更。"
                )

        if new_status in ("closed", "abandoned") and not data.get("closed_reason"):
            labels = {"closed": "关闭", "abandoned": "作废"}
            return _fail(f"status 为 {new_status} 时必须提供 {labels[new_status]}原因（closed_reason）。")

        for fld in ("project", "created_at", "related_doc_types"):
            if fld not in data:
                data[fld] = existing.get(fld, "")

    errors = validate_spec(data)
    if errors:
        enhanced = []
        for e in errors:
            if "最小 150 字符" in e:
                enhanced.append(f"  - {e} — 建议补充决策理由、约束条件或影响范围。")
            elif "不在允许范围内" in e:
                enhanced.append(f"  - {e} — 请检查是否拼写错误。")
            else:
                enhanced.append(f"  - {e}")
        return _fail("Schema 校验失败:\n" + "\n".join(enhanced))

    _write_spec_file(project_root, data)

    summary = render_summary(data)
    result = f"## ✅ 议题已保存\n\n{summary}"

    if existing is not None:
        existing_res = existing.get("resolutions", [])
        new_res = data.get("resolutions", [])
        if existing_res and not new_res:
            result += f"\n\n⚠️ **注意**：提交的 resolutions 为空，但该议题原有 {len(existing_res)} 条决议。如果是有意清空请忽略此提示。"

    if data.get("status") == "closed":
        result += "\n\n**下一步建议**：调用 spec archive 归档已关闭的议题。"
    elif data.get("status") == "abandoned":
        result += "\n\n**下一步建议**：调用 spec archive 归档已作废的议题。"
    else:
        result += "\n\n**下一步建议**：调用 doc structure 查看文档结构，将决议写入对应文档。"

    return _ok(
        message=result,
        data={"session_spec_id": sid, "status": data.get("status")},
    )


def cmd_spec_archive(project_root: Path) -> str:
    """归档已关闭或已作废的议题（active → archive）。"""
    try:
        sid = _detect_active_session(project_root)
    except ValueError as e:
        return _fail(str(e))
    if sid is None:
        return _fail("当前没有可归档的议题（active 目录为空）。")
    spec = _read_spec_file(project_root, sid)
    if spec is None:
        return _fail("错误: 文件不存在")
    status = spec.get("status")
    if status not in ("closed", "abandoned"):
        return _fail(f"议题 {sid} 状态为 {status}，只有 closed 或 abandoned 的议题才能归档。请先通过 spec write 设置正确状态。")
    src = _spec_path(project_root, sid)
    dst = _archive_path(project_root, sid)
    _ensure_dir(dst)
    src.replace(dst)
    return _ok(
        message=f"## ✅ 议题已归档\n\n**议题**: {sid}\n\n已移至 SessionSpec/archive/。",
        data={"session_spec_id": sid, "status": status},
    )


# ═══════════════════════════════════════════════════════════════
#  doc 子命令（对应原 read_doc / update_section / add_section /
#  doc_structure；新增 new / remove-section）
# ═══════════════════════════════════════════════════════════════

# 18 种文档类型注册表（与 app/engine/registry.py 的 DEFAULT_TYPES 一致）。
# doc_type → level/template；composite 标记精简模式复合类型。
DOC_TYPE_REGISTRY = [
    # Level 0 - Top
    {"doc_type": "business_context", "level": "top", "template": "business-context.md"},
    {"doc_type": "technical_framework", "level": "top", "template": "technical-framework.md"},
    {"doc_type": "non_functional_constraints", "level": "top", "template": "non-functional-constraints.md"},
    {"doc_type": "global_policies", "level": "top", "template": "global-policies.md"},
    {"doc_type": "inter_module_contract", "level": "top", "template": "inter-module-contracts.md"},
    {"doc_type": "stakeholders", "level": "top", "template": "stakeholders.md"},
    {"doc_type": "release_policy", "level": "top", "template": "release-policy.md"},
    {"doc_type": "charter", "level": "top", "template": "charter.md", "composite": True},
    # Level 1 - Module
    {"doc_type": "architecture", "level": "module", "template": "architecture.md"},
    {"doc_type": "domain_model", "level": "module", "template": "domain-model.md"},
    {"doc_type": "module_manifest", "level": "module", "template": "module-manifest.md"},
    {"doc_type": "integration", "level": "module", "template": "integration.md"},
    {"doc_type": "module_design", "level": "module", "template": "module-design.md", "composite": True},
    # Level 2 - Feature
    {"doc_type": "feature_design", "level": "feature", "template": "feature-design.md"},
    {"doc_type": "decision_log", "level": "feature", "template": "decision-log.md"},
    {"doc_type": "unit_test", "level": "feature", "template": "unit-tests.md"},
    {"doc_type": "acceptance_test", "level": "feature", "template": "acceptance-tests.md"},
    {"doc_type": "feature_package", "level": "feature", "template": "feature-package.md", "composite": True},
]




def _parse_module_path(module: str) -> tuple[str, str | None]:
    """解析模块路径（点分）：'order' → ('order', None)；'order.core' → ('order', 'sub-modules/core')。"""
    parts = module.split(".")
    main = parts[0]
    if len(parts) == 1:
        return main, None
    sub_parts: list[str] = []
    for p in parts[1:]:
        sub_parts.append("sub-modules")
        sub_parts.append(p)
    return main, "/".join(sub_parts)


def cmd_doc_read(project_root: Path, doc_path: str) -> str:
    """读取指定文档的完整内容，按段落层级拍平成 JSON。"""
    full_path = _find_doc(project_root, doc_path)
    if not full_path:
        return _fail(f"未找到文档: {doc_path}，可用 doc structure 查看所有文档路径")
    try:
        raw_text = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return _fail(f"读取文档失败: {e}")
    try:
        meta_dict, body = FrontmatterParser.parse(raw_text)
    except Exception:
        meta_dict, body = {}, raw_text

    rel_path = str(full_path.relative_to(project_root).as_posix())

    index = _load_index(project_root)
    index_depends_on: list[str] = []
    index_mtime = ""
    if index:
        entry = index.get_entry(rel_path)
        if entry:
            index_mtime = entry.mtime
            index_depends_on = _simplify_depends_on(entry.depends_on)

    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""),
        module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""),
        version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"),
        mtime=index_mtime,
    )
    content = DocContent.from_body(rel_path, doc_meta, body, raw_frontmatter=meta_dict)
    data = content.to_dict()
    data["depends_on"] = index_depends_on

    suggestions = [
        "如需修改某个段落，请调用 doc update-section <reference> --content ...",
        "如需新增段落，请调用 doc add-section <reference> <heading> [--content ...]",
    ]
    if index_depends_on:
        dep_list = "、".join(index_depends_on)
        suggestions.append(f"该文档依赖: {dep_list}，可调用 doc read 查看依赖文档了解上下文")

    return _ok(data=data, suggestions=suggestions)


def cmd_doc_update_section(project_root: Path, reference: str, content: str) -> str:
    """更新文档中指定段落的正文内容，自动写回文件。"""
    file_rel = reference.split("#")[0]
    doc_rel = file_rel if file_rel.startswith("ProjectSpec/") else f"ProjectSpec/{file_rel}"
    safe_path = safe_join(project_root, doc_rel)
    if safe_path is None:
        return _fail(f"非法的路径: {file_rel}")
    full_path = safe_path
    if not full_path.exists():
        return _fail(f"文件不存在: {file_rel}")
    try:
        raw_text = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return _fail(f"读取文件失败: {e}")
    try:
        meta_dict, body = FrontmatterParser.parse(raw_text)
    except Exception:
        meta_dict, body = {}, raw_text
    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""), module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""), version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"), mtime="",
    )
    doc_content = DocContent.from_body(file_rel, doc_meta, body, raw_frontmatter=meta_dict)
    section = doc_content.get_section(reference)
    if section is None:
        return _fail(f"未找到段落: {reference}，可用 doc read 查看所有段落 reference")
    old_content = section.content
    section.content = content
    try:
        new_markdown = doc_content.to_markdown()
        full_path.write_text(new_markdown, encoding="utf-8")
    except Exception as e:
        section.content = old_content
        return _fail(f"写回文件失败: {e}")
    return _ok(suggestions=["段落已更新，可通过 doc read 读取最新文档内容验证"])


def cmd_doc_add_section(project_root: Path, reference: str, heading: str, content: str, level: str) -> str:
    """在文档中新增一个段落，自动写回文件。"""
    file_rel = reference.split("#")[0]
    doc_rel = file_rel if file_rel.startswith("ProjectSpec/") else f"ProjectSpec/{file_rel}"
    safe_path = safe_join(project_root, doc_rel)
    if safe_path is None:
        return _fail(f"非法的路径: {file_rel}")
    full_path = safe_path
    if not full_path.exists():
        return _fail(f"文件不存在: {file_rel}")
    if not heading.strip():
        return _fail("heading 不能为空")
    try:
        raw_text = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return _fail(f"读取文件失败: {e}")
    try:
        meta_dict, body = FrontmatterParser.parse(raw_text)
    except Exception:
        meta_dict, body = {}, raw_text
    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""), module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""), version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"), mtime="",
    )
    if level not in ("sibling", "child"):
        return _fail("level 参数仅支持 'sibling' 或 'child'")
    doc_content = DocContent.from_body(file_rel, doc_meta, body, raw_frontmatter=meta_dict)
    level_offset = 1 if level == "child" else 0
    try:
        new_section = doc_content.insert_section(reference, heading.strip(), content.strip(), level_offset=level_offset)
    except ValueError as e:
        return _fail(str(e))
    try:
        new_markdown = doc_content.to_markdown()
        full_path.write_text(new_markdown, encoding="utf-8")
    except Exception as e:
        doc_content.sections = [s for s in doc_content.sections if s.reference != new_section.reference]
        return _fail(f"写回文件失败: {e}")
    return _ok(suggestions=[f"段落「{heading}」已新增，可通过 doc read 读取最新文档内容验证"])


def _load_registry(project_root: Path) -> dict | None:
    """从 .doc-kit/registry.yaml 加载 doc_type 注册表；缺失或解析失败返回 None（回退内置）。"""
    reg_path = project_root / ".doc-kit" / "registry.yaml"
    if not reg_path.exists():
        return None
    try:
        raw = _parse_yaml_block(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    types = raw.get("types") or []
    result: dict[str, dict] = {}
    for t in types:
        if isinstance(t, dict) and t.get("doc_type"):
            result[t["doc_type"]] = {k: v for k, v in t.items() if v is not None}
    return result or None


def cmd_doc_new(
    project_root: Path,
    doc_type: str,
    module: str | None = None,
    feature: str | None = None,
    author: str | None = None,
) -> str:
    """新增文档：按 registry 自动定位模板（.doc-kit/templates/）与目标目录，渲染后写入并更新索引。"""
    # 注册表：优先 .doc-kit/registry.yaml（用户可自定义），缺失回退内置
    registry = _load_registry(project_root) or {d["doc_type"]: d for d in DOC_TYPE_REGISTRY}
    defn = registry.get(doc_type)
    if defn is None:
        candidates = "、".join(sorted(registry))
        return _fail(
            f"ERROR [new_doc.unknown_type] 未知的文档类型 '{doc_type}'。"
            f"修复：从已注册类型中选择其一（{candidates}），详见 doc-capabilities/_index.md §1。"
        )
    level = defn["level"]
    # 复合性是体系固有属性（engine 用 property 判定，registry.yaml 未必带 composite 字段），
    # 因此以内置集合兜底：defn 显式声明或属于内置复合类型即视为复合
    is_composite = defn.get("composite", False) or doc_type in {"charter", "module_design", "feature_package"}

    # —— 参数与层级匹配校验 ——
    if level == "module" and not module:
        return _fail(
            f"ERROR [new_doc.missing_module] '{doc_type}' 为模块级类型，缺少 --module。"
            "修复：补 --module <模块名>（子模块用点分，如 order.core）。"
        )
    if level == "feature":
        missing = [n for n, v in (("--module", module), ("--feature", feature)) if not v]
        if missing:
            return _fail(
                f"ERROR [new_doc.missing_param] '{doc_type}' 为功能级类型，缺少 {', '.join(missing)}。"
                "修复：补全参数后重试。"
            )
    if level == "top" and module:
        return _fail(
            f"ERROR [new_doc.top_module_not_allowed] '{doc_type}' 为顶层类型，不接受 --module。"
            "修复：去掉 --module 重试。"
        )

    docs_root = project_root / "ProjectSpec"
    if not docs_root.is_dir():
        return _fail("ERROR [new_doc.no_docs] 未找到 ProjectSpec/ 目录。修复：先运行项目初始化。")

    # —— 精简模式：仅允许复合类型 ——
    if (docs_root / "charter.md").exists() and not is_composite:
        return _fail(
            f"ERROR [new_doc.minimal_profile] 项目处于精简模式（charter.md 存在），不能创建独立基础文档 '{doc_type}'。"
            "修复：写入 charter.md 对应章节，或先执行文档拆分（§3.7）。"
        )

    # —— 计算目标路径 ——
    if level == "top":
        target = docs_root / defn["template"]
    else:
        main_module, sub_path = _parse_module_path(module)
        module_dir = docs_root / f"module-{main_module}"
        if sub_path:
            module_dir = module_dir / sub_path
        if not module_dir.is_dir():
            if is_composite:
                # 复合类型（模块骨架）允许自动创建目录
                module_dir.mkdir(parents=True, exist_ok=True)
            else:
                return _fail(
                    f"ERROR [new_doc.module_not_found] 模块 '{module}' 不存在（期望目录 "
                    f"{module_dir.relative_to(project_root).as_posix()}）。修复：先创建模块骨架，"
                    f"如 doc new module_design --module {main_module}。"
                )
        if level == "module":
            target = module_dir / defn["template"]
        else:
            feature_dir = module_dir / "features" / feature
            if not feature_dir.is_dir():
                if is_composite:
                    feature_dir.mkdir(parents=True, exist_ok=True)
                else:
                    return _fail(
                        f"ERROR [new_doc.feature_not_found] 功能 '{feature}' 不存在（期望目录 "
                        f"{feature_dir.relative_to(project_root).as_posix()}）。修复：先创建功能骨架，"
                        f"如 doc new feature_package --module {module} --feature {feature}。"
                    )
            target = feature_dir / defn["template"]

    rel_target = str(target.relative_to(project_root).as_posix())
    if target.exists():
        return _fail(
            f"ERROR [new_doc.exists] 目标文件已存在: {rel_target}。"
            "修复：改用 doc update-section / add-section，或换一个 doc_type。"
        )

    # —— 渲染模板并写入 ——
    template_path = project_root / ".doc-kit" / "templates" / defn["template"]
    if not template_path.exists():
        return _fail(
            f"ERROR [new_doc.template_missing] 模板缺失: {template_path}。修复：重新运行项目初始化以复制模板。"
        )
    try:
        now = datetime.now().strftime("%Y-%m-%d")
        tpl = Template(template_path.read_text(encoding="utf-8"))
        content = tpl.safe_substitute(
            module=module or "",
            feature=feature or "",
            now=now,
            author=(author or "").strip(),
            project_name=project_root.name,
        )
    except Exception as e:
        return _fail(f"ERROR [new_doc.render_failed] 模板渲染失败: {e}。")

    try:
        meta_dict, _ = FrontmatterParser.parse(content)
    except Exception as e:
        return _fail(f"ERROR [new_doc.render_failed] 渲染结果 frontmatter 解析失败: {e}。")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as e:
        return _fail(f"ERROR [new_doc.write_failed] 写文件失败: {e}。")

    index = _load_index(project_root)
    if index:
        entry = IndexEntry(
            path=rel_target,
            doc_type=doc_type,
            module=str(meta_dict.get("module") or module or "project-charter"),
            level=level,
            version=str(meta_dict.get("version") or "0.1.0"),
            status=str(meta_dict.get("status") or "active"),
            depends_on=[],
            mtime=datetime.now().strftime("%Y-%m-%d"),
        )
        index.add_entry(entry)
        index.save()

    return _ok(
        message=f"## ✅ 文档已创建\n\n**路径**: {rel_target}\n\n**doc_type**: {doc_type}",
        data={"path": rel_target, "doc_type": doc_type, "level": level},
        suggestions=[
            f"可 doc read {rel_target} 查看骨架。",
            "正文按 doc-capabilities/<doc_type>.md 的能力说明填充。",
            "frontmatter 的 version / last_updated / author / depends_on 由人工维护，AI 不修改。",
        ],
    )


def cmd_doc_remove_section(project_root: Path, reference: str) -> str:
    """删除指定段落及其全部子段落，自动写回文件。"""
    file_rel = reference.split("#")[0]
    doc_rel = file_rel if file_rel.startswith("ProjectSpec/") else f"ProjectSpec/{file_rel}"
    safe_path = safe_join(project_root, doc_rel)
    if safe_path is None:
        return _fail(f"ERROR [remove_section.invalid_path] 非法的路径: {file_rel}。")
    full_path = safe_path
    if not full_path.exists():
        return _fail(
            f"ERROR [remove_section.not_found] 文件不存在: {file_rel}。修复：先 doc structure 确认路径。"
        )
    try:
        raw_text = full_path.read_text(encoding="utf-8")
        meta_dict, body = FrontmatterParser.parse(raw_text)
    except Exception as e:
        return _fail(f"ERROR [remove_section.read_failed] 读取文件失败: {e}。")
    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""), module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""), version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"), mtime="",
    )
    doc_content = DocContent.from_body(file_rel, doc_meta, body, raw_frontmatter=meta_dict)
    try:
        removed = doc_content.remove_section(reference)
    except ValueError as e:
        return _fail(
            f"ERROR [remove_section.not_found] {e}。修复：先 doc read 获取正确的段落 reference。"
        )
    try:
        new_markdown = doc_content.to_markdown()
        full_path.write_text(new_markdown, encoding="utf-8")
    except Exception as e:
        return _fail(f"ERROR [remove_section.write_failed] 写回文件失败: {e}。")
    removed_refs = [s.reference for s in removed]
    return _ok(
        message=f"## ✅ 段落已删除\n\n共删除 {len(removed)} 个段落（含子段落）",
        data={"removed": removed_refs},
        suggestions=[f"已从 {file_rel} 删除段落及其子段落，可 doc read 验证。"],
    )


def cmd_doc_structure(project_root: Path) -> str:
    """扫描 ProjectSpec/ 下所有文档，返回 JSON 格式的文档结构树和查找表。"""
    index = _load_index(project_root)
    if not index:
        return _fail("项目索引不存在，请先运行初始化。")
    entries = index.list_entries()
    if not entries:
        return _ok(data={"doc_map": {}})
    structure = DocStructure(project_root, entries)
    doc_map_dict = {k: v.to_dict() for k, v in structure.doc_map.items()}
    return _ok(
        data={"doc_map": doc_map_dict},
        suggestions=["获取文档完整内容请调用 doc read <doc_map中的path值>，如 doc read ProjectSpec/business-context.md"],
    )


# ═══════════════════════════════════════════════════════════════
#  review 子命令（对应原 get_git_history / add_git_history /
#  write_review_report）
# ═══════════════════════════════════════════════════════════════

REVIEW_STATE_DEFAULTS = {
    "last_reviewed_commit": None,
    "last_reviewed_at": None,
    "review_history": [],
}


def _review_state_path(project_root: Path) -> Path:
    return project_root / ".doc-kit" / "code-review-state.json"


def _read_review_state(project_root: Path) -> dict:
    path = _review_state_path(project_root)
    if not path.exists():
        return dict(REVIEW_STATE_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for k, v in REVIEW_STATE_DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, OSError):
        return dict(REVIEW_STATE_DEFAULTS)


def _write_review_state(project_root: Path, state: dict) -> None:
    path = _review_state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_review_anchor_get(project_root: Path) -> str:
    """获取上一次 code review 的 git 提交锚点。"""
    state = _read_review_state(project_root)
    commit = state.get("last_reviewed_commit")
    if not commit:
        return _ok(
            data={"last_reviewed_commit": None, "last_reviewed_at": None, "review_history": []},
            suggestions=["尚无评审记录，将从头开始评审所有提交。"],
        )
    return _ok(
        data={
            "last_reviewed_commit": commit,
            "last_reviewed_at": state.get("last_reviewed_at"),
            "review_history": state.get("review_history", []),
        },
        suggestions=[
            f"上次评审锚点: {commit}",
            f"可用 git log {commit}..HEAD --oneline 查看新增提交。",
        ],
    )


def cmd_review_anchor_set(project_root: Path, commit_hash: str, session_spec_id: str = "") -> str:
    """保存本次 code review 的 git 提交锚点。"""
    if not commit_hash or not commit_hash.strip():
        return _fail("commit_hash 不能为空")
    commit_hash = commit_hash.strip()
    state = _read_review_state(project_root)
    state["last_reviewed_commit"] = commit_hash
    state["last_reviewed_at"] = datetime.now(timezone.utc).isoformat()
    record = {"commit": commit_hash, "time": state["last_reviewed_at"]}
    if session_spec_id:
        record["session"] = session_spec_id
    state.setdefault("review_history", []).append(record)
    _write_review_state(project_root, state)
    return _ok(
        data={"last_reviewed_commit": commit_hash, "last_reviewed_at": state["last_reviewed_at"]},
        suggestions=[f"评审锚点已更新为 {commit_hash}。下次 code review 将从此 commit 开始。"],
    )


REVIEW_REPORT_SECTIONS = {
    "required": [
        ("# ", "报告标题"),
        ("## 基本信息", "基本信息段"),
        ("## 评审热点", "热点区域段"),
    ],
    "recommended": [
        ("## 深入确认项", "确认项段"),
        ("## 未深入比对项", "未深入比对项段"),
        ("## 后续动作", "后续动作段"),
    ],
}


def _validate_review_report(markdown: str) -> list[str]:
    warnings = []
    for heading, label in REVIEW_REPORT_SECTIONS["required"]:
        if heading not in markdown:
            warnings.append(f"缺少必填段落: {label} (以 '{heading}' 开头)")
    for heading, label in REVIEW_REPORT_SECTIONS["recommended"]:
        if heading not in markdown:
            warnings.append(f"建议补充段落: {label} (以 '{heading}' 开头)")
    return warnings


def cmd_review_report_write(project_root: Path, report_markdown: str) -> str:
    """将代码评审报告写入 ReviewSpec/ 目录。"""
    if not report_markdown or not report_markdown.strip():
        return _fail("report_markdown 不能为空")
    warnings = _validate_review_report(report_markdown)
    now = datetime.now()
    filename = f"code-review-{now.strftime('%Y%m%d-%H%M%S')}.md"
    reviews_dir = project_root / "ReviewSpec"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    file_path = reviews_dir / filename
    file_path.write_text(report_markdown.strip() + "\n", encoding="utf-8")

    result = {
        "success": True,
        "data": {"file": filename, "path": str(file_path.relative_to(project_root))},
        "suggestions": [],
    }
    if warnings:
        result["warnings"] = warnings
        result["suggestions"].append(f"报告已写入但格式有 {len(warnings)} 个提示，详见 warnings 字段")
    else:
        result["suggestions"].append("报告格式完整，已写入 ReviewSpec/")
    return json.dumps(result, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
#  文本参数处理
# ═══════════════════════════════════════════════════════════════


def _unescape_text(text: str) -> str:
    """将命令行文本参数中的字面转义序列还原为真实字符。

    Shell 单引号参数中的 `\\n` 会保持字面两字符到达脚本（如 AI 生成的多行
    正文），此处统一还原为换行，避免 `\\n` 作为字符串原样写入文件；
    `\\\\n` 则保留为字面 `\\n`（反斜杠逃生通道）。真实换行符与不含 `\\n`
    的文本原样返回。
    """
    if "\\n" not in text:
        return text
    return re.sub(r"\\\\n|\\n", lambda m: "\\n" if m.group(0) == "\\\\n" else "\n", text)


# ═══════════════════════════════════════════════════════════════
#  输出辅助
# ═══════════════════════════════════════════════════════════════


def _ok(message: str = "", *, data: Any = None, suggestions: list[str] | None = None) -> str:
    return json.dumps(
        {"success": True, "message": message, "data": data, "suggestions": suggestions or []},
        indent=2, ensure_ascii=False,
    )


def _fail(text: str) -> str:
    return json.dumps(
        {"success": False, "data": None, "suggestions": [text]},
        indent=2, ensure_ascii=False,
    )


def _exit_code(out: str) -> int:
    """根据命令输出推断退出码：JSON 看 success 字段；纯文本看是否以「错误:」开头。"""
    if out.lstrip().startswith("{"):
        try:
            return 0 if json.loads(out).get("success", True) else 1
        except json.JSONDecodeError:
            return 0
    return 1 if out.startswith("错误:") else 0


def _emit(text: str, exit_code: int | None = None) -> None:
    print(text)
    sys.exit(exit_code if exit_code is not None else _exit_code(text))


# ═══════════════════════════════════════════════════════════════
#  argparse
# ═══════════════════════════════════════════════════════════════


def _read_stdin() -> str:
    return sys.stdin.read()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli.py", description="doc-kit skills CLI")
    parser.add_argument("--root", help="doc-kit 项目根目录（默认从 cwd 向上查找）")
    sub = parser.add_subparsers(dest="group", required=True)

    # ── spec ──
    spec = sub.add_parser("spec", help="议题（SessionSpec）操作")
    spec_sub = spec.add_subparsers(dest="command", required=True)
    spec_sub.add_parser("status", help="检查议题状态")
    spec_sub.add_parser("read", help="读取活跃议题")
    spec_sub.add_parser("archive", help="归档已关闭/已作废议题")
    spec_sub.add_parser("schema", help="输出 SpecStruct 字段定义")
    spec_write_p = spec_sub.add_parser("write", help="写入完整议题数据（全量替换）")
    spec_write_p.add_argument("--json", help="完整 spec JSON；未提供时从 stdin 读取")

    # ── doc ──
    doc = sub.add_parser("doc", help="文档（ProjectSpec）操作")
    doc_sub = doc.add_subparsers(dest="command", required=True)
    doc_sub.add_parser("structure", help="文档结构树")
    doc_read_p = doc_sub.add_parser("read", help="读取文档（按段落拍平）")
    doc_read_p.add_argument("path", help="文档路径，可带或不带 ProjectSpec/ 前缀")
    doc_upd_p = doc_sub.add_parser("update-section", help="更新段落正文")
    doc_upd_p.add_argument("reference", help="段落引用，如 ProjectSpec/arch.md#模块概述")
    doc_upd_p.add_argument("--content", required=True, help="新的正文内容")
    doc_add_p = doc_sub.add_parser("add-section", help="新增段落")
    doc_add_p.add_argument("reference", help="锚点段落引用")
    doc_add_p.add_argument("heading", help="新段落标题")
    doc_add_p.add_argument("--content", default="", help="正文内容")
    doc_add_p.add_argument("--level", default="sibling", choices=["sibling", "child"], help="同级或子级插入")
    doc_new_p = doc_sub.add_parser("new", help="新增文档（按 registry 自动定位模板与目录）")
    doc_new_p.add_argument("doc_type", help="文档类型，如 business_context / feature_design")
    doc_new_p.add_argument("--module", default=None, help="模块名（module/feature 级必填；子模块用点分，如 order.core）")
    doc_new_p.add_argument("--feature", default=None, help="功能名（仅 feature 级必填）")
    doc_new_p.add_argument("--author", default=None, help="文档负责人（可选；留空则交人工维护）")
    doc_rm_p = doc_sub.add_parser("remove-section", help="删除段落及其全部子段落")
    doc_rm_p.add_argument("reference", help="段落引用，如 ProjectSpec/arch.md#模块概述")

    review = sub.add_parser("review", help="代码评审锚点与报告")
    review_sub = review.add_subparsers(dest="command", required=True)
    review_sub.add_parser("anchor-get", help="获取评审锚点")
    anchor_set_p = review_sub.add_parser("anchor-set", help="保存评审锚点")
    anchor_set_p.add_argument("commit_hash", help="本次评审到的完整 commit hash")
    anchor_set_p.add_argument("--session", default="", help="关联的议题 ID（可选）")
    report_p = review_sub.add_parser("report-write", help="写入评审报告到 ReviewSpec/")
    report_p.add_argument("--content", help="报告 Markdown；未提供时从 --file 或 stdin 读取")
    report_p.add_argument("--file", help="报告 Markdown 文件路径")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        project_root = find_project_root(getattr(args, "root", None))
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    try:
        if args.group == "spec":
            if args.command == "status":
                _emit(cmd_spec_status(project_root))
            elif args.command == "read":
                _emit(cmd_spec_read(project_root))
            elif args.command == "schema":
                _emit(cmd_spec_schema(project_root))
            elif args.command == "archive":
                _emit(cmd_spec_archive(project_root))
            elif args.command == "write":
                spec_json = args.json if args.json is not None else _read_stdin()
                _emit(cmd_spec_write(project_root, spec_json))
        elif args.group == "doc":
            if args.command == "structure":
                _emit(cmd_doc_structure(project_root))
            elif args.command == "read":
                _emit(cmd_doc_read(project_root, args.path))
            elif args.command == "update-section":
                _emit(cmd_doc_update_section(project_root, args.reference, _unescape_text(args.content)))
            elif args.command == "add-section":
                _emit(cmd_doc_add_section(project_root, args.reference, args.heading, _unescape_text(args.content), args.level))
            elif args.command == "new":
                _emit(cmd_doc_new(project_root, args.doc_type, args.module, args.feature, args.author))
            elif args.command == "remove-section":
                _emit(cmd_doc_remove_section(project_root, args.reference))
        elif args.group == "review":
            if args.command == "anchor-get":
                _emit(cmd_review_anchor_get(project_root))
            elif args.command == "anchor-set":
                _emit(cmd_review_anchor_set(project_root, args.commit_hash, args.session))
            elif args.command == "report-write":
                content = args.content
                from_file = False
                if content is None and args.file:
                    content = Path(args.file).read_text(encoding="utf-8")
                    from_file = True
                if content is None:
                    content = _read_stdin()
                if not from_file:
                    content = _unescape_text(content)
                _emit(cmd_review_report_write(project_root, content))
    except Exception as e:  # 未预期的运行时错误：输出到 stderr 便于调试
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

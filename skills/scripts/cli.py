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
    python .doc-kit/cli/cli.py [--root <项目目录>] dev status
    python .doc-kit/cli/cli.py [--root <项目目录>] dev plan create --scope <module|feature> --target <范围> [--module <模块>] [--title <标题>] [--session <id>]
    python .doc-kit/cli/cli.py [--root <项目目录>] dev plan read
    python .doc-kit/cli/cli.py [--root <项目目录>] dev plan update-section <reference> --content '<正文>'
    python .doc-kit/cli/cli.py [--root <项目目录>] dev plan add-section <reference> '<标题>' [--content '<正文>'] [--level sibling|child]
    python .doc-kit/cli/cli.py [--root <项目目录>] dev task list
    python .doc-kit/cli/cli.py [--root <项目目录>] dev task set --json '<tasks 数组>'
    python .doc-kit/cli/cli.py [--root <项目目录>] dev task update <task_id> --status <状态> [--note '<备注>']
    python .doc-kit/cli/cli.py [--root <项目目录>] dev task annotate <task_id> --note '<备注>'
    python .doc-kit/cli/cli.py [--root <项目目录>] dev align --feature <功能名> --module <模块名> --status <aligned|done> [--note]
    python .doc-kit/cli/cli.py [--root <项目目录>] dev integrate --module <模块名> --status <integrated|documented|done> [--note]
    python .doc-kit/cli/cli.py [--root <项目目录>] dev notes append --content '<md>' [--section <章节名>]
    python .doc-kit/cli/cli.py [--root <项目目录>] dev report-write --kind <feature|module> --name <目标> --content '<md>'
    python .doc-kit/cli/cli.py [--root <项目目录>] dev close --reason '<原因>'
    python .doc-kit/cli/cli.py [--root <项目目录>] dev abort --reason '<原因>'
    python .doc-kit/cli/cli.py [--root <项目目录>] dev archive

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
    # 先建目录再判定状态：archive/ 缺失只说明项目还没走过归档，不代表没有
    # 活跃议题。若在此直接返回「无活跃议题」，会与 spec read / 实际文件状态
    # 互相矛盾（首次 status 晚于创建议题时尤其明显）。
    first_time = not active_dir.is_dir() or not archive_dir.is_dir()
    active_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    try:
        sid = _detect_active_session(project_root)
    except ValueError as e:
        return f"错误: {e}"

    if sid is None:
        if first_time:
            return "✅ 项目已初始化，SessionSpec/ 目录已就绪。当前无活跃议题，可参考 spec-start 流程开启新议题。"
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
        # 议程结清护栏：关闭时尚有未 resolved 的议程时如实提示。宁可看到这条
        # 提示，也不允许为了关闭把待决议项谎报为 resolved（deferred / blocked
        # 才是诚实的处置方式）。
        unresolved = [
            str(p.get("topic", "?"))
            for p in data.get("pending_decisions", [])
            if p.get("status") != "resolved"
        ]
        if unresolved:
            shown = "、".join(unresolved[:5]) + ("…" if len(unresolved) > 5 else "")
            result += (
                f"\n\n⚠️ **注意**：关闭时尚有 {len(unresolved)} 项议程未 resolved（{shown}）。"
                "请确认它们的 status 是否属实：已解决的用 resolved，推迟的用 deferred"
                "（并写入 next_steps），受阻的用 blocked（在 note 中写明阻塞原因）"
                "——不要为了关闭而谎报 resolved。"
            )

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

# 15 种文档类型注册表（与 app/engine/registry.py 的 DEFAULT_TYPES 一致）。
# doc_type → level/template
DOC_TYPE_REGISTRY = [
    # Level 0 - Top
    {"doc_type": "business_context", "level": "top", "template": "business-context.md"},
    {"doc_type": "technical_framework", "level": "top", "template": "technical-framework.md"},
    {"doc_type": "non_functional_constraints", "level": "top", "template": "non-functional-constraints.md"},
    {"doc_type": "global_policies", "level": "top", "template": "global-policies.md"},
    {"doc_type": "inter_module_contract", "level": "top", "template": "inter-module-contracts.md"},
    {"doc_type": "stakeholders", "level": "top", "template": "stakeholders.md"},
    {"doc_type": "release_policy", "level": "top", "template": "release-policy.md"},
    # Level 1 - Module
    {"doc_type": "architecture", "level": "module", "template": "architecture.md"},
    {"doc_type": "domain_model", "level": "module", "template": "domain-model.md"},
    {"doc_type": "module_manifest", "level": "module", "template": "module-manifest.md"},
    {"doc_type": "integration", "level": "module", "template": "integration.md"},
    # Level 2 - Feature
    {"doc_type": "feature_design", "level": "feature", "template": "feature-design.md"},
    {"doc_type": "decision_log", "level": "feature", "template": "decision-log.md"},
    {"doc_type": "unit_test", "level": "feature", "template": "unit-tests.md"},
    {"doc_type": "acceptance_test", "level": "feature", "template": "acceptance-tests.md"},
]

# 注册表条目必需、且必须为真值的字段：只有 doc_type 的残缺条目不参与加载，
# 否则会顶替整个内置注册表，并让 cmd_doc_new 里的 defn["level"] 抛 KeyError
_REQUIRED_TYPE_FIELDS = ("level", "template")


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
    """从 .doc-kit/registry.yaml 加载 doc_type 注册表。

    结构非法（顶层非映射、types 非列表）、条目缺 level/template 必需键、
    文件缺失、解析失败或结果为空均返回 None（回退内置注册表）。

    刻意**不**按名字过滤「已下线的文档类型」：项目内 .doc-kit/registry.yaml
    陈旧时应照原样加载，让异常保持可见，由人工重跑 init 同步；而不是在代码里
    写死黑名单静默掩盖（项目内那份旧 CLI / 旧能力库 / 旧模板并不会因此消失）。

    结构判定在此显式做出，不再依赖 _parse_yaml_block 对非法输入抛异常被
    except 兜住。这里刻意**不支持**顶层裸列表格式：本函数用的
    _parse_yaml_block 是手写迷你解析器，本来就解析不了裸列表；裸列表
    registry.yaml 一律返回 None，回退内置注册表。
    """
    reg_path = project_root / ".doc-kit" / "registry.yaml"
    if not reg_path.exists():
        return None
    try:
        raw = _parse_yaml_block(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    types = raw.get("types")
    if not isinstance(types, list):
        return None
    result: dict[str, dict] = {}
    for t in types:
        if not isinstance(t, dict) or not t.get("doc_type"):
            continue
        # 缺 level/template 必需键的残缺条目跳过，避免顶替整个内置注册表，
        # 也避免 cmd_doc_new 里 defn["level"] 抛 KeyError
        if not all(t.get(k) for k in _REQUIRED_TYPE_FIELDS):
            continue
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

    # —— 计算目标路径 ——
    if level == "top":
        target = docs_root / defn["template"]
    else:
        main_module, sub_path = _parse_module_path(module)
        module_dir = docs_root / f"module-{main_module}"
        if sub_path:
            module_dir = module_dir / sub_path
        if level == "module":
            target = module_dir / defn["template"]
        else:
            feature_dir = module_dir / "features" / feature
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
#  DevSpec（spec-dev-loop 开发执行循环）子命令
# ═══════════════════════════════════════════════════════════════
#  DevSpec 是开发循环的工作区（DevSpec/active/<session>/），与 ProjectSpec
#  （唯一权威源）完全分离。核心纪律：本组命令不提供任何写 ProjectSpec 的
#  入口——开发循环内 ProjectSpec 只读，发现的设计问题只记录到 CodeNotes /
#  报告，修改由评审/会议在循环外完成（有版本痕迹地修改）。

DEV_TASK_STATUSES = ["pending", "in-progress", "implemented", "unit-green", "done", "fixing"]
DEV_TASK_TRANSITIONS = {
    "pending": {"in-progress"},
    "in-progress": {"implemented", "fixing"},
    "implemented": {"unit-green", "fixing"},
    "unit-green": {"done", "fixing"},
    "fixing": {"in-progress"},
    "done": set(),
}
DEV_FEATURE_STATUSES = ["tasks-done", "aligned", "done"]
DEV_FEATURE_TRANSITIONS = {"tasks-done": {"aligned"}, "aligned": {"done"}, "done": set()}
DEV_MODULE_STATUSES = ["features-done", "integrated", "documented", "done"]
DEV_MODULE_TRANSITIONS = {
    "features-done": {"integrated"},
    "integrated": {"documented"},
    "documented": {"done"},
    "done": set(),
}

PLAN_SKELETON = """# 开发计划：{title}

## 1. 范围与目标

<!-- 范围：{scope_type} {target}。由 AI 在规划对话中填充：目标、边界、依赖范围。 -->

## 2. 约束整合

<!-- 将散落在 ProjectSpec 各文档的相关约束整合于此，逐条注明来源引用（如 feature-design@<功能名>:C-101）。
ProjectSpec 在开发循环内只读，此处仅整合不修改。 -->

## 3. 任务清单

<!-- 由 CLI 从 tasks.json 自动渲染（dev task set / dev task update 后自动刷新）。 -->

## 4. 变更记录

<!-- 追加式记录计划调整与设计偏差（只记录，不修改 ProjectSpec）。 -->

## 5. 完成标准

<!-- 对齐目标：G4 约束覆盖 / G5 测试全绿 / 功能验收对齐 / 模块集成契约闭合。 -->

## 6. 分支信息

<!-- 开发分支：dev-loop/{session_id}（建议值，可人工调整后在此记录）。
断点续跑时先检查当前分支（git branch --show-current），与记录不一致则 git checkout 切换。
所有开发提交都在此分支，合并回主分支由人工在循环外完成。 -->
"""

CODE_NOTES_SKELETON = """# CodeNotes — {title}

> 开发过程知识资产（追加式记录，只追加不改写，纪律同 decision_log）。
> 供验收的研发设计人员查阅，也可作为改善流程、调整方案的依据。
> ProjectSpec 在开发循环内**只读**：发现的设计问题只记录于此，不直接修改文档。

## 开发问题与解决

<!-- ### <问题标题>
- **问题**：
- **根因**：
- **解决**：
- **影响范围**： -->

## 设计文档遗漏与偏差

<!-- ### <偏差标题>
- **发现**：
- **判断**：（设计错误 / 实现偏差 / 测试层级错位 / 文档前后矛盾）
- **依据**：
- **影响范围**：
- **建议的 Spec 修改**：（含精确引用，如 feature-design@<功能名>:C-101；只记录建议，不执行修改） -->

## 重点关注区域

<!-- ### <区域标题>
- **对象**：
- **原因**：
- **建议**： -->

## 流程与方案改进建议

<!-- ### <建议标题>
- **现状问题**：
- **改进建议**：
- **预期收益**： -->
"""


def _dev_active_dir(project_root: Path) -> Path:
    return project_root / "DevSpec" / "active"


def _detect_active_dev_session(project_root: Path) -> Path | None:
    """检测活跃开发循环：DevSpec/active/ 下含 dev-spec.json 的目录（串行约束）。"""
    active_dir = _dev_active_dir(project_root)
    if not active_dir.is_dir():
        return None
    sessions = [
        p for p in sorted(active_dir.iterdir())
        if p.is_dir() and (p / "dev-spec.json").exists()
    ]
    if len(sessions) == 0:
        return None
    if len(sessions) == 1:
        return sessions[0]
    raise ValueError(f"存在多个活跃开发循环（{len(sessions)} 个），违反了串行约束。")


def _require_active_dev_session(project_root: Path) -> tuple[Path | None, str | None]:
    """返回 (session_dir, error)；error 非空时调用方应 _fail。"""
    try:
        session_dir = _detect_active_dev_session(project_root)
    except ValueError as e:
        return None, str(e)
    if session_dir is None:
        return None, "当前没有活跃开发循环。修复：先 dev plan create 开启。"
    return session_dir, None


def _load_dev_spec(session_dir: Path) -> dict:
    p = session_dir / "dev-spec.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_dev_spec(session_dir: Path, dev_spec: dict) -> None:
    (session_dir / "dev-spec.json").write_text(
        json.dumps(dev_spec, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_dev_tasks(session_dir: Path) -> list[dict]:
    p = session_dir / "tasks.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("tasks", [])
    except (json.JSONDecodeError, OSError):
        return []


def _dev_scope_path(project_root: Path, scope: str, target: str, module: str | None) -> Path | None:
    """定位开发范围对应的 ProjectSpec 目录（仅校验存在性，绝不写入）。"""
    docs_root = project_root / "ProjectSpec"
    if scope == "module":
        main, sub = _parse_module_path(target)
        p = docs_root / f"module-{main}"
        if sub:
            p = p / sub
        return p
    if scope == "feature":
        if not module:
            return None
        main, sub = _parse_module_path(module)
        p = docs_root / f"module-{main}"
        if sub:
            p = p / sub
        return p / "features" / target
    return None


def cmd_dev_status(project_root: Path) -> str:
    """查看当前活跃开发循环的状态与进度。"""
    active_dir = _dev_active_dir(project_root)
    if not active_dir.is_dir() or not any(p.is_dir() for p in active_dir.iterdir()):
        return _ok(
            message="当前没有活跃开发循环。",
            data={"active_session": None},
            suggestions=["可参考 spec-dev-loop 流程：dev plan create --scope <module|feature> --target <范围> 开启新循环。"],
        )
    try:
        session_dir = _detect_active_dev_session(project_root)
    except ValueError as e:
        return _fail(f"错误: {e}")
    if session_dir is None:
        return _ok(
            message="当前没有活跃开发循环。",
            data={"active_session": None},
            suggestions=["可参考 spec-dev-loop 流程：dev plan create --scope <module|feature> --target <范围> 开启新循环。"],
        )
    dev_spec = _load_dev_spec(session_dir)
    tasks = _load_dev_tasks(session_dir)
    sid = dev_spec.get("session_id", session_dir.name)
    branch = dev_spec.get("branch", "") or ""
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    lines = [
        "## ✅ 当前活跃开发循环",
        "",
        f"**会话**: {sid}",
        f"**范围**: {dev_spec.get('scope_type')} {dev_spec.get('scope_target')} · {dev_spec.get('title', '')}",
        f"**任务进度**: {done}/{total} done",
    ]
    if branch:
        lines.append(f"**开发分支**: {branch}")
    if tasks:
        lines.append("")
        lines.append("| 任务 | 标题 | 状态 |")
        lines.append("|------|------|------|")
        for t in tasks:
            lines.append(f"| {t.get('task_id')} | {t.get('title', '')} | {t.get('status', 'pending')} |")
    features = dev_spec.get("features", {})
    modules = dev_spec.get("modules", {})
    if features:
        lines.append("")
        lines.append("**功能状态**:")
        for fname, info in features.items():
            lines.append(f"- {fname}: {info.get('status')}（module {info.get('module')}）")
    if modules:
        lines.append("")
        lines.append("**模块状态**:")
        for mname, info in modules.items():
            lines.append(f"- {mname}: {info.get('status')}")

    suggestions = []
    if branch:
        suggestions.append(
            f"分支检查：git branch --show-current 应为 {branch}；不一致则 git checkout {branch}（或按 plan.md §6 记录的分支名）。"
        )
    next_task = next((t for t in tasks if t.get("status") == "pending"), None)
    if next_task:
        suggestions.append(f"下一步：dev task update {next_task['task_id']} --status in-progress 开始任务。")
    else:
        unaligned = [f for f, info in features.items() if info.get("status") in (None, "tasks-done")]
        for fname in unaligned:
            suggestions.append(f"功能 {fname} 任务已全部完成，下一步：dev align --feature {fname} --module <模块> --status aligned。")
        unin = [m for m in modules if modules[m].get("status") in (None, "features-done")]
        if unin and not unaligned:
            suggestions.append(f"模块 {unin[0]} 功能已全部对齐，下一步：dev integrate --module {unin[0]} --status integrated。")
    if not suggestions:
        suggestions.append("所有任务与里程碑已完成，可 dev close --reason '<原因>' 后 dev archive 归档。")

    return _ok(
        message="\n".join(lines),
        data={
            "session_id": sid,
            "scope_type": dev_spec.get("scope_type"),
            "scope_target": dev_spec.get("scope_target"),
            "title": dev_spec.get("title"),
            "status": dev_spec.get("status"),
            "branch": branch,
            "tasks": tasks,
            "features": features,
            "modules": modules,
            "progress": {"done": done, "total": total},
        },
        suggestions=suggestions,
    )


def cmd_dev_plan_create(
    project_root: Path,
    scope: str,
    target: str,
    module: str | None = None,
    title: str | None = None,
    session: str | None = None,
) -> str:
    """创建开发循环会话骨架（DevSpec/active/<sid>/）。"""
    if scope not in ("module", "feature"):
        return _fail(f"ERROR [dev_plan.invalid_scope] scope 仅支持 module / feature，收到 '{scope}'。修复：--scope <module|feature>。")
    if not target or not target.strip():
        return _fail("ERROR [dev_plan.missing_target] 缺少 --target。修复：指定模块名（module 范围）或功能名（feature 范围）。")
    if scope == "feature" and not module:
        return _fail("ERROR [dev_plan.missing_module] feature 范围需要 --module 指定所属模块。修复：补 --module <模块名>。")
    target = target.strip()

    scope_path = _dev_scope_path(project_root, scope, target, module)
    if scope_path is None or not scope_path.is_dir():
        expected = _dev_scope_hint(scope, target, module)
        return _fail(
            f"ERROR [dev_plan.scope_not_found] 范围不存在（期望目录 {expected}）。"
            "修复：确认范围在 ProjectSpec/ 下的路径，或先用 doc new 创建该模块/功能的文档。"
        )

    active_dir = _dev_active_dir(project_root)
    active_dir.mkdir(parents=True, exist_ok=True)
    try:
        existing = _detect_active_dev_session(project_root)
        if existing is not None:
            return _fail(
                f"ERROR [dev_plan.active_exists] 已存在活跃开发循环 {existing.name}（串行约束）。"
                "修复：先 dev close / dev abort 并 dev archive 归档，再开启新循环。"
            )
    except ValueError as e:
        return _fail(f"ERROR [dev_plan.active_conflict] {e}。修复：处理 DevSpec/active/ 下的多个会话后再创建。")

    sid = session or _generate_spec_id(target)
    session_dir = active_dir / sid
    if session_dir.exists():
        return _fail(
            f"ERROR [dev_plan.session_exists] 会话 {sid} 已存在。"
            "修复：换 --session <id>，或先归档旧会话。"
        )

    scope_label = "模块" if scope == "module" else "功能"
    title = title or f"{scope_label} {target} 开发循环"
    branch = f"dev-loop/{sid}"  # 建议值；人工可调整，dev plan update-section 'plan.md#6. 分支信息' 记录最终分支名
    dev_spec = {
        "session_id": sid,
        "scope_type": scope,
        "scope_target": target,
        "module": module or target,
        "title": title,
        "branch": branch,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "closed_at": None,
        "closed_reason": None,
        "features": {},
        "modules": {},
    }
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "evidence").mkdir(exist_ok=True)
        (session_dir / "reports").mkdir(exist_ok=True)
        (session_dir / "dev-spec.json").write_text(
            json.dumps(dev_spec, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (session_dir / "tasks.json").write_text(
            json.dumps({"version": 1, "tasks": []}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (session_dir / "plan.md").write_text(
            PLAN_SKELETON.format(title=title, scope_type=scope, target=target, session_id=sid),
            encoding="utf-8",
        )
        (session_dir / "code-notes.md").write_text(
            CODE_NOTES_SKELETON.format(title=title), encoding="utf-8"
        )
    except OSError as e:
        return _fail(f"ERROR [dev_plan.write_failed] 写会话骨架失败: {e}。")

    return _ok(
        message=f"## ✅ 开发循环已创建\n\n**会话**: {sid}\n**开发分支**: {branch}\n\n位于 DevSpec/active/{sid}/",
        data={"session_id": sid, "path": str(session_dir.relative_to(project_root).as_posix()),
              "scope_type": scope, "scope_target": target, "branch": branch},
        suggestions=[
            "读取范围文档：doc structure / doc read（ProjectSpec 只读）。",
            "整合约束：dev plan update-section '<plan.md>#2. 约束整合' --content ...",
            "确认任务边界后写入：dev task set --json '<tasks 数组>'（全量替换）。",
            f"第一个任务开始前创建开发分支：git checkout -b {branch}（从当前分支）。",
        ],
    )


def _dev_scope_hint(scope: str, target: str, module: str | None) -> str:
    if scope == "module":
        return f"ProjectSpec/module-{target}/"
    return f"ProjectSpec/module-{module}/features/{target}/"


def _require_dev_plan(project_root: Path) -> tuple[Path | None, str | None]:
    """返回 (plan_md_path, error)。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return None, f"ERROR [dev.no_session] {err}"
    plan_path = session_dir / "plan.md"
    if not plan_path.exists():
        return None, "ERROR [dev_plan.missing] plan.md 不存在。修复：重新 dev plan create。"
    return plan_path, None


def _parse_dev_plan_reference(reference: str, rel: str) -> str:
    """将 reference 归一化为以 rel 为前缀的完整段落引用。"""
    if reference.startswith(rel):
        return reference
    if "#" in reference:
        file_part, heading = reference.split("#", 1)
        if file_part.strip() in ("plan.md", rel):
            return f"{rel}#{heading}"
    return reference


def cmd_dev_plan_read(project_root: Path) -> str:
    """读取当前开发计划 plan.md（段落级拍平）。"""
    plan_path, err = _require_dev_plan(project_root)
    if err:
        return _fail(err)
    text = plan_path.read_text(encoding="utf-8")
    try:
        meta_dict, body = FrontmatterParser.parse(text)
    except Exception:
        meta_dict, body = {}, text
    doc_meta = DocMeta("", "", "", "", "active", "")
    rel = str(plan_path.relative_to(project_root).as_posix())
    content = DocContent.from_body(rel, doc_meta, body, raw_frontmatter=meta_dict)
    sections = [
        {"level": s.level, "heading": s.heading, "reference": s.reference, "content": s.content}
        for s in content.sections
    ]
    return _ok(
        data={"path": rel, "sections": sections},
        suggestions=[
            "修改段落：dev plan update-section <reference> --content '<正文>'",
            "新增段落：dev plan add-section <reference> '<标题>' [--content ...]",
            "任务清单（§3）由 CLI 从 tasks.json 自动渲染，勿手动编辑。",
        ],
    )


def cmd_dev_plan_update_section(project_root: Path, reference: str, content: str) -> str:
    """更新 plan.md 指定段落正文。"""
    plan_path, err = _require_dev_plan(project_root)
    if err:
        return _fail(err)
    file_part = reference.split("#", 1)[0].strip()
    if file_part and file_part not in ("plan.md",) and not file_part.endswith("plan.md"):
        return _fail(
            f"ERROR [dev_plan.invalid_ref] reference 必须指向 plan.md，收到 '{file_part}'。修复：用 dev plan read 输出的 reference。"
        )
    text = plan_path.read_text(encoding="utf-8")
    try:
        meta_dict, body = FrontmatterParser.parse(text)
    except Exception:
        meta_dict, body = {}, text
    doc_meta = DocMeta("", "", "", "", "active", "")
    rel = str(plan_path.relative_to(project_root).as_posix())
    doc = DocContent.from_body(rel, doc_meta, body, raw_frontmatter=meta_dict)
    ref = _parse_dev_plan_reference(reference, rel)
    section = doc.get_section(ref)
    if section is None:
        return _fail(
            f"ERROR [dev_plan.section_not_found] 未找到段落: {reference}。修复：先 dev plan read 查看可用 reference。"
        )
    section.content = content
    try:
        plan_path.write_text(doc.to_markdown(), encoding="utf-8")
    except OSError as e:
        return _fail(f"ERROR [dev_plan.write_failed] 写回失败: {e}。")
    return _ok(suggestions=["计划已更新。任务清单（§3）由 CLI 从 tasks.json 自动渲染。"])


def cmd_dev_plan_add_section(project_root: Path, reference: str, heading: str, content: str, level: str) -> str:
    """在 plan.md 中新增段落。"""
    plan_path, err = _require_dev_plan(project_root)
    if err:
        return _fail(err)
    if not heading.strip():
        return _fail("heading 不能为空")
    if level not in ("sibling", "child"):
        return _fail("level 参数仅支持 'sibling' 或 'child'")
    text = plan_path.read_text(encoding="utf-8")
    try:
        meta_dict, body = FrontmatterParser.parse(text)
    except Exception:
        meta_dict, body = {}, text
    doc_meta = DocMeta("", "", "", "", "active", "")
    rel = str(plan_path.relative_to(project_root).as_posix())
    doc = DocContent.from_body(rel, doc_meta, body, raw_frontmatter=meta_dict)
    ref = _parse_dev_plan_reference(reference, rel)
    level_offset = 1 if level == "child" else 0
    try:
        new_section = doc.insert_section(ref, heading.strip(), content.strip(), level_offset=level_offset)
    except ValueError as e:
        return _fail(f"ERROR [dev_plan.section_exists] {e}")
    try:
        plan_path.write_text(doc.to_markdown(), encoding="utf-8")
    except OSError as e:
        return _fail(f"ERROR [dev_plan.write_failed] 写回失败: {e}。")
    return _ok(suggestions=[f"段落「{heading}」已新增（reference: {new_section.reference}），可 dev plan read 验证。"])


def _render_task_table(tasks: list[dict]) -> str:
    rows = ["| 任务 | 标题 | 函数 | 覆盖约束 | 状态 |", "|------|------|------|---------|------|"]
    for t in tasks:
        fns = ", ".join(
            f"**{f}**（入口）" if f == t.get("entry_function") else f
            for f in t.get("functions", [])
        )
        cons = ", ".join(t.get("constraint_ids", [])) or "—"
        rows.append(
            f"| {t.get('task_id','')} | {t.get('title','')} | {fns or '—'} | {cons} | {t.get('status','pending')} |"
        )
    return "\n".join(rows)


def _refresh_plan_tasks(project_root: Path, session_dir: Path, tasks: list[dict]) -> None:
    """同步 plan.md §3 任务清单（tasks.json 为唯一数据源）。"""
    plan_path = session_dir / "plan.md"
    if not plan_path.exists():
        return
    text = plan_path.read_text(encoding="utf-8")
    try:
        meta_dict, body = FrontmatterParser.parse(text)
    except Exception:
        meta_dict, body = {}, text
    doc_meta = DocMeta("", "", "", "", "active", "")
    rel = str(plan_path.relative_to(project_root).as_posix())
    doc = DocContent.from_body(rel, doc_meta, body, raw_frontmatter=meta_dict)
    table = _render_task_table(tasks)
    heading = "3. 任务清单"
    section = doc.get_section(f"{rel}#{heading}")
    if section is None:
        doc.insert_section(rel, heading, table)
    else:
        section.content = table
    plan_path.write_text(doc.to_markdown(), encoding="utf-8")


TASK_ALLOWED_KEYS = (
    "task_id", "title", "module", "feature", "functions", "entry_function",
    "signature", "gwt_refs", "constraint_ids", "status", "deviation", "notes",
)


def _clean_task(raw: dict, index: int) -> tuple[dict | None, str | None]:
    """校验并清洗单条任务。返回 (cleaned, error)。"""
    tid = raw.get("task_id")
    if not tid or not str(tid).strip():
        return None, f"tasks[{index}] 缺少 task_id"
    tid = str(tid).strip()
    if not raw.get("title") or not str(raw["title"]).strip():
        return None, f"tasks[{index}]（{tid}）缺少 title"
    status = raw.get("status", "pending")
    if status not in DEV_TASK_STATUSES:
        return None, f"task '{tid}' status '{status}' 不合法。允许: {DEV_TASK_STATUSES}"
    item: dict = {k: raw[k] for k in TASK_ALLOWED_KEYS if k in raw}
    item["task_id"] = tid
    item["status"] = status
    for k in ("functions", "gwt_refs", "constraint_ids"):
        v = item.get(k)
        if v is None:
            item[k] = []
        elif isinstance(v, list):
            item[k] = [str(x) for x in v]
        else:
            return None, f"task '{tid}' 字段 {k} 必须是数组"
    for k in ("module", "feature", "entry_function", "signature", "title", "deviation", "notes"):
        if k in item and item[k] is not None and not isinstance(item[k], str):
            item[k] = str(item[k])
    return item, None


def cmd_dev_task_list(project_root: Path) -> str:
    """列出当前开发循环的全部任务（JSON）。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    tasks = _load_dev_tasks(session_dir)
    return _ok(
        message=f"共 {len(tasks)} 个任务",
        data={"tasks": tasks},
        suggestions=["任务状态由 dev task set（全量）/ dev task update（增量）维护；plan.md §3 自动同步。"],
    )


def cmd_dev_task_set(project_root: Path, tasks_json: str) -> str:
    """全量写入任务清单（full-replace，语义同 spec write）。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    if len(tasks_json) > 1_000_000:
        return _fail("数据量过大（超过 1MB），请精简后再试")
    try:
        data = json.loads(tasks_json)
    except json.JSONDecodeError as e:
        return _fail(f"不是合法 JSON: {e}")
    if isinstance(data, dict) and "tasks" in data:
        tasks = data["tasks"]
    elif isinstance(data, list):
        tasks = data
    else:
        return _fail("dev task set 需要 JSON 数组，或 {\"tasks\": [...]} 对象")
    if not isinstance(tasks, list):
        return _fail("tasks 必须是数组")

    cleaned: list[dict] = []
    seen: set[str] = set()
    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            return _fail(f"tasks[{i}] 必须是对象")
        item, c_err = _clean_task(t, i)
        if c_err:
            return _fail(c_err)
        assert item is not None
        if item["task_id"] in seen:
            return _fail(f"task_id '{item['task_id']}' 重复，必须唯一")
        seen.add(item["task_id"])
        cleaned.append(item)

    try:
        (session_dir / "tasks.json").write_text(
            json.dumps({"version": 1, "tasks": cleaned}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _refresh_plan_tasks(project_root, session_dir, cleaned)
    except OSError as e:
        return _fail(f"ERROR [dev_task.write_failed] 写 tasks.json 失败: {e}。")
    return _ok(
        message=f"## ✅ 任务清单已保存（{len(cleaned)} 个任务）",
        data={"count": len(cleaned)},
        suggestions=["plan.md §3 已同步。进入 LOOP：dev task update <id> --status in-progress。"],
    )


def cmd_dev_task_update(project_root: Path, task_id: str, status: str, note: str = "") -> str:
    """任务状态迁移（按状态机校验），可附带备注。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    if status not in DEV_TASK_STATUSES:
        return _fail(f"ERROR [dev_task.invalid_status] status '{status}' 不合法。允许: {DEV_TASK_STATUSES}。")
    tasks = _load_dev_tasks(session_dir)
    target = next((t for t in tasks if t.get("task_id") == task_id), None)
    if target is None:
        return _fail(f"ERROR [dev_task.not_found] 任务 {task_id} 不存在。修复：dev task list 查看任务 ID。")
    cur = target.get("status", "pending")
    if status not in DEV_TASK_TRANSITIONS.get(cur, set()):
        return _fail(
            f"ERROR [dev_task.invalid_transition] 状态 {cur} → {status} 不合法。修复：按状态机推进"
            "（pending → in-progress → implemented → unit-green → done；失败 → fixing → in-progress）。"
        )
    target["status"] = status
    if note:
        date = datetime.now().strftime("%Y-%m-%d")
        target["notes"] = ((target.get("notes", "") + "\n") if target.get("notes") else "") + f"[{date}] {note}"
    try:
        (session_dir / "tasks.json").write_text(
            json.dumps({"version": 1, "tasks": tasks}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _refresh_plan_tasks(project_root, session_dir, tasks)
    except OSError as e:
        return _fail(f"ERROR [dev_task.write_failed] 写 tasks.json 失败: {e}。")
    return _ok(
        message=f"## ✅ 任务 {task_id} → {status}",
        data={"task_id": task_id, "status": status},
        suggestions=["证据（测试输出等）可写入 DevSpec/active/<sid>/evidence/ 并在此备注路径。"],
    )


def cmd_dev_task_annotate(project_root: Path, task_id: str, note: str) -> str:
    """给任务追加备注（不改变状态），如记录偏差。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    if not note or not note.strip():
        return _fail("note 不能为空")
    tasks = _load_dev_tasks(session_dir)
    target = next((t for t in tasks if t.get("task_id") == task_id), None)
    if target is None:
        return _fail(f"ERROR [dev_task.not_found] 任务 {task_id} 不存在。修复：dev task list 查看任务 ID。")
    date = datetime.now().strftime("%Y-%m-%d")
    target["notes"] = ((target.get("notes", "") + "\n") if target.get("notes") else "") + f"[{date}] {note}"
    try:
        (session_dir / "tasks.json").write_text(
            json.dumps({"version": 1, "tasks": tasks}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as e:
        return _fail(f"ERROR [dev_task.write_failed] 写 tasks.json 失败: {e}。")
    return _ok(message=f"## ✅ 任务 {task_id} 备注已追加", data={"task_id": task_id})


def cmd_dev_align(project_root: Path, feature: str, module: str, status: str, note: str = "") -> str:
    """功能对齐：要求该功能全部任务 done 后记录 aligned / done。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    if status not in ("aligned", "done"):
        return _fail(f"ERROR [dev_align.invalid_status] status 仅支持 aligned / done，收到 '{status}'。")
    if not module or not module.strip():
        return _fail("ERROR [dev_align.missing_module] 缺少 --module。修复：补 --module <模块名>。")
    tasks = _load_dev_tasks(session_dir)
    feats = [t for t in tasks if t.get("feature") == feature]
    if not feats:
        return _fail(
            f"ERROR [dev_align.no_tasks] 功能 {feature} 下没有任务。修复：确认 tasks.json 中任务的 feature 字段。"
        )
    pending = [t["task_id"] for t in feats if t.get("status") != "done"]
    if pending:
        return _fail(
            f"ERROR [dev_align.tasks_not_done] 功能 {feature} 仍有任务未完成: {', '.join(pending)}。修复：完成任务后再对齐。"
        )
    dev_spec = _load_dev_spec(session_dir)
    features = dev_spec.setdefault("features", {})
    cur = features.get(feature, {}).get("status")
    if status not in DEV_FEATURE_TRANSITIONS.get(cur or "tasks-done", set()):
        return _fail(
            f"ERROR [dev_align.invalid_transition] 功能状态 {cur or 'tasks-done'} → {status} 不合法。修复：tasks-done → aligned → done。"
        )
    features[feature] = {
        "module": module,
        "status": status,
        "note": note or features.get(feature, {}).get("note", ""),
    }
    _save_dev_spec(session_dir, dev_spec)
    return _ok(
        message=f"## ✅ 功能 {feature} 对齐 → {status}",
        data={"feature": feature, "status": status},
        suggestions=["功能对齐应在验收测试（自动化为主）与 G4 约束覆盖检查通过后记录。"],
    )


def cmd_dev_integrate(project_root: Path, module: str, status: str, note: str = "") -> str:
    """模块集成：要求该模块全部功能已对齐后，按 integrated → documented → done 推进。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    if status not in ("integrated", "documented", "done"):
        return _fail(f"ERROR [dev_integrate.invalid_status] status 仅支持 integrated / documented / done，收到 '{status}'。")
    if not module or not module.strip():
        return _fail("ERROR [dev_integrate.missing_module] 缺少 --module。修复：补 --module <模块名>。")
    dev_spec = _load_dev_spec(session_dir)
    features = dev_spec.get("features", {})
    modules = dev_spec.setdefault("modules", {})
    if status == "integrated":
        related = [f for f, info in features.items() if info.get("module") == module]
        if not related:
            return _fail(
                f"ERROR [dev_integrate.features_not_aligned] 模块 {module} 尚无任何功能对齐记录。"
                "修复：先对该模块的功能 dev align。"
            )
        unaligned = [f for f in related if features[f].get("status") not in ("aligned", "done")]
        if unaligned:
            return _fail(
                f"ERROR [dev_integrate.features_not_aligned] 模块 {module} 的功能尚未全部对齐: {', '.join(unaligned)}。"
                "修复：先对每个功能 dev align。"
            )
    cur = modules.get(module, {}).get("status")
    if status not in DEV_MODULE_TRANSITIONS.get(cur or "features-done", set()):
        return _fail(
            f"ERROR [dev_integrate.invalid_transition] 模块状态 {cur or 'features-done'} → {status} 不合法。"
            "修复：features-done → integrated → documented → done。"
        )
    modules[module] = {
        "status": status,
        "note": note or modules.get(module, {}).get("note", ""),
    }
    _save_dev_spec(session_dir, dev_spec)
    return _ok(
        message=f"## ✅ 模块 {module} 集成 → {status}",
        data={"module": module, "status": status},
        suggestions=[
            "integrated 应在 G3 契约闭合（import↔export 配对）与 inter-module-contracts 字段校验通过后记录。",
            "documented 表示 CodeNotes 已整理、模块报告已产出（dev report-write）。",
        ],
    )


def cmd_dev_notes_append(project_root: Path, content: str, section: str | None = None) -> str:
    """向 code-notes.md 指定章节追加内容（只追加，不改写既有记录）。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    if not content or not content.strip():
        return _fail("content 不能为空")
    notes_path = session_dir / "code-notes.md"
    if not notes_path.exists():
        return _fail("ERROR [dev_notes.missing] code-notes.md 不存在。修复：重新 dev plan create。")
    heading = section or "开发问题与解决"
    text = notes_path.read_text(encoding="utf-8")
    try:
        meta_dict, body = FrontmatterParser.parse(text)
    except Exception:
        meta_dict, body = {}, text
    doc_meta = DocMeta("", "", "", "", "active", "")
    rel = str(notes_path.relative_to(project_root).as_posix())
    doc = DocContent.from_body(rel, doc_meta, body, raw_frontmatter=meta_dict)
    sec = doc.get_section(f"{rel}#{heading}")
    if sec is None:
        sec = doc.insert_section(rel, heading, content.strip())
    else:
        if sec.content.strip().startswith("<!--"):
            sec.content = content.strip()
        else:
            sec.content = (sec.content + "\n\n" + content).strip()
    try:
        notes_path.write_text(doc.to_markdown(), encoding="utf-8")
    except OSError as e:
        return _fail(f"ERROR [dev_notes.write_failed] 写回失败: {e}。")
    return _ok(
        message=f"## ✅ CodeNotes 已追加（§{heading}）",
        data={"section": heading},
        suggestions=["CodeNotes 只追加不改写（纪律同 decision_log）。"],
    )


def cmd_dev_report_write(project_root: Path, kind: str, name: str, content: str) -> str:
    """写入功能对齐报告 / 模块开发报告到 DevSpec/active/<sid>/reports/。"""
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    if kind not in ("feature", "module"):
        return _fail("ERROR [dev_report.invalid_kind] kind 仅支持 feature / module。")
    if not name or not name.strip():
        return _fail("ERROR [dev_report.missing_name] 缺少 --name。")
    if not content or not content.strip():
        return _fail("report 内容不能为空")
    reports_dir = session_dir / "reports"
    reports_dir.mkdir(exist_ok=True)
    filename = f"{kind}-{name.strip()}.md"
    file_path = reports_dir / filename
    try:
        file_path.write_text(content.strip() + "\n", encoding="utf-8")
    except OSError as e:
        return _fail(f"ERROR [dev_report.write_failed] 写报告失败: {e}。")
    return _ok(
        message=f"## ✅ 报告已写入\n\n**文件**: {filename}",
        data={"file": filename, "path": str(file_path.relative_to(project_root).as_posix())},
        suggestions=["报告模板见 spec-dev-loop/SKILL.md（功能对齐报告 / 模块开发报告）。"],
    )


def _cmd_dev_set_status(project_root: Path, reason: str, target_status: str, label: str) -> str:
    session_dir, err = _require_active_dev_session(project_root)
    if err:
        return _fail(f"ERROR [dev.no_session] {err}")
    if not reason or not reason.strip():
        return _fail(f"ERROR [dev_{label}.missing_reason] 缺少 --reason。")
    dev_spec = _load_dev_spec(session_dir)
    if dev_spec.get("status") != "active":
        return _fail(
            f"ERROR [dev_{label}.invalid_status] 当前状态 {dev_spec.get('status')}，仅 active 可{label}。"
        )
    dev_spec["status"] = target_status
    dev_spec["closed_at"] = datetime.now(timezone.utc).isoformat()
    dev_spec["closed_reason"] = reason.strip()
    _save_dev_spec(session_dir, dev_spec)
    return _ok(
        message=f"## ✅ 开发循环已{label}",
        data={"session_id": dev_spec.get("session_id"), "status": target_status},
        suggestions=[f"下一步：dev archive 归档。"],
    )


def cmd_dev_close(project_root: Path, reason: str) -> str:
    """关闭开发循环（正常完成）。"""
    return _cmd_dev_set_status(project_root, reason, "closed", "close")


def cmd_dev_abort(project_root: Path, reason: str) -> str:
    """作废开发循环（非正常终止）。"""
    return _cmd_dev_set_status(project_root, reason, "abandoned", "abort")


def cmd_dev_archive(project_root: Path) -> str:
    """归档已关闭/已作废的开发循环（active → archive）。"""
    try:
        session_dir = _detect_active_dev_session(project_root)
    except ValueError as e:
        return _fail(f"错误: {e}")
    if session_dir is None:
        return _fail("当前没有可归档的开发循环（DevSpec/active/ 为空）。")
    dev_spec = _load_dev_spec(session_dir)
    status = dev_spec.get("status")
    if status not in ("closed", "abandoned"):
        return _fail(
            f"ERROR [dev_archive.invalid_status] 会话 {dev_spec.get('session_id')} 状态为 {status}，"
            "只有 closed 或 abandoned 才能归档。修复：先 dev close / dev abort。"
        )
    archive_dir = project_root / "DevSpec" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dst = archive_dir / session_dir.name
    if dst.exists():
        return _fail(f"ERROR [dev_archive.exists] 归档目录已存在: {dst.name}。")
    session_dir.replace(dst)
    return _ok(
        message=f"## ✅ 开发循环已归档\n\n**会话**: {dev_spec.get('session_id')}\n\n已移至 DevSpec/archive/。",
        data={"session_id": dev_spec.get("session_id"), "status": status},
    )


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

    # ── dev（spec-dev-loop 开发执行循环）──
    dev = sub.add_parser("dev", help="开发执行循环（DevSpec）操作")
    dev_sub = dev.add_subparsers(dest="command", required=True)
    dev_sub.add_parser("status", help="查看活跃开发循环状态")

    plan_p = dev_sub.add_parser("plan", help="开发计划（plan.md）操作")
    plan_sub = plan_p.add_subparsers(dest="subcommand", required=True)
    plan_create_p = plan_sub.add_parser("create", help="创建开发循环会话骨架")
    plan_create_p.add_argument("--scope", required=True, choices=["module", "feature"], help="范围类型")
    plan_create_p.add_argument("--target", required=True, help="模块名（module）/ 功能名（feature）")
    plan_create_p.add_argument("--module", default=None, help="feature 范围必填：所属模块（子模块用点分，如 order.core）")
    plan_create_p.add_argument("--title", default=None, help="会话标题（默认自动生成）")
    plan_create_p.add_argument("--session", default=None, help="会话 ID（默认 {日期}-{范围kebab}）")
    plan_sub.add_parser("read", help="读取开发计划（段落级拍平）")
    plan_upd_p = plan_sub.add_parser("update-section", help="更新计划段落正文")
    plan_upd_p.add_argument("reference", help="段落引用，如 <plan.md>#2. 约束整合")
    plan_upd_p.add_argument("--content", required=True, help="新的正文内容")
    plan_add_p = plan_sub.add_parser("add-section", help="新增计划段落")
    plan_add_p.add_argument("reference", help="锚点段落引用")
    plan_add_p.add_argument("heading", help="新段落标题")
    plan_add_p.add_argument("--content", default="", help="正文内容")
    plan_add_p.add_argument("--level", default="sibling", choices=["sibling", "child"])

    task_p = dev_sub.add_parser("task", help="任务（tasks.json）操作")
    task_sub = task_p.add_subparsers(dest="subcommand", required=True)
    task_sub.add_parser("list", help="列出全部任务")
    task_set_p = task_sub.add_parser("set", help="全量写入任务清单（full-replace）")
    task_set_p.add_argument("--json", required=True, help="完整 tasks 数组 JSON；或 {\"tasks\": [...]}")
    task_upd_p = task_sub.add_parser("update", help="任务状态迁移")
    task_upd_p.add_argument("task_id", help="任务 ID")
    task_upd_p.add_argument("--status", required=True, help="目标状态：pending/in-progress/implemented/unit-green/done/fixing")
    task_upd_p.add_argument("--note", default="", help="附加备注（追加到 notes）")
    task_ann_p = task_sub.add_parser("annotate", help="给任务追加备注（不改变状态）")
    task_ann_p.add_argument("task_id", help="任务 ID")
    task_ann_p.add_argument("--note", required=True, help="备注内容")

    align_p = dev_sub.add_parser("align", help="功能对齐（要求该功能全部任务 done）")
    align_p.add_argument("--feature", required=True, help="功能名")
    align_p.add_argument("--module", required=True, help="所属模块名")
    align_p.add_argument("--status", required=True, choices=["aligned", "done"], help="对齐状态")
    align_p.add_argument("--note", default="", help="备注")

    integrate_p = dev_sub.add_parser("integrate", help="模块集成（要求该模块全部功能已对齐）")
    integrate_p.add_argument("--module", required=True, help="模块名")
    integrate_p.add_argument("--status", required=True, choices=["integrated", "documented", "done"], help="集成状态")
    integrate_p.add_argument("--note", default="", help="备注")

    notes_p = dev_sub.add_parser("notes", help="CodeNotes 操作")
    notes_sub = notes_p.add_subparsers(dest="subcommand", required=True)
    notes_app_p = notes_sub.add_parser("append", help="向 CodeNotes 追加内容（只追加不改写）")
    notes_app_p.add_argument("--content", required=True, help="要追加的 Markdown 内容")
    notes_app_p.add_argument("--section", default=None, help="目标章节（默认 开发问题与解决）")

    report_p = dev_sub.add_parser("report-write", help="写入功能/模块报告到 reports/")
    report_p.add_argument("--kind", required=True, choices=["feature", "module"], help="报告类型")
    report_p.add_argument("--name", required=True, help="功能名 / 模块名")
    report_p.add_argument("--content", required=True, help="报告 Markdown")

    close_p = dev_sub.add_parser("close", help="关闭开发循环（正常完成）")
    close_p.add_argument("--reason", required=True, help="关闭原因")
    abort_p = dev_sub.add_parser("abort", help="作废开发循环（非正常终止）")
    abort_p.add_argument("--reason", required=True, help="作废原因")
    dev_sub.add_parser("archive", help="归档已关闭/已作废的开发循环")

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
        elif args.group == "dev":
            if args.command == "status":
                _emit(cmd_dev_status(project_root))
            elif args.command == "plan":
                if args.subcommand == "create":
                    _emit(cmd_dev_plan_create(project_root, args.scope, args.target, args.module, args.title, args.session))
                elif args.subcommand == "read":
                    _emit(cmd_dev_plan_read(project_root))
                elif args.subcommand == "update-section":
                    _emit(cmd_dev_plan_update_section(project_root, args.reference, _unescape_text(args.content)))
                elif args.subcommand == "add-section":
                    _emit(cmd_dev_plan_add_section(project_root, args.reference, args.heading, _unescape_text(args.content), args.level))
            elif args.command == "task":
                if args.subcommand == "list":
                    _emit(cmd_dev_task_list(project_root))
                elif args.subcommand == "set":
                    _emit(cmd_dev_task_set(project_root, args.json))
                elif args.subcommand == "update":
                    _emit(cmd_dev_task_update(project_root, args.task_id, args.status, args.note))
                elif args.subcommand == "annotate":
                    _emit(cmd_dev_task_annotate(project_root, args.task_id, args.note))
            elif args.command == "align":
                _emit(cmd_dev_align(project_root, args.feature, args.module, args.status, args.note))
            elif args.command == "integrate":
                _emit(cmd_dev_integrate(project_root, args.module, args.status, args.note))
            elif args.command == "notes":
                if args.subcommand == "append":
                    _emit(cmd_dev_notes_append(project_root, _unescape_text(args.content), args.section))
            elif args.command == "report-write":
                _emit(cmd_dev_report_write(project_root, args.kind, args.name, _unescape_text(args.content)))
            elif args.command == "close":
                _emit(cmd_dev_close(project_root, args.reason))
            elif args.command == "abort":
                _emit(cmd_dev_abort(project_root, args.reason))
            elif args.command == "archive":
                _emit(cmd_dev_archive(project_root))
    except Exception as e:  # 未预期的运行时错误：输出到 stderr 便于调试
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

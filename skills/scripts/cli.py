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
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
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
from frontmatter import FrontmatterParser  # noqa: E402
from index import IndexManager  # noqa: E402
from spec_schema import (  # noqa: E402
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
        data.setdefault("related_doc_types", [])
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
#  doc_structure）
# ═══════════════════════════════════════════════════════════════


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
#  deploy 子命令（自举：把本 CLI 包部署到项目固定路径）
# ═══════════════════════════════════════════════════════════════

CLI_PACKAGE_FILES = [
    "__init__.py",
    "cli.py",
    "docmodel.py",
    "frontmatter.py",
    "index.py",
    "spec_schema.py",
]
"""部署时复制的文件清单（本目录下的 .py 源文件）。"""


def cmd_deploy(target: str | None = None) -> str:
    """把本 CLI 包（cli.py 同目录的源文件）复制到项目固定路径。

    默认目标：<当前目录>/.doc-kit/cli/（不要求项目已初始化，新项目也能自举）。
    部署后统一调用：python .doc-kit/cli/cli.py <group> <command> ...
    """
    src_dir = Path(__file__).resolve().parent
    if target:
        dst_dir = Path(target).resolve()
    else:
        dst_dir = Path.cwd().resolve() / ".doc-kit" / "cli"
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in CLI_PACKAGE_FILES:
        src = src_dir / name
        if not src.exists():
            continue
        shutil.copy2(src, dst_dir / name)
        copied.append(name)
    if not copied:
        return _fail(f"cli.py 同目录下未找到任何源文件（{src_dir}），无法部署。")
    rel = dst_dir.relative_to(Path.cwd().resolve()) if dst_dir.is_relative_to(Path.cwd().resolve()) else dst_dir
    return _ok(
        message=f"✅ CLI 已部署到 {rel}（{len(copied)} 个文件）。\n\n后续统一调用：python {rel.as_posix()}/cli.py <group> <command> ...",
        data={"target": str(dst_dir), "files": copied},
    )


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

    # ── deploy（顶层子命令，不依赖项目根）──
    deploy_p = sub.add_parser("deploy", help="自举：把本 CLI 包复制到项目固定路径")
    deploy_p.add_argument("--target", help="部署目标目录（默认 <当前目录>/.doc-kit/cli）")

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

    # deploy 不依赖项目根，最先处理（目标项目可能尚未初始化）
    if args.group == "deploy":
        _emit(cmd_deploy(args.target))

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
                _emit(cmd_doc_update_section(project_root, args.reference, args.content))
            elif args.command == "add-section":
                _emit(cmd_doc_add_section(project_root, args.reference, args.heading, args.content, args.level))
        elif args.group == "review":
            if args.command == "anchor-get":
                _emit(cmd_review_anchor_get(project_root))
            elif args.command == "anchor-set":
                _emit(cmd_review_anchor_set(project_root, args.commit_hash, args.session))
            elif args.command == "report-write":
                content = args.content
                if content is None and args.file:
                    content = Path(args.file).read_text(encoding="utf-8")
                if content is None:
                    content = _read_stdin()
                _emit(cmd_review_report_write(project_root, content))
    except Exception as e:  # 未预期的运行时错误：输出到 stderr 便于调试
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

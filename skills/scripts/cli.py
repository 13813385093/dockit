#!/usr/bin/env python3
"""doc-kit skills CLI — 议题与文档管理命令行工具（取代原 MCP 服务器）。

Stdlib-only command line interface for skills. Each subcommand mirrors the
behaviour of the former MCP tools with identical validation logic.

用法:
    python .doc-kit/cli/cli.py [--root <项目目录>] tool status
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
    python .doc-kit/cli/cli.py [--root <项目目录>] doc reindex
    python .doc-kit/cli/cli.py [--root <项目目录>] doc lint [--baseline <file>] [--summary]
    python .doc-kit/cli/cli.py [--root <项目目录>] review anchor-get [--branch <分支名>]
    python .doc-kit/cli/cli.py [--root <项目目录>] review anchor-set <commit_hash> [--session <sid>] [--branch <分支名>]
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

退出码: 0 = 成功；1 = 业务拒绝（输出 success=false 的 JSON）或运行时错误；2 = 参数错误（argparse：未知选项、缺必填参数）。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
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
    RESOLVED_VIA_BASENAME,
    _simplify_depends_on,
    resolve_doc,
    safe_join,
)
from frontmatter import FrontmatterParser, _parse_yaml_block, read_document  # noqa: E402
from index import IndexEntry, IndexManager  # noqa: E402
from spec_schema import (  # noqa: E402
    SCENARIO_DOC_TYPES,
    SPEC_SCHEMA,
    get_schema_metadata,
    render_summary,
    unknown_keys,
    validate as validate_spec,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


TOOLCHAIN_VERSION = "2026.11.1"
"""工具链版本 —— 技能文本与项目内 `.doc-kit/` 副本的配套标识。

改动 `skills/scripts/*.py`、`skills/spec-*/SKILL.md`、`skills/guidance/**`、
`src/app/templates/*.md` 中任何一处，都要递增本版本号（格式 `YYYY.MM.N`）。

为什么需要它：`init` 是把工具链**快照复制**进项目，之后两边各自演化；
而一次开发同时依赖 agent 侧的 SKILL.md、项目侧的 `.doc-kit/cli/`（执行体）
与 `.doc-kit/skills/guidance/`（写文档的规范）。三者错配的后果不对称——
新技能配旧 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（如 `implemented_in`），
命令报"已保存"但关键信息消失。为此：

- `tests/render_skill_preamble.py` 把本常量注入 8 份 SKILL.md 的前言；
- `init` 把本版本与各副本的 sha256 写入 `.doc-kit/toolchain.json`；
- `tool status` 比对"技能声明的版本 / 项目记录的版本 / 当前 CLI 版本"，
  并校验副本哈希，从而把错配从"静默"变成"显式提示"。
"""

TOOLCHAIN_HISTORY = [
    {
        "version": "2026.09.1",
        "date": "2026-09-15",
        "note": "首个版本化工具链：模块三评审修复（提交改 pathspec 形式、评审锚点按分支记录、报告段落对齐）、共享前言生成（9 份技能收敛为 3 个变体、工具清单自动派生）、spec-dev-loop 骨架化与委托实现流程、议题类技能改为「议程驱动 + 两个落盘点 + ProjectSpec 单点写入」"
    },
    {
        "version": "2026.09.2",
        "date": "2026-09-15",
        "note": "新增工具链版本历史与变更说明：tool status 可报告「项目落后几版 + 期间改了什么」，同步动作从此有理由、有内容"
    },
    {
        "version": "2026.09.3",
        "date": "2026-09-16",
        "note": "阶段1：修正 plan 段落引用的建议形式（<plan.md> 占位符会被拒绝）、_fail 与 review report-write 补齐 message 字段、前言中关于错误格式与退出码的断言改为符合实现"
    },
    {
        "version": "2026.09.4",
        "date": "2026-09-16",
        "note": "阶段2：统一落盘点表述并在前言给出三处权威定义；修正 spec-start 的非真实状态名 idle；spec-close 边界补议题链路内限定；git 前言去掉对 spec-code-review 的指名；USAGE 三处选项可选性改为与实现一致"
    },
    {
        "version": "2026.09.5",
        "date": "2026-09-16",
        "note": "阶段3：spec-start 与 spec-archive 的路由改用 spec read 的 JSON 字段（消除对 spec status 中文散文的隐式耦合）；spec-close Step 1 改为复用 spec-pause 不再重述落盘流程；新增路由/去重/边界/描述预算四类内容契约"
    },
    {
        "version": "2026.09.6",
        "date": "2026-09-16",
        "note": "阶段3：9 份 description 补触发条件与近亲消歧（24–65→96–137 字符）；同步更新 test_session_flow 的 pause 落盘点断言为「唯一保存通道」"
    },
    {
        "version": "2026.09.7",
        "date": "2026-09-16",
        "note": "A1：未初始化时的终止话术改为给出可执行的初始化命令，并明确初始化由人工完成（不新增 spec-init 技能）"
    },
    {
        "version": "2026.09.8",
        "date": "2026-09-16",
        "note": "A2：spec status 增加跨存储报告（有活跃开发循环时额外一行，含 phase）；spec write 拒绝新增的未知字段（顶层与嵌套），与 dev task set 对齐；USAGE 把两条仅供人工的命令移出并改为显式声明"
    },
    {
        "version": "2026.09.9",
        "date": "2026-09-16",
        "note": "dev-loop 文档化 dev task annotate（不改状态的备注通道）；记录 CI 已决为不接入"
    },
    {
        "version": "2026.09.10",
        "date": "2026-09-16",
        "note": "技能合并：spec-load 并入 spec-start（新对话单一入口：有议题走续接 Step 0b、无议题走创建）、spec-abort 并入 spec-close（作废分支）；9 份 → 7 份"
    },
    {
        "version": "2026.10.1",
        "date": "2026-10-07",
        "note": "新增 doc reindex 命令（把 App 侧 IndexManager.rebuild 搬进 CLI，spec-close 写盘后调用一次）；并移除 index.json 的 mtime / built_at 生成时刻字段——内容未变时 App 刷新不再产生 diff，加载时兼容旧字段"
    },
    {
        "version": "2026.10.2",
        "date": "2026-10-10",
        "note": "新增 doc lint 规格完整性门禁（R1/R3/R4/R5/R7/R8/R9/R10/R11/R12，只读、支持 lint.yaml 配置与 JSON baseline）；doc reindex 回报 skipped；能力库 _index.md 补「权威分层与引用纪律」节"
    },
    {
        "version": "2026.10.3",
        "date": "2026-10-10",
        "note": "doc lint 接入 spec-code-review(提示)/spec-close(阻断新增 error) 收尾；新增 doc lint --summary 精简输出；doc lint 从 CLI_ONLY 迁入 USAGE"
    },
    {
        "version": "2026.10.4",
        "date": "2026-10-15",
        "note": "doc/dev plan update-section 拒绝空 --content（防止误删段落）；技能前言与能力库中 read_file/write_file 改为与 agent 无关的「直接读写/直接读取」措辞"
    },
    {
        "version": "2026.10.5",
        "date": "2026-10-21",
        "note": "新增 spec-code-smell（快速/深入双模式、源文件分类不绑定 src/、范围摘要）与 smell-capabilities；spec-code-review 收尾提示带显式范围"
    },
    {
        "version": "2026.11.1",
        "date": "2026-11-03",
        "note": "修复 doc read 路径解析：省略 .md 与 ProjectSpec/ 前缀时不再静默解析到另一篇同名文档；多候选报 doc_read.ambiguous 并列出全部候选，输出新增 resolved_via 说明命中方式"
    }
]
"""工具链版本历史（旧 → 新，体积很小，随 CLI 一起分发）。

用途：`tool status` 据此算出**项目落后几个版本、期间改了什么**，让"该同步"
这件事有理由、有内容，而不只是一句"版本不一致"。

维护方式：递增 `TOOLCHAIN_VERSION` 后运行
`python tests/check_toolchain_version.py --update --note "<一句变更说明>"`，
由脚本自动追加本列表，不要手工编辑。
"""


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


def _active_dev_loop_hint(project_root: Path) -> str:
    """有活跃开发循环时给 `spec status` 追加的一行。

    议题侧（`SessionSpec/`）与开发循环侧（`DevSpec/`）互不可见：spec_schema 对 DevSpec
    零引用，`_detect_active_session` 只 glob `SessionSpec/active/*.spec.json`。因此开发循环
    进行中开新对话时，`spec status` 会如实报告"没有活跃议题"——那句话是**真的**，但会让人
    以为什么都没在跑（`TODO.md` §A2）。

    修在这里而不是修在某份技能里：`spec status` 的职责本就是"报告现在什么在跑"，
    放进 CLI 则 8 份技能同时受益，也不需要任何技能越界去读别人的状态。只读内存，不写盘。
    """
    try:
        session = _detect_active_dev_session(project_root)
    except ValueError:
        return "\n⚠️ 存在多个活跃开发循环，违反串行约束：请先处理 `DevSpec/active/` 下的会话。"
    if session is None:
        return ""
    return (
        f"\n⚠️ 另有活跃开发循环 **{session.name}**（phase: {_dev_phase(_load_dev_tasks(session))}）"
        "——开发相关请求请走 `spec-dev-loop` 续接（先 `dev status` 看进度）。"
    )


def cmd_spec_status(project_root: Path) -> str:
    """检查当前议题状态并给出下一步操作指引。返回纯文本（通常一行，有开发循环时两行）。"""
    return _spec_status_text(project_root) + _active_dev_loop_hint(project_root)


def _spec_status_text(project_root: Path) -> str:
    """议题侧的状态描述（原有实现）。"""
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

    # 未知字段校验：validate_spec 只遍历 schema 定义过的字段，从不反问"你给的键里有没有
    # 我不认识的"，于是拼错的字段名会被 success 回执 + 原样写盘，且永远不被读到。
    # 与 dev task set 的 TASK_ALLOWED_KEYS 校验对齐：**新增**的未知字段一律拒绝；
    # 磁盘上已存在的历史未知字段只提示不拒绝，否则历史数据无法完成一次合法往返。
    unknown = unknown_keys(data)
    inherited = set(unknown_keys(existing)) if isinstance(existing, dict) else set()
    blocking = sorted(k for k in unknown if k not in inherited)
    if blocking:
        return _fail(
            f"ERROR [spec.unknown_field] spec 含未知字段 {blocking}。"
            f" 允许的字段: {sorted(SPEC_SCHEMA)}"
            f"；条目内允许: resolutions{list(SPEC_SCHEMA['resolutions']['item_schema'])}"
            f" / pending_decisions{list(SPEC_SCHEMA['pending_decisions']['item_schema'])}。"
            " 修复：字段名拼错不会报错、会被静默写盘且永不被读取，请先核对该字段是否应存在。"
        )
    tolerated = sorted(k for k in unknown if k in inherited)

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

    if tolerated:
        result += (
            f"\n\n⚠️ **注意**：本次提交含 {len(tolerated)} 个未知字段"
            f"（磁盘上已存在，为兼容历史数据未拒绝）：{tolerated}。"
            " 若非有意保留，建议清理后重新写入。"
        )

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
    """读取指定文档的完整内容，按段落层级拍平成 JSON。

    路径解析走 ``docmodel.resolve_doc``（精确 → 补 `.md` → 路径段后缀 → 裸名唯一）。
    解析结果多候选时报 ``doc_read.ambiguous`` 并列出全部候选，**绝不静默取首个**：
    读错文档会让调用方据另一模块的内容做判断，而 ``success`` 仍是 true。
    """
    resolution = resolve_doc(project_root, doc_path)
    if resolution.invalid:
        return _fail(
            f"ERROR [doc_read.invalid_path] 非法路径: {doc_path}（不得跳出 ProjectSpec/）。"
            "请改用 doc structure 返回的完整路径。"
        )
    if resolution.is_dir:
        return _fail(
            f"ERROR [doc_read.is_directory] 这是一个目录而非文档: {doc_path}。"
            "请用 doc structure 查看该目录下的文档路径后重试。"
        )
    if resolution.path is None:
        if resolution.candidates:
            rels = [p.relative_to(project_root).as_posix() for p in resolution.candidates]
            listed = "\n".join(f"  - {rel}" for rel in rels)
            return _fail(
                f"ERROR [doc_read.ambiguous] 「{doc_path}」匹配到 {len(rels)} 个候选文档，已拒绝猜测：\n{listed}\n"
                "请把候选中的完整路径（含 .md）原样传给 doc read。",
                data={"input": doc_path, "candidates": rels},
                suggestions=[f"候选：{'、'.join(rels)}"],
            )
        return _fail(
            f"ERROR [doc_read.not_found] 未找到文档: {doc_path}，可用 doc structure 查看所有文档路径。"
            "若路径省略了 .md 后缀，请补上后重试（如 module-x/architecture.md）。",
            data={"input": doc_path},
        )
    full_path = resolution.path
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
    if index:
        entry = index.get_entry(rel_path)
        if entry:
            index_depends_on = _simplify_depends_on(entry.depends_on)

    doc_meta = DocMeta(
        doc_type=meta_dict.get("doc_type", ""),
        module=meta_dict.get("module", ""),
        level=meta_dict.get("level", ""),
        version=meta_dict.get("version", ""),
        status=meta_dict.get("status", "active"),
    )
    content = DocContent.from_body(rel_path, doc_meta, body, raw_frontmatter=meta_dict)
    data = content.to_dict()
    data["depends_on"] = index_depends_on
    # 让调用方能判断"这次解析是不是靠猜"：exact / suffix_added / path_suffix / basename
    data["resolved_via"] = resolution.via

    suggestions = [
        "如需修改某个段落，请调用 doc update-section <reference> --content ...",
        "如需新增段落，请调用 doc add-section <reference> <heading> [--content ...]",
    ]
    if resolution.via == RESOLVED_VIA_BASENAME:
        suggestions.append(
            f"本次输入 `{doc_path}` 未带目录，按文件名唯一匹配到 {rel_path}；"
            "建议后续直接用完整路径，避免同名文档增多后触发歧义。"
        )
    if index_depends_on:
        dep_list = "、".join(index_depends_on)
        suggestions.append(f"该文档依赖: {dep_list}，可调用 doc read 查看依赖文档了解上下文")

    return _ok(data=data, suggestions=suggestions)


def cmd_doc_update_section(project_root: Path, reference: str, content: str) -> str:
    """更新文档中指定段落的正文内容，自动写回文件。"""
    # 空正文会把段落内容整段清空（等同于误删章节）——这是调用方最易犯的错，
    # 直接拒绝，避免一次失误就静默抹掉知识资产；要删段落请走 doc remove-section。
    if not content.strip():
        return _fail(
            "ERROR [update_section.empty_content] --content 不能为空，已拒绝修改（空正文会清空该章节）。"
            "修复：传入非空 --content；如需删除段落请改用 doc remove-section。"
        )
    file_rel = reference.split("#")[0]
    doc_rel = file_rel if file_rel.startswith("ProjectSpec/") else f"ProjectSpec/{file_rel}"
    safe_path = safe_join(project_root, doc_rel)
    if safe_path is None:
        return _fail(f"非法的路径: {file_rel}")
    full_path = safe_path
    if not full_path.exists():
        return _fail(
            f"ERROR [update_section.not_found] 文件不存在: {file_rel}。"
            "请先用 doc structure 取完整路径（doc read 允许省略 .md 与目录，"
            "写命令要求完整路径）。"
        )
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
        status=meta_dict.get("status", "active"),
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
        return _fail(
            f"ERROR [add_section.not_found] 文件不存在: {file_rel}。"
            "请先用 doc structure 取完整路径（doc read 允许省略 .md 与目录，"
            "写命令要求完整路径）。"
        )
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
        status=meta_dict.get("status", "active"),
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
        status=meta_dict.get("status", "active"),
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


def cmd_doc_reindex(project_root: Path) -> str:
    """全量重建 .doc-kit/index.json —— 扫描 ProjectSpec/ 下所有文档的 frontmatter。

    桌面 App 每次加载项目都会 rebuild 索引；纯 AI 流程没有 App，索引无人维护，
    于是 doc structure / doc read 读取的目录与依赖结构会与磁盘脱节（新建文档缺失、
    depends_on 为空）。本命令把 App 侧 ``IndexManager.rebuild`` 的同一职责搬进 CLI，
    由 spec-close 在批量写入 ProjectSpec 之后调用一次，使索引重新与磁盘一致。
    幂等：可反复调用，每次都从磁盘现状整体重建。

    解析失败的文档**不再无声吞掉**：在 ``data.skipped`` 回报清单，message 提示。
    本命令仍是**写操作**（重建索引），但与门禁职责分离——对账由只读的 ``doc lint``
    负责（R11）；此处 skipped 非致命，不改退出码。
    """
    index_path = project_root / ".doc-kit" / "index.json"
    mgr = IndexManager(index_path)
    count = mgr.rebuild(project_root / "ProjectSpec")
    mgr.save()
    skipped = list(getattr(mgr, "skipped", []))
    message = f"## ✅ 索引已重建\n\n共收录 {count} 篇文档"
    if skipped:
        shown = "、".join(skipped[:5]) + ("…" if len(skipped) > 5 else "")
        message += (
            f"\n\n⚠️ 有 {len(skipped)} 篇文档 frontmatter 解析失败、未入索引：{shown}"
            "。请运行 doc lint 查看 R11 明细。"
        )
    return _ok(
        message=message,
        data={"documents": count, "skipped": skipped, "skipped_count": len(skipped)},
        suggestions=["可调用 doc structure 验证目录与依赖结构已与磁盘一致。"],
    )


# ═══════════════════════════════════════════════════════════════
#  doc lint —— 规格完整性门禁（只读）
# ═══════════════════════════════════════════════════════════════
#
# 规则语义见 skills/guidance/doc-capabilities/_index.md §5 与
# SpecGovernance/spec-check-rules.md（luca 参考实现，出货后退役）。
# 硬门禁只收零 false-positive 的客观项；模糊项降 warning；语义层不进门禁。
#
# v1 规则（零项目参数）：
#   R1 (warning) frontmatter 必填字段齐备且非空
#   R3 (error)   限定引用可解析（目标文档存在且定义了该编号）
#   R4 (warning) 跨包裸写编号（同包 = 同 module + 同 feature；顶层/模块层不互认同包）
#   R5 (error)   同文档约束编号唯一
#   R7 (error)   无模板占位符（模式集从 .doc-kit/templates 派生）
#   R8 (error)   depends_on 版本与目标一致（含目标不存在）
#   R9 (error)   锚点 {#C-xxx}C-xxx 的锚名与编号一致
#   R10 (warning) registry 声明的必选顶层文档缺失
#   R11 (error)  frontmatter 必须可解析（不可降级/停用）
#   R12 (error)  表格行之间不得夹空行
# v2（需参数化）：R4 命名空间策略可配置化、R2 版本/日期诚实、R6 implemented_in 路径存在。

_RULE_LEVELS: dict[str, str] = {
    "R1": "warning",
    "R3": "error",
    "R4": "warning",
    "R5": "error",
    "R7": "error",
    "R8": "error",
    "R9": "error",
    "R10": "warning",
    "R11": "error",
    "R12": "error",
}

#: 不可降级 / 不可停用的规则（"自己的文档无法解析"是不可协商底线）
_LOCKED_RULES = {"R11"}

#: baseline key 取"具体违规标识"的规则；其余规则 key 为空、按文件级吸收
_BASELINE_KEYED_RULES = {"R4"}

_REQUIRED_FM_KEYS = ("doc_type", "module", "level", "version", "last_updated", "status")

# 限定引用：doc-type@module(.feature):C-xxx / :S-xxx（doc-type 用连字符或下划线）
_QUALIFIED_REF_RE = re.compile(
    r"(?P<dt>[a-z][a-z_-]+)@(?P<mod>[a-z0-9-]+)"
    r"(?:\.(?P<feat>[a-z0-9-]+))?:(?P<id>[CS]-\d+)"
)
# 裸写编号：前面不能再是标识符字符（避免命中 `LG-101` 之类）
_ANY_ID_RE = re.compile(r"(?<![A-Za-z0-9-])([CS]-\d+)")
# 文档内"定义"的编号：表格单元格（可带 {#C-xxx} 锚点）或锚点本身
_DEFINED_CELL_RE = re.compile(r"\|\s*(?:\{#([CS]-\d+)\})?([CS]-\d+)\s*\|")
_ANCHOR_RE = re.compile(r"\{#([CS]-\d+)\}")
_ANCHOR_PAIR_RE = re.compile(r"\{#([CS]-\d+)\}([CS]-\d+)")

#: 模板占位符（当项目内无 .doc-kit/templates 时的兜底形态集）
_FALLBACK_PLACEHOLDERS = ("<替代文档>", "<所属模块>", "<源码目录>", "<语言>")
_PLACEHOLDER_VAR_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")


def _mask_code_and_comments(text: str) -> str:
    """把 fenced code block 与 HTML 注释替换为等长空白（保留换行与行号）。

    硬门禁的前提：规则不得被代码块/注释里的示例误伤。替换为**等长空白**而非删除，
    使 findings 报告的行号仍是原文行号。
    """
    def _blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    masked = re.sub(r"<!--.*?-->", _blank, text, flags=re.DOTALL)
    lines = masked.split("\n")
    in_fence = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        is_fence = stripped.startswith("```") or stripped.startswith("~~~")
        if in_fence or is_fence:
            lines[i] = " " * len(line)
        if is_fence:
            in_fence = not in_fence
    return "\n".join(lines)


class _LintDoc:
    """lint 的只读文档视图：raw text + 解析结果 + 屏蔽代码/注释后的文本 + 已定义编号。"""

    def __init__(self, project_root: Path, path: Path) -> None:
        self.path = path
        self.rel = str(path.relative_to(project_root).as_posix())
        self.text, self.meta, self.error = read_document(path)
        meta = self.meta or {}
        self.doc_type = str(meta.get("doc_type", "") or "")
        self.module = str(meta.get("module", "") or "")
        self.level = str(meta.get("level", "") or "")
        self.feature = str(meta.get("feature", "") or "")
        self.version = str(meta.get("version", "") or "")
        self.last_updated = str(meta.get("last_updated", "") or "")
        self.status = str(meta.get("status", "") or "")
        self.masked = _mask_code_and_comments(self.text)
        self.defined_ids: set[str] = set()
        for anchor, cell in _DEFINED_CELL_RE.findall(self.masked):
            self.defined_ids.add(anchor or cell)
        for anchor in _ANCHOR_RE.findall(self.masked):
            self.defined_ids.add(anchor)


def _placeholder_patterns(project_root: Path) -> list[str]:
    """R7 的占位符形态集：从模板 **frontmatter** 派生 `<...>` 具体 token；`$identifier` 另行匹配。

    只取 frontmatter 里的 `<...>`（如 `superseded_by` 的 `<替代文档>`、`implemented_in`
    的 `<源码目录>`）：这些是"整值未填"型占位符，残留即静默腐化。模板**正文**里的
    `<功能名>` 之类是行文示例（合法引用），若一并纳入会产生误报——硬门禁零误报优先。

    优先从项目内 ``.doc-kit/templates/`` 派生（含用户自定义模板）；无则回退到仓库内
    ``src/app/templates/``（开发/测试态），再不行用内置兜底形态集。
    """
    tokens: set[str] = set()
    candidates = [project_root / ".doc-kit" / "templates"]
    repo_templates = Path(__file__).resolve().parents[2] / "src" / "app" / "templates"
    if repo_templates.is_dir():
        candidates.append(repo_templates)
    for tdir in candidates:
        if not tdir.is_dir():
            continue
        for tmpl in sorted(tdir.glob("*.md")):
            try:
                body = tmpl.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
            if fm:
                tokens.update(re.findall(r"<[^<>\n]{1,40}>", fm.group(1)))
        if tokens:
            break
    if not tokens:
        tokens.update(_FALLBACK_PLACEHOLDERS)
    return sorted(tokens)


def _lint_registry(project_root: Path) -> dict[str, dict]:
    return _load_registry(project_root) or {d["doc_type"]: d for d in DOC_TYPE_REGISTRY}


def _lint_spec_paths(project_root: Path, registry: dict[str, dict]) -> list[Path] | None:
    """规格文档 = ProjectSpec/ 下文件名 ∈ registry 模板文件名集合的 *.md。

    刻意**不**用"是否在 index.json 里"判定：reindex 会跳过解析失败的文档，
    用它判定会让 R11 永远看不到坏文档（循环失效）。
    """
    docs_root = project_root / "ProjectSpec"
    if not docs_root.is_dir():
        return None
    templates = {d.get("template") for d in registry.values() if d.get("template")}
    return [p for p in sorted(docs_root.rglob("*.md")) if p.name in templates]


def _lint_doc_type_for_stem(stem: str, registry: dict[str, dict]) -> str:
    for d in registry.values():
        tpl = str(d.get("template") or "")
        if tpl.endswith(".md") and tpl[:-3] == stem:
            return str(d.get("doc_type") or stem)
    return stem.replace("-", "_")


def _lint_resolve_target(docs: list["_LintDoc"], doc_type: str, module: str, feature: str | None) -> "_LintDoc | None":
    for d in docs:
        if d.doc_type != doc_type or d.module != module:
            continue
        if feature is None:
            if d.level == "module" or not d.feature:
                return d
        elif d.feature == feature:
            return d
    return None


def _load_lint_config(project_root: Path) -> tuple[bool, str, bool, dict[str, str], list[dict]]:
    """读取 .doc-kit/lint.yaml（仅用迷你解析器支持的子集）。

    返回 ``(enabled, baseline_rel, baseline_configured, severities, overrides)``。
    ``baseline_configured`` 为真才在缺文件时告警——项目压根没配 baseline 时不应报警。
    """
    cfg_path = project_root / ".doc-kit" / "lint.yaml"
    cfg: dict = {}
    if cfg_path.exists():
        try:
            raw = _parse_yaml_block(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg = raw
        except Exception:
            cfg = {}

    enabled = cfg.get("lint_enabled", True)
    if not isinstance(enabled, bool):
        enabled = True
    baseline_configured = bool(cfg.get("lint_baseline"))
    baseline = str(cfg.get("lint_baseline") or ".doc-kit/lint-baseline.json")

    severities = dict(_RULE_LEVELS)
    overrides: list[dict] = []
    rules = cfg.get("lint_rules") or []
    order = {"off": 0, "warning": 1, "error": 2}
    if isinstance(rules, list):
        for item in rules:
            if not isinstance(item, dict):
                continue
            rule = str(item.get("rule") or "").strip()
            level = str(item.get("level") or "").strip()
            if rule not in _RULE_LEVELS or level not in order:
                continue
            if level == _RULE_LEVELS[rule]:
                continue
            if rule in _LOCKED_RULES:
                overrides.append({"rule": rule, "from": _RULE_LEVELS[rule], "to": level,
                                  "applied": False, "reason": f"{rule} 不可降级/停用"})
                continue
            if order[level] > order[_RULE_LEVELS[rule]]:
                overrides.append({"rule": rule, "from": _RULE_LEVELS[rule], "to": level,
                                  "applied": False, "reason": "只允许降级或停用，禁止升级"})
                continue
            severities[rule] = level
            overrides.append({"rule": rule, "from": _RULE_LEVELS[rule], "to": level, "applied": True})
    return enabled, baseline, baseline_configured, severities, overrides


def _load_lint_baseline(project_root: Path, rel: str) -> tuple[set[tuple[str, str, str]], bool]:
    """读取 baseline JSON。返回 (集合, missing)。支持 {"entries":[...]} 或顶层列表。"""
    path = project_root / rel
    if not path.exists():
        return set(), True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set(), True
    entries = data.get("entries") if isinstance(data, dict) else data
    keys: set[tuple[str, str, str]] = set()
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        rule = e.get("rule")
        key = e.get("key", "")
        if rule and (e.get("file") is not None):
            keys.add((str(rule), str(e.get("file") or ""), str(key if key is not None else "")))
    return keys, False


def _required_top_doc_types(project_root: Path, registry: dict[str, dict]) -> set[str]:
    """从 .doc-kit 能力库 _index.md §1 解析"必选且顶层"的 doc_type。

    仅取顶层必选（business_context 等）：模块/功能层的必选性是**按作用域**的
    （有模块才要求 architecture），在无模块的项目上不该报表。
    """
    idx = project_root / ".doc-kit" / "skills" / "guidance" / "doc-capabilities" / "_index.md"
    if not idx.exists():
        return set()
    required: set[str] = set()
    for line in idx.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*`([a-z_]+)`\s*\|\s*[a-z0-9\-]+\.md\s*\|\s*([^|]*)\|", line)
        if not m:
            continue
        doc_type, mark = m.group(1), m.group(2)
        if "✅" in mark and (registry.get(doc_type) or {}).get("level") == "top":
            required.add(doc_type)
    return required


def _lint_findings(project_root: Path, docs: list[_LintDoc], registry: dict[str, dict]) -> tuple[list[tuple[str, str, str, str]], dict]:
    """返回 (findings, metrics)。findings 元素 = (rule, file, key, message)。"""
    findings: list[tuple[str, str, str, str]] = []
    metrics = {
        "documents": len(docs),
        "total_lines": sum(d.text.count("\n") + 1 for d in docs),
        "qualified_refs": 0,
        "qualified_refs_bad": 0,
        "bare_id_suspects": 0,
    }

    patterns = _placeholder_patterns(project_root)

    # ---- R11 frontmatter 可解析（其余规则跳过不可解析文档）----
    for d in docs:
        if d.error is not None:
            findings.append(("R11", d.rel, "", f"[R11] {d.rel}: frontmatter 解析失败：{d.error}"))

    parseable = [d for d in docs if d.error is None]

    for d in parseable:
        # ---- R1 必填字段 ----
        for k in _REQUIRED_FM_KEYS:
            if not str((d.meta or {}).get(k, "") or "").strip():
                findings.append(("R1", d.rel, "", f"[R1] {d.rel}: 缺少或为空 frontmatter 字段 `{k}`"))

        # ---- R5 同文档编号唯一 ----
        seen: dict[str, int] = {}
        for raw in d.masked.split("\n"):
            m = re.match(r"\|\s*(?:\{#([CS]-\d+)\})?([CS]-\d+)\s*\|", raw)
            if m:
                cid = m.group(1) or m.group(2)
                seen[cid] = seen.get(cid, 0) + 1
        dup = sorted(k for k, v in seen.items() if v > 1)
        if dup:
            findings.append(("R5", d.rel, "", f"[R5] {d.rel}: 同文档重复约束编号 {dup}"))

        # ---- R9 锚点与编号一致 ----
        for raw in d.masked.split("\n"):
            for a, b in _ANCHOR_PAIR_RE.findall(raw):
                if a != b:
                    findings.append(("R9", d.rel, "", f"[R9] {d.rel}: 锚点 `{{#{a}}}{b}` 的锚名与编号不一致"))

        # ---- R7 模板占位符 ----
        for token in patterns:
            if token in d.masked:
                findings.append(("R7", d.rel, "", f"[R7] {d.rel}: 残留模板占位符 `{token}`"))
        for var in sorted(set(_PLACEHOLDER_VAR_RE.findall(d.masked))):
            findings.append(("R7", d.rel, "", f"[R7] {d.rel}: 残留模板占位符 `{var}`"))

        # ---- R12 表格断裂（表行之间夹空行）----
        lines = d.masked.split("\n")
        for i in range(1, len(lines) - 1):
            if (lines[i].strip() == "" and lines[i - 1].lstrip().startswith("|")
                    and lines[i + 1].lstrip().startswith("|")):
                findings.append(("R12", d.rel, "", f"[R12] {d.rel}: 表格行之间夹空行（约第 {i + 1} 行）"))
                break

        # ---- R8 depends_on 版本一致 ----
        deps = (d.meta or {}).get("depends_on")
        if isinstance(deps, list):
            for dep in deps:
                if not isinstance(dep, dict):
                    continue
                dep_doc = dep.get("doc")
                if not dep_doc:
                    continue
                dep_rel = str(dep_doc)
                target = next((x for x in parseable if x.rel == dep_rel), None)
                if target is None:
                    target = next(
                        (x for x in parseable if x.rel.endswith("/" + dep_rel) or x.rel == f"ProjectSpec/{dep_rel}"),
                        None,
                    )
                if target is None:
                    findings.append(("R8", d.rel, "", f"[R8] {d.rel}: depends_on 目标不存在 {dep_doc}"))
                elif target.version and dep.get("version") and str(target.version) != str(dep["version"]):
                    findings.append((
                        "R8", d.rel, "",
                        f"[R8] {d.rel}: depends_on {dep_doc} version={dep.get('version')} 与目标 {target.version} 不一致",
                    ))

    # ---- R3 限定引用可解析 ----
    for d in parseable:
        for m in _QUALIFIED_REF_RE.finditer(d.masked):
            metrics["qualified_refs"] += 1
            doc_type = _lint_doc_type_for_stem(m.group("dt"), registry)
            target = _lint_resolve_target(parseable, doc_type, m.group("mod"), m.group("feat"))
            if target is None:
                metrics["qualified_refs_bad"] += 1
                findings.append(("R3", d.rel, "", f"[R3] {d.rel}: 限定引用目标文档不存在：{m.group(0)}"))
            elif m.group("id") not in target.defined_ids:
                metrics["qualified_refs_bad"] += 1
                findings.append((
                    "R3", d.rel, "",
                    f"[R3] {d.rel}: 限定引用目标约束不存在：{m.group(0)}（{target.rel} 未定义该编号）",
                ))

    # ---- R4 跨包裸写编号（warning）----
    for d in parseable:
        own = set(d.defined_ids)
        if d.feature:
            package = set(own)
            for o in parseable:
                if o.feature and o.module == d.module and o.feature == d.feature:
                    package |= o.defined_ids
        else:
            # 顶层/模块层不再互认同包：跨文档引用一律需全限定
            package = set(own)
        reported: set[str] = set()
        for m in _ANY_ID_RE.finditer(d.masked):
            cid = m.group(1)
            start = m.start(1)
            if start > 0 and d.masked[start - 1] == ":":
                continue  # 已全限定 `...:C-xxx`
            if cid in package:
                continue
            metrics["bare_id_suspects"] += 1  # 计"出现次数"（与参考实现口径一致）
            if cid in reported:
                continue  # findings/baseline 按 (file, id) 去重
            reported.add(cid)
            findings.append((
                "R4", d.rel, cid,
                f"[R4] {d.rel}: 疑似跨文档裸写编号 {cid}（跨文档引用应全限定为 doc-type@module(.feature):{cid}）",
            ))

    # ---- R10 registry 声明的必选顶层文档缺失 ----
    required = _required_top_doc_types(project_root, registry)
    present = {d.doc_type for d in parseable}
    missing = sorted(t for t in required if t not in present)
    if missing:
        findings.append(("R10", "", "", f"[R10] registry 声明的必选顶层文档缺失：{missing}"))

    return findings, metrics


def cmd_doc_lint(project_root: Path, baseline_path: str | None = None, summary: bool = False) -> str:
    """规格完整性门禁（只读）。有 error → success=false、退出码 1；仅 warning → 退出码 0。

    ``summary=True`` 时输出精简版（供技能收尾把结果读进 agent 上下文）：``data`` 只含
    ``metrics`` 与最多 20 条 ``errors[].message``，**不含 warnings 明细**。默认（无
    ``--summary``）保持完整输出（供 pre-commit / CI）。
    """
    enabled, baseline_rel, baseline_configured, severities, overrides = _load_lint_config(project_root)
    if baseline_path:
        baseline_rel = baseline_path
        baseline_configured = True

    if not enabled:
        data = {
            "metrics": {"documents": 0, "errors": 0, "warnings": 0, "baselined": 0},
            "errors": [], "warnings": [], "overrides_applied": overrides,
        }
        return _ok("doc lint 已按 .doc-kit/lint.yaml 停用（lint_enabled=false）", data=data, suggestions=[])

    registry = _lint_registry(project_root)
    paths = _lint_spec_paths(project_root, registry)
    if paths is None:
        return _fail(
            "ERROR [lint.no_docs] 未找到 ProjectSpec/ 目录。修复：先创建项目规格文档。",
            data={"metrics": {}, "errors": [], "warnings": []},
            suggestions=[],
        )

    docs = [_LintDoc(project_root, p) for p in paths]
    findings, metrics = _lint_findings(project_root, docs, registry)

    baseline_keys, baseline_missing = _load_lint_baseline(project_root, baseline_rel)
    if not baseline_configured:
        baseline_missing = False  # 未配置 baseline：缺文件是正常状态，不告警

    errors: list[dict] = []
    warnings: list[dict] = []
    baselined = 0
    rules_off: list[str] = []
    for rule, file, key, message in findings:
        sev = severities.get(rule, "warning")
        if sev == "off":
            if rule not in rules_off:
                rules_off.append(rule)
            continue
        if (rule, file, key) in baseline_keys:
            baselined += 1
            continue
        entry = {"rule": rule, "file": file, "key": key, "message": message}
        (errors if sev == "error" else warnings).append(entry)

    if baseline_missing:
        warnings.append({
            "rule": "config", "file": baseline_rel, "key": "",
            "message": f"[config] 已配置 baseline 但文件不存在：{baseline_rel}（按空 baseline 处理）",
        })

    metrics.update({
        "errors": len(errors),
        "warnings": len(warnings),
        "baselined": baselined,
    })
    data = {
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
        "overrides_applied": overrides,
        "rules_off": rules_off,
        "baseline": {"path": baseline_rel, "missing": baseline_missing, "absorbed": baselined},
    }
    if summary:
        # 精简版：只带 metrics 与 errors 摘要（≤20），不灌 warnings 明细进 agent 上下文
        data = {"metrics": metrics, "errors": errors[:20]}
        if len(errors) > 20:
            data["errors_truncated"] = True

    text = f"规格门禁：{len(errors)} error / {len(warnings)} warning（baseline 吸收 {baselined}）"
    if errors:
        return _fail(text, data=data, suggestions=[])
    return _ok(
        text,
        data=data,
        suggestions=["doc lint 只读；存量违规可用 .doc-kit/lint-baseline.json 吸收，配置见 .doc-kit/lint.yaml。"],
    )


# ═══════════════════════════════════════════════════════════════
#  review 子命令（对应原 get_git_history / add_git_history /
#  write_review_report）
# ═══════════════════════════════════════════════════════════════

REVIEW_STATE_DEFAULTS = {
    # 兼容字段：始终记录"最近一次"评审（旧版本只有这三个字段）
    "last_reviewed_commit": None,
    "last_reviewed_at": None,
    "review_history": [],
    # 按分支记录锚点：多分支并行评审不再互相覆盖
    "branches": {},
}


def _review_state_path(project_root: Path) -> Path:
    return project_root / ".doc-kit" / "code-review-state.json"


def _read_review_state(project_root: Path) -> dict:
    # 注意：REVIEW_STATE_DEFAULTS 含可变容器（review_history / branches），
    # 必须 deepcopy——浅拷贝会让多个项目共享同一个 dict/list，造成状态跨项目泄漏。
    path = _review_state_path(project_root)
    if not path.exists():
        return copy.deepcopy(REVIEW_STATE_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for k, v in REVIEW_STATE_DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(REVIEW_STATE_DEFAULTS)


def _write_review_state(project_root: Path, state: dict) -> None:
    path = _review_state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _current_git_branch(project_root: Path) -> str:
    """读取当前 git 分支名（只读 .git/HEAD，不执行 git 命令）。

    支持：常规仓库（.git/ 目录）、worktree/submodule（.git 是内含
    "gitdir: <路径>" 的文件）。读不到时返回空串——调用方据此走"无分支"
    的兼容路径，不报错。
    """
    git_path = project_root / ".git"
    try:
        if git_path.is_file():
            content = git_path.read_text(encoding="utf-8", errors="replace").strip()
            if content.startswith("gitdir:"):
                target = content.split(":", 1)[1].strip()
                git_dir = (project_root / target).resolve() if not Path(target).is_absolute() else Path(target)
            else:
                return ""
        elif git_path.is_dir():
            git_dir = git_path
        else:
            return ""
        head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if head.startswith("ref: refs/heads/"):
        return head[len("ref: refs/heads/"):].strip()
    return ""  # detached HEAD


def cmd_review_anchor_get(project_root: Path, branch: str = "") -> str:
    """获取指定分支（默认当前分支）上一次 code review 的 git 提交锚点。"""
    state = _read_review_state(project_root)
    branches = state.get("branches", {}) or {}
    target = branch.strip() or _current_git_branch(project_root)
    entry = branches.get(target) if target else None

    if entry:
        commit = entry.get("commit")
        return _ok(
            data={
                "branch": target,
                "last_reviewed_commit": commit,
                "last_reviewed_at": entry.get("at"),
                "source": "branch",
                "branches": branches,
                "review_history": state.get("review_history", []),
            },
            suggestions=[
                f"分支 {target} 上次评审锚点: {commit}",
                f"先校验锚点是否仍存在：git cat-file -e {commit}^{{commit}}（rebase / force-push 后可能已失效）",
                f"可用 git log {commit}..HEAD --oneline 查看新增提交。",
            ],
        )

    commit = state.get("last_reviewed_commit")
    if not commit:
        return _ok(
            data={
                "branch": target,
                "last_reviewed_commit": None,
                "last_reviewed_at": None,
                "source": "none",
                "branches": branches,
                "review_history": [],
            },
            suggestions=["尚无评审记录，将从头开始评审所有提交（或由用户指定起始 commit）。"],
        )
    return _ok(
        data={
            "branch": target,
            "last_reviewed_commit": commit,
            "last_reviewed_at": state.get("last_reviewed_at"),
            "source": "global",
            "branches": branches,
            "review_history": state.get("review_history", []),
        },
        suggestions=[
            f"分支 {target or '(未识别)'} 无专属锚点，回退到最近一次评审锚点: {commit}",
            "该锚点可能来自其它分支：请确认比对范围，或先校验 git cat-file -e <锚点>^{commit}。",
        ],
    )


def cmd_review_anchor_set(
    project_root: Path, commit_hash: str, session_spec_id: str = "", branch: str = ""
) -> str:
    """保存本次 code review 的 git 提交锚点（按分支记录，兼容旧的全局字段）。"""
    if not commit_hash or not commit_hash.strip():
        return _fail("commit_hash 不能为空")
    commit_hash = commit_hash.strip()
    target = branch.strip() or _current_git_branch(project_root)
    state = _read_review_state(project_root)
    now = datetime.now(timezone.utc).isoformat()
    state["last_reviewed_commit"] = commit_hash
    state["last_reviewed_at"] = now
    record = {"commit": commit_hash, "time": now}
    if session_spec_id:
        record["session"] = session_spec_id
    if target:
        record["branch"] = target
        entry = {"commit": commit_hash, "at": now}
        if session_spec_id:
            entry["session"] = session_spec_id
        state.setdefault("branches", {})[target] = entry
    state.setdefault("review_history", []).append(record)
    _write_review_state(project_root, state)
    scope = f"分支 {target}" if target else "全局（未能识别当前分支）"
    return _ok(
        data={
            "branch": target,
            "last_reviewed_commit": commit_hash,
            "last_reviewed_at": now,
            "branches": state.get("branches", {}),
        },
        suggestions=[
            f"{scope}的评审锚点已更新为 {commit_hash}。下次 code review 将从此 commit 开始。"
        ],
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
        "message": f"评审报告已写入 {filename}",
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
#  tool 子命令（工具链版本与副本一致性）
# ═══════════════════════════════════════════════════════════════

TOOLCHAIN_MANIFEST = ".doc-kit/toolchain.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        return ""
    return h.hexdigest()



def _version_key(version: str) -> tuple:
    """版本比较用键（YYYY.MM.N → 整数元组；非数字段退化为字符串）。"""
    parts = []
    for seg in str(version).split("."):
        parts.append(int(seg) if seg.isdigit() else -1)
    return tuple(parts)


def pending_toolchain_changes(recorded: str | None) -> tuple[int, list[dict], bool]:
    """返回 (落后版本数, 落后期间的变更条目, 项目版本是否早于历史起点)。

    - 落后 0 且 known=True：项目版本 == 当前版本；
    - known=False：项目版本不在历史上（早于历史起点，或版本号异常），
     此时把整段历史都当作"可能相关"，由调用方决定怎么提示。
    """
    versions = [h.get("version") for h in TOOLCHAIN_HISTORY]
    if not recorded or recorded not in versions:
        return (-1, list(TOOLCHAIN_HISTORY), False)
    idx = versions.index(recorded)
    pending = TOOLCHAIN_HISTORY[idx + 1:]
    return (len(pending), pending, True)


def cmd_tool_status(project_root: Path) -> str:
    """报告工具链版本与项目内副本的一致性。

    init 会把工具链快照复制进项目。此后仓库与项目各自演化，若不同步会出现
    「新技能 + 旧 CLI」：旧 CLI 会静默丢弃不认识的字段，命令却报成功。
    本命令把这种错配变成显式提示。
    """
    manifest_path = project_root / TOOLCHAIN_MANIFEST
    if not manifest_path.exists():
        return _ok(
            message="## ⚠️ 未找到工具链记录文件",
            data={
                "toolchain_version": TOOLCHAIN_VERSION,
                "recorded_version": None,
                "manifest": TOOLCHAIN_MANIFEST,
                "stale": True,
                "consistent": False,
                "reason": "no_manifest",
                "checked": 0,
                "mismatched": [],
                "missing": [],
            },
            suggestions=[
                "本项目由旧版 init 生成（没有 .doc-kit/toolchain.json），无法校验副本一致性。",
                f"请重跑：doc-kit init <项目根>（把 .doc-kit/ 刷新到 {TOOLCHAIN_VERSION}，不会改动 ProjectSpec/）",
                "并为 agent 侧重跑：doc-kit install-skills <agent 技能目录>，然后重新开始本次流程。",
            ],
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return _fail(f"ERROR [tool.bad_manifest] 读取 {TOOLCHAIN_MANIFEST} 失败: {e}。修复：重跑 doc-kit init 重新生成。")

    recorded = manifest.get("toolchain_version")
    files: dict = manifest.get("files", {}) or {}
    mismatched, missing = [], []
    for rel, digest in sorted(files.items()):
        target = project_root / rel
        if not target.exists():
            missing.append(rel)
        elif _sha256_file(target) != digest:
            mismatched.append(rel)

    stale = recorded != TOOLCHAIN_VERSION
    consistent = (not stale) and not mismatched and not missing
    behind, pending, version_known = pending_toolchain_changes(recorded)

    lines = ["## 工具链状态", ""]
    lines.append(f"**本 CLI 版本**: {TOOLCHAIN_VERSION}")
    lines.append(f"**项目记录版本**: {recorded or '（未记录）'}")
    lines.append(f"**记录时间**: {manifest.get('generated_at', '（未知）')}")
    if stale and behind > 0:
        lines.append(f"**落后**: {behind} 个版本")
    elif stale and recorded and not version_known:
        lines.append("**落后**: 版本号不在历史记录中（早于历史起点）")
    if stale and pending:
        lines.append("")
        lines.append("**该项目版本之后发布的内容**:")
        for item in pending[-8:]:
            lines.append(f"- `{item.get('version')}`（{item.get('date', '—')}）：{item.get('note', '（无说明）')}")
    lines.append(f"**副本校验**: {len(files) - len(mismatched) - len(missing)}/{len(files)} 一致")
    if mismatched:
        lines.append(f"**被改动/不一致**: {', '.join(mismatched[:5])}" + ("…" if len(mismatched) > 5 else ""))
    if missing:
        lines.append(f"**缺失**: {', '.join(missing[:5])}" + ("…" if len(missing) > 5 else ""))

    suggestions = []
    if stale:
        suggestions.append(
            f"项目记录的工具链版本（{recorded}）与当前 CLI（{TOOLCHAIN_VERSION}）不一致："
            "技能文本与项目副本可能不同步——新版技能配旧版 CLI 时，旧 CLI 会静默丢弃未知字段。"
        )
        if behind > 0:
            suggestions.append(f"本项目落后 {behind} 个版本，期间变更：")
            for item in pending[-8:]:
                suggestions.append(f"  · {item.get('version')}：{item.get('note', '（无说明）')}")
        elif recorded and not version_known:
            suggestions.append("项目版本早于历史记录起点，无法列出逐版差异；建议直接同步到当前版本。")
    if mismatched:
        suggestions.append(
            "存在被本地改动或半更新的副本（见上）。除非是有意定制，否则建议重跑 init 覆盖。"
        )
    if missing:
        suggestions.append("存在缺失副本（可能是手工删除或 init 中断）。建议重跑 init 补齐。")

    if suggestions:
        suggestions.append(
            "同步方式：doc-kit init <项目根>（只刷新 .doc-kit/，不改动 ProjectSpec/）"
            " + doc-kit install-skills <agent 技能目录>；完成后重新开始本次流程。"
        )
    else:
        suggestions.append("工具链一致，可继续。")

    return _ok(
        message="\n".join(lines),
        data={
            "toolchain_version": TOOLCHAIN_VERSION,
            "recorded_version": recorded,
            "manifest": TOOLCHAIN_MANIFEST,
            "generated_at": manifest.get("generated_at"),
            "stale": stale,
            "consistent": consistent,
            "behind_versions": behind if behind > 0 else 0,
            "pending_changes": pending if stale else [],
            "recorded_version_known": version_known,
            "checked": len(files),
            "mismatched": mismatched,
            "missing": missing,
        },
        suggestions=suggestions,
    )


# ═══════════════════════════════════════════════════════════════
#  DevSpec（spec-dev-loop 开发执行循环）子命令
# ═══════════════════════════════════════════════════════════════
#  DevSpec 是开发循环的工作区（DevSpec/active/<session>/），与 ProjectSpec
#  （唯一权威源）完全分离。核心纪律：本组命令不提供任何写 ProjectSpec 的
#  入口——开发循环内 ProjectSpec 只读，发现的设计问题只记录到 CodeNotes /
#  报告，修改由评审/会议在循环外完成（有版本痕迹地修改）。

DEV_TASK_STATUSES = [
    "pending", "implementing", "submitted", "accepted", "tested", "done", "rejected", "blocked",
]
"""任务状态（骨架化 + 委托实现流程）。

pending      骨架已确认，待实现
implementing 子代理/主代理实现中
submitted    产出已交回，待主代理验收
accepted     主代理验收通过（签名/注释承诺/文件范围/编译/冒烟）
tested       该任务的 GWT 用例真实通过
done         已提交
rejected     验收或测试不通过（note 必带失败证据），可重派
blocked      发现设计缺口/签名需变更，待用户裁决
"""
DEV_TASK_TRANSITIONS = {
    "pending": {"implementing"},
    "implementing": {"submitted", "rejected", "blocked"},
    "submitted": {"accepted", "rejected"},
    "accepted": {"tested", "rejected"},
    "tested": {"done", "rejected"},
    "rejected": {"implementing"},
    "blocked": {"implementing", "rejected"},
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

DEV_PHASE_LABELS = {
    "design": "设计与骨架化",
    "implement": "逐方法实现与验收",
    "test": "单元测试与验收测试",
    "close": "收尾归档",
}
"""循环阶段标签。阶段由 tasks.json 派生（不落库），避免与任务状态漂移。"""


def _dev_phase(tasks: list[dict]) -> str:
    """由任务状态派生当前阶段：design → implement → test → close。"""
    if not tasks:
        return "design"
    statuses = [t.get("status", "pending") for t in tasks]
    if all(s == "done" for s in statuses):
        return "close"
    if all(s in ("accepted", "tested", "done") for s in statuses):
        return "test"
    return "implement"


def _dev_next_step_suggestions(
    phase: str, tasks: list[dict], features: dict, modules: dict
) -> list[str]:
    """按阶段给出可执行的下一步（仅在循环内提议，不越界改 ProjectSpec）。"""
    out: list[str] = []
    if phase == "design":
        return [
            "尚无任务清单：完成 Phase 1（读设计 + 代码考古 + 约束整合）后进入 Phase 2 骨架化，"
            "再 dev task set 写入（每个方法必须带 implemented_in）。"
        ]
    if phase == "implement":
        blocked = [t for t in tasks if t.get("status") == "blocked"]
        if blocked:
            return [
                f"有 {len(blocked)} 个任务处于 blocked（设计缺口或签名变更待裁决）："
                f"先与用户确认处置后再继续（如 {blocked[0].get('task_id')}）。"
            ]
        submitted = [t for t in tasks if t.get("status") == "submitted"]
        if submitted:
            out.append(
                f"待验收 {len(submitted)} 个：主代理逐项验收后 "
                f"dev task update {submitted[0]['task_id']} --status accepted"
                "（不通过则 --status rejected --note '<失败证据>'）。"
            )
        rejected = [t for t in tasks if t.get("status") == "rejected"]
        if rejected:
            out.append(
                f"有 {len(rejected)} 个 rejected：补简报/修正后重派 → "
                f"dev task update {rejected[0]['task_id']} --status implementing。"
            )
        nxt = next((t for t in tasks if t.get("status") == "pending"), None)
        if nxt:
            out.append(
                f"按拓扑序取下一个任务：dev task update {nxt['task_id']} --status implementing 后派发实现。"
            )
    elif phase == "test":
        accepted = [t for t in tasks if t.get("status") == "accepted"]
        tested = [t for t in tasks if t.get("status") == "tested"]
        if accepted:
            out.append(
                f"待测试 {len(accepted)} 个：按 unit-tests.md 的 GWT 用例真实运行，"
                f"通过后 dev task update {accepted[0]['task_id']} --status tested，再 --status done。"
            )
        if tested:
            out.append(
                f"已 tested {len(tested)} 个：提交后 dev task update {tested[0]['task_id']} --status done。"
            )
        if not accepted:
            out.append(
                "单元测试已通过：执行验收测试（acceptance-tests.md 的 Gherkin）与回归，"
                "再 dev align --feature <功能名> --module <模块> --status aligned。"
            )
    elif phase == "close":
        unaligned = [f for f, info in features.items() if info.get("status") in (None, "tasks-done")]
        for fname in unaligned:
            out.append(
                f"功能 {fname} 任务已全部完成，下一步："
                f"dev align --feature {fname} --module <模块> --status aligned。"
            )
        unin = [m for m in modules if modules[m].get("status") in (None, "features-done")]
        if unin and not unaligned:
            out.append(
                f"模块 {unin[0]} 功能已全部对齐，下一步：dev integrate --module {unin[0]} --status integrated。"
            )
    if not out:
        out.append("所有任务与里程碑已完成，可 dev close --reason '<原因>' 后 dev archive 归档。")
    return out

#: 建议 agent 使用的 plan.md 段落引用示例。必须是 `plan.md#<章节>` 字面量：
#: `<plan.md>` 这类占位符会被 cmd_dev_plan_update_section 的 reference 校验拒绝。
#: 所有 help / suggestions 都应引用本常量，避免同一示例手写多遍后漂移
#: （回归见 tests/test_cli_self_consistency.py）。
PLAN_REFERENCE_EXAMPLE = "plan.md#2. 约束整合"

PLAN_SKELETON = """# 开发计划：{title}

## 1. 范围与目标

<!-- 范围：{scope_type} {target}。由 AI 在规划对话中填充：目标、边界、依赖范围。 -->

## 2. 约束整合

<!-- 将散落在 ProjectSpec 各文档的相关约束整合于此，逐条注明来源引用（如 feature-design@<功能名>:C-101）。
ProjectSpec 在开发循环内只读，此处仅整合不修改。 -->

## 2.5 代码风格快照

<!-- 代码考古产物（Phase 1 Step 3.5）：从目标模块存量代码提取的命名约定、错误处理模式、
日志格式、现有工具类/中间件。本节的每条都是实现阶段的强制风格约束，子代理简报必带。 -->

## 3. 骨架与任务清单

<!-- 由 CLI 从 tasks.json 自动渲染（dev task set / dev task update 后自动刷新）。
列含义：任务 / 方法(类) / 实现文件 / 覆盖约束 / 状态。骨架信息（类、方法、落点）在 Phase 2 骨架化时确定。 -->

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


DEV_LEGACY_TASK_STATUSES = {
    "in-progress": "implementing",
    "unit-green": "tested",
    "fixing": "rejected",
}
"""旧版任务状态 → 新版状态（骨架化流程上线前的会话迁移）。

旧 CLI 写到一半的会话（如 status=in-progress）在新状态机下会卡死：
task update 报非法迁移，task set 补救又要求 implemented_in。读取时统一映射，
任何一次写操作都会把映射结果落盘，从而让在途会话平滑升级。
"""


def _load_dev_tasks_raw(session_dir: Path) -> list[dict]:
    """读取 tasks.json 原文（不做状态映射）。"""
    p = session_dir / "tasks.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("tasks", [])
    except (json.JSONDecodeError, OSError):
        return []


def _normalize_legacy_task_statuses(tasks: list[dict]) -> int:
    """就地映射旧状态，返回被映射的任务数。"""
    mapped = 0
    for t in tasks:
        cur = t.get("status", "pending")
        if cur in DEV_LEGACY_TASK_STATUSES:
            t["status"] = DEV_LEGACY_TASK_STATUSES[cur]
            mapped += 1
    return mapped


def _load_dev_tasks(session_dir: Path) -> list[dict]:
    """读取任务清单（自动映射旧版状态，让在途会话可继续）。"""
    tasks = _load_dev_tasks_raw(session_dir)
    _normalize_legacy_task_statuses(tasks)
    return tasks


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
    raw_tasks = _load_dev_tasks_raw(session_dir)
    legacy_count = sum(1 for t in raw_tasks if t.get("status") in DEV_LEGACY_TASK_STATUSES)
    tasks = [dict(t) for t in raw_tasks]
    _normalize_legacy_task_statuses(tasks)
    sid = dev_spec.get("session_id", session_dir.name)
    branch = dev_spec.get("branch", "") or ""
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    phase = _dev_phase(tasks)
    counts = {s: sum(1 for t in tasks if t.get("status", "pending") == s) for s in DEV_TASK_STATUSES}
    lines = [
        "## ✅ 当前活跃开发循环",
        "",
        f"**会话**: {sid}",
        f"**范围**: {dev_spec.get('scope_type')} {dev_spec.get('scope_target')} · {dev_spec.get('title', '')}",
        f"**阶段**: {DEV_PHASE_LABELS[phase]}（{phase}）",
        f"**任务进度**: {done}/{total} done",
    ]
    if tasks:
        counters = " · ".join(f"{s} {counts[s]}" for s in DEV_TASK_STATUSES if counts[s])
        lines.append(f"**状态分布**: {counters}")
    if branch:
        lines.append(f"**开发分支**: {branch}")
    if tasks:
        lines.append("")
        lines.append("| 任务 | 方法 | 文件 | 状态 |")
        lines.append("|------|------|------|------|")
        for t in tasks:
            impl = t.get("implemented_in") or {}
            path = impl.get("path", "") if isinstance(impl, dict) else str(impl)
            symbol = t.get("symbol") or ", ".join(t.get("functions", [])[:2]) or "—"
            lines.append(
                f"| {t.get('task_id')} | {symbol} | {path or '—'} | {t.get('status', 'pending')} |"
            )
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
    if legacy_count:
        suggestions.append(
            f"检测到 {len(raw_tasks)} 个任务中含旧版状态（已自动映射为 {DEV_LEGACY_TASK_STATUSES}）："
            "继续开发即可，任何一次 dev task update 都会把映射结果落盘完成迁移。"
        )
    missing_loc = [t.get("task_id") for t in tasks if not (t.get("implemented_in") or {}).get("path")]
    if missing_loc:
        suggestions.append(
            f"有 {len(missing_loc)} 个任务缺少 implemented_in（实现落点）："
            "子代理派发需要它，请用 dev task set 补齐（Phase 2 骨架化产物）。"
        )
    suggestions.extend(_dev_next_step_suggestions(phase, tasks, features, modules))

    return _ok(
        message="\n".join(lines),
        data={
            "session_id": sid,
            "scope_type": dev_spec.get("scope_type"),
            "scope_target": dev_spec.get("scope_target"),
            "title": dev_spec.get("title"),
            "status": dev_spec.get("status"),
            "branch": branch,
            "phase": phase,
            "legacy_status_migrated": legacy_count,
            "status_counts": counts,
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
            f"整合约束：dev plan update-section '{PLAN_REFERENCE_EXAMPLE}' --content ...",
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
    doc_meta = DocMeta("", "", "", "", "active")
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
    # 与 doc update-section 同口径：空正文会清空段落，直接拒绝而非静默覆盖。
    if not content.strip():
        return _fail(
            "ERROR [dev_plan.empty_content] --content 不能为空，已拒绝修改（空正文会清空该段落）。"
            "修复：传入非空 --content。"
        )
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
    doc_meta = DocMeta("", "", "", "", "active")
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
    doc_meta = DocMeta("", "", "", "", "active")
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
    rows = ["| 任务 | 方法（类） | 实现文件 | 覆盖约束 | 状态 |", "|------|-----------|---------|---------|------|"]
    for t in tasks:
        fns = ", ".join(
            f"**{f}**（入口）" if f == t.get("entry_function") else f
            for f in t.get("functions", [])
        )
        cls = t.get("cls") or ""
        symbol = t.get("symbol") or ""
        if symbol and cls:
            method = f"`{cls}.{symbol}`"
        elif symbol:
            method = f"`{symbol}`"
        else:
            method = fns or "—"
        if fns and symbol:
            method = f"{method}<br/>{fns}"
        impl = t.get("implemented_in") or {}
        path = impl.get("path", "") if isinstance(impl, dict) else str(impl)
        lang = impl.get("lang", "") if isinstance(impl, dict) else ""
        loc = f"`{path}`" + (f" ({lang})" if lang else "") if path else "—"
        cons = ", ".join(t.get("constraint_ids", [])) or "—"
        rows.append(
            f"| {t.get('task_id','')} | {method} | {loc} | {cons} | {t.get('status','pending')} |"
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
    doc_meta = DocMeta("", "", "", "", "active")
    rel = str(plan_path.relative_to(project_root).as_posix())
    doc = DocContent.from_body(rel, doc_meta, body, raw_frontmatter=meta_dict)
    table = _render_task_table(tasks)
    heading = "3. 骨架与任务清单"
    section = doc.get_section(f"{rel}#{heading}")
    if section is None:
        # 向后兼容旧会话（旧骨架的章节名为 "3. 任务清单"）
        legacy = doc.get_section(f"{rel}#3. 任务清单")
        if legacy is not None:
            legacy.content = table
            plan_path.write_text(doc.to_markdown(), encoding="utf-8")
            return
        doc.insert_section(rel, heading, table)
    else:
        section.content = table
    plan_path.write_text(doc.to_markdown(), encoding="utf-8")


TASK_ALLOWED_KEYS = (
    "task_id", "title", "module", "feature", "functions", "entry_function",
    "signature", "gwt_refs", "constraint_ids", "status", "deviation", "notes",
    # 骨架化（Phase 2）确定的结构信息：类/方法归属、实现落点、调用关系、能力注释
    "cls", "symbol", "implemented_in", "calls", "capability_notes", "merge_reason",
    # 委托实现（Phase 3）的派发参数
    "timeout_seconds", "max_attempts", "attempts",
)

_TASK_LIST_FIELDS = ("functions", "gwt_refs", "constraint_ids", "calls", "capability_notes")
_TASK_STR_FIELDS = (
    "module", "feature", "entry_function", "signature", "title", "deviation", "notes",
    "cls", "symbol", "merge_reason",
)


def _clean_task(raw: dict, index: int) -> tuple[dict | None, str | None]:
    """校验并清洗单条任务。返回 (cleaned, error)。

    未知字段一律**报错**（不再静默丢弃）：历史上 timeout_seconds 与
    implemented_in 都曾因静默丢弃而"写了没生效"，这类坑必须在写入时就暴露。
    """
    tid = raw.get("task_id")
    if not tid or not str(tid).strip():
        return None, f"tasks[{index}] 缺少 task_id"
    tid = str(tid).strip()

    unknown = [k for k in raw if k not in TASK_ALLOWED_KEYS]
    if unknown:
        return None, (
            f"task '{tid}' 含未知字段 {unknown}。允许的字段: {list(TASK_ALLOWED_KEYS)}。"
            "（未知字段不再被静默忽略——如需新增字段请先扩展 CLI schema）"
        )

    if not raw.get("title") or not str(raw["title"]).strip():
        return None, f"tasks[{index}]（{tid}）缺少 title"
    status = raw.get("status", "pending")
    if status not in DEV_TASK_STATUSES:
        return None, f"task '{tid}' status '{status}' 不合法。允许: {DEV_TASK_STATUSES}"

    # 实现落点：骨架化的核心产物，子代理派发必需
    impl = raw.get("implemented_in")
    if impl is None or (isinstance(impl, dict) and not str(impl.get("path", "")).strip()):
        return None, (
            f"task '{tid}' 缺少 implemented_in.path（实现落点）。"
            "修复：Phase 2 骨架化时确定每个方法的源码文件，形如 "
            '{"path": "src/order/service.go", "lang": "go"}。'
        )
    if isinstance(impl, str):
        if not impl.strip():
            return None, f"task '{tid}' implemented_in 不能为空"
        impl = {"path": impl.strip()}
    elif not isinstance(impl, dict):
        return None, f"task '{tid}' implemented_in 必须是对象或路径字符串"
    else:
        impl = {"path": str(impl["path"]).strip()}
        if impl.get("lang") or raw["implemented_in"].get("lang"):
            impl["lang"] = str(raw["implemented_in"].get("lang", "")).strip()

    item: dict = {k: raw[k] for k in TASK_ALLOWED_KEYS if k in raw}
    item["task_id"] = tid
    item["status"] = status
    item["implemented_in"] = impl
    for k in _TASK_LIST_FIELDS:
        v = item.get(k)
        if v is None:
            item[k] = []
        elif isinstance(v, list):
            item[k] = [str(x) for x in v]
        else:
            return None, f"task '{tid}' 字段 {k} 必须是数组"
    for k in _TASK_STR_FIELDS:
        if k in item and item[k] is not None and not isinstance(item[k], str):
            item[k] = str(item[k])
    # 派发参数：数值 + 默认值
    for k, default in (("timeout_seconds", 300), ("max_attempts", 2), ("attempts", 0)):
        v = item.get(k, default)
        try:
            item[k] = int(v)
        except (TypeError, ValueError):
            return None, f"task '{tid}' 字段 {k} 必须是整数"
    if item["timeout_seconds"] <= 0:
        return None, f"task '{tid}' timeout_seconds 必须为正整数"
    if item["max_attempts"] < 0:
        return None, f"task '{tid}' max_attempts 不能为负"
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
        suggestions=[
            "plan.md §3 已同步（骨架与任务清单）。"
            "下一步：创建开发分支后，按拓扑序 dev task update <id> --status implementing 开始派发实现。"
        ],
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
            "（骨架确认后 pending → implementing → submitted（交回待验收）→ accepted（主代理验收通过）"
            " → tested（GWT 真实通过）→ done；验收/测试不通过 → rejected（可重派）；"
            "发现设计缺口或签名需变更 → blocked（待用户裁决））。"
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
    doc_meta = DocMeta("", "", "", "", "active")
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


def _fail(text: str, *, data: Any = None, suggestions: list[str] | None = None) -> str:
    # message 与 suggestions[0] 同文本：前者让"JSON 恒含四个字段"的约定成立，
    # 后者是历史消费方的读取位置，两者都保留。
    # 显式传入 suggestions（如 doc lint 用 []）时按传入值返回，便于把 findings
    # 全部放进 data，而不把上千条明细灌进 message/suggestions。
    return json.dumps(
        {
            "success": False,
            "message": text,
            "data": data,
            "suggestions": suggestions if suggestions is not None else [text],
        },
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

    tool = sub.add_parser("tool", help="工具链版本与副本一致性")
    tool_sub = tool.add_subparsers(dest="command", required=True)
    tool_sub.add_parser("status", help="报告工具链版本、项目副本一致性与同步建议")

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
    doc_read_p.add_argument(
        "path",
        help="文档路径：可带或不带 ProjectSpec/ 前缀，.md 后缀可省略；"
             "短路径有多个同名候选时报 doc_read.ambiguous 并列出全部候选（不猜）",
    )
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
    doc_sub.add_parser("reindex", help="全量重建 .doc-kit/index.json（扫描 ProjectSpec/ 的 frontmatter）")
    doc_lint_p = doc_sub.add_parser("lint", help="规格完整性门禁（只读；有 error 时退出码 1）")
    doc_lint_p.add_argument("--baseline", default=None, help="baseline JSON 路径（默认取 .doc-kit/lint.yaml 的 lint_baseline）")
    doc_lint_p.add_argument("--summary", action="store_true", help="精简输出：仅 metrics + ≤20 条 errors 摘要，不含 warnings 明细（供技能收尾）")

    review = sub.add_parser("review", help="代码评审锚点与报告")
    review_sub = review.add_subparsers(dest="command", required=True)
    anchor_get_p = review_sub.add_parser("anchor-get", help="获取评审锚点（默认当前分支）")
    anchor_get_p.add_argument("--branch", default="", help="指定分支名（默认读取 .git/HEAD）")
    anchor_set_p = review_sub.add_parser("anchor-set", help="保存评审锚点（按分支记录）")
    anchor_set_p.add_argument("commit_hash", help="本次评审到的完整 commit hash")
    anchor_set_p.add_argument("--session", default="", help="关联的议题 ID（可选）")
    anchor_set_p.add_argument("--branch", default="", help="指定分支名（默认读取 .git/HEAD）")
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
    plan_upd_p.add_argument("reference", help=f"段落引用，如 {PLAN_REFERENCE_EXAMPLE}")
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
    task_upd_p.add_argument("--status", required=True, help="目标状态：" + "/".join(DEV_TASK_STATUSES))
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
        if args.group == "tool":
            if args.command == "status":
                _emit(cmd_tool_status(project_root))
        elif args.group == "spec":
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
            elif args.command == "reindex":
                _emit(cmd_doc_reindex(project_root))
            elif args.command == "lint":
                _emit(cmd_doc_lint(project_root, args.baseline, args.summary))
        elif args.group == "review":
            if args.command == "anchor-get":
                _emit(cmd_review_anchor_get(project_root, args.branch))
            elif args.command == "anchor-set":
                _emit(cmd_review_anchor_set(project_root, args.commit_hash, args.session, args.branch))
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

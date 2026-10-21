"""SKILL.md 内容规则检具（阶段 0-4）。

背景：`TODO.md` §B2 记录——`check_skill_sync.py` 只查"命令是否存在 + 技能名一致性"，
而"状态值 / 字段 / 占位符格式"这类检查**只存在于 spec-dev-loop 的专用测试**里，
其余 7 份技能的内容规则在 CI 里无人守。本文件把四类规则提升为对全部 8 份生效的断言：

  1. 所有 `--status X` 取值必须来自实现导出的枚举；
  2. 不得出现实现中不存在的状态名；
  3. 共享前言不得对 CLI 运行时做与实现相反的断言；
  4. 引用某条 CLI 输出文本时，必须在其附近指明它来自哪个命令。

已知缺陷一律用"守卫 + 解除"两个测试表达：守卫（绿）从第一天起拦住**新增**违规，
解除测试为 `xfail(strict=True)`（当前红），修好后转为 XPASS 而报错，逼迫删除标记。
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "scripts"))

import cli  # noqa: E402

SKILLS = sorted((REPO / "skills").glob("spec-*/SKILL.md"))
CONVENTION = REPO / "skills" / "_shared" / "output-convention.md"

#: 已知使用了"实现中不存在的状态名"的条目。**阶段 2 已清空**：
#: spec-start 的 `idle` 已改为「没有活跃议题」。
#: 本检具只认这份显式清单——它是一条定向回归，不是通用的状态词汇推断。
KNOWN_NON_REAL_STATE_NAMES: dict[str, str] = {}

#: 已知把某条 CLI 输出文本归错了命令的条目。
QUOTED_OUTPUT = "存在残留文件"
#: 当前无已知条目——2026-09 已修正 spec-archive 的归属错误（该文本属 `spec write`，不属 `spec status`）。
KNOWN_MISATTRIBUTED_OUTPUTS: dict[tuple[str, str], str] = {}
#: 判定"附近是否指明了来源命令"的字符窗口。
ATTRIBUTION_WINDOW = 160


def _iter_parsers(parser: argparse.ArgumentParser):
    yield parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                yield from _iter_parsers(sub)


def _parser_status_choices() -> set[str]:
    """argparse 树中所有 `--status` 选项的合法取值（dev align / dev integrate 等）。"""
    values: set[str] = set()
    for parser in _iter_parsers(cli.build_parser()):
        for action in parser._actions:
            if action.dest == "status" and action.choices:
                values.update(str(choice) for choice in action.choices)
    return values


def _allowed_statuses() -> set[str]:
    """任务状态来自实现常量，其余来自 argparse choices。"""
    return set(cli.DEV_TASK_STATUSES) | _parser_status_choices()


def test_skill_status_values_are_real_enum_values():
    """`--status` 的取值必须真实存在，否则 AI 会照文档调用一个非法值。"""
    allowed = _allowed_statuses()
    assert allowed, "未能从实现导出任何合法状态值，检具本身可能已失效"
    problems: list[str] = []
    seen = 0
    for path in SKILLS:
        for match in re.finditer(r"--status\s+<?([a-z][a-z|_-]*)", path.read_text(encoding="utf-8")):
            for value in filter(None, match.group(1).split("|")):
                seen += 1
                if value not in allowed:
                    problems.append(f"{path.parent.name}: --status {value}（合法值：{sorted(allowed)}）")
    assert seen >= 10, f"只抽到 {seen} 个 --status 取值，抽取逻辑可能已失效"
    assert problems == [], "SKILL.md 使用了非法的 --status 取值：\n  " + "\n  ".join(problems)


def _found_non_real_state_names() -> set[str]:
    found: set[str] = set()
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        for name in ("idle",):
            if re.search(rf"\b{name}\b", text):
                found.add(name)
    return found


def test_no_new_non_real_state_names():
    """漂移守卫：不得引入实现中不存在的状态名。"""
    new = sorted(_found_non_real_state_names() - set(KNOWN_NON_REAL_STATE_NAMES))
    assert new == [], f"引入了实现中不存在的状态名：{new}（应改用「没有活跃议题」这类与 CLI 输出一致的措辞）"


def _misattributed_quoted_outputs() -> set[tuple[str, str]]:
    """引用了 CLI 输出文本、但附近没指明来源命令的位置。"""
    found: set[tuple[str, str]] = set()
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(re.escape(QUOTED_OUTPUT), text):
            window = text[max(0, match.start() - ATTRIBUTION_WINDOW): match.end() + ATTRIBUTION_WINDOW]
            if "spec write" not in window:
                found.add((path.parent.name, QUOTED_OUTPUT))
    return found


def test_no_new_misattributed_quoted_outputs():
    """漂移守卫：引用 CLI 输出文本时必须写明它来自哪个命令。"""
    new = sorted(_misattributed_quoted_outputs() - set(KNOWN_MISATTRIBUTED_OUTPUTS))
    assert new == [], (
        "以下位置引用了 CLI 输出文本，但附近没有指明来源命令"
        f"（须在 {ATTRIBUTION_WINDOW} 字符内出现该命令名）：{new}"
    )


def test_convention_does_not_claim_a_uniform_error_format():
    """前言不得声称错误格式"统一为 …"——实测只有约四分之一的失败点符合。"""
    text = CONVENTION.read_text(encoding="utf-8")
    assert "错误信息统一为" not in text, (
        "前言声称错误信息『统一为 ERROR [<错误码>] <原因>。修复：<建议>』，"
        "但实测仅 32/115 处 _fail() 符合；应改为『部分错误带此格式，不要依赖正则解析』"
    )


def _json_response_dicts() -> list[tuple[int, set[str]]]:
    """cli.py 中所有"响应信封"字典字面量（含 `success` 键者）及其键集合。

    用 AST 而不是正则：`review report-write` 的响应里嵌了 `data` 子字典，
    正则会被嵌套大括号骗到。
    """
    tree = ast.parse((REPO / "skills" / "scripts" / "cli.py").read_text(encoding="utf-8"))
    found: list[tuple[int, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if "success" in keys:
            found.append((node.lineno, keys))
    return found


def test_json_responses_carry_the_documented_keys():
    """前言承诺 JSON 结果含四个字段——那么每个响应字典都必须真的带上它们。

    这条替代了早先"前言声称 message 恒在、但实现没有"的 xfail：
    阶段 1 选择**把约定变成真的**（给 `_fail` 与 `review report-write` 补上 `message`），
    而不是把承诺削弱成"有时有"。所以这里改为校验实现与约定一致。
    """
    documented = {"success", "message", "data", "suggestions"}
    responses = _json_response_dicts()
    assert responses, "未找到任何响应字典，检具本身可能已失效"
    missing = [
        f"cli.py:{line} 缺 {sorted(documented - keys)}"
        for line, keys in responses
        if not documented <= keys
    ]
    assert missing == [], "响应字典缺少前言承诺的字段：\n  " + "\n  ".join(missing)


def test_convention_documents_the_argparse_exit_code():
    """前言只提"退出码 0 = 成功、1 = 失败"，漏了 argparse 层的 2。"""
    text = CONVENTION.read_text(encoding="utf-8")
    assert not re.search(r"退出码 0 = 成功、1 = 失败", text), (
        "前言只说明退出码 0/1；实测参数错误（未知选项、缺必填参数）返回 exit 2，"
        "而这恰是 agent 最典型的失误场景"
    )


# ── 路由与去重的契约（阶段 3：让原先无内容级校验的 6 份技能也有人守）─────────────

#: 必须按 `spec read` 的结构化 JSON 路由的技能。
ROUTING_SKILLS = ("spec-start", "spec-archive")
#: 其中必须**彻底**不再引用 `spec status` 的技能。
#: （原先 `spec-load` 不在此列——它保留 `spec status` 仅用于给用户的一句话现状摘要；
#:  该技能已于 2026.09.10 并入 `spec-start`，因此本项不再需要例外。）
SKILLS_WITHOUT_STATUS_ROUTING = ("spec-start", "spec-archive")


def _skill_text(name: str) -> str:
    return (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def _skill_body(name: str) -> str:
    """只取正文（去掉生成的前言）。

    必须按区域扫描：前言是生成物，它注入的共享"输出约定"段落里本来就提到
    `spec status`（那是"三个纯文本命令"的例外说明），并不是路由依据。
    扫全文会把生成的共享文字当成技能自己的写法来判——这是本检具最容易犯的错。
    """
    text = _skill_text(name)
    match = re.search(r"^# spec-", text, re.M)
    assert match, f"{name} 找不到正文 H1（`# spec-`）"
    return text[match.start():]


def test_routing_uses_structured_state_not_chinese_prose():
    """路由必须基于 `spec read` 的 JSON 字段，而不是 `spec status` 的中文散文。

    `spec status` 只输出一行中文描述（`cli.py:225-258`），CLI 一改文案技能路由就失效——
    即 `TODO.md` §B1 记的隐式耦合。本测试要求这些路由技能都用 `spec read` 的字段判定。

    判据是**行为**而非措辞：正文必须**调用** `spec read`，且不得**调用** `spec status`。
    只说"不要用 spec status"的解释性文字不算违规——早先按"出现即违规"判定时，
    正是被这类说明文字误伤（本检具第四次栽在"扫文本而不看角色"上）。
    """
    problems: list[str] = []
    for name in ROUTING_SKILLS:
        if "cli.py spec read" not in _skill_body(name):
            problems.append(f"{name}：正文未调用 `spec read` 做路由")
    for name in SKILLS_WITHOUT_STATUS_ROUTING:
        if "cli.py spec status" in _skill_body(name):
            problems.append(f"{name}：正文仍调用 `spec status`（应改用 `spec read` 的 JSON 字段判定）")
    assert problems == [], "\n  ".join(problems)


def test_unique_checkpoint_claim_is_qualified():
    """"唯一落盘点"必须带"讨论期间"限定，否则与前言的三处落盘点定义冲突。"""
    problems: list[str] = []
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer("唯一落盘点", text):
            window = text[max(0, match.start() - 30): match.end()]
            if "讨论期间" not in window:
                line = text[: match.start()].count("\n") + 1
                problems.append(f"{path.parent.name}:{line}「{window.strip()}」")
    assert problems == [], (
        "以下位置的「唯一落盘点」缺少「讨论期间」限定：\n  " + "\n  ".join(problems)
    )


def test_spec_close_delegates_persistence_to_spec_pause():
    """`spec-close` 不得重述落盘流程——同一流程两处来源必然漂移。"""
    text = _skill_text("spec-close")
    assert "spec-pause" in text, "spec-close 未引用 spec-pause，落盘流程可能又被复制了一份"
    assert "等价于 `spec-pause` 的核心流程" not in text, (
        "spec-close 仍在重述 spec-pause 的落盘流程；应改为加载并执行该技能"
    )


#: 反触发面的**等价措辞**——本仓库实际用到的几种"明确说明不做什么"的写法。
#: 这是一条措辞代理，不是语义证明：它只保证"存在一处负向范围声明"，不判断内容质量。
BOUNDARY_MARKERS = ("## 边界", "不适用", "不走本技能")


def test_every_skill_declares_its_boundaries():
    """每份技能都要有反触发面声明（可路由性的"何时不该用"）。"""
    problems: list[str] = []
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        if not any(marker in text for marker in BOUNDARY_MARKERS):
            problems.append(path.parent.name)
    assert problems == [], (
        f"以下技能缺少反触发面声明（需含 {BOUNDARY_MARKERS} 之一）：{problems}"
    )


def test_descriptions_fit_the_catalog_budget():
    """描述是常驻目录成本；`tool-skill` 的 `catalogDescriptionMaxLength` 是 500 字符硬截断。

    下限 20 字符用于排除"没写触发条件"的退化描述。上限取 200 而不是 500：
    目录是每轮都计费的历史消息，8 份描述的超支要乘以 8。
    """
    problems: list[str] = []
    for path in SKILLS:
        match = re.search(r"^description:\s*(.+)$", path.read_text(encoding="utf-8"), re.M)
        assert match, f"{path.parent.name} 缺 description"
        description = match.group(1).strip()
        if not 20 <= len(description) <= 200:
            problems.append(f"{path.parent.name}：{len(description)} 字符（要求 20–200）")
    assert problems == [], "\n  ".join(problems)

"""USAGE 表 ↔ 真实 argparse 树 的等值检具（阶段 0-2；阶段 2 完成可选性修复）。

背景：全库没有任何检具校验 CLI 的**选项与位置参数**。
`check_skill_sync.py` 的 `GROUP_RE` 只匹配"命令组 + 至多 2 个单词"（只认命令路径）；
`test_skill_preamble.py::test_all_commands_registered` 只校验命令登记在**手写的** USAGE 表里，
而 USAGE 表本身不等于真实 CLI。本文件补上这一环。

`tests/render_skill_preamble.py` 的 USAGE 是"命令 → 规范用法行"的单一事实源，
会被派生注入全部 9 份 SKILL.md 的工具清单。它一旦与真实 CLI 漂移，
AI 就会照着错的用法调用。

检查五项：
  1. 每条 USAGE 命令都存在于真实 argparse 树；
  2. 真实 argparse 树的每个叶子命令都在 USAGE 里登记（防新增命令漏登记）；
  3. USAGE 里写的每个 `--选项` 都真实存在；
  4. USAGE 里位置参数个数与真实一致；
  5. **可选性标注**：未加 `[]` 的选项必须真的 `required=True`，加了 `[]` 的必须真的可选。

第 5 项有一类**合法例外**：argparse 非必填、但命令内按情形强制要求的选项
（如 `dev plan create --module` 只在 `scope=feature` 时要求）。
这类例外没有被"豁免"掉——`CONDITIONALLY_REQUIRED` 的每一条都由
`test_conditionally_required_options_are_really_enforced` 用**实跑探针**验证：
一旦命令内不再校验，该测试就会失败，例外立刻失效。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import cli  # noqa: E402
import render_skill_preamble as R  # noqa: E402

CLI = REPO / "skills" / "scripts" / "cli.py"

#: 合法的"条件必填"例外：(USAGE 命令, 选项) → 说明与实跑探针。
#: 探针必须**失败**（省略该选项时命令拒绝执行），否则例外不成立。
CONDITIONALLY_REQUIRED: dict[tuple[str, str], dict[str, object]] = {
    ("dev plan create", "--module"): {
        "why": "argparse 非必填，但 scope=feature 时命令内强制要求（ERROR [dev_plan.missing_module]）",
        "probe": ["dev", "plan", "create", "--scope", "feature", "--target", "demo"],
    },
}


def _leaf_commands() -> dict[str, argparse.ArgumentParser]:
    """{命令路径: 子解析器}，路径形如 `dev plan update-section`（与 USAGE 键同格式）。"""
    def walk(parser: argparse.ArgumentParser, prefix: str) -> dict[str, argparse.ArgumentParser]:
        found: dict[str, argparse.ArgumentParser] = {}
        for action in parser._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            for name, sub in action.choices.items():
                nested = walk(sub, f"{prefix}{name} ")
                found.update(nested or {f"{prefix}{name}": sub})
        return found

    top = [a for a in cli.build_parser()._actions if isinstance(a, argparse._SubParsersAction)][0]
    return {f"{group} {path}": sub for group, gp in top.choices.items() for path, sub in walk(gp, "").items()}


def _parse_usage(key: str, value: str) -> tuple[set[str], set[str], list[str]]:
    """把一条 USAGE 用法行拆成 (未加[]的选项, 加了[]的选项, 位置参数)。

    依次做：去掉行尾 `#` 注释 → 抽出 `[...]` 段（其中的选项视为可选）→
    把 `'...'` 折成单个词（选项值常含空格，如 `'<完整 spec JSON>'`）→ 分词。
    选项后紧跟的那个词是它的取值，不计入位置参数。
    """
    body = value.split("#", 1)[0]
    body = body.split("cli.py", 1)[1] if "cli.py" in body else body
    bracketed_options = set(re.findall(r"--[a-z][a-z-]*", " ".join(re.findall(r"\[[^\]]*\]", body))))
    text = re.sub(r"\[[^\]]*\]", " ", body)
    text = re.sub(r"'[^']*'", "QVALUE", text)
    words = text.split()[len(key.split()):]
    required_presented: set[str] = set()
    positionals: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word.startswith("--"):
            required_presented.add(word)
            index += 2  # 跳过该选项的取值
        else:
            positionals.append(word)
            index += 1
    return required_presented, bracketed_options, positionals


def _optionality_violations() -> list[tuple[str, str, str]]:
    """[(命令, 选项, 说明)]：USAGE 的 `[]` 标注与实现的 required 不符者。"""
    table = _leaf_commands()
    violations: list[tuple[str, str, str]] = []
    for key, value in R.USAGE.items():
        sub = table.get(key)
        if sub is None:
            continue
        real = {opt: action for action in sub._actions if action.option_strings for opt in action.option_strings}
        required_presented, bracketed, _ = _parse_usage(key, value)
        for option in sorted(required_presented):
            if option in real and not real[option].required:
                violations.append((key, option, "标为必填，但 argparse 中 required=False"))
        for option in sorted(bracketed):
            if option in real and real[option].required:
                violations.append((key, option, "标为可选，但 argparse 中 required=True"))
    return violations


def _violation_keys() -> set[tuple[str, str]]:
    return {(key, option) for key, option, _ in _optionality_violations()}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """能被 CLI 识别的最小工程：`SessionSpec/` 标记项目根，`ProjectSpec/` 提供 feature 范围。"""
    (tmp_path / "SessionSpec").mkdir()
    (tmp_path / "ProjectSpec" / "module-m" / "features" / "demo").mkdir(parents=True)
    return tmp_path


def test_every_usage_command_exists():
    table = _leaf_commands()
    missing = [key for key in R.USAGE if key not in table]
    assert missing == [], f"USAGE 登记了真实 CLI 中不存在的命令：{missing}"


#: 有意**只给人工用**、不进技能工具清单的 CLI 命令 → 理由。
#: 它们不进 USAGE 是正当的：技能不该教 agent 删除段落或改 plan 骨架。
#: 但必须在此显式登记——否则"新增命令时忘了说清用途"与"有意不进技能"无法区分。
CLI_ONLY_COMMANDS: dict[str, str] = {
    "doc remove-section": "删除段落是破坏性操作，spec-close 明确把它划出职责；仅供人工使用",
    "dev plan add-section": "plan.md 骨架由 PLAN_SKELETON 固定，技能无需新建段落；仅供人工使用",
    "doc lint": "门禁命令，供人工/CI 直接调用；skill 集成待模型层落地后评估",
}


def test_every_cli_command_is_registered_in_usage():
    """每个 CLI 命令要么登记进 USAGE（技能可引用），要么显式声明为仅供人工。"""
    missing = sorted(set(_leaf_commands()) - set(R.USAGE) - set(CLI_ONLY_COMMANDS))
    assert missing == [], (
        "以下 CLI 命令既未登记 USAGE，也未声明为仅供人工：\n  "
        + "\n  ".join(missing)
        + "\n\n若它有意不进技能工具清单，请加入 CLI_ONLY_COMMANDS 并写明理由；"
        "否则请登记进 render_skill_preamble.USAGE。"
    )


def test_cli_only_commands_are_real_and_stay_out_of_usage():
    """CLI_ONLY_COMMANDS 必须指向真实命令，且确实不在 USAGE 里（两条声明不能自相矛盾）。"""
    table = _leaf_commands()
    problems = [f"{key}：CLI 中不存在" for key in CLI_ONLY_COMMANDS if key not in table]
    problems += [f"{key}：已在 USAGE 中，应从 CLI_ONLY_COMMANDS 移除" for key in CLI_ONLY_COMMANDS if key in R.USAGE]
    problems += [f"{key}：缺理由" for key, why in CLI_ONLY_COMMANDS.items() if not why.strip()]
    assert problems == [], "CLI_ONLY_COMMANDS 条目失效：\n  " + "\n  ".join(problems)


def test_every_usage_option_exists():
    table = _leaf_commands()
    problems: list[str] = []
    for key, value in R.USAGE.items():
        sub = table.get(key)
        if sub is None:
            continue
        real = {opt for action in sub._actions if action.option_strings for opt in action.option_strings}
        required_presented, bracketed, _ = _parse_usage(key, value)
        for option in sorted(required_presented | bracketed):
            if option not in real:
                problems.append(f"{key} {option}：实现中不存在该选项（可用：{sorted(real)}）")
    assert problems == [], "USAGE 写了不存在的选项：\n  " + "\n  ".join(problems)


def test_every_usage_positional_count_matches():
    table = _leaf_commands()
    problems: list[str] = []
    for key, value in R.USAGE.items():
        sub = table.get(key)
        if sub is None:
            continue
        real = [action.dest for action in sub._actions if not action.option_strings]
        _, _, positionals = _parse_usage(key, value)
        if len(positionals) != len(real):
            problems.append(f"{key}：USAGE 有 {len(positionals)} 个位置参数 {positionals}，实现有 {len(real)} 个 {real}")
    assert problems == [], "USAGE 的位置参数与实现不符：\n  " + "\n  ".join(problems)


def test_no_unexplained_optionality_violations():
    """可选性标注必须与实现一致，除非是已被实跑验证的"条件必填"例外。"""
    unexplained = sorted(_violation_keys() - set(CONDITIONALLY_REQUIRED))
    allowed = "\n  ".join(f"{key} {opt}：{cfg['why']}" for (key, opt), cfg in CONDITIONALLY_REQUIRED.items())
    assert unexplained == [], (
        "USAGE 的可选性标注与实现不符（未加 [] 者必须 required=True，加了 [] 者必须可选）：\n  "
        + "\n  ".join(f"{key} {opt}" for key, opt in unexplained)
        + f"\n\n已由实跑验证的条件必填例外：\n  {allowed}"
    )


def test_conditionally_required_options_are_really_enforced(project: Path):
    """例外不是豁免：探针必须真的失败，否则"条件必填"的说法不成立。"""
    failures: list[str] = []
    for (key, option), config in CONDITIONALLY_REQUIRED.items():
        probe = list(config["probe"])  # type: ignore[arg-type]
        assert option not in probe, f"{key} {option} 的探针不应包含该选项，否则无法证明它是必填"
        done = subprocess.run(
            [sys.executable, str(CLI), "--root", str(project), *probe],
            capture_output=True, text=True, cwd=str(project),
        )
        payload = json.loads(done.stdout) if done.stdout.lstrip().startswith("{") else {}
        if done.returncode == 0 or payload.get("success") is not False:
            failures.append(f"{key} {option}：省略该选项时命令竟然成功（exit {done.returncode}）")
    assert failures == [], (
        "以下「条件必填」例外已不成立——命令内不再强制要求该选项，"
        "应从 CONDITIONALLY_REQUIRED 移到违规判定里：\n  " + "\n  ".join(failures)
    )

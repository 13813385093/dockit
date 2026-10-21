#!/usr/bin/env python3
"""工具链版本递增检查 —— 内容变了就必须递增 TOOLCHAIN_VERSION。

要解决的问题
------------
`init` 把工具链**快照复制**进项目（CLI / 技能 / 能力库 / 模板）。改了工具链内容
却不递增 `cli.py` 的 `TOOLCHAIN_VERSION` 时，`tool status` 无法察觉「项目副本
是旧版」——因为**副本哈希仍然一致**，版本号也没变。这类漏改会让"新技能配旧
CLI"的错配重新变成静默问题。

工作方式（不依赖 git 历史，浅克隆/压缩包同样可用）
--------------------------------------------------
1. 对工具链**源文件**取内容指纹（成员 = init 会复制进项目的那些文件）；
2. 指纹存入 `tests/toolchain-fingerprint.json`（连同上一次记录的版本号）；
3. 校验：当前指纹 == 记录指纹，否则失败并给出修复步骤；
4. 更新：`--update` 写入新指纹，但**若内容已变而版本号未变则拒绝**
   —— 这是规则「内容变 ⇒ 版本必须变」的落点。

用法
----
    python tests/check_toolchain_version.py            # 校验（CI / pytest 调用）
    python tests/check_toolchain_version.py --update   # 内容与版本都改好后更新指纹

维护者发布流程（改工具链时按顺序做，缺一步都会被检具拦住）
--------------------------------------------------------
    1. 改内容      —— skills/scripts、skills/spec-*/SKILL.md、skills/_shared、
                      skills/guidance、src/app/templates 任意一处
    2. 递增版本    —— skills/scripts/cli.py 的 TOOLCHAIN_VERSION（格式 YYYY.MM.N）
    3. 重生成前言  —— python tests/render_skill_preamble.py
                      （把新版本注入 8 份 SKILL.md；漏做则 --check 失败）
    4. 更新指纹    —— python tests/check_toolchain_version.py --update
                      （版本未递增会被拒绝写入）
    5. 全绿再提交  —— python -m pytest tests/
                      + 三个检具（check_skill_sync / check_doc_consistency /
                        check_toolchain_version）

    若在**同一版本内继续迭代**（本次发布尚未提交、也没有任何项目用过该版本）：
    直接删除 tests/toolchain-fingerprint.json 再跑 --update 即可等价于
    "本次发布尚未定稿"；一旦提交/发布过，就必须递增版本号。

边界说明
--------
指纹成员**只含会被复制进项目的文件**（skills/scripts、spec-*/SKILL.md、
skills/_shared、guidance、src/app/templates）。应用侧代码（src/app/main.py、
engine/）不进指纹——它们随程序分发，不会在项目里形成版本偏斜。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FINGERPRINT_FILE = REPO / "tests" / "toolchain-fingerprint.json"

# 工具链源文件成员（相对仓库根；目录会被递归展开）
TOOLCHAIN_MEMBERS = (
    "skills/scripts",
    "skills/_shared",
    "skills/guidance",
    "src/app/templates",
)
TOOLCHAIN_GLOB_SKILLS = "skills/spec-*/SKILL.md"

VERSION_RE = re.compile(r'^TOOLCHAIN_VERSION\s*=\s*["\']([^"\']+)["\']', re.M)
HISTORY_RE = re.compile(r"(?ms)^TOOLCHAIN_HISTORY = \[.*?^\]")
CLI_PATH = "skills/scripts/cli.py"


def cli_source() -> str:
    return (REPO / CLI_PATH).read_text(encoding="utf-8")


def toolchain_history() -> list[dict]:
    """读取 cli.py 里的版本历史（old → new）。"""
    text = cli_source()
    m = HISTORY_RE.search(text)
    if not m:
        return []
    ns: dict = {}
    exec(m.group(0), ns)  # noqa: S102 - 读取仓库内自有常量，非外部输入
    return list(ns.get("TOOLCHAIN_HISTORY", []))


def write_history(history: list[dict]) -> None:
    """把版本历史写回 cli.py（保持 JSON 字面量，便于脚本与人工阅读）。"""
    text = cli_source()
    m = HISTORY_RE.search(text)
    if not m:
        raise RuntimeError("cli.py 中找不到 TOOLCHAIN_HISTORY 块")
    literal = "TOOLCHAIN_HISTORY = " + json.dumps(history, ensure_ascii=False, indent=4)
    (REPO / CLI_PATH).write_text(text[:m.start()] + literal + text[m.end():], encoding="utf-8")


def toolchain_version() -> str:
    """读取当前工具链版本（cli.py 是单一事实源）。"""
    m = VERSION_RE.search(cli_source())
    if not m:
        raise RuntimeError("skills/scripts/cli.py 中找不到 TOOLCHAIN_VERSION")
    return m.group(1)


def toolchain_files() -> list[Path]:
    """列出参与指纹的工具链源文件（排序后，排除 __pycache__）。"""
    files: list[Path] = []
    for member in TOOLCHAIN_MEMBERS:
        base = REPO / member
        if base.is_file():
            files.append(base)
        elif base.is_dir():
            files.extend(p for p in base.rglob("*") if p.is_file())
    files.extend(REPO.glob(TOOLCHAIN_GLOB_SKILLS))
    return sorted(
        {p for p in files if "__pycache__" not in p.parts},
        key=lambda p: p.relative_to(REPO).as_posix(),
    )


def _normalized_bytes(path: Path, rel: str) -> bytes:
    """读出参与指纹的字节并做归一化。

    - CRLF → LF：否则 Windows 检出与 Linux CI 会算出不同指纹，把"版本检查"
      变成"换行符检查"；
    - cli.py 里的 TOOLCHAIN_VERSION 字面量替换为占位符：版本号本身就在被指纹
      的文件里，不清掉就会"改版本 = 改内容"，无法区分"只递增版本"与
      "改了内容"。
    """
    data = path.read_bytes().replace(b"\r\n", b"\n")
    if rel == "skills/scripts/cli.py":
        data = re.sub(rb"(?m)^TOOLCHAIN_VERSION\s*=.*$",
                      b"TOOLCHAIN_VERSION = <version>", data)
    return data


def fingerprint() -> tuple[str, int]:
    """计算工具链指纹（内容层面，不受版本号字面量影响）。"""
    h = hashlib.sha256()
    files = toolchain_files()
    for path in files:
        rel = path.relative_to(REPO).as_posix()
        data = _normalized_bytes(path, rel)
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(data).digest())
    return h.hexdigest(), len(files)


def read_record() -> dict:
    if not FINGERPRINT_FILE.exists():
        return {}
    try:
        return json.loads(FINGERPRINT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def check() -> list[str]:
    """返回问题列表（空 = 通过）。"""
    record = read_record()
    current_fp, count = fingerprint()
    version = toolchain_version()
    problems: list[str] = []

    if not record:
        problems.append(
            f"缺少指纹文件 {FINGERPRINT_FILE.relative_to(REPO)}（首次使用请运行 "
            "python tests/check_toolchain_version.py --update）"
        )
        return problems

    if record.get("fingerprint") != current_fp:
        problems.append(
            "工具链内容已变更，但指纹未更新——请确认已递增 TOOLCHAIN_VERSION"
            f"（当前 {version}，记录 {record.get('toolchain_version')}），"
            "然后运行 python tests/check_toolchain_version.py --update"
        )
    return problems


def update(note: str | None = None) -> int:
    record = read_record()
    version = toolchain_version()

    # ① 先判定"内容变了但版本没变"（必须在写历史之前，否则判定被自己破坏）
    if record and record.get("fingerprint") != fingerprint()[0]:
        if record.get("toolchain_version") == version:
            print("!! 拒绝更新：工具链内容已变更，但 TOOLCHAIN_VERSION 未变"
                  f"（仍为 {version}）。")
            print("   请先在 skills/scripts/cli.py 递增 TOOLCHAIN_VERSION（格式 YYYY.MM.N），再重跑 --update。")
            return 1

    # ② 新版本：追加历史条目（要求一句变更说明）
    history = toolchain_history()
    if not history or history[-1].get("version") != version:
        if not note:
            print(f"!! 新增版本 {version} 需要变更说明："
                  'python tests/check_toolchain_version.py --update --note "<一句说明>"')
            print("   （说明会随 CLI 分发，用户同步时会看到「落后 N 版 + 改了什么」）")
            return 1
        history.append({
            "version": version,
            "date": datetime.date.today().isoformat(),
            "note": note,
        })
        write_history(history)
        print(f"已追加版本历史：{version} —— {note}")
    elif note:
        history[-1]["note"] = note
        write_history(history)
        print(f"已更新版本 {version} 的变更说明。")

    # ③ 写指纹（在历史更新之后再算，保证指纹覆盖本次全部改动）
    current_fp, count = fingerprint()
    if record and record.get("toolchain_version") != version:
        print(f"版本已变更（{record.get('toolchain_version')} → {version}），更新指纹。")

    FINGERPRINT_FILE.write_text(json.dumps({
        "toolchain_version": version,
        "fingerprint": current_fp,
        "files": count,
        "note": "由 tests/check_toolchain_version.py --update 生成；工具链内容或版本变更后需同步更新",
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OK 指纹已更新：{current_fp[:16]}…（{count} 个文件，版本 {version}）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="工具链版本递增检查")
    ap.add_argument("--update", action="store_true", help="更新指纹记录（需先递增版本）")
    ap.add_argument("--note", default=None, help="新版本的变更说明（新增版本时必填，会随 CLI 分发）")
    args = ap.parse_args(argv)

    if args.update:
        return update(args.note)

    problems = check()
    if problems:
        print("!! 工具链版本检查失败：\n")
        for p in problems:
            print("  -", p)
        return 1
    fp, count = fingerprint()
    print("OK 工具链版本检查通过"
          f"（版本 {toolchain_version()}，{count} 个文件，指纹 {fp[:16]}…）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

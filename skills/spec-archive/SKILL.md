---
name: spec-archive
description: 归档已关闭或已作废的议题（从 active 移至 archive）
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**CLI 定位（按优先级，执行前先确认）**：
1. 项目内已部署：`<项目根>/.doc-kit/cli/cli.py`
2. 项目内 skill 目录：`<项目根>/skills/scripts/cli.py`
3. 全局 skills 目录：`$REASONIX_HOME/skills/`（Windows 默认 `%APPDATA%\reasonix`，macOS/Linux `~/.reasonix`）下任意 `*/scripts/cli.py`（可用 `find` 在 workspace 与上述目录中搜索）

**首次自举**：若 1 不存在，先运行 `python <定位到的 cli.py> deploy`，将 CLI 部署到 `<项目根>/.doc-kit/cli/`。部署后一律从项目根调用：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py spec status
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
python .doc-kit/cli/cli.py spec archive
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败；纯文本输出（spec status）以「错误:」开头即失败。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根。
---

# spec-archive — 归档已关闭或已作废的议题

## 定位

将已关闭（closed）或已作废（abandoned）的议题从 `active/` 移至 `archive/`。

## 在哪选

当议题已 closed 或已 abandoned，用户说「归档」「清理」时。

## 选择判断

1. 调 `python .doc-kit/cli/cli.py spec status` 确认当前议题状态为 **closed** 或 **abandoned**。如仍为 active，应先调 `spec_close` 或 `spec_abort`。
2. 确认后调 `python .doc-kit/cli/cli.py spec archive` 完成归档。

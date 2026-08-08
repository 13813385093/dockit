---
name: spec-archive
description: 归档已关闭或已作废的议题（从 active 移至 archive）
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**例外（能力库）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接 read_file 读取**（仅读，禁止写入）。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「请先运行 doc-kit 初始化该项目」，终止流程，不尝试任何自举安装。

工具调用（从项目根执行）：

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

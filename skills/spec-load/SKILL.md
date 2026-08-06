---
name: spec-load
description: 加载之前的会议记录，继续讨论
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
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
python .doc-kit/cli/cli.py spec archive
python .doc-kit/cli/cli.py doc structure
python .doc-kit/cli/cli.py doc read <path>
python .doc-kit/cli/cli.py doc update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py doc add-section <reference> '<标题>' --content '<正文>' [--level sibling|child]
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败；纯文本输出（spec status / spec read / spec schema）以「错误:」开头即失败。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根。
---

# spec-load — 查看当前议题状态

## 定位

每次新对话的第一步。运行 `python .doc-kit/cli/cli.py spec status` 了解当前在哪，然后决定下一步走哪个岔路。

## 在哪选

这是每次对话的必选前导动作，非独立岔路。

## 选择判断

直接运行 `python .doc-kit/cli/cli.py spec status` 查看返回文案：

| 返回包含 | 含义 | 下一步 |
|----------|------|--------|
| 「无活跃议题」或「已初始化」 | 当前无进行中的会议 | 引导用户：可选 `spec_start` 开启新议题 |
| 「有活跃议题：**{id}**」 | 有议题进行中 | 调 `python .doc-kit/cli/cli.py spec read` 获取完整内容后展示给用户，由用户决定下一步：`spec_pause` / `spec_close` / `spec_abort` |
| 「有已关闭/已作废但未归档」 | 有已结束但未归档的议题 | 引导用户调 `python .doc-kit/cli/cli.py spec archive` 归档 |

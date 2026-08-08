---
name: spec-close
description: 关闭当前议题，包含决议完整性检查和文档写入确认
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**例外（能力库）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接 read_file 读取**（仅读，禁止写入）。写入 ProjectSpec 文档前，须先读 `_index.md` 定位 doc_type，再读对应能力文件 `<doc_type>.md` 获取段落结构与行文规则。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「请先运行 doc-kit 初始化该项目」，终止流程，不尝试任何自举安装。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
python .doc-kit/cli/cli.py spec archive
python .doc-kit/cli/cli.py doc structure
python .doc-kit/cli/cli.py doc read <path>
python .doc-kit/cli/cli.py doc update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py doc add-section <reference> '<标题>' --content '<正文>' [--level sibling|child]
python .doc-kit/cli/cli.py doc new <doc_type> [--module <模块名>] [--feature <功能名>]
python .doc-kit/cli/cli.py doc remove-section <reference>
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败；纯文本输出（spec read）以「错误:」开头即失败。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根。
---

# spec-close — 关闭当前议题

## 定位

结束整个议题。议题关闭后不可续接，需开启新议题。

## 在哪选

`active` 状态下，当用户说「这个议题讨论完了」「关闭」时。

## 选择判断

在调 `spec write` 之前，先检查和确认以下事项：

### 1. 读取当前议题

调 `python .doc-kit/cli/cli.py spec read` 获取完整的议题数据（含 resolutions、pending_decisions、next_steps）。

### 2. 提取本次对话的变更

从本次对话中提取所有未保存的决议、待定决议和后续计划，结构同 spec-pause Step 1：

- 已达成明确结论的 → 追加到 `resolutions[]`
- 悬而未决的新问题 → 追加到 `pending_decisions[]`
- 下一步计划 → 追加到 `next_steps[]`

> 以下 Step 3–5 的检查均基于「已有数据 + 本次新增」的合并结果。

### 3. 待定决议检查

检查合并后的 `pending_decisions[]`：

- 如果还有 **未 resolved 的待定决议**，提示用户：
  > 仍有 X 项待定决议未解决，建议继续讨论后再关闭。
  > 如需强行关闭，将这些未解决项的 status 改为 resolved 即可清除。

- 用户可选择继续讨论或强行关闭。

### 4. 决议 Detail 完整性检查

检查合并后的每条决议的 `detail` 是否 ≥150 字。不足时提示用户：

  > ⚠️ 以下决议的 detail 不足 150 字，写入文档时可能信息不足：
  >
  > 建议用 spec write 补充后再关闭。

> 注意：`detail` 的最小长度校验由 `spec write` 自动执行。

### 5. 文档写入检查

确认所有已决议的内容（已有 + 本次新增）已写入 ProjectSpec/ 对应文档：

1. 调 `python .doc-kit/cli/cli.py doc structure` 查看当前文档结构（结果可缓存复用）
2. 对每条未写入的决议，按 spec-pause Step 3 的流程（能力库定位 → doc structure → doc read → 判断 update/add 或 doc new）确定写入位置
3. 汇总待写入清单，向用户确认
4. 用户确认后，一次性调 `doc update-section` / `doc add-section` 写入

### 6. 组装关闭 spec 并写入

修改 spec：

- `status`: `"closed"`
- `closed_at`: `"当前时间 ISO 8601"`
- `closed_reason`: `"关闭原因"`
- 如有需要强行清除未解决的待定决议，将其 status 改为 `resolved`

调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'` 保存关闭状态。

### 7. 归档

调 `python .doc-kit/cli/cli.py spec archive` 将已关闭的议题从 active 移至 archive。

## 成功后

- MCP 标记为 closed，移至 archive
- 下次 `python .doc-kit/cli/cli.py spec status` 返回「没有活跃议题」
- 如需再次讨论，需开启新议题

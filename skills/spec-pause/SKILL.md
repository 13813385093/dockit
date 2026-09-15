---
name: spec-pause
description: 把本次讨论落盘为会议纪要（讨论期间的唯一落盘点），不写 ProjectSpec、不改状态
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**例外（能力库，仅读）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接 read_file 读取，禁止写入**。只有需要把决议写入 ProjectSpec 文档的技能（如 `spec-close`）才读它：先读 `_index.md` 定位 doc_type，再读对应 `<doc_type>.md` 获取段落结构与行文规则。

**git 操作**一律用 `bash` 执行（CLI 不执行 git）。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「请先运行 doc-kit 初始化该项目」，终止流程，不尝试任何自举安装。

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `2026.09.2` 生成。先运行 `python .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `2026.09.2`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py tool status
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec schema
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。错误信息统一为 `ERROR [<错误码>] <原因>。修复：<建议>`，读到后直接按建议行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一行中文状态描述，`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-pause — 保存本次讨论（唯一落盘点）

## 定位

讨论期间**不落盘**，讨论内容只存在于对话上下文中。

本技能是把讨论成果写回 `SessionSpec/active/<sid>.spec.json` 的**唯一通道**（另一个落盘点是 `spec-start` 创建议题时）。**只写会议文件，不写 `ProjectSpec/`**——项目文档统一由 `spec-close` 一次性写入。

## 在哪选

`active` 状态下，用户说「就到这里」「先保存」「下次继续」时。

AI 在对话明显变长、或用户出现收尾语气时，也应主动提醒用户执行本技能——因为**未保存的讨论会随上下文丢失**。

## 操作矩阵

| 分项 | 允许的操作 | 说明 |
|------|-----------|------|
| 决议 | 仅新增 | 决议不可修改或删除，修正需另开议题 |
| 议程（待定决议） | 新增 + 状态推进 | `needs_discussion` → `resolved` / `deferred` / `blocked`，不存在删除 |
| 后续计划 | 新增 + 删除 | 按文本精确匹配删除 |

> 以上操作在 skill 层通过 `spec read` → 内存修改 → `spec write --json '<spec_json>'` 实现。

## 选择判断

### Step 1：读取当前议题

调 `python .doc-kit/cli/cli.py spec read` 获取完整 spec。

### Step 2：提取本轮讨论的变更

从本次对话中提取：

- 哪些议题达成了明确结论 → `resolutions[]` 新增
- 哪些议程已推进/已有答案 → `pending_decisions[].status` 改为 `resolved`
- 哪些议程被搁置或受阻 → 改为 `deferred`（推迟，同时写入 `next_steps[]`）或 `blocked`（受阻，在 `note` 中写明阻塞原因）
- 哪些新问题悬而未决 → `pending_decisions[]` 新增（`status: "needs_discussion"`）
- 下一步要做什么 → `next_steps[]` 新增
- 哪些旧的后续计划已不需要 → `next_steps[]` 删除

> **诚实原则**：状态必须反映真实情况。没谈出结果就不要标 `resolved`——用 `deferred` / `blocked` 如实记录，`spec-close` 会据此提示。

### Step 3：完整化 Detail（必填，≥150 字）

`detail` 是**必填字段**，最少 **150 字**。它是后续 `spec-close` 写入项目文档时的主要信息来源——**这里写不清，文档就落不实**。

对每条决议，AI 应主动引导用户补充 detail。一个好 detail 包含以下要素：

| 要素 | 说明 | 适用于 |
|------|------|--------|
| 决策理由/Why | 为什么选这个方案？解决了什么问题？ | 所有决议 |
| 替代方案 | 不选什么？为什么不选？ | 技术/功能决策 |
| 约束条件 | 有什么 MUST/SHOULD 限制？ | 技术/约束类 |
| 影响范围 | 影响哪些模块或功能？ | 跨模块决策 |
| 具体配置/参数 | 如版本号、阈值、协议参数 | 技术选型类 |

AI 也可根据对话上下文中已有的信息主动整理 detail 让用户确认。

### Step 4：用户确认

展示变更清单给用户确认。格式示例：

```
📋 本次落盘清单，请确认：

✅ 新增决议（共 N 条）：
  ① 决议标题（简要）
     detail：…（N 字 ✅/❌）
❓ 议程推进：
  - 议题 ①[needs_discussion] → resolved
  - 议题 ③[needs_discussion] → deferred（转入后续计划）
  - 议题 ④ [blocked]：阻塞原因…
📌 后续计划：
  + 新增项
  - 删除项

本次落盘后：累计已决议 X 条（全部待 spec-close 写入 ProjectSpec）
```

以上是否正确？各条 detail 是否需要调整？

> 清单只涉及**会议纪要**。项目文档的写入清单在 `spec-close` 中单独梳理，届时一并审核。

### Step 5：组装完整 spec

调 `python .doc-kit/cli/cli.py spec read` 获取当前数据，据 Step 2 的结果修改内存中的 spec（全量替换模式）：

| 变更操作 | 做法 |
|---------|------|
| 新增决议 | `spec["resolutions"].append({"topic": ..., "decision": ..., "detail": ...})` |
| 推进议程状态 | 按 `topic` 匹配后改 `status` |
| 新增议程 | `spec["pending_decisions"].append({"topic": ..., "status": "needs_discussion", "note": ...})` |
| 新增后续计划 | `spec["next_steps"].append(...)` |
| 删除后续计划 | `spec["next_steps"].remove(...)` 或 list comprehension |

> 调 `python .doc-kit/cli/cli.py spec schema` 可获取字段的详细约束（如 `detail` 最小 150 字）。

### Step 6：调用工具

用户确认后调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'` 写回完整 spec（全量替换，保存到 `SessionSpec/active/`）。

### Step 7：落盘后复述

向用户报告并留痕认知差：

- 已保存 X 条决议，议程剩余 Y 项（未 resolved）；
- **本次未写入任何 ProjectSpec 文档**；累计待落盘决议 N 条，将在 `spec-close` 时统一梳理并写入；
- 下次继续：新开对话用 `spec-load` 复述议程；结束议题用 `spec-close`。

## 边界

- 不改变 `status`（保持 `active`）
- **不写 `ProjectSpec/`**：若用户要求"顺手把文档也改了"，说明文档写入集中在 `spec-close`（一次性梳理 + 审核 + 批量写入）；确需先记下来的，就作为一条议程或决议记录，等 close 时落盘
- `topic` 是议程匹配的 key，必须与 `spec-start` 建立的议程**精确一致**
- 每条决议的 `detail` 必须 ≥150 字符，否则 `spec write` 的 Schema 校验会拒绝保存
- `spec write` 前必须经过用户确认（Step 4）

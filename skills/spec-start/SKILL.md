---
name: spec-start
description: 开启新议题：先与用户确认本次讨论议程（待决议议题）并落盘，再生成 session_spec_id
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
python .doc-kit/cli/cli.py spec status
python .doc-kit/cli/cli.py spec schema
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。错误信息统一为 `ERROR [<错误码>] <原因>。修复：<建议>`，读到后直接按建议行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一行中文状态描述，`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-start — 开启新议题（议程落地）

## 定位

当用户提出一个需求或想法、当前没有活跃议题时，选择此岔路。

本技能是议题的**开关**：创建议题的同时，把**本次讨论要解决哪些议题（议程）**确认下来并写入 `pending_decisions`。后续 `spec-load` 复述它、`spec-pause` 推进它、`spec-close` 逐条结清它——议程是整条议题链路的锚点。

> 本技能是**讨论期间的落盘点之一**（另一个是 `spec-pause`）。除这两处，讨论期间不落盘。

## 在哪选

这是 `idle` 状态下的唯一岔路。如果没有活跃议题，这就是第一步。

## 选择判断

### Step 0：确认当前状态

调 `python .doc-kit/cli/cli.py spec status` 确认。若返回「当前有活跃议题」，引导用户先处理已有议题（`spec-load` 续接 / `spec-pause` 保存 / `spec-close` 关闭 / `spec-abort` 作废），**不要重复创建议题**。

### Step 1：获取数据模板

调 `python .doc-kit/cli/cli.py spec schema` 了解 SpecStruct 的字段定义（类型、允许值、约束），为组装初始数据做准备。

### Step 2：提取议题信息

从用户描述中提取：

- **topic**（2-6 个英文词概括）→ 用于生成 `session_spec_id`
- **scenario**：
  - 纯需求讨论、业务背景、目标用户 → `spec-scribe`
  - 技术选型、模块划分、架构设计 → `tech-ref`
  - 功能规格、测试用例、实现细节 → `feature-dev`

### Step 3：确认议程（本技能的关键动作，必做）

创建议题前，必须先把「本次讨论要确定哪些议题」确认下来：

1. 从用户描述中拆出**候选议题**，逐条给出：
   - `topic`：简洁、可辨识，**一经确认不再改名**——它是后续所有阶段（pause 推进 / close 结清）的匹配 key
   - `note`：这条议题要澄清什么、背景是什么、以什么为验收口径
2. 向用户展示议程草案，请其**增 / 删 / 改 / 合并 / 排序**。格式示例：

```
本次议题的议程草案（3 项），请确认或调整：

 ① 认证协议选型
    待澄清：OAuth2 与自签 JWT 的取舍，是否引入第三方 IdP
 ② token 有效期策略
    待澄清：30min 还是 60min，是否引入滑动续期
 ③ 与网关的鉴权边界
    待澄清：鉴权放网关还是服务内，错误码如何统一

确认 / 调整（增删改合并 / 调整顺序）？
```

3. 用户确认后即为本次议题的**议程**，写入 `pending_decisions`，每条 `status: "needs_discussion"`。

> **议程为空不要创建议题**：纯记录性、没有待决议项的对话不需要开会话，直接说明即可。
> 若用户首轮已给出明确结论，可同时写入 `resolutions`（`detail` ≥150 字，见 Step 5）。

### Step 4：生成 session_spec_id

按格式 `{当天日期}-{topic-kebab}` 生成，例如 `20260618-cert-auth`（与 CLI 的生成规则一致）。

向用户提议议题名称，等待确认。

### Step 5：组装初始 spec 并写入

按 `spec schema` 输出的结构组装完整 spec：
`session_spec_id` / `scenario` / `status: "active"` / `pending_decisions`（Step 3 的议程）/ `resolutions`（通常为空）/ `next_steps`（通常为空）。

调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'`。

> 注意：`project`、`created_at`、`related_doc_types` 由服务端自动填充，无需传入。
> 若 `spec write` 返回「SessionSpec/active/ 下存在残留文件」：**不要自行删除或搬移文件**，引导用户走 `spec-archive` 的残局处置流程或人工处理后再重试。

### Step 6：创建后的引导

向用户复述议程（逐条列出 `topic`），并说明本次议题的落盘规则：

- 讨论期间**不落盘**，讨论内容只存在于当前对话中；
- 需要保存时说「保存 / 先到这里」，执行 `spec-pause`（讨论期间的**唯一落盘点**）；
- `ProjectSpec/` 下的项目文档**不在讨论期间改写**，统一由 `spec-close` 一次性写入。

## 成功后的状态

进入 `active`。`spec write` 返回的摘要包含议程（待定决议）清单；决议与后续计划通常为空。

## 边界

- 不写 `ProjectSpec/`（文档写入是 `spec-close` 的职责）
- 一次只开一个议题（CLI 有串行约束，`active/` 有残留时 `spec write` 会拒绝）
- 议程 `topic` 一旦确认即冻结，改名会导致后续匹配失败

## 与其它技能的分工

| 技能 | 分工 |
|------|------|
| spec-start（本技能） | 开启议题 + 建立议程 |
| spec-load | 重开上下文，复述议程并续接讨论 |
| spec-pause | 把讨论落盘为会议纪要（唯一落盘点，不写 ProjectSpec） |
| spec-close | 结建议题：落盘 → 梳理并写入 ProjectSpec → 归档 |
| spec-abort | 作废议题并直接归档（不写任何文档） |

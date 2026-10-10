---
name: spec-start
description: 议题侧唯一入口：当用户新开对话要接着上次继续（「我们上次聊到哪了」），或提出新需求而当前没有活跃议题时使用。已有议题则读取并逐条复述待决议议程、重建上下文后续接；无议题则确认议程后创建。
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**例外（能力库，仅读）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接 read_file 读取，禁止写入**。只有需要把决议写入 ProjectSpec 文档的技能（如 `spec-close`）才读它：先读 `_index.md` 定位 doc_type，再读对应 `<doc_type>.md` 获取段落结构与行文规则。

**git 操作**一律用 `bash` 执行（CLI 不执行 git）。

**落盘点只有三处**：`spec-start` 创建议题并写入议程、`spec-pause` 保存讨论进展、`spec-close` 收尾时统一落盘。讨论**进行中**的保存通道只有 `spec-pause`；除这三处，讨论期间不落盘，`ProjectSpec/` 项目文档统一由 `spec-close` 写入。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「该项目尚未初始化：请人工执行 `doc-kit init <项目根>`，再执行 `doc-kit install-skills <agent 技能目录>`」并终止流程。**初始化由人工完成，不要尝试任何自举安装。**

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `2026.10.2` 生成。先运行 `python .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `2026.10.2`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py tool status
python .doc-kit/cli/cli.py spec status
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec schema
python .doc-kit/cli/cli.py spec write [--json '<完整 spec JSON>']   # 省 --json 则从 stdin 读入
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 四个字段；退出码 0 = 成功、1 = 业务拒绝或运行时错误、**2 = 参数错误**（未知选项 / 缺必填参数，按提示修正后重试）。
>
> 错误文本**没有统一格式**：较新的错误写作 `ERROR [<错误码>] <原因>。修复：<建议>`，但多数历史错误是散文形式（如「未找到文档: <path>，可用 doc structure 查看所有文档路径」）。**不要用正则解析错误文本**——错误原文同时出现在 `message` 与 `suggestions[0]`，按语义阅读后行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一至两行中文状态描述（**有活跃开发循环时会额外给出一行提示**），`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-start — 开启新议题（议程落地）

## 定位

当用户提出一个需求或想法、**或想接着上次的讨论继续**时，选择此岔路。

本技能是议题侧的**唯一入口**，内部分两条路：

- **续接分支**（已有活跃议题）：读取议题、逐条复述议程、重建上下文，然后接着谈——**只读**，不落盘。
- **创建分支**（无活跃议题）：与用户确认议程并写入 `pending_decisions`，生成 `session_spec_id`——这是讨论期间的落盘点之一。

议程是整条议题链路的锚点：`spec-pause` 推进它、`spec-close` 逐条结清它。

> 落盘点只有前言说的三处；本技能只在**创建分支**落盘一次，续接分支全程只读。

## 在哪选

这是议题侧的唯一入口，也是新对话的第一步：**不管有没有活跃议题都从这里进**——有议题就续接，没有就创建。

## 选择判断

### Step 0：确认当前状态

调 `python .doc-kit/cli/cli.py spec read`，**按输出形态与 `status` 字段判定，不做中文字符串匹配**：

| `spec read` 的输出 | 判定 | 下一步 |
|---------|------|--------|
| 可解析为 JSON（含 `session_spec_id`），`status` 为 `active` | 已有活跃议题 | **走续接分支（Step 0b）**：复述议程、重建上下文后续接；不要重复创建议题 |
| 可解析为 JSON 但 `status` 为 `closed` / `abandoned` | 终态未归档 | 提示用户先走 `spec-archive` 归档，再回到本技能创建新议题 |
| 以「错误:」开头 | 数据或 CLI 异常 | 原文报告错误，终止流程 |
| 其它（如「当前没有活跃议题…」） | 无活跃议题 | 进入创建分支（Step 1） |

> 用 `spec read` 而不是 `spec status`：前者输出结构化 JSON，可以判字段；后者只是一行中文散文，CLI 改文案就会让这里的路由失效。

### Step 0b：续接分支（已有活跃议题时，全程只读）

用户想接着上次的讨论继续时，**不要创建议题**，改为重建上下文：

1. 从 `spec read` 的 JSON 取 `pending_decisions` / `resolutions` / `next_steps`，**先列议程、再列已决议与后续计划**：

```
📌 议题 20260618-cert-auth ｜场景：技术评审 ｜状态：active

待决议议程（3 项）：
 ① 认证协议选型 —— needs_discussion
    待澄清：OAuth2 与自签 JWT 的取舍，是否引入第三方 IdP
 ② token 有效期策略 —— needs_discussion
 ③ 与网关的鉴权边界 —— deferred（上次搁置）

已决议（2 项）：
 - 认证失败统一返回 401 —— 由网关拦截并记录审计日志
 - 用户表沿用现有 user_id 主键 —— 不引入外部身份主键

后续计划（1 项）：
 1. 下次议事先定 token 有效期

请选择要推进的议题（也可以直接抛出新话题，我会把它加入议程）。
```

2. 规则：
   - **议程 = `pending_decisions` 中 `status != "resolved"` 的全部条目**，逐条列出 `topic` + `status` + `note`，**一条都不能省略**——这是重开上下文时唯一的信息重建块。
   - 已决议只列 `topic：decision` 摘要，不必展开 `detail`。
   - 议程已清空（全部 resolved）时，提示用户可执行 `spec-close` 做结清与文档写入。
3. 续接后说明落盘规则：讨论期间**不落盘**；需要保存时说一句，执行 `spec-pause`；结束议题走 `spec-close`。

> 本分支**只读**：不调用任何写命令、不改状态；也不做 DevSpec 的状态检查（`spec status` 会在有活跃开发循环时额外给出提示，照实转述即可）。

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
- 需要保存时说「保存 / 先到这里」，执行 `spec-pause`（讨论进行中的**唯一保存通道**）；
- `ProjectSpec/` 下的项目文档**不在讨论期间改写**，统一由 `spec-close` 一次性写入。

## 成功后的状态

进入 `active`。`spec write` 返回的摘要包含议程（待定决议）清单；决议与后续计划通常为空。

## 边界

- **续接分支全程只读**；只有创建分支落盘一次（写入议程）
- 不写 `ProjectSpec/`（文档写入是 `spec-close` 的职责）
- 一次只开一个议题（CLI 有串行约束，`active/` 有残留时 `spec write` 会拒绝）
- 议程 `topic` 一旦确认即冻结，改名会导致后续匹配失败

## 与其它技能的分工

| 技能 | 分工 |
|------|------|
| spec-start（本技能） | 议题侧唯一入口：续接已有议题（复述议程、重建上下文）或创建议题并建立议程 |
| spec-pause | 把讨论落盘为会议纪要（讨论进行中的唯一保存通道，不写 ProjectSpec） |
| spec-close | 结束议题：正常关闭（落盘 → 梳理并写入 ProjectSpec → 归档）；或作废分支（放弃成果，直接归档） |
| spec-archive | 归档兜底（正常流程由 `spec-close` 内联完成） |

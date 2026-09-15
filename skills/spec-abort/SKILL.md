---
name: spec-abort
description: 作废当前议题并直接归档，不写任何 ProjectSpec 文档
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
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
python .doc-kit/cli/cli.py spec archive
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。错误信息统一为 `ERROR [<错误码>] <原因>。修复：<建议>`，读到后直接按建议行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一行中文状态描述，`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-abort — 作废当前议题

## 定位

非正常终止议题：前置条件不足、方向变更、不再有价值时使用。

**作废是"直接归档、零文档副作用"**：不写 `ProjectSpec/`，不产出会议纪要之外的任何内容，也不做文档归属梳理——那些都是 `spec-close` 的动作。

## 在哪选

`active` 状态下，当用户说「这个议题算了」「不讨论了」「作废」「转向别的事」时。

## 选择判断

### Step 1：确认意图与原因

先确认意图，并**必须取得作废原因**（`closed_reason` 是必填字段，CLI 会校验）。用户尚未提供原因时先询问，不编造。

```
请确认：议题 {session_spec_id} 将作废（原因：{用户提供的原因}）。
作废后议题直接归档，不可撤销、不可续接，请确认。
```

> **先分流**：如果用户其实是想**留住讨论成果**（只是不想再谈了），引导改用 `spec-close`——`spec-close` 会把决议写入 `ProjectSpec/` 后归档；作废会让本次讨论的结论永久停留在 SessionSpec 里。

### Step 2：读取当前议题

调 `python .doc-kit/cli/cli.py spec read` 获取完整议题数据。

### Step 3：修改为作废状态

在 spec 上设置：

- `status` → `"abandoned"`
- `closed_at` → 当前时间 ISO 8601
- `closed_reason` → 用户提供的原因

> 其余字段（`resolutions` / `pending_decisions` / `next_steps`）原样保留，作为"讨论未走完"的如实记录，不做清空或改写。

### Step 4：写入并归档

1. 调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'` 保存作废状态（CLI 校验：`abandoned` 必须有 `closed_reason`）
2. 调 `python .doc-kit/cli/cli.py spec archive` 归档

## 成功后

- 议题被标记为 `abandoned`，移至 `SessionSpec/archive/`
<!-- preamble-tools-exclude: spec status -->
- 下次 `spec status` 返回「没有活跃议题」
- **`ProjectSpec/` 未被改动**：作废不产生任何文档副作用

## 边界

- 不改写、不清空已记录的决议与议程（保留讨论痕迹）
- 不写 `ProjectSpec/`（需要落盘文档的议题应走 `spec-close`）
- 终态不可回退：`abandoned` 之后不能再改回 `active`
- 归档步骤若失败（如 `active/` 有残留），用 `spec-archive` 兜底处理

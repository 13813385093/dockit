---
name: spec-archive
description: 归档兜底：处理已终态未归档或 active/ 残局，正常流程不直接调用
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
python .doc-kit/cli/cli.py spec archive
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。错误信息统一为 `ERROR [<错误码>] <原因>。修复：<建议>`，读到后直接按建议行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一行中文状态描述，`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-archive — 归档兜底

## 定位

归档的**兜底通道**。

正常路径下，归档由 `spec-close`（Step 5）和 `spec-abort`（Step 4）在流程末尾**内联完成**；因此本技能**通常不由用户或议程直接调用**，只在流程中断、`SessionSpec/active/` 出现残局时使用。

将已关闭（`closed`）或已作废（`abandoned`）的议题从 `SessionSpec/active/` 移至 `SessionSpec/archive/`。

## 在哪选

用户说「归档」「清理一下」时；或上一次 `spec-close` / `spec-abort` 在归档前中断时。

## 选择判断

### Step 1：残局体检

调 `python .doc-kit/cli/cli.py spec status` 看当前处于哪种情形，按下表处置：

| 状态输出 | 情形 | 处置 |
|---------|------|------|
| 「有已关闭/已作废但未归档的议题」 | 终态收尾中断（唯一需要本技能的常规情形） | 直接执行 Step 2 归档 |
| 「当前有活跃议题」 | 议题还没走完 | **不代为改状态**，引导用户走 `spec-close`（保留成果）或 `spec-abort`（放弃成果） |
| 「没有活跃议题」 | 已归档或无议题 | 无需操作，直接说明 |
| 以「错误:」开头（如「存在多个活跃 SessionSpec」「存在残留文件」） | 违反串行约束 / 目录有残留 | 原文报告错误并**终止**：交人工确认后处理，本技能不删除、不搬移任何文件 |

> `spec archive` 本身也有同样的护栏：状态不是 `closed` / `abandoned`、`active/` 为空、或存在多个活跃会话时，CLI 会拒绝并给出修复建议——读到后按建议行动，不要绕过。

### Step 2：归档

调 `python .doc-kit/cli/cli.py spec archive` 完成归档。

## 成功后

- 议题文件从 `SessionSpec/active/` 移至 `SessionSpec/archive/`
- 串行约束释放：可执行 `spec-start` 开启新议题
- 归档不可逆；如需再议同一主题，必须开启新议题

## 边界

- **只做搬迁**：不改 `status`、不改 `closed_reason`、不写 `ProjectSpec/`
- **不清理未知文件**：`active/` 中的残留或异常文件一律交人工判断（删除属破坏性操作，超出本技能权限）
- 正常流程不调用本技能：归档已内联在 `spec-close` / `spec-abort` 中

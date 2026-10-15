---
name: spec-archive
description: 归档兜底，正常流程不直接调用（归档已内联在 spec-close 的关闭路径与作废分支末尾）：当用户说「归档」「清理一下」，或上次关闭/作废在归档前中断、active/ 留下残局时使用。只做搬迁，不改状态、不删文件、不写文档。
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接读写这些文件）。

**例外（能力库，仅读）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接读取，禁止写入**。只有需要把决议写入 ProjectSpec 文档的技能（如 `spec-close`）才读它：先读 `_index.md` 定位 doc_type，再读对应 `<doc_type>.md` 获取段落结构与行文规则。

**git 操作**一律用 `bash` 执行（CLI 不执行 git）。

**落盘点只有三处**：`spec-start` 创建议题并写入议程、`spec-pause` 保存讨论进展、`spec-close` 收尾时统一落盘。讨论**进行中**的保存通道只有 `spec-pause`；除这三处，讨论期间不落盘，`ProjectSpec/` 项目文档统一由 `spec-close` 写入。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「该项目尚未初始化：请人工执行 `doc-kit init <项目根>`，再执行 `doc-kit install-skills <agent 技能目录>`」并终止流程。**初始化由人工完成，不要尝试任何自举安装。**

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `2026.10.4` 生成。先运行 `python .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `2026.10.4`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py tool status
python .doc-kit/cli/cli.py spec status
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec write [--json '<完整 spec JSON>']   # 省 --json 则从 stdin 读入
python .doc-kit/cli/cli.py spec archive
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 四个字段；退出码 0 = 成功、1 = 业务拒绝或运行时错误、**2 = 参数错误**（未知选项 / 缺必填参数，按提示修正后重试）。
>
> 错误文本**没有统一格式**：较新的错误写作 `ERROR [<错误码>] <原因>。修复：<建议>`，但多数历史错误是散文形式（如「未找到文档: <path>，可用 doc structure 查看所有文档路径」）。**不要用正则解析错误文本**——错误原文同时出现在 `message` 与 `suggestions[0]`，按语义阅读后行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一至两行中文状态描述（**有活跃开发循环时会额外给出一行提示**），`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-archive — 归档兜底

## 定位

归档的**兜底通道**。

正常路径下，归档由 `spec-close` 在流程末尾**内联完成**（关闭路径的 Step 5、作废分支的最后一步）；因此本技能**通常不由用户或议程直接调用**，只在流程中断、`SessionSpec/active/` 出现残局时使用。

将已关闭（`closed`）或已作废（`abandoned`）的议题从 `SessionSpec/active/` 移至 `SessionSpec/archive/`。

## 在哪选

用户说「归档」「清理一下」时；或上一次 `spec-close` 在归档前中断时。

## 选择判断

### Step 1：残局体检

调 `python .doc-kit/cli/cli.py spec read`，**按输出形态与 `status` 字段判定，不做中文字符串匹配**：

| `spec read` 的输出 | 判定 | 处置 |
|---------|------|------|
| JSON 且 `status` 为 `closed` / `abandoned` | 终态收尾中断（唯一需要本技能的常规情形） | 直接执行 Step 2 归档 |
| JSON 且 `status` 为 `active` | 议题还没走完 | **不代为改状态**，引导用户走 `spec-close`：它的关闭路径保留成果，作废分支放弃成果 |
| 以「错误:」开头（如「存在多个活跃 SessionSpec」） | 违反串行约束 | 原文报告错误并**终止**：交人工确认后处理，本技能不删除、不搬移任何文件 |
| 其它（如「当前没有活跃议题」） | 无活跃议题 | 无需操作，直接说明。**注意**：`active/` 里存在非 `*.spec.json` 的杂物时也落到这一行——`spec read` 只认 `*.spec.json`，对它**不会报错**（「存在残留文件」是 `spec write` 的报错，不出现在此处）；此类残局交人工处理 |

> 用 `spec read` 而不是 `spec status`：前者输出结构化 JSON（含 `status` 字段），后者只是一行中文散文，CLI 改文案就会让这里的路由失效。

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
- 正常流程不调用本技能：归档已内联在 `spec-close` 中（关闭路径与作废分支）

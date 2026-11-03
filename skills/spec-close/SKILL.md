---
name: spec-close
description: 当用户说「讨论完了」「关闭」「收尾」（保留成果）或「这个议题算了」「作废」（放弃成果）时使用：前者落盘纪要 → 梳理决议的文档归宿 → 交审核后写入 ProjectSpec → 归档；后者只记原因直接归档，不写任何文档。
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接读写这些文件）。

**例外（能力库，仅读）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接读取，禁止写入**。只有需要把决议写入 ProjectSpec 文档的技能（如 `spec-close`）才读它：先读 `_index.md` 定位 doc_type，再读对应 `<doc_type>.md` 获取段落结构与行文规则。

**git 操作**一律用 `bash` 执行（CLI 不执行 git）。

**落盘点只有三处**：`spec-start` 创建议题并写入议程、`spec-pause` 保存讨论进展、`spec-close` 收尾时统一落盘。讨论**进行中**的保存通道只有 `spec-pause`；除这三处，讨论期间不落盘，`ProjectSpec/` 项目文档统一由 `spec-close` 写入。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「该项目尚未初始化：请人工执行 `doc-kit init <项目根>`，再执行 `doc-kit install-skills <agent 技能目录>`」并终止流程。**初始化由人工完成，不要尝试任何自举安装。**

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `2026.11.2` 生成。先运行 `python .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `2026.11.2`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py tool status
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec write [--json '<完整 spec JSON>']   # 省 --json 则从 stdin 读入
python .doc-kit/cli/cli.py spec archive
python .doc-kit/cli/cli.py spec coverage [--verify] [--id <sid>]
python .doc-kit/cli/cli.py doc structure
python .doc-kit/cli/cli.py doc read <path>
python .doc-kit/cli/cli.py doc update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py doc add-section <reference> '<标题>' [--content '<正文>'] [--level sibling|child]
python .doc-kit/cli/cli.py doc new <doc_type> [--module <模块名>] [--feature <功能名>] [--author <负责人>]
python .doc-kit/cli/cli.py doc reindex
python .doc-kit/cli/cli.py doc lint [--baseline <file>] [--summary]
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 四个字段；退出码 0 = 成功、1 = 业务拒绝或运行时错误、**2 = 参数错误**（未知选项 / 缺必填参数，按提示修正后重试）。
>
> 错误文本**没有统一格式**：较新的错误写作 `ERROR [<错误码>] <原因>。修复：<建议>`，但多数历史错误是散文形式（如「未找到文档: <path>，可用 doc structure 查看所有文档路径」）。**不要用正则解析错误文本**——错误原文同时出现在 `message` 与 `suggestions[0]`，按语义阅读后行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一至两行中文状态描述（**有活跃开发循环时会额外给出一行提示**），`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-close — 结建议题

## 定位

结束整个议题。六步走：

```
① 落盘本轮讨论（会议纪要） → ② 议程结清检查 → ③ 梳理 ProjectSpec 变更清单（用户审核）
   → ④ 批量写入 ProjectSpec → ⑤ 文档一致性复核（doc lint 门禁） → ⑥ 标终态并归档
```

本技能是议题链路中**唯一写 `ProjectSpec/` 的技能**：整个讨论期间攒下的决议，在这里一次性梳理、审核、落盘。议题关闭后不可续接，需开启新议题。

## 在哪选

`active` 状态下，用户说「这个议题讨论完了」「关闭」「收尾」时（走**关闭路径**）；或用户说「这个议题算了」「不讨论了」「作废」「转向别的事」时（走**作废分支**）；或议程已全部 resolved 时。

## 作废分支（放弃成果，不写任何文档）

当用户明确要**放弃**本次讨论成果时走本分支，**不要执行下面的 Step 1–6**。

1. **先分流**：若用户其实是想**留住讨论成果**（只是不想再谈了），改走关闭路径——关闭会把决议写入 `ProjectSpec/` 后归档；作废会让本次讨论的结论永久停留在 SessionSpec 里。

2. **必须取得作废原因**：`closed_reason` 是必填字段（CLI 会校验）。用户未提供时先询问，**不编造**。确认话术：

```
请确认：议题 {session_spec_id} 将作废（原因：{用户提供的原因}）。
作废后议题直接归档，不可撤销、不可续接，请确认。
```

3. 调 `python .doc-kit/cli/cli.py spec read` 取当前 spec，设置 `status: "abandoned"`、`closed_at`（ISO 8601）、`closed_reason`（用户提供的原因）。**其余字段原样保留**——`resolutions` / `pending_decisions` / `next_steps` 是"讨论未走完"的如实记录，**不清空、不改写**。

4. 调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'` 保存，再调 `python .doc-kit/cli/cli.py spec archive` 归档（归档失败时用 `spec-archive` 兜底）。

**作废的四条纪律**（缺一条都可能造成不可逆损失）：

- **先分流**：别把"想留住成果"当成"想作废"——两者归档后的差别是决议有没有进 `ProjectSpec/`。
- **原因必填、不编造**：`abandoned` 必须有 `closed_reason`，CLI 会拒绝。
- **不改写、不清空已记录的决议与议程**：保留讨论痕迹。
- **终态不可回退**：`abandoned` 之后不能再改回 `active`；如需再议同一主题，必须开启新议题。

> 本分支**不写 `ProjectSpec/`**、不做文档归属梳理——那些都是关闭路径的动作。

## 选择判断

> 以下为**关闭路径**（保留成果）。要走作废分支请回上一节。

### Step 1：确认本轮讨论已落盘

本步**只写会议纪要**（`SessionSpec/active/`），不写 `ProjectSpec/`。

- 若本轮对话尚未落盘（上次 `spec-pause` 之后又谈出了新结论）→ **加载并执行 `spec-pause`**。落盘流程、字段要求与用户确认清单**以该技能为准**，本技能不重述——同一流程两处来源必然漂移。
- 若本轮无可落盘内容（上次已 `spec-pause` 保存过）→ 直接进入 Step 2。

> 落盘完成后回到本技能继续 Step 2。`spec-pause` 是讨论进行中的唯一保存通道（见前言「落盘点只有三处」）。

### Step 2：议程结清检查

检查 `pending_decisions[]` 中所有未 `resolved` 的条目，**逐条与用户确认处置**：

| 处置 | 用法 | 后续 |
|------|------|------|
| `resolved` | 本次已谈出结论 | 若结论成立，同时补入 `resolutions[]`（`detail` ≥150 字） |
| `deferred` | 推迟到下次 | 写入 `next_steps[]`，说明下次要谈什么 |
| `blocked` | 受阻无法推进 | 在 `note` 中写明阻塞原因与解除条件 |

- **禁止为了关闭而谎报 `resolved`**：没谈出结果就如实标 `deferred` / `blocked`（CLI 在关闭时会对此给出提示）。
- 用户坚持继续讨论时，回到讨论（本技能中止，待用户再次触发）。
- 处置结果同样通过 `spec write` 落盘。

### Step 3：梳理 ProjectSpec 变更清单（用户审核）

对**全部决议**（已有 + 本次新增）确定文档归宿。**先定层级，再定位置**：层级由能力库决定；该层没有能承载它的文档就新建，不要把细节硬塞进上一层的既有段落。

1. 调 `python .doc-kit/cli/cli.py doc structure` 查看当前 `ProjectSpec/` 的文档与段落结构（结果可缓存在内存复用）
2. 逐条决议路由：读取 `<项目根>/.doc-kit/skills/guidance/doc-capabilities/_index.md`，按 §2（议题场景）/ §3（决议主题）定位 doc_type，按 §4 判断「新增 vs 更新」
3. 加载能力：读取 `<项目根>/.doc-kit/skills/guidance/doc-capabilities/<doc_type>.md`，按其「段落结构 / 行文规则」确定目标章节与写法（含约束编号规则）
4. 调 `python .doc-kit/cli/cli.py doc read <path>` 查看目标文档现状，确认是更新已有段落还是新增段落；**该层没有能承载它的文档时就 `doc new` 新建**
5. 汇总为**变更清单表**（一行 = 一条决议的一处归宿；一条决议要写多处就占多行）：

| # | 决议 topic | 层级 | 目标文档 | 章节 | 动作 | 写入摘要 |
|---|-----------|------|---------|------|------|---------|
| 1 | 认证协议选型 | 项目 | `technical-framework.md` | `主要框架与中间件` | `doc_update_section` | … |
| 2 | 退款功能设计 | 功能 | `module-pay/features/pay-refund/feature-design.md` | ——（新建） | `doc_new` | … |
| 3 | 内部讨论口径 | —— | —— | —— | `doc_skip` | 仅会议纪要，理由：… |

6. 展示清单给用户审核，允许**改目标文档/章节、拆条、删条、标记"不落文档"**。
7. **审核通过后立刻落表**：把每行的文档 / 章节 / 动作写进对应决议的 `targets[]`（`doc` 为带 `.md` 的 `ProjectSpec/` 相对路径；`section` 形如 `架构设计#组件划分`；`doc_skip` 必写 `reason`），`spec write` 保存，`status` 仍为 `active`。**必须在 Step 4 之前**：写完再补 targets 只能证明"写过的都记了"，证明不了"该写的都写了"。

**三条硬性纪律**：

- **每条决议必须有归宿**：或写入某文档，或显式标「不落文档」并写明理由——不允许静默漏写。
- **找不到承载位置时也要占一行**：写「层级 = X、目标文档 = ——、动作 = `doc_skip`」，摘要里说明理由与建议；
- **审核通过前不得写入任何一条**（不允许边梳理边写）。

> 约束标记（`[MUST]` / `[SHOULD]` / `[MAY]`）应忠实保留到目标文档中，不可降级或升格。

### Step 4：批量写入 ProjectSpec

用户审核通过后，按清单顺序执行：

1. **先 `doc new`**：目标文档不存在的条目先建（`doc new architecture --module <模块名>` 会自动创建模块目录；`doc new feature_design --module <模块名> --feature <功能名>` 会自动创建功能目录）
2. 再逐条 `doc update-section` / `doc add-section` 写入正文
3. 逐条记录结果（成功 / 失败 + 错误码 `ERROR [<错误码>] …。修复：<建议>`），**失败项记录后继续执行其余条目**（条目之间相互独立）
4. 末尾汇总：「成功 N 条 / 失败 M 条；失败清单与建议」，失败项交用户决定重试或人工处理
5. 写入结束后调 `python .doc-kit/cli/cli.py doc reindex` **全量重建 `.doc-kit/index.json`**：纯 AI 流程没有桌面 App 自动维护索引，若不重建，后续 `doc structure` / `doc read` 读到的目录与依赖结构会与磁盘脱节（新建文档缺失、`depends_on` 为空）。本步幂等，只要 Step 4 有写入就执行一次
6. 最后调 `python .doc-kit/cli/cli.py spec coverage --verify`，对照 Step 3 冻结的 `targets` 核对磁盘：

   - `success=true`（状态全为 `ok` / `skipped`）→ 进入 Step 5。
   - `success=false`（存在 `missing` / `empty` / `ambiguous`）→ **阻断关闭**：把 `data.rows` 里非 ok 的项**原样**展示给用户，请其补齐文档或修正清单（改清单则回 Step 3 重走冻结与核对）。

### Step 5：文档一致性复核（`doc lint` 门禁）

Step 4 写入完成（含末尾 `doc reindex`）后、归档前，运行规格门禁复核本次写入结果：

```bash
python .doc-kit/cli/cli.py doc lint --summary
```

- `success=true` → 通过，进入 Step 6。
- `success=false`（存在**未被 baseline 吸收**的 error）→ **阻断关闭**：把 `message` 与 `data.errors`（≤20 条）摘要展示给用户，请其修正后重跑本步；**不要**继续 Step 6。
- **仅 `warning` 不阻断**。若项目已配置 `.doc-kit/lint.yaml` / baseline，存量违规已被吸收，`success` 只反映**本次写入新增**的问题。

> 用 `--summary` 而非完整输出：未配 baseline 的项目可能有数百条 findings，完整 JSON 会灌进上下文；`--summary` 只给 `metrics` 与 error 摘要。

### Step 6：标终态并归档

1. 调 `python .doc-kit/cli/cli.py spec read` 取当前 spec，设置 `status: "closed"`、`closed_at`（ISO 8601）、`closed_reason`（**必填**，用户未提供时先询问，不编造）。**不要手写 `coverage`**——CLI 按磁盘重算并覆写，传值被丢弃（快照用于审计「已落盘」声明，不能由声明方自填）
2. 调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'` 保存关闭状态。此步校验每条决议的 `targets`：缺失即报 `ERROR [spec.targets_missing]` 并**指名**是哪条、拒绝关闭；通过则写入覆盖快照
3. 调 `python .doc-kit/cli/cli.py spec archive` 归档（`SessionSpec/active/` → `SessionSpec/archive/`）

## 成功后

<!-- preamble-tools-exclude: spec status -->
- 议题状态为 `closed` 并移至 `SessionSpec/archive/`；下次 `spec status` 返回「没有活跃议题」
- 项目文档已按清单更新，`.doc-kit/index.json` 已重建；如需再次讨论，必须开启新议题（`spec-start`）
- 若上次关闭后归档未完成，用 `spec-archive` 兜底补归档

## 边界

- **只有本技能在议题链路内写 `ProjectSpec/`**（`spec-code-review` 的后续动作经用户确认后也可写文档，见该技能 Phase 4）；`spec-start` / `spec-pause` 都不写。**本技能的作废分支也不写**——它只改状态并归档
- 写入必须经用户审核通过（Step 3 → Step 4 的顺序不可颠倒）
- 归档不可逆：`closed` / `abandoned` 是终态，不能回退为 `active`
<!-- preamble-tools-exclude: doc remove-section -->
- 删除段落（`doc remove-section`）不在本技能职责内——如需清理废弃段落，属人工或后续议题范畴
- 决议只增不改：已写入的决议要修正，另开议题

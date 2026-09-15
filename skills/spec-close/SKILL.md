---
name: spec-close
description: 结建议题：先落盘会议纪要，再梳理 ProjectSpec 变更清单交审核并批量写入，最后归档
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**例外（能力库）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接 read_file 读取**（仅读，禁止写入）。写入 ProjectSpec 文档前，须先读 `_index.md` 定位 doc_type，再读对应能力文件 `<doc_type>.md` 获取段落结构与行文规则。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「请先运行 doc-kit 初始化该项目」，终止流程，不尝试任何自举安装。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec schema
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
python .doc-kit/cli/cli.py doc structure
python .doc-kit/cli/cli.py doc read <path>
python .doc-kit/cli/cli.py doc new <doc_type> [--module <模块名>] [--feature <功能名>] [--author <负责人>]
python .doc-kit/cli/cli.py doc update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py doc add-section <reference> '<标题>' --content '<正文>' [--level sibling|child]
python .doc-kit/cli/cli.py spec archive
```

> 输出约定：`spec status` / `spec read` / `spec schema` 直接输出文本——`spec status` 是一行中文状态描述，`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。其余命令输出 JSON 信封，含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `dev`）之前。
---

# spec-close — 结建议题

## 定位

结束整个议题。五步走：

```
① 落盘本轮讨论（会议纪要） → ② 议程结清检查 → ③ 梳理 ProjectSpec 变更清单（用户审核）
   → ④ 批量写入 ProjectSpec → ⑤ 标终态并归档
```

本技能是议题链路中**唯一写 `ProjectSpec/` 的技能**：整个讨论期间攒下的决议，在这里一次性梳理、审核、落盘。议题关闭后不可续接，需开启新议题。

## 在哪选

`active` 状态下，用户说「这个议题讨论完了」「关闭」「收尾」时；或 `spec-load` 发现议程已全部 resolved 时。

## 选择判断

### Step 1：落盘本轮讨论（先确保上下文都进了会议纪要）

本轮对话中的内容如果还没保存，先按本节落盘（等价于 `spec-pause` 的核心流程）：

1. 调 `python .doc-kit/cli/cli.py spec read` 取当前 spec
2. 从本次对话提取变更：新决议（`detail` ≥150 字）/ 议程状态推进 / 新增议程 / 后续计划增删
3. 组装完整 spec（全量替换）→ `python .doc-kit/cli/cli.py spec write --json '<spec_json>'`

> 本步**只写会议纪要**（`SessionSpec/active/`），不写 `ProjectSpec/`。
> 若本轮无可落盘内容（上次已 `spec-pause` 保存过），直接进入 Step 2。

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

对**全部决议**（已有 + 本次新增）确定文档归宿：

1. 调 `python .doc-kit/cli/cli.py doc structure` 查看当前 `ProjectSpec/` 的文档与段落结构（结果可缓存在内存复用）
2. 逐条决议路由：`read_file <项目根>/.doc-kit/skills/guidance/doc-capabilities/_index.md`，按 §2（议题场景）/ §3（决议主题）定位 doc_type，按 §4 判断「新增 vs 更新」
3. 加载能力：`read_file <项目根>/.doc-kit/skills/guidance/doc-capabilities/<doc_type>.md`，按其「段落结构 / 行文规则」确定目标章节与写法（含约束编号规则）
4. 调 `python .doc-kit/cli/cli.py doc read <path>` 查看目标文档现状，确认是更新已有段落还是新增段落；文档不存在则计划 `doc new <doc_type> --module <模块名> --feature <功能名> [--author <负责人>]`
5. 汇总为**变更清单表**：

| # | 决议 topic | 目标文档 | 章节 | 动作 | 写入摘要 |
|---|-----------|---------|------|------|---------|
| 1 | 认证协议选型 | `technical-framework.md` | §主要框架与中间件 | `doc update-section` | … |
| 2 | 退款功能设计 | `module-pay/features/pay-refund/feature-design.md` | ——（新建） | `doc new` | … |
| 3 | 内部讨论口径 | —— | —— | 不落文档 | 仅会议纪要，理由：… |

6. 展示清单给用户审核，允许**改目标文档/章节、拆条、删条、标记"不落文档"**。

**两条硬性纪律**：

- **每条决议必须有归宿**：或写入某文档，或显式标「不落文档」并写明理由——不允许静默漏写。
- **审核通过前不得写入任何一条**（不允许边梳理边写）。

> 约束标记（`[MUST]` / `[SHOULD]` / `[MAY]`）应忠实保留到目标文档中，不可降级或升格。

### Step 4：批量写入 ProjectSpec

用户审核通过后，按清单顺序执行：

1. **先 `doc new`**：目标文档不存在的条目先建（`doc new architecture --module <模块名>` 会自动创建模块目录；`doc new feature_design --module <模块名> --feature <功能名>` 会自动创建功能目录）
2. 再逐条 `doc update-section` / `doc add-section` 写入正文
3. 逐条记录结果（成功 / 失败 + 错误码 `ERROR [<错误码>] …。修复：<建议>`），**失败项记录后继续执行其余条目**（条目之间相互独立）
4. 末尾汇总：「成功 N 条 / 失败 M 条；失败清单与建议」，失败项交用户决定重试或人工处理

### Step 5：标终态并归档

1. 组装关闭 spec：`status: "closed"`、`closed_at`（ISO 8601）、`closed_reason`（**必填**，用户未提供时先询问，不编造）
2. 调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'` 保存关闭状态
3. 调 `python .doc-kit/cli/cli.py spec archive` 归档（`SessionSpec/active/` → `SessionSpec/archive/`）

## 成功后

- 议题状态为 `closed` 并移至 `SessionSpec/archive/`；下次 `spec status` 返回「没有活跃议题」
- 项目文档已按清单更新；如需再次讨论，必须开启新议题（`spec-start`）
- 若上次关闭后归档未完成，用 `spec-archive` 兜底补归档

## 边界

- **只有本技能写 `ProjectSpec/`**；`spec-start` / `spec-load` / `spec-pause` / `spec-abort` 都不写
- 写入必须经用户审核通过（Step 3 → Step 4 的顺序不可颠倒）
- 归档不可逆：`closed` / `abandoned` 是终态，不能回退为 `active`
- 删除段落（`doc remove-section`）不在本技能职责内——如需清理废弃段落，属人工或后续议题范畴
- 决议只增不改：已写入的决议要修正，另开议题

---
name: spec-dev-loop
description: 根据 ProjectSpec 设计执行 开发->自测->缺陷修复->回归->报告提交 的开发循环
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**例外（能力库）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接 read_file 读取**（仅读，禁止写入）。

**核心纪律：ProjectSpec 全程只读（不可协商）**

- 整个 spec-dev-loop 过程中，**禁止任何对 ProjectSpec/ 的写操作**：不调用 `doc update-section` / `doc add-section` / `doc new` / `doc remove-section`，不直接编辑 ProjectSpec 文件
- `doc structure` / `doc read` **仅允许读取**用途——用于理解设计、整合约束、对齐检查
- 开发中发现的**设计问题只记录到 CodeNotes 与报告**（`dev notes append` / `dev report-write`），**不修改 ProjectSpec**
- 设计修改的决策留给循环外的评审/会议流程（那里有版本递增与人工确认机制），循环内只记录、不执行

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「请先运行 doc-kit 初始化该项目」，终止流程，不尝试任何自举安装。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
# —— DevSpec（开发循环工作区）——
python .doc-kit/cli/cli.py dev status
python .doc-kit/cli/cli.py dev plan create --scope <module|feature> --target <范围> [--module <模块>] [--title <标题>] [--session <id>]
python .doc-kit/cli/cli.py dev plan read
python .doc-kit/cli/cli.py dev plan update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py dev plan add-section <reference> '<标题>' [--content '<正文>'] [--level sibling|child]
python .doc-kit/cli/cli.py dev task list
python .doc-kit/cli/cli.py dev task set --json '<tasks 数组>'
python .doc-kit/cli/cli.py dev task update <task_id> --status <状态> [--note '<备注>']
python .doc-kit/cli/cli.py dev task annotate <task_id> --note '<备注>'
python .doc-kit/cli/cli.py dev align --feature <功能名> --module <模块名> --status <aligned|done> [--note '<备注>']
python .doc-kit/cli/cli.py dev integrate --module <模块名> --status <integrated|documented|done> [--note '<备注>']
python .doc-kit/cli/cli.py dev notes append --content '<md>' [--section <章节名>]
python .doc-kit/cli/cli.py dev report-write --kind <feature|module> --name <目标> --content '<md>'
python .doc-kit/cli/cli.py dev close --reason '<原因>'
python .doc-kit/cli/cli.py dev abort --reason '<原因>'
python .doc-kit/cli/cli.py dev archive
# —— ProjectSpec（只读）——
python .doc-kit/cli/cli.py doc structure
python .doc-kit/cli/cli.py doc read <path>
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。错误信息统一为 `ERROR [<错误码>] <原因>。修复：<建议>`，读到后直接按建议行动。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根。
---

# spec-dev-loop — 开发执行循环

## 定位

根据 ProjectSpec 的设计完成 **开发 → 自测 → 缺陷修复 → 回归 → 报告提交 → 循环**。范围由用户指定 ProjectSpec/ 下的某一个**模块**或**子功能**。粒度分层：

| 层级 | 粒度 | 完成标志 |
|------|------|---------|
| 任务 | 一个函数/方法（可合并内聚助手函数）+ 单元测试 | 单元测试真实运行通过 |
| 功能 | N 个任务 + 验收测试 + 约束覆盖 | 功能对齐（aligned） |
| 模块 | N 个功能 + 契约集成 + CodeNotes | 模块集成（documented）→ 循环结束 |

ProjectSpec 中的 `feature-design.md`（§函数调用关系 / §边界约束）、`unit-tests.md`（GWT + 覆盖约束）、`module-manifest.md`（imports/exports）、`inter-module-contracts.md`（字段级契约）就是本循环的**任务来源与验收依据**——开发是把这些规格翻译成代码派生制品的过程。

## 核心纪律

1. **ProjectSpec 只读**（见「最高优先级」）：设计问题只记录，不修改；修改由循环外评审/会议完成
2. **DevSpec 操作一律经 CLI**：plan.md / tasks.json / code-notes.md 的读写都走 dev 命令组
3. **CodeNotes 追加式**：只追加不改写，保持过程真实（纪律同 decision_log）
4. **自测必须真实运行**：GWT 是语言无关描述，必须翻译成真实测试代码（`implemented_in` 声明的语言与路径）并实际跑通——禁止写 trivial 测试糊弄自测（假绿）
5. **一次只有一个活跃开发循环**（串行约束）：新的循环必须等当前循环 close/abort + archive 后开启

## 流程总览

```
Phase 0 — 入口：dev status（断点检测）
Phase 1 — 规划（人机交互）：dev plan create → 读取范围文档 → 约束整合 → 任务提案 → 用户确认边界 → dev task set
Phase 2 — 任务循环（LOOP）：拓扑序执行任务（in-progress → implemented → unit-green / fixing → done）
Phase 3 — 功能对齐：验收测试（自动化为主）→ G4 约束覆盖 → 回归 → dev align → 功能报告
Phase 4 — 模块集成：G3 契约闭合 + 契约字段校验 → dev integrate → CodeNotes 整理 → 模块开发报告 → documented → done
Phase 5 — 收尾：dev close → dev archive
```

## Phase 0：入口

调 `python .doc-kit/cli/cli.py dev status`：

| 返回包含 | 含义 | 下一步 |
|----------|------|--------|
| 「当前没有活跃开发循环」 | 无进行中的循环 | 引导用户指定范围，进入 Phase 1 |
| 「当前有活跃开发循环」 | 有循环进行中 | 读取进度，从断点继续（任务 LOOP / 功能对齐 / 模块集成） |
| 报错「多个活跃开发循环」 | 违反串行约束 | 提示用户处理 DevSpec/active/ 后重试 |

## Phase 1：规划（人机交互）

规划是**交互过程**：AI 提出任务边界方案，用户确认/调整后固化。

### Step 1：确认范围

用户指定范围（如 `/spec-dev-loop order`、`/spec-dev-loop order-timeout-cancel`）：
- `module` 范围：`--scope module --target <模块名>`（子模块用点分，如 `order.core`）
- `feature` 范围：`--scope feature --target <功能名> --module <所属模块>`

### Step 2：创建会话

调 `python .doc-kit/cli/cli.py dev plan create --scope ... --target ... [--module ...] [--title ...]`，生成 `DevSpec/active/{日期}-{范围kebab}/` 会话骨架（dev-spec.json / plan.md / tasks.json / code-notes.md / evidence/ / reports/）。

### Step 3：读取范围文档（只读）

按渐进式披露加载最小上下文集：
1. `doc structure` 查看全部文档与依赖
2. `doc read` 读取范围内文档：功能 → `feature-design.md` + `unit-tests.md` + `acceptance-tests.md` + `decision-log.md`；模块 → `architecture.md` + `domain-model.md` + `module-manifest.md` + `integration.md`
3. 沿 `depends_on` / imports 读取相关的顶层文档（`global-policies.md` / `inter-module-contracts.md` / `non-functional-constraints.md` 等）

### Step 4：整合约束到计划表

调 `dev plan update-section '<plan.md>#2. 约束整合' --content ...`，把散落在各文档的相关约束**整合到计划表**，每条注明来源引用（体系引用格式，如 `feature-design@order-timeout-cancel:C-101`）：

- 功能约束（§边界约束，C-xxx/S-xxx 原样保留编号）
- 全局策略（认证、错误码、日志等）
- 接口契约（inter-module-contracts 字段级定义）
- 领域约束（domain-model）
- 验收标准摘要（acceptance-tests 场景清单）

> 目标：执行任务时，AI 只需读 plan.md 的任务卡 + `implemented_in` 源码，无需回翻 ProjectSpec。计划表是开发循环的**唯一工作上下文**。

### Step 5：任务提案与确认

AI 基于 §函数调用关系 推导任务清单（含拓扑序：**先被调用者、后调用者**——天然最优自测顺序），按以下原则切分：
- 粒度**要细**，但不必严格 1 函数 = 1 任务：入口函数 + 内聚助手函数可合并为一个任务
- 单函数过大可拆分为多个任务
- **入口函数对应测试必须存在于 unit-tests.md**；「覆盖约束」行（C-101 等）即该任务的硬性验收约束

向用户展示提案（格式示例）：

```
📋 开发计划提案：order-timeout-cancel（order 模块）

任务清单（按依赖拓扑序，共 2 个）：
  T1  扫描并取消超时订单（入口）
      函数: cancelExpiredOrders(入口), findExpiredOrders, cancelOrder, releaseStock
      覆盖约束: C-101, C-102
      GWT: unit-tests.md#测试用例：超时订单被扫描
  T2  释放库存
      函数: releaseStock
      覆盖约束: C-102

确认 / 调整（合并/拆分/跳过/顺序）？
```

用户确认后，调 `python .doc-kit/cli/cli.py dev task set --json '<tasks 数组>'` 全量写入（plan.md §3 任务清单自动渲染）。任务卡 schema：

```json
{
  "task_id": "T1",
  "title": "扫描并取消超时订单（入口）",
  "module": "order",
  "feature": "order-timeout-cancel",
  "functions": ["cancelExpiredOrders", "findExpiredOrders", "cancelOrder", "releaseStock"],
  "entry_function": "cancelExpiredOrders",
  "signature": "(ctx context.Context) error",
  "gwt_refs": ["unit-tests.md#测试用例：超时订单被扫描"],
  "constraint_ids": ["C-101", "C-102"],
  "status": "pending",
  "deviation": "",
  "notes": ""
}
```

## Phase 2：任务循环（LOOP）

对拓扑序中的每个 pending 任务执行：

### Step 1：开始任务

`dev task update <id> --status in-progress`（可在 evidence/ 留测试计划）

### Step 2：实现

在 `implemented_in` 声明的源码路径实现函数，**签名与 §函数调用关系 一致**；遵守计划表 §2 整合的全部约束。

### Step 3：自测（真实运行）

1. 将任务引用的 GWT 用例翻译为真实测试代码（语言无关描述 → `xxx_test.go` / `xxxTest.java` 等），测试函数按场景命名
2. 实际运行测试，**必须真实执行通过**（非「写了测试」）
3. 测试输出留档到 `DevSpec/active/<sid>/evidence/`，`dev task update <id> --status unit-green --note '<结果摘要 + 证据路径>'`

### Step 4：缺陷修复（三分类）

右翼测试失败时，向左翼追溯（指南 §3.3.3 原则），**按档位处理**：

| 档位 | 情形 | 处理 |
|------|------|------|
| 轻 | 实现细节、措辞、测试层级错位（如 unit-tests 设计了 1 小时流量冲击测试，不应在单元层执行） | 采用当下合理方式，`dev task update <id> --status fixing --note '<偏差>'` → 修复 → `dev task annotate` 记录 → `dev notes append` 记录到 CodeNotes，**不碰 ProjectSpec** |
| 中 | 约束自相矛盾、文档前后不一致 | 选择当下更合理者实现，CodeNotes 详记（发现/判断/依据/影响范围/建议的 Spec 修改），**不碰 ProjectSpec** |
| 重 | 跨模块契约（inter-module-contracts / module-manifest）变更、[MUST] 冲突无法裁决 | **停止任务**，升级用户决策；如需改设计，由用户在循环外走会议/人工流程，改完后再恢复循环 |

> 开发过程是**反思设计的过程**：设计文档出现问题时，开发可以选择合理方式实现并记录，评审后可快速追溯到需要调整的位置（报告 → CodeNotes 反链 → 原文档段落）。唯一底线：**不直接修改 ProjectSpec**。

### Step 5：完成任务

`dev task update <id> --status done`。任务 DoD：
- 函数签名与 §函数调用关系 一致，位于 `implemented_in` 路径内
- 覆盖约束对应的 GWT 场景全部真实通过
- 代码提交（可调 spec-smart-git 智能提交）

## Phase 3：功能对齐

当某功能全部任务 done 后：

### Step 1：验收测试执行

以**自动化为主**：将 `acceptance-tests.md` 的 Gherkin 场景翻译为集成/E2E 测试代码并执行；提前设计有集成测试环境的，集成测试是自动测试的一部分。无法自动化的场景以「人工验证 + 证据」（截图/日志/记录）兜底。

### Step 2：约束覆盖检查（G4）

核对每个编号的 [MUST] 约束（C-xxx）在 unit-tests.md 中有对应场景引用。

### Step 3：回归

回归范围 = 本功能全部测试 + **依赖它的下游**（用 `doc structure` 的 depends_on 反查 / `module-manifest` imports 反查）——文档依赖图即回归影响面。

### Step 4：记录对齐

`dev align --feature <功能名> --module <模块名> --status aligned [--note ...]`（CLI 校验：该功能全部任务必须 done）。

### Step 5：功能对齐报告

`dev report-write --kind feature --name <功能名> --content '<报告>'`。报告模板：

```markdown
# 功能对齐报告：<功能名>

> 会话: <session_id> · 日期: <YYYY-MM-DD>

## 完成情况
| 任务 | 函数 | 状态 | 测试结果 | 证据 |
|------|------|------|---------|------|

## 验收对齐
- 验收场景：X/Y 通过（自动化）/ Z 人工验证
- G4 约束覆盖：C-101 ✓ C-102 ✓ …
- 回归：<范围 + 结果>

## 设计偏差
- （引用 CodeNotes §设计文档遗漏与偏差 条目，只记录不修改）
```

## Phase 4：模块集成

当某模块全部功能 aligned/done 后：

### Step 1：契约闭合校验（G3）

核对 `module-manifest.md` 的 import↔export 配对（消费方每个 import 能在提供方 exports 找到）、`inter-module-contracts.md` 字段级契约与实现一致（请求/响应结构、错误码、超时/重试）。

### Step 2：记录集成

`dev integrate --module <模块名> --status integrated [--note ...]`（CLI 校验：该模块全部功能已对齐）。

### Step 3：整理 CodeNotes（知识资产沉淀）

将循环中 `dev notes append` 的记录**整理收拢**（仍追加式），确保覆盖四类：
- 开发问题与解决（问题 → 根因 → 解决 → 影响范围）
- 设计文档遗漏与偏差（发现 → 判断 → 依据 → 影响范围 → **建议的 Spec 修改**，含精确引用）
- 重点关注区域（供验收/评审人员优先查看）
- 流程与方案改进建议

### Step 4：模块开发报告

`dev integrate --module <模块名> --status documented` 表示 CodeNotes 已整理、报告已产出；`dev report-write --kind module --name <模块名> --content '<报告>'`。报告模板：

```markdown
# 模块开发报告：<模块名>

> 会话: <session_id> · 日期: <YYYY-MM-DD>

## 完成情况
| 功能 | 任务数 | 对齐状态 | 验收结果 |
|------|-------|---------|---------|

## 集成校验
- G3 契约闭合：import↔export 配对 X/Y
- inter-module-contracts 字段校验：通过/问题

## 回归结果
- <范围 + 结果>

## 设计偏差汇总（供评审追溯）
| # | 偏差 | 判断 | CodeNotes 条目 | 建议的 Spec 修改 |
|---|------|------|---------------|-----------------|

## 流程与方案改进建议
- ...
```

### Step 5：完成

`dev integrate --module <模块名> --status done`。

## Phase 5：收尾

1. `dev close --reason '<原因>'`（正常完成）或 `dev abort --reason '<原因>'`（非正常终止）
2. `dev archive` 将整个会话目录移入 `DevSpec/archive/`，释放串行约束
3. 下次开发 = 新会话：`dev plan create` 重新生成，互不干扰

## 断点续跑

开发很少一次跑完：每次进入先 `dev status` 查看进度，从 pending 任务 / 待对齐功能 / 待集成模块处继续。循环中所有状态均持久化在 `DevSpec/active/<sid>/`（dev-spec.json + tasks.json + plan.md + code-notes.md）。

## 与其它技能的分工

| 技能 | 分工 |
|------|------|
| spec-dev-loop（本技能） | 开发执行闭环，ProjectSpec 只读 |
| spec-smart-git | 代码提交（任务 done / 功能对齐时调用） |
| spec-code-review | 循环外代码评审（比对设计文档，允许改文档） |
| SessionSpec 会议 | 纯会议用途，与开发循环互不耦合；设计修改决策走会议/人工流程 |

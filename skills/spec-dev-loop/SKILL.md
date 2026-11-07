---
name: spec-dev-loop
description: 当 ProjectSpec 里的设计已就绪、要把某个 feature 忠实实现成代码时使用：读设计 → 骨架化（用户确认签名）→ 委托子代理实现并由主代理验收 → 单元与验收测试 → 对齐收尾，全程 ProjectSpec 只读。横切工作（构建、CI、依赖升级）不走本技能。
---

# 最高优先级：

**三层边界（先看清各自走哪条路，是全篇纪律的基础）**：

| 对象 | 读写方式 |
|------|---------|
| `ProjectSpec/`（设计文档） | **只读，经 CLI**（`doc structure` / `doc read`）。禁止任何写操作——设计问题只记录到 CodeNotes 与报告 |
| `DevSpec/`（plan.md / tasks.json / code-notes.md / reports） | **经 CLI**（`dev *` 命令组） |
| **源码与测试代码** | **直接读写**（文件工具 / `bash`）。骨架 stub、方法实现、单元测试代码都属于这一类，CLI 不介入 |

**git 操作**一律用 `bash` 执行（CLI 只**只读** `.git/HEAD` 做分支前置断言，**绝不执行 git 写操作、也不调用 git 子进程**）：`git branch` / `git checkout` / `git rev-parse` / `git diff`。仅**主代理**执行 git，子代理禁止。

**CLI 容灾 Fallback（紧急直读）**：若 `dev task list` / `dev status` 因 CLI 异常（非 JSON 输出、超时或 Python 报错）**连续失败 2 次**，可降级为**直接只读** `DevSpec/active/<sid>/tasks.json` 与 `dev-spec.json` 解析断点（仅限当前活跃会话目录，且必须遵守"禁止写"原则）。此降级必须在 `dev notes append` 中记录"CLI Fallback 触发"。**写操作仍必须走 CLI**，CLI 写失败则停止并提示用户检查 doc-kit 安装。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`。若该文件不存在，输出「该项目尚未初始化：请人工执行 `doc-kit init <项目根>`，再执行 `doc-kit install-skills <agent 技能目录>`」并终止流程。**初始化由人工完成，不要尝试任何自举安装。**

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `2026.11.3` 生成。先运行 `python3 .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `2026.11.3`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

> 若 `python3` 不在 PATH（部分 Windows 环境只有 `python` 或 `py -3`），把命令中的 `python3` 替换为可用解释器；`command not found` 不代表工具链损坏。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python3 .doc-kit/cli/cli.py tool status
python3 .doc-kit/cli/cli.py doc structure
python3 .doc-kit/cli/cli.py doc read <path>
python3 .doc-kit/cli/cli.py dev status
python3 .doc-kit/cli/cli.py dev plan create --scope feature --target <功能名> --module <模块名> [--title <标题>]
python3 .doc-kit/cli/cli.py dev plan read
python3 .doc-kit/cli/cli.py dev plan update-section <reference> --content '<正文>'
python3 .doc-kit/cli/cli.py dev task list
python3 .doc-kit/cli/cli.py dev task set --json '<tasks 数组>'
python3 .doc-kit/cli/cli.py dev task patch <task_id> --json '<字段子集>'
python3 .doc-kit/cli/cli.py dev task update <task_id> --status <状态> [--note '<备注>']
python3 .doc-kit/cli/cli.py dev task annotate <task_id> --note '<备注>'
python3 .doc-kit/cli/cli.py dev branch set <branch>
python3 .doc-kit/cli/cli.py dev align --feature <功能名> --module <模块名> --status <aligned|done> [--note '<备注>'] [--allow-branch-mismatch --reason '<原因>']
python3 .doc-kit/cli/cli.py dev integrate --module <模块名> --status <integrated|documented|done> [--note '<备注>'] [--allow-branch-mismatch --reason '<原因>']
python3 .doc-kit/cli/cli.py dev notes append --content '<md>' [--section <章节名>]
python3 .doc-kit/cli/cli.py dev report-write --kind <feature|module> --name <目标> --content '<md>'
python3 .doc-kit/cli/cli.py dev close --reason '<原因>'
python3 .doc-kit/cli/cli.py dev abort --reason '<原因>'
python3 .doc-kit/cli/cli.py dev archive
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 四个字段；退出码 0 = 成功、1 = 业务拒绝或运行时错误、**2 = 参数错误**（未知选项 / 缺必填参数，按提示修正后重试）。
>
> 错误文本**没有统一格式**：较新的错误写作 `ERROR [<错误码>] <原因>。修复：<建议>`，但多数历史错误是散文形式（如「未找到文档: <path>，可用 doc structure 查看所有文档路径」）。**不要用正则解析错误文本**——错误原文同时出现在 `message` 与 `suggestions[0]`，按语义阅读后行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一至两行中文状态描述（**有活跃开发循环时会额外给出一行提示**），`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-dev-loop — 依托文档的功能级开发循环

## 定位

把 ProjectSpec 的设计**忠实翻译**成代码派生制品。设计决策已经在文档里做完了，本循环的职责是**翻译 + 验证**，不是重新设计。

```
Phase 0  入口：dev status（断点检测 + 分支检查）
Phase 1  读设计：feature 文档 + 模块上下文 + 代码考古 + 约束整合
Phase 2  骨架化：类/方法与调用关系 → 用户确认 → 源码 stub → dev task set → 建分支
Phase 3  逐方法实现：派发子代理 → submitted → 主代理验收 → accepted
Phase 4  测试：GWT 单元测试 → tested → 提交 done → 验收测试 + G4 + 回归
Phase 5  收尾：dev align → CodeNotes → 功能报告 → dev close → dev archive
```

| 层级 | 粒度 | 完成标志 |
|------|------|---------|
| 任务 | 一条**单文件内聚调用链**（入口 + 伴生方法，默认粒度），含实现落点 | 主代理验收通过（`accepted`）+ GWT 通过（`tested`）|
| 功能 | N 个任务 + 验收测试 + 约束覆盖 + 回归 | 功能对齐（`aligned`）|

**范围规则**：一次开发**只做一个 feature**。选择 feature 而不是 module，主要不是为省上下文（省上下文靠骨架化与委托实现），而是为了**完成判据明确**：`dev align` 有唯一的对齐对象，验收范围可界定，回归影响面可反查。模块级契约/集成见「附录 C」；无 feature 归属的横切工作见「附录 D」。

## 核心纪律

1. **ProjectSpec 全程只读**（不可协商）：设计问题只记录到 CodeNotes 与报告；修改留给循环外的评审/会议
2. **DevSpec 操作一律经 CLI**；**源码与测试代码直接读写**（见「最高优先级」三层边界）
3. **骨架先行**：没有 `implemented_in`（实现落点）的任务不许开工——`dev task set` 会直接拒绝缺失落点的任务
4. **委托实现必须验收**：`submitted → accepted` 只能由主代理置位，且验收必须**亲自运行命令**复核，**不得采信子代理的自述**
5. **测试必须真实运行**：GWT 是语言无关描述，必须翻译成真实测试代码并跑通——禁止写 trivial 测试糊弄（假绿）；每个任务**先观测失败（Red）再观测通过（Green）**，测试结果只能由主代理判定（见 Phase 3 Step 1.5 / Phase 4 Step 1）
6. **一次只有一个活跃开发循环**：新循环必须等当前循环 close/abort + archive 后开启

## git 分支策略（开发分支隔离，人工合并）

- 分支命名 `dev-loop/<sid>`，与开发循环**严格一一对应**（串行约束 → 一次一个活跃分支）
- **创建时机**：Phase 2 `dev task set` 成功后、Phase 3 第一个任务开始前
- 分支名由 `dev plan create` 记录在 `dev-spec.json` 与 `plan.md §6`；**实际分支名与记录不一致时，创建后立即 `dev branch set <实际分支>`**（同时同步 `plan.md §6`），不要再靠人工改 plan.md
- 循环内所有提交都在开发分支上；**合并回主分支是人工在循环外完成的动作**，循环内不合并、不推送
- **断点续跑检查**：Phase 0 读 `dev status` 的 `data.branch` 与 `data.branch_matches`（不要解析中文正文），不匹配则先 `git checkout <分支名>` 或 `dev branch set <实际分支>`
- 每个 feature 一个分支 → **分支数量会随功能数增长**，合并节奏由人工把控
- 项目不是 git 仓库时跳过全部 git 操作（提交完全由人工决定）

> **CLI 的分支断言是只读的**：CLI 只读 `.git/HEAD` 判断当前分支，**绝不执行 git 子进程**（更不执行 git 写操作）。**读命令始终允许**（`dev status` / `dev task list` / `dev plan read`）——不能因为分支错误而无法诊断。

### 分支断言矩阵（写操作才阻断）

| 命令/操作 | 分支不匹配时 |
|---|---|
| `dev status` / `dev task list` / `dev plan read` | **允许**；`dev status` 的 `data.branch_matches` 为 `true`/`false`/`null`，正文同时显示当前分支与期望分支 |
| `dev task update --status implementing/submitted/accepted/tested/done` | **阻断**（返回 `dev_branch.mismatch`，退出码 1） |
| `dev task update --status rejected/blocked` | **允许**（记录失败、设计缺口，不能把人锁死） |
| `dev task patch` | **阻断**（属于状态/基线写操作；分支创建前改用 `dev task set`） |
| `dev task annotate` / `dev notes append` / `dev report-write` | **允许**（记录证据，不改任务状态） |
| `dev branch set <branch>` | **允许**（这是修复不匹配的通道本身） |
| `dev abort` / `dev close` / `dev archive` | **允许**（用于恢复/收尾） |
| `dev align` / `dev integrate` | 默认阻断；用 `--allow-branch-mismatch --reason '<原因>'` 显式放行（分支已合并/删除后的收尾） |
| `dev plan create` / `dev task set` | **跳过**（分支尚未创建，属于 Phase 2 前段） |
| 非 git 项目 / `branch` 为空 / 无 `.git` | **跳过**，`branch_matches = null`，`dev status` 提示未记录分支 |
| detached HEAD / 读不到 HEAD | **阻断写操作**，提示 `git checkout <期望分支>` 或 `dev branch set <实际分支>` |

## Phase 0：入口

调 `python3 .doc-kit/cli/cli.py dev status`，**读 `data.branch` 与 `data.branch_matches`**：

| 返回 | 含义 | 下一步 |
|------|------|--------|
| 「当前没有活跃开发循环」 | 无进行中的循环 | 引导用户指定 feature 范围，进入 Phase 1 |
| `phase: design` | 尚无任务清单 | 从 Phase 1 开始（读设计 → 骨架化） |
| `phase: implement` | 有任务待实现/待验收 | 先 `python3 .doc-kit/cli/cli.py dev task list` 看任务状态，再按 `suggestions` 从断点继续（pending → 派发；submitted → 验收；rejected → 重派；blocked → 找用户裁决） |
| `phase: test` | 任务已验收，待测试 | 进入 Phase 4 |
| `phase: close` | 任务全完成 | 进入 Phase 5 |
| 报错「多个活跃开发循环」 | 违反串行约束 | 提示用户处理 `DevSpec/active/` 后重试 |

**分支硬闸（只对续跑生效）**：

- 已有活跃循环且 `data.branch_matches == false` → **停止推进后续任务**，先 `git checkout <期望分支>`，或确认实际分支正确后 `dev branch set '<实际分支>'`；
- **首次开发、分支尚未创建（Phase 2 Step 5 之前）→ 不检查**；
- `branch_matches == null`（非 git / 未记录分支）→ 跳过断言；
- 读命令（`dev status` / `dev task list` / `dev plan read`）始终可用，先诊断再修复。

## Phase 1：读设计（只读 ProjectSpec）

### Step 1：确认范围

用户指定 feature（如 `/spec-dev-loop order-timeout-cancel`）：

```bash
python3 .doc-kit/cli/cli.py dev plan create --scope feature --target <功能名> --module <所属模块>
```

生成 `DevSpec/active/{日期}-{功能名}/`（dev-spec.json / plan.md / tasks.json / code-notes.md / evidence/ / reports/）。

> 先做**右尺寸判断**：若该功能 §函数调用关系 的方法数 ≤ 3 且落点在同一文件，按「附录 E」合并 Phase 2/3（豁免逐方法派发与逐项验收，但仍保留"接口确认"与"主代理验收"两个闸门）。

### Step 2：读取范围文档

按渐进式披露加载最小上下文集：

1. `python3 .doc-kit/cli/cli.py doc structure` 查看全部文档与依赖；再用 `python3 .doc-kit/cli/cli.py doc read <path>` 读取下面列出的具体文档
2. **功能文档**：`feature-design.md`（§功能描述 / §触发条件 / §适用前提 / §处理流程 / §异常路径 / §边界约束 / **§函数调用关系**）、`unit-tests.md`（GWT + 覆盖约束）、`acceptance-tests.md`（Gherkin）、`decision-log.md`
3. **所属模块上下文（必需，不是可选阅读）**：
   - `architecture.md` **§组件划分** → **"方法落在哪个类/组件"的设计来源**，骨架阶段没有它无法决定类归属
   - `domain-model.md` → 领域实体与不变条件
   - `module-manifest.md` / `inter-module-contracts.md` → 本功能涉及的能力声明与字段级契约
4. 顶层文档（按需）：`global-policies.md` / `non-functional-constraints.md`

> 说明：`feature-design.md` 的 frontmatter `implemented_in: [{path, lang}]` 声明本功能的实现位置与语言——它是骨架阶段填写每个方法落点的依据。

### Step 3：代码考古（风格快照）

在目标模块的现有代码中提取隐性风格规范（命名约定、错误处理模式、现有工具类/中间件、日志格式），避免生成代码与存量代码割裂：

```bash
find <模块源码路径> -type f \( -name "*.go" -o -name "*.java" -o -name "*.py" -o -name "*.ts" \) | head -5 | xargs cat
```

（按项目主语言调整扩展名；模块路径为空时从项目根同语言入口文件取样。）

把提取到的模式写入计划表：

```bash
python3 .doc-kit/cli/cli.py dev plan update-section 'plan.md#2.5 代码风格快照' --content '<风格摘要>'
```

### Step 3.5：验证命令采集（静态诊断前置）

与风格快照一起，采集项目**已有**的验证命令，写入 `plan.md §2.6 验证命令`（Phase 3/4 与附录 B 直接取用）：

```text
验证命令：
- build: <项目构建命令>
- lint: <项目 lint 命令，或“未配置”>
- typecheck: <项目类型检查命令，或“未配置”>
- test: <定向测试命令>
- 增量/基线参数: <如 --new-from-rev=<base>；没有则写“按变更文件过滤”>
```

```bash
python3 .doc-kit/cli/cli.py dev plan update-section 'plan.md#2.6 验证命令' --content '<上述清单>'
```

- 只允许使用项目**已有工具**（Makefile / package.json scripts / pyproject / go.mod 等里声明的命令）；
- **禁止自动安装** linter / 类型检查器，也不得为此新增依赖；
- 没配置的项写“未配置”，后续按“skipped: not configured”处理，**不得因此阻断流程**；
- 旧会话的骨架里没有 §2.6 时，把同一清单追加到 `plan.md §2.5 代码风格快照` 末尾即可（不要手工编辑 plan.md）。

### Step 4：约束整合

```bash
python3 .doc-kit/cli/cli.py dev plan update-section 'plan.md#2. 约束整合' --content '<整合后的约束清单>'
```

整合范围：功能约束（§边界约束，C-xxx/S-xxx 原样保留编号）、全局策略（认证/错误码/日志）、接口契约（inter-module-contracts 字段级定义）、领域约束（domain-model）、验收标准摘要、代码风格快照。

> 目标：Phase 3 派发时，简报只需取 plan.md 的约束 + 任务卡，无需回翻 ProjectSpec。计划表是开发循环的**唯一工作上下文**。

## Phase 2：骨架化（本技能的核心步骤）

> 骨架化同时是**对设计方案的一次复核**：设计缺口在这里暴露最便宜（改一个签名 + 通报），在实现后暴露最贵（改 N 个方法 + 已写测试 + 已提交历史）。

### Step 1：梳理类与方法

依据 `feature-design.md §函数调用关系`（函数名 / 签名 / 职责 / 调用 + 入口标注）与 `architecture.md §组件划分`（类/组件归属），产出：

| 项 | 内容 |
|----|------|
| 类/结构 | 每个方法归属的类或模块结构（来自 §组件划分） |
| 签名 | 与设计文档一致；语言用 `implemented_in.lang` 声明的语言 |
| 调用关系 | 本功能内部的调用边；据此定**拓扑序（先被调用者、后调用者）**——天然最优验收顺序 |
| 落点 | 每个方法的源码文件（来自 frontmatter `implemented_in` 的路径范围） |
| 能力注释 | 该方法"做什么"的一句话 + 负面路径策略（见 Step 3） |
| 表外产物 | DDL / 迁移 / 建库逻辑、跨模块契约共享类型、流程隐含写入——**不在 §函数调用关系 里的交付物**，按下方三类归属处理 |

#### 表外产物的三类归属

`feature-design.md §函数调用关系` 只列函数；但设计里还有三类交付物没有函数条目。**不要自造 `T0` 后随便找落点**，按下列归属处理：

- **(a) DDL / 迁移 / 建库逻辑**：允许建 helper 任务（建议 `T0` 或 `H1`）。约定：
  - `title` 以 `[helper]` 开头（如 `[helper] 创建 store 索引与触发器`）；
  - `capability_notes` 首条写 `HELPER: 兑现 C-106~C-114`；
  - `implemented_in` 指向迁移/建库文件（如 `packages/behavior-log/src/store/migrations.ts` 或 `.sql`）；
  - `constraint_ids` 列全它兑现的约束；`calls` 记录被哪个入口调用，没有则空数组；
  - `symbol` / `functions` **允许为空**；
  - helper 任务仍走同一状态机与验收，**不豁免 `accepted` / `tested`**。
- **(b) 跨模块契约共享类型**（如 `EventEnvelope` 落成源码类型文件）：建普通任务卡，`implemented_in` 指向类型文件，`constraint_ids` 引用契约条款；**多个模块共用的归到契约 owner 模块**，不按调用方重复建卡。
- **(c) 流程隐含的写入**（如"会话行 upsert"）：**不单独建卡**，并入触发该写入的流程任务，在 `capability_notes` 写清写入点；跨两个流程时归到**拥有该表/先执行**的一方。

> 与附录 D 的关系：**入口签名冻结不适用于表外产物**；但表外产物若被入口调用，必须在入口的 `calls` 登记，并在该入口验收时覆盖。修改表外产物的落点/签名按"轻"处理，不走 `blocked`（见附录 D）。

### Step 2：用户确认骨架（闸门，不可跳过）

展示骨架表给用户确认：

```
骨架提案：order-timeout-cancel（order 模块，3 个方法）

类：OrderTimeoutService（src/order/timeout_service.go）
  T1 cancelExpiredOrders(ctx) error     入口  调用 findExpiredOrders, cancelOrder
  T2 findExpiredOrders(ctx) []Order           调用 —
  T3 cancelOrder(ctx, o Order) error          调用 releaseStock
类：StockService（src/order/stock.go）
  T4 releaseStock(o Order) error              调用 —

调用链：cancelExpiredOrders → findExpiredOrders / cancelOrder → releaseStock
覆盖约束：T1=C-101,C-102  T2=C-101  T3=C-102  T4=C-102
表外产物：T0 [helper] 创建索引与触发器（兑现 C-106~C-114）/ 无

确认 / 调整（签名、类归属、落点、拆分合并、顺序）？
```

用户可改签名、改类归属、改落点、拆分或合并任务、调整顺序。**确认后签名即冻结**（变更走「附录 D 签名变更协议」）。

> **分支创建后的小幅修订用 `dev task patch`**：只改签名 / 调用 / 能力注释 / 约束等字段时，不要用 `dev task set` 重灌整张清单（会静默重置缺失字段）；分支尚未创建时仍用 `dev task set`。

### Step 3：写入源码 stub

在落点文件写入**只有签名与注释、没有实现**的骨架。注释即能力契约：

- 一句话说明该方法的能力（做什么、边界在哪）
- `// NEGATIVE: ...` —— 该方法的负面路径策略（依赖超时/拒绝/空返回/脏数据时的降级、重试或明确报错）。**写不出来就说明设计有缺口**，此时不要编造，转 Step 2 或记 CodeNotes 并升级用户
- `// DECISION: ... (Ref: CodeNotes#<条目>)` —— 存在歧义或跨文档冲突时的决策回溯占位

函数体只留"未实现"占位（如 `panic("TODO")` / `NotImplementedError`），**不写任何实现逻辑**。

> 骨架提交：建议把 stub 单独提交一次（commit message 说明"骨架：<功能名>，签名与调用关系"），便于后续逐方法 diff。

### Step 4：写入任务清单

```bash
python3 .doc-kit/cli/cli.py dev task set --json '<tasks 数组>'
```

**默认粒度：一张任务卡 = 单个文件内的一条内聚调用链**（入口方法 + 仅被该入口调用的私有伴生方法），**不是一个方法一卡**。卡内用 `entry_function` + `functions`（包含入口在内的全部函数名）表达；`signature` 记入口签名，全部函数签名写入 `signatures` 映射（供附录 B 第 1 项机械比对）：

```json
{
  "task_id": "T1",
  "title": "扫描并取消超时订单（入口）",
  "module": "order",
  "feature": "order-timeout-cancel",
  "cls": "OrderTimeoutService",
  "symbol": "cancelExpiredOrders",
  "implemented_in": {"path": "src/order/timeout_service.go", "lang": "go"},
  "calls": ["findExpiredOrders", "cancelOrder"],
  "capability_notes": ["扫描周期 5 分钟；取消成功后释放库存", "NEGATIVE: 库存服务不可用时保留订单并重试"],
  "functions": ["cancelExpiredOrders", "findExpiredOrders", "cancelOrder", "releaseStock"],
  "entry_function": "cancelExpiredOrders",
  "signature": "cancelExpiredOrders(ctx context.Context) error",
  "signatures": {
    "cancelExpiredOrders": "cancelExpiredOrders(ctx context.Context) error",
    "findExpiredOrders": "findExpiredOrders(ctx context.Context) []Order",
    "cancelOrder": "cancelOrder(ctx context.Context, o Order) error",
    "releaseStock": "releaseStock(o Order) error"
  },
  "gwt_refs": ["unit-tests.md#测试用例：超时订单被扫描"],
  "constraint_ids": ["C-101", "C-102"],
  "timeout_seconds": 300,
  "max_attempts": 2,
  "status": "pending"
}
```

> 合并同一文件内的调用链时必须在 `merge_reason` 写明合并理由。表外产物 helper（DDL/迁移）是**交付物**，仍单独建卡——本项弱化的只是"纯内部辅助方法"。

**拆分判据（满足任一即拆成独立卡）**：

- 被多个入口调用（共享 helper 不能挂在单一入口下）；
- 有独立 `gwt_refs` 或独立 `constraint_ids`；
- 高风险：IO / 事务 / 锁 / 缓存 / 并发 / 跨模块契约触点；
- 体量超阈值：超过 3 个方法或约 200 行；
- 需要独立验收或独立回滚。

> `dev task set` 是**全量替换**且**拒绝未知字段**：字段名写错会直接报错（不会静默丢弃）。plan.md §3 自动渲染为「任务 / 方法（类） / 实现文件 / 覆盖约束 / 状态」。
>
> **分支创建后的基线修订用 `dev task patch <task_id> --json '<字段子集>'`**：只覆盖给出的字段，`status` / `attempts` / `notes` / 其它任务卡一律保持原值；未给出的字段不会回默认值。`implemented_in` 为对象时**整体替换**——要保留 `lang` 请一并传入。分支尚未创建时仍用 `dev task set`（见「附录 D」）。

### Step 5：创建开发分支

1. `git rev-parse --git-dir` 确认是 git 仓库（不是则跳过本步）
2. 分支名取 `dev-spec.json` 的 `branch`（`dev-loop/<sid>`）
3. `git checkout -b dev-loop/<sid>`
4. **实际分支名与记录不一致时，立即 `dev branch set <实际分支>`**（同步 `dev-spec.json` 与 `plan.md §6`）——否则后续 `dev task update` / `dev task patch` 会被分支断言阻断
5. 创建失败（分支已存在等）→ `dev abort --reason "Git 分支创建失败: <错误信息>"`，提示用户处理后重开。**严禁在无分支状态下进入 Phase 3**

## Phase 3：逐方法实现（委托 + 验收）

### Step 1：选任务并置状态

按拓扑序取一个 `pending` 任务：`dev task update <task_id> --status implementing`

### Step 1.5：测试先行（Red）

在派发实现之前，先把该任务的验证方式固定下来（**每任务 TDD**，不做 Phase 2 批量前置）：

1. 主代理从任务卡 `gwt_refs` 取 GWT，写/确认**定向测试**（只覆盖该任务，不跑全量套件）。
2. 任务**没有 `gwt_refs`**（如表外产物 helper）时，必须在 `capability_notes` 写一条 `VERIFY: <可执行验证方式>`（迁移测试、契约测试或编译/类型检查），否则**不允许进入实现**。
3. 对仍为 stub 的代码运行该定向测试，留档 `DevSpec/active/<sid>/evidence/<task_id>_red.log`：

   ```bash
   set -o pipefail
   timeout ${timeout_seconds}s <定向测试命令> 2>&1 | tee DevSpec/active/<sid>/evidence/<task_id>_red.log
   ```

4. **测试作者 ≠ 实现者**：由主代理或独立测试子代理写测试；实现子代理的简报**不得包含测试代码或断言**，只给 GWT 原文与接口（见附录 A）。

**有效红灯判据**（防止形式化红灯）：

- 日志必须包含指定测试名/用例 ID（与 `gwt_refs` 对得上）；
- 失败原因必须是 stub 的 `TODO` / `NotImplemented` / `panic`，或目标断言失败；
- **编译失败、导入失败、语法错误不算有效红灯**。若语言/类型系统导致 stub 无法编译，先把 stub 改成可编译占位（`throw new Error("TODO")` / `panic("TODO")` / `unimplemented!()`），再重跑红灯；确实无法做到时，在任务 `notes` 记录例外，并在最小可编译骨架后补一次红灯。

### Step 2：决定谁来实现

| 方法类型 | 实现者 |
|---------|--------|
| 机械、模板化、重复度高（校验、映射、样板） | **子代理**（隔离收益最大、风险最低） |
| 高风险：IO / 事务 / 锁 / 缓存 / 并发 / 跨模块契约触点 | **主代理亲自**（语义验收成本高于实现成本） |
| 同一文件内的紧耦合调用链 | **同一单元**（整包交给一个子代理或主代理自做） |

**派发单元 = 一个文件内的一个内聚调用链**（= **一张任务卡**，不是一个方法）。**可并行 ⟺ 各单元落点文件互不相同**；同一文件必须串行；跨卡调用关系继续用 `calls` 维护拓扑序。

### Step 3：组装简报并派发（子代理路径）

按「附录 A」组装**自包含简报**（任务卡 + plan.md §2/§2.5/§2.6 片段），调用子代理工具（后台运行，可并行）。子代理不读 ProjectSpec，只按简报实现指定文件内、卡内声明的函数体。**简报不得包含测试代码或断言**（只给 GWT 原文与接口），否则红灯证据不可信。

### Step 4：交回并验收

子代理返回后：`dev task update <task_id> --status submitted`，然后按「附录 B」七项**亲自**验收：

- 全部通过 → `dev task update <task_id> --status accepted`
- 任一项不过 → `dev task update <task_id> --status rejected --note '<失败证据 + 期望>'`

> **红线**：子代理的"已完成/已测试"自述不作为验收依据。验收命令与输出留档到 `DevSpec/active/<sid>/evidence/`。
>
> 需要给任务留一条**不改变状态**的备注（如记录观察到的偏差）时，用 `python3 .doc-kit/cli/cli.py dev task annotate <task_id> --note '<备注>'`——它带日期追加到该任务的 `notes`，可在 `dev task list` 的 JSON 中读到。要改状态就用 `dev task update`（`--status` 必填且受状态机约束）。

### Step 5：失败与缺口处置

| 档位 | 情形 | 处置 |
|------|------|------|
| 简报不足 | 子代理指出信息缺失/歧义 | 补简报重派（不计入 `attempts`） |
| 实现错误 | 验收任一项不过 | `rejected` + 证据 → 重派；`attempts` 超 `max_attempts` → 主代理接手 |
| 超时 | 超过 `timeout_seconds` 无产出 | `rejected`（note 记 timeout）→ 缩小简报或拆任务后重派 |
| 设计缺口 / 签名需变更 | 文档矛盾、缺失、签名不合适 | **停止**：`blocked` + CodeNotes + 升级用户裁决（见「附录 D」） |

> 设计问题**只记录、不修改 ProjectSpec**：报告 → CodeNotes 反链 → 原文档段落，评审后可快速追溯。

## Phase 4：单元测试、提交与验收测试

### Step 1：GWT 单元测试（Green 验收）

用 **Phase 3 Step 1.5 的同一条定向测试命令**重新运行，观察红灯转绿，留档 `evidence/<task_id>_green.log`：

```bash
set -o pipefail
timeout ${timeout_seconds}s <定向测试命令> 2>&1 | tee DevSpec/active/<sid>/evidence/<task_id>_green.log
```

- 绿灯与红灯的测试名/用例 ID 必须一致；
- 绿灯失败 → `dev task update <task_id> --status rejected --note '<green 失败摘要 + 证据路径>'`，**不得置 `tested`**；
- 通过后 `dev task update <task_id> --status tested`（测试结果由主代理判定，可派子代理起草测试代码，但**执行与判定必须主代理做**）。

> `set -o pipefail` 不可省：没有它时 `| tee` 会把测试命令的非零退出码吞掉，失败可能被当成"已跑过"。日志里的测试名与 `gwt_refs` 必须对得上。

**`tested` 硬闸**：主代理置 `tested` 前必须**同时核对 `_red.log` 与 `_green.log`**——缺失红灯、红灯无效（编译/导入失败）、红绿测试名不一致，均**不得置 `tested`**。用 `dev task annotate <task_id> --note 'red=<path> green=<path>'` 记录路径，便于审计。

> 机械强制（`dev task update --status tested` 校验证据文件存在）不在本轮实现，先用技能级硬闸 + `annotate` 记录。

### Step 2：提交

任务 DoD 全满足后提交（可调 spec-smart-git；**提交前确认 `git branch --show-current` 是 `dev-loop/<sid>`**），然后 `dev task update <task_id> --status done`。

### Step 3：验收测试

全部任务 done 后，`phase` 进入测试/收尾。以**自动化为主**：把 `acceptance-tests.md` 的 Gherkin 场景翻译为集成/E2E 测试并执行；无法自动化的场景以「人工验证 + 证据」（截图/日志/记录）兜底。

### Step 4：约束覆盖检查（G4）

核对 `feature-design.md §边界约束` 中每个编号 `[MUST]`（C-xxx）在 `unit-tests.md` 中有对应场景引用。

### Step 5：回归

回归范围 = 本功能全部测试 + **依赖它的下游**（用 `doc structure` 的 `depends_on` 反查 / `module-manifest` imports 反查）。

## Phase 5：收尾

1. `dev align --feature <功能名> --module <模块名> --status aligned`（CLI 校验：该功能全部任务必须 done）
2. 整理 CodeNotes（`dev notes append`，仍为追加式）：开发问题与解决 / 设计文档遗漏与偏差（含建议的 Spec 修改）/ 重点关注区域 / 流程与方案改进建议
3. `dev report-write --kind feature --name <功能名> --content '<报告>'`

```markdown
# 功能对齐报告：<功能名>

> 会话: <session_id> · 日期: <YYYY-MM-DD>

## 完成情况
| 任务 | 方法 | 落点 | 状态 | 验收结果 | 测试证据 |
|------|------|------|------|---------|---------|

## 验收对齐
- 验收场景：X/Y 通过（自动化）/ Z 人工验证
- G4 约束覆盖：C-101 ✓ C-102 ✓ …
- 回归：<范围 + 结果>

## 设计偏差汇总（供评审追溯）
| # | 严重等级 | 偏差描述 | 判断依据 | CodeNotes 条目 | 建议的 Spec 修改 |
|---|---------|---------|---------|---------------|-----------------|
```

4. `dev close --reason '<原因>'` → `dev archive`
5. **提示人工合并分支**：代码位于 `dev-loop/<sid>`，请人工评审/验收通过后合并回主分支并删除开发分支

## 运行前检查

### 任务状态机（与 `DEV_TASK_TRANSITIONS` 一致）

```text
主链：pending → implementing → submitted → accepted → tested → done
回退与旁路（与主链并列）：
implementing → rejected
implementing → blocked
submitted → rejected
accepted → rejected
tested → rejected
rejected → implementing
blocked → implementing
blocked → rejected
done → （终态）
```

- 非法转移返回 `ERROR [dev_task.invalid_transition]` 且退出码 1，**任务状态不变**；
- **批量推进状态后，用 `dev task list` 复查，不要只看最后一条命令的 stdout；多条命令用 `&&` 串联或 `set -e`**——`| tee` / 多命令串行吞掉退出码是"状态静默失真"的常见来源。

每次进入先 `python3 .doc-kit/cli/cli.py dev status` 看 `phase`、`data.branch` 与 `data.branch_matches`，需要任务明细时用 `python3 .doc-kit/cli/cli.py dev task list`，需要回看计划表用 `python3 .doc-kit/cli/cli.py dev plan read`，从对应阶段的断点继续：

```bash
git branch --show-current        # 应与 dev status 的 data.branch 一致
git checkout <记录的分支名>        # 不一致时切换后再继续（或 dev branch set <实际分支>）
```

## 与其它技能的分工

| 技能 | 分工 |
|------|------|
| spec-dev-loop（本技能） | feature 级开发闭环，ProjectSpec 只读 |
| spec-smart-git | 代码提交（任务 done 时调用） |
| spec-code-review | 循环外代码评审（比对设计文档，允许改文档） |

---

## 附录 A：子代理简报模板

```markdown
【任务】<task_id> / <feature>（<module> 模块）
【目标文件】<implemented_in.path>（**仅此文件**；已存在的骨架请勿改动卡外函数签名）
【入口函数】<cls>.<entry_function>
【入口签名】<signature>
【伴生函数清单（逐个签名 + 能力注释）】
  - <fn1>：<signatures[fn1]>
      能力：<对应 capability_notes>
  - <fn2>：<signatures[fn2]>
      能力：<对应 capability_notes>
【调用】<calls>
【必须满足的约束】<constraint_ids 及 plan.md §2 中对应条目原文>
【代码风格快照】<plan.md §2.5 摘要>
【验证命令】<plan.md §2.6 的 build / lint / typecheck>
【禁止】改 ProjectSpec 任何文件 / 改卡内未声明函数的签名 / 新增公开 API / 引入新依赖 / 执行 git 命令 / 自行编写测试断言
【交付】仅修改目标文件中**卡内声明的函数**（入口 + 伴生）的函数体；用一句话说明实现思路与自测方式
```

**主代理职责**：简报必须自包含（子代理不读 ProjectSpec、不读 plan.md）；同一文件的任务必须串行派发。

> 简报**不得包含测试断言**（也不给测试代码）：只给 GWT 原文与接口，测试由主代理或独立测试子代理编写。实现子代理只改卡内声明的函数，不得自行扩大范围。

## 附录 B：验收清单（主代理逐项亲跑）

| # | 核对项 | 手段 | 深度 |
|---|--------|------|------|
| 1 | 签名与骨架基线一致 | 比对 `tasks.json` 的 `signatures` 中**全部函数签名**（无 `signatures` 时退回比对 `signature`） | 机械 |
| 2 | 只改了声明的文件 | `git diff --stat -- <源码根> ':(exclude)DevSpec/' ':(exclude)SessionSpec/'`（**必须排除 DevSpec/SessionSpec**：CLI 会在每次任务状态变更时改写 tasks.json / plan.md，未排除会误判"改了多余文件"） | 机械 |
| 3 | 静态诊断（lint / typecheck） | 按 plan.md §2.6 的项目命令运行，**只拦本次新增**（见下方 B-1） | 机械 |
| 4 | 编译/构建通过 | 项目构建命令 | 机械 |
| 5 | 冒烟：最小可执行路径跑通 | 子代理留下的临时脚本或最小调用 | 机械 |
| 6 | 未新增依赖、未扩大公开 API | 读 diff | 机械 |
| 7 | 能力注释承诺落实（含 `NEGATIVE` 分支） | 读实现代码，按卡内**每个高风险函数**逐项走查 | **仅高风险函数** |

> 机械项让回流主上下文的体积保持最小；第 7 项只对 IO/事务/锁/缓存/并发/契约触点类函数执行。**验收命令与输出留档 evidence/**。

### 附录 B-1：静态诊断（第 3 项）

- 主代理在子代理交回、任务状态为 `submitted` 后**亲自**运行；
- 若构建命令已包含 lint/typecheck，在 §2.6 标注"包含在 build 中"，不重复执行；
- 未配置工具时写 `skipped: not configured`，继续后续验收，**不得因此阻断**；
- **只拦"本次新增"的错误**：优先用工具自带增量参数（如 `--new-from-rev`）；否则按本次变更文件/行过滤诊断输出；无法过滤时记录"全量诊断历史问题 N 条，本次新增 M 条"，**只以 M > 0 作为打回依据**——历史问题不得阻断本次任务；
- 诊断非零且可归因于本任务 → **不进入第 7 项**，直接 `dev task update <task_id> --status rejected --note '<≤20 行摘要 + 完整日志路径>'`；完整日志写 `evidence/<task_id>_static.log`；摘要格式 `file:line  rule  message`，最多 20 行；warning 不阻断，除非项目显式规定；
- **不采信子代理自述**：诊断必须由主代理运行并留档，子代理只按 rejection note 修正。

## 附录 C：模块专项（契约 / 集成）

日常开发不走 module scope。仅以下情形开模块专项 run（`--scope module`）：

- **契约闭合（G3）**：`module-manifest` 的 import↔export 配对校验、`inter-module-contracts` 字段级契约与实现一致性；
- **跨功能重构**：影响同一模块多个 feature 的结构性调整；
- **集成验证**：多个 feature 已 aligned 后的模块级回归。

模块专项沿用同一套阶段与状态机，差异：任务粒度以"契约项/重构项"为单位，Phase 2 骨架化为"模块级接口骨架"，验收后走 `dev integrate --module <模块名> --status <integrated|documented|done>`。

## 附录 D：签名变更协议

骨架确认后签名视为**冻结基线**（`tasks.json` 的 `signature` / `signatures` / `calls` 即基线），实现中发现需要变更时：

| 影响面 | 处置 |
|--------|------|
| 本任务的私有助手函数 / 表外 helper 的落点或签名 | 主代理确认后用 **`dev task patch <id> --json '{"signature": "...", "signatures": {...}, "implemented_in": {...}}'`** 更新基线 + `dev notes append` 记录（**轻**） |
| 入口签名 / 跨任务调用关系 | **停止**：`blocked` + 升级用户；确认后更新基线，**并重新验收所有已 `accepted` 的调用方任务**（**重**） |
| 跨模块契约 / `inter-module-contracts` | 不属于循环内可决议范围：`blocked` + 记 CodeNotes + 由用户决定是否回议题（`spec-close` 流程），改完后再恢复 |

- **轻 = `dev task patch <id> --json '{...}'`**（分支创建后，只覆盖给出的字段）；**重 = `dev task set` 全量重建**（含分支创建前）。
- **表外 helper 的签名变化属于"轻"**，但仍需 `dev notes append` 记录并更新基线。
- **基线变更后重开红灯**：任何 `signature` / `signatures` / `functions` / `implemented_in` 的变更都会使旧红灯失效；受影响任务及其调用方必须重新红灯、重新绿灯（Phase 3 Step 1.5 → Phase 4 Step 1）。

禁止：为守住不合适的签名而写出别扭实现；或悄悄改签名而不更新基线（验收第 1 项会比对基线）。

## 附录 E：小功能流程右尺寸（与任务粒度无关）

当本功能 §函数调用关系 的方法数 **≤ 3 且落点在同一文件**时，可**合并 Phase 2 与 Phase 3 的流程开销**：

- 骨架可直接落在源码 stub（不必逐卡派发），也不强制逐卡验收；
- 仍保留两个闸门：**用户确认接口** 与 **主代理验收**；
- Phase 4 测试与 Phase 5 收尾不变。

> **本附录只决定"流程开销"，不参与任务切片**：任务粒度按 Phase 2 Step 4 的"单文件内聚调用链 + 拆分判据"决定，与是否走小功能捷径是两件事。不要把"卡片粒度"和"流程开销"混为一谈。
>
> 理由：新流程的固定开销（骨架 + 简报 + 逐项验收）对小功能可能超过开发本身；流程明显不划算就会被绕过。

## 附录 F：横切 / 基础设施工作的出口

以下工作**不走本技能**：构建脚本、CI 流水线、共享工具库、依赖升级、数据库迁移框架等无 feature 归属的横切工作。

出口：走 `spec-start` 开启议题（或已有议题的 `spec-pause`）记录决策 → 人工/主代理直接实现 → `spec-code-review` 做文档一致性复核。**不要塞进最近的 feature 蹭流程。**

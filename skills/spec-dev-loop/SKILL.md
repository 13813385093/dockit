---
name: spec-dev-loop
description: 依托 ProjectSpec 做 feature 级开发：读设计 → 骨架化 → 委托实现并验收 → 单元/验收测试 → 功能对齐
---

# 最高优先级：

**三层边界（先看清各自走哪条路，是全篇纪律的基础）**：

| 对象 | 读写方式 |
|------|---------|
| `ProjectSpec/`（设计文档） | **只读，经 CLI**（`doc structure` / `doc read`）。禁止任何写操作——设计问题只记录到 CodeNotes 与报告 |
| `DevSpec/`（plan.md / tasks.json / code-notes.md / reports） | **经 CLI**（`dev *` 命令组） |
| **源码与测试代码** | **直接读写**（文件工具 / `bash`）。骨架 stub、方法实现、单元测试代码都属于这一类，CLI 不介入 |

**git 操作**一律用 `bash` 执行（CLI 不执行 git）：`git branch` / `git checkout` / `git rev-parse` / `git diff`。仅**主代理**执行 git，子代理禁止。

**CLI 容灾 Fallback（紧急直读）**：若 `dev task list` / `dev status` 因 CLI 异常（非 JSON 输出、超时或 Python 报错）**连续失败 2 次**，可降级为**直接只读** `DevSpec/active/<sid>/tasks.json` 与 `dev-spec.json` 解析断点（`read_file`，仅限当前活跃会话目录，且必须遵守"禁止写"原则）。此降级必须在 `dev notes append` 中记录"CLI Fallback 触发"。**写操作仍必须走 CLI**，CLI 写失败则停止并提示用户检查 doc-kit 安装。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`。若该文件不存在，输出「请先运行 doc-kit 初始化该项目」，终止流程，不尝试任何自举安装。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py dev status
python .doc-kit/cli/cli.py dev plan create --scope feature --target <功能名> --module <模块名> [--title <标题>]
python .doc-kit/cli/cli.py dev plan read
python .doc-kit/cli/cli.py dev plan update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py dev plan add-section <reference> '<标题>' [--content '<正文>'] [--level sibling|child]
python .doc-kit/cli/cli.py dev task list
python .doc-kit/cli/cli.py dev task set --json '<tasks 数组>'
python .doc-kit/cli/cli.py dev task update <task_id> --status <状态> [--note '<备注>']
python .doc-kit/cli/cli.py dev task annotate <task_id> --note '<备注>'
python .doc-kit/cli/cli.py dev notes append --content '<md>' [--section <章节名>]
python .doc-kit/cli/cli.py dev align --feature <功能名> --module <模块名> --status <aligned|done> [--note '<备注>']
python .doc-kit/cli/cli.py dev report-write --kind feature --name <功能名> --content '<md>'
python .doc-kit/cli/cli.py dev close --reason '<原因>'
python .doc-kit/cli/cli.py dev abort --reason '<原因>'
python .doc-kit/cli/cli.py dev archive
python .doc-kit/cli/cli.py doc structure
python .doc-kit/cli/cli.py doc read <path>
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。错误信息统一为 `ERROR [<错误码>] <原因>。修复：<建议>`，读到后直接按建议行动。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根（`--root` 是全局参数，写在命令组之前）。

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
| 任务 | 一个方法（或一个内聚调用链），含实现落点 | 主代理验收通过（`accepted`）+ GWT 通过（`tested`）|
| 功能 | N 个任务 + 验收测试 + 约束覆盖 + 回归 | 功能对齐（`aligned`）|

**范围规则**：一次开发**只做一个 feature**。选择 feature 而不是 module，主要不是为省上下文（省上下文靠骨架化与委托实现），而是为了**完成判据明确**：`dev align` 有唯一的对齐对象，验收范围可界定，回归影响面可反查。模块级契约/集成见「附录 C」；无 feature 归属的横切工作见「附录 D」。

## 核心纪律

1. **ProjectSpec 全程只读**（不可协商）：设计问题只记录到 CodeNotes 与报告；修改留给循环外的评审/会议
2. **DevSpec 操作一律经 CLI**；**源码与测试代码直接读写**（见「最高优先级」三层边界）
3. **骨架先行**：没有 `implemented_in`（实现落点）的任务不许开工——`dev task set` 会直接拒绝缺失落点的任务
4. **委托实现必须验收**：`submitted → accepted` 只能由主代理置位，且验收必须**亲自运行命令**复核，**不得采信子代理的自述**
5. **测试必须真实运行**：GWT 是语言无关描述，必须翻译成真实测试代码并跑通——禁止写 trivial 测试糊弄（假绿）；测试结果只能由主代理判定
6. **一次只有一个活跃开发循环**：新循环必须等当前循环 close/abort + archive 后开启

## git 分支策略（开发分支隔离，人工合并）

- 分支命名 `dev-loop/<sid>`，与开发循环**严格一一对应**（串行约束 → 一次一个活跃分支）
- **创建时机**：Phase 2 `dev task set` 成功后、Phase 3 第一个任务开始前
- 分支名由 `dev plan create` 记录在 `dev-spec.json` 与 `plan.md §6`；人工调整后用 `dev plan update-section 'plan.md#6. 分支信息'` 更新
- 循环内所有提交都在开发分支上；**合并回主分支是人工在循环外完成的动作**，循环内不合并、不推送
- **断点续跑检查**：Phase 0 后执行 `git branch --show-current`，与 `dev status` 报告的分支名不一致则 `git checkout <分支名>`
- 每个 feature 一个分支 → **分支数量会随功能数增长**，合并节奏由人工把控
- 项目不是 git 仓库时跳过全部 git 操作（提交完全由人工决定）

## Phase 0：入口

调 `python .doc-kit/cli/cli.py dev status`：

| 返回 | 含义 | 下一步 |
|------|------|--------|
| 「当前没有活跃开发循环」 | 无进行中的循环 | 引导用户指定 feature 范围，进入 Phase 1 |
| `phase: design` | 尚无任务清单 | 从 Phase 1 开始（读设计 → 骨架化） |
| `phase: implement` | 有任务待实现/待验收 | 按 `suggestions` 从断点继续（pending → 派发；submitted → 验收；rejected → 重派；blocked → 找用户裁决） |
| `phase: test` | 任务已验收，待测试 | 进入 Phase 4 |
| `phase: close` | 任务全完成 | 进入 Phase 5 |
| 报错「多个活跃开发循环」 | 违反串行约束 | 提示用户处理 `DevSpec/active/` 后重试 |

## Phase 1：读设计（只读 ProjectSpec）

### Step 1：确认范围

用户指定 feature（如 `/spec-dev-loop order-timeout-cancel`）：

```bash
python .doc-kit/cli/cli.py dev plan create --scope feature --target <功能名> --module <所属模块>
```

生成 `DevSpec/active/{日期}-{功能名}/`（dev-spec.json / plan.md / tasks.json / code-notes.md / evidence/ / reports/）。

> 先做**右尺寸判断**：若该功能 §函数调用关系 的方法数 ≤ 3 且落点在同一文件，按「附录 E」合并 Phase 2/3（豁免逐方法派发与逐项验收，但仍保留"接口确认"与"主代理验收"两个闸门）。

### Step 2：读取范围文档

按渐进式披露加载最小上下文集：

1. `doc structure` 查看全部文档与依赖
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
python .doc-kit/cli/cli.py dev plan update-section 'plan.md#2.5 代码风格快照' --content '<风格摘要>'
```

### Step 4：约束整合

```bash
python .doc-kit/cli/cli.py dev plan update-section 'plan.md#2. 约束整合' --content '<整合后的约束清单>'
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

确认 / 调整（签名、类归属、落点、拆分合并、顺序）？
```

用户可改签名、改类归属、改落点、拆分或合并任务、调整顺序。**确认后签名即冻结**（变更走「附录 D 签名变更协议」）。

### Step 3：写入源码 stub

在落点文件写入**只有签名与注释、没有实现**的骨架。注释即能力契约：

- 一句话说明该方法的能力（做什么、边界在哪）
- `// NEGATIVE: ...` —— 该方法的负面路径策略（依赖超时/拒绝/空返回/脏数据时的降级、重试或明确报错）。**写不出来就说明设计有缺口**，此时不要编造，转 Step 2 或记 CodeNotes 并升级用户
- `// DECISION: ... (Ref: CodeNotes#<条目>)` —— 存在歧义或跨文档冲突时的决策回溯占位

函数体只留"未实现"占位（如 `panic("TODO")` / `NotImplementedError`），**不写任何实现逻辑**。

> 骨架提交：建议把 stub 单独提交一次（commit message 说明"骨架：<功能名>，签名与调用关系"），便于后续逐方法 diff。

### Step 4：写入任务清单

```bash
python .doc-kit/cli/cli.py dev task set --json '<tasks 数组>'
```

任务卡（每方法一卡；合并内聚方法须写 `merge_reason`）：

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
  "functions": ["cancelExpiredOrders"],
  "entry_function": "cancelExpiredOrders",
  "signature": "cancelExpiredOrders(ctx context.Context) error",
  "gwt_refs": ["unit-tests.md#测试用例：超时订单被扫描"],
  "constraint_ids": ["C-101", "C-102"],
  "timeout_seconds": 300,
  "max_attempts": 2,
  "status": "pending"
}
```

> `dev task set` 是**全量替换**且**拒绝未知字段**：字段名写错会直接报错（不会静默丢弃）。plan.md §3 自动渲染为「任务 / 方法（类） / 实现文件 / 覆盖约束 / 状态」。

### Step 5：创建开发分支

1. `git rev-parse --git-dir` 确认是 git 仓库（不是则跳过本步）
2. 分支名取 `dev-spec.json` 的 `branch`（`dev-loop/<sid>`）
3. `git checkout -b dev-loop/<sid>`
4. 创建失败（分支已存在等）→ `dev abort --reason "Git 分支创建失败: <错误信息>"`，提示用户处理后重开。**严禁在无分支状态下进入 Phase 3**

## Phase 3：逐方法实现（委托 + 验收）

### Step 1：选任务并置状态

按拓扑序取一个 `pending` 任务：`dev task update <task_id> --status implementing`

### Step 2：决定谁来实现

| 方法类型 | 实现者 |
|---------|--------|
| 机械、模板化、重复度高（校验、映射、样板） | **子代理**（隔离收益最大、风险最低） |
| 高风险：IO / 事务 / 锁 / 缓存 / 并发 / 跨模块契约触点 | **主代理亲自**（语义验收成本高于实现成本） |
| 同一文件内的紧耦合调用链 | **同一单元**（整包交给一个子代理或主代理自做） |

**派发单元 = 一个文件内的一个内聚调用链**（不是一个方法）。**可并行 ⟺ 各单元落点文件互不相同**；同一文件必须串行。

### Step 3：组装简报并派发（子代理路径）

按「附录 A」组装**自包含简报**（任务卡 + plan.md §2/§2.5 片段），调用子代理工具（后台运行，可并行）。子代理不读 ProjectSpec，只按简报实现指定文件的指定方法体。

### Step 4：交回并验收

子代理返回后：`dev task update <task_id> --status submitted`，然后按「附录 B」六项**亲自**验收：

- 全部通过 → `dev task update <task_id> --status accepted`
- 任一项不过 → `dev task update <task_id> --status rejected --note '<失败证据 + 期望>'`

> **红线**：子代理的"已完成/已测试"自述不作为验收依据。验收命令与输出留档到 `DevSpec/active/<sid>/evidence/`。

### Step 5：失败与缺口处置

| 档位 | 情形 | 处置 |
|------|------|------|
| 简报不足 | 子代理指出信息缺失/歧义 | 补简报重派（不计入 `attempts`） |
| 实现错误 | 验收任一项不过 | `rejected` + 证据 → 重派；`attempts` 超 `max_attempts` → 主代理接手 |
| 超时 | 超过 `timeout_seconds` 无产出 | `rejected`（note 记 timeout）→ 缩小简报或拆任务后重派 |
| 设计缺口 / 签名需变更 | 文档矛盾、缺失、签名不合适 | **停止**：`blocked` + CodeNotes + 升级用户裁决（见「附录 D」） |

> 设计问题**只记录、不修改 ProjectSpec**：报告 → CodeNotes 反链 → 原文档段落，评审后可快速追溯。

## Phase 4：单元测试、提交与验收测试

### Step 1：GWT 单元测试（真实运行）

把任务卡 `gwt_refs` 引用的 GWT 用例翻译为真实测试代码（语言按 `implemented_in.lang`），**实际运行通过**：

```bash
timeout ${timeout_seconds}s <测试命令> 2>&1 | tee DevSpec/active/<sid>/evidence/<task_id>.log
```

通过后 `dev task update <task_id> --status tested`（测试结果由主代理判定，可派子代理起草测试代码，但**执行与判定必须主代理做**）。

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

每次进入先 `dev status` 看 `phase` 与状态分布，从对应阶段的断点继续：

```bash
git branch --show-current        # 应与 dev status 报告的分支一致
git checkout <记录的分支名>        # 不一致时切换后再继续
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
【目标文件】<implemented_in.path>（**仅此文件**；已存在的骨架请勿改动其他方法签名）
【方法】<cls>.<symbol>
【签名】<signature>
【能力注释（骨架已定，必须兑现）】
  - <capability_notes 逐条>
【调用】<calls>
【必须满足的约束】<constraint_ids 及 plan.md §2 中对应条目原文>
【代码风格快照】<plan.md §2.5 摘要>
【禁止】改 ProjectSpec 任何文件 / 改其他方法签名 / 新增公开 API / 引入新依赖 / 执行 git 命令
【交付】仅修改目标文件中指定方法的函数体；用一句话说明实现思路与自测方式
```

**主代理职责**：简报必须自包含（子代理不读 ProjectSpec、不读 plan.md）；同一文件的任务必须串行派发。

## 附录 B：验收清单（主代理逐项亲跑）

| # | 核对项 | 手段 | 深度 |
|---|--------|------|------|
| 1 | 签名与骨架基线一致 | 比对 `tasks.json` 的 `signature` | 机械 |
| 2 | 只改了声明的文件 | `git diff --stat -- <源码根> ':(exclude)DevSpec/' ':(exclude)SessionSpec/'`（**必须排除 DevSpec/SessionSpec**：CLI 会在每次任务状态变更时改写 tasks.json / plan.md，未排除会误判"改了多余文件"） | 机械 |
| 3 | 编译/构建通过 | 项目构建命令 | 机械 |
| 4 | 冒烟：最小可执行路径跑通 | 子代理留下的临时脚本或最小调用 | 机械 |
| 5 | 未新增依赖、未扩大公开 API | 读 diff | 机械 |
| 6 | 能力注释承诺落实（含 `NEGATIVE` 分支） | 读实现代码 | **仅高风险方法** |

> 机械项让回流主上下文的体积保持最小；第 6 项只对 IO/事务/锁/缓存/并发/契约触点类方法执行。**验收命令与输出留档 evidence/**。

## 附录 C：模块专项（契约 / 集成）

日常开发不走 module scope。仅以下情形开模块专项 run（`--scope module`）：

- **契约闭合（G3）**：`module-manifest` 的 import↔export 配对校验、`inter-module-contracts` 字段级契约与实现一致性；
- **跨功能重构**：影响同一模块多个 feature 的结构性调整；
- **集成验证**：多个 feature 已 aligned 后的模块级回归。

模块专项沿用同一套阶段与状态机，差异：任务粒度以"契约项/重构项"为单位，Phase 2 骨架化为"模块级接口骨架"，验收后走 `dev integrate --module <模块名> --status <integrated|documented|done>`。

## 附录 D：签名变更协议

骨架确认后签名视为**冻结基线**（`tasks.json` 的 `signature`/`calls` 即基线），实现中发现需要变更时：

| 影响面 | 处置 |
|--------|------|
| 本任务的私有助手函数 | 主代理确认后变更；更新 `dev task set` 的基线 + `dev notes append` 记录（轻） |
| 入口签名 / 跨任务调用关系 | **停止**：`blocked` + 升级用户；确认后更新基线，**并重新验收所有已 `accepted` 的调用方任务** |
| 跨模块契约 / `inter-module-contracts` | 不属于循环内可决议范围：`blocked` + 记 CodeNotes + 由用户决定是否回议题（`spec-close` 流程），改完后再恢复 |

禁止：为守住不合适的签名而写出别扭实现；或悄悄改签名而不更新基线（验收第 1 项会比对基线）。

## 附录 E：右尺寸规则

当本功能 §函数调用关系 的方法数 **≤ 3 且落点在同一文件**时：

- Phase 2 与 Phase 3 合并：骨架可直接落在源码 stub（不必逐方法派发），也不强制 `dev task set` 每方法一卡（可按 1 个任务承载整组方法，需写 `merge_reason`）；
- 仍保留两个闸门：**用户确认接口** 与 **主代理验收**；
- Phase 4 测试与 Phase 5 收尾不变。

> 理由：新流程的固定开销（骨架 + 简报 + 逐项验收）对小功能可能超过开发本身；流程明显不划算就会被绕过。

## 附录 F：横切 / 基础设施工作的出口

以下工作**不走本技能**：构建脚本、CI 流水线、共享工具库、依赖升级、数据库迁移框架等无 feature 归属的横切工作。

出口：走 `spec-start` 开启议题（或已有议题的 `spec-pause`）记录决策 → 人工/主代理直接实现 → `spec-code-review` 做文档一致性复核。**不要塞进最近的 feature 蹭流程。**

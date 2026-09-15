# spec-dev-loop 差距分析

> 对照对象：用户提出的「文档驱动的骨架化开发」设想 vs 现状技能（`skills/spec-dev-loop/SKILL.md`，386 行）
> 依据：现状代码/文本实测 + 《01-技能梳理》问题清单 + ProjectSpec 能力库对 §函数调用关系 的定义
> 结论：**同目标、不同重心；三个核心缺失 + 一个关键数据断裂 + 一项流程顺序冲突**

---

## 0. 结论摘要

现状把 `feature-design.md §函数调用关系` 当作**任务切分依据**，切完任务就直接进入「实现 + 自测」；
你的设想把它当作**骨架化依据**，中间插入两个新阶段（骨架确认、子代理实现 + 主代理验收），并把单元测试后置。

| 判定 | 内容 |
|------|------|
| ✅ 方向一致 | 上下文经济（现状已提出"计划表是开发循环的唯一工作上下文"）、以文档为唯一权威、ProjectSpec 只读 |
| 🔴 **核心缺失 1** | **没有骨架阶段**：现状产物是 plan.md §3 的"任务表"，不是类/方法骨架；`signature` 字段只承载"入口函数"一个签名 |
| 🔴 **核心缺失 2** | **没有子代理与验收协议**：全文 0 处提及子代理（已核实）；Phase 2 由主代理实现 + 自己写测试 + 自我验证，没有独立验收环节 |
| 🔴 **关键断裂 3** | **方法→文件映射不存在**：技能 4 处指令依赖 `implemented_in`，但该字段只存在于 ProjectSpec 文档 frontmatter，**不在任务卡 schema**（`TASK_ALLOWED_KEYS` 12 个键不含它）——子代理派发的第一块砖拿不到 |
| 🟠 **顺序冲突 4** | 现状 `unit-green` 是 done 的**前置**（测试与实现交织）；你的设计把测试放到最后一步 |
| 🟠 范围冲突 5 | 现状支持 `module` / `feature` 两种 scope，Phase 4「模块集成（G3 契约闭合）」在 feature 级循环内无法完成 |
| ⚠️ 前置缺陷 | 既有 P0 中 4 项（§2.5 不存在、缺 implemented 状态、timeout 字段被丢弃、`<plan.md>#` 占位符）在新流程下**依然会挡路**，且第 2 项会因状态机重构而必须重做 |

> 好消息：设计侧**早已预留钩子**。能力库 `feature_design.md` 明确定义 §函数调用关系 是「行为规格到代码实现的桥（弥补『设计 → 编码』的最后一步）」，frontmatter 也定义了 `implemented_in: [{path, lang}]`。缺的不是文档能力，而是 dev-loop 里"把桥走完"的那一步。

---

## 1. 你的设想（规范化）

| 阶段 | 动作 | 关键约束 |
|------|------|---------|
| **P1 读设计** | 读 `feature-design.md`（功能行为 + §边界约束 + §函数调用关系）、`unit-tests.md`，**以及所属模块的上下文设计**（`architecture.md` 组件划分、`domain-model.md`、`module-manifest.md`、`inter-module-contracts.md`） | 一次只聚焦一个 feature |
| **P2 骨架化** | 从设计文档梳理**整体的类与方法**（调用关系）；产出**只有签名 + 能力注释**的骨架，**不写方法实现** | 重点是"确认主要方法的调用关系"，即对设计方案的一次复核 |
| **P3 逐方法实现** | 因为签名与调用逻辑已固定，**每个方法的实现派给子代理**，主代理负责**验收** | 目的是少占用主 agent 上下文 |
| **P4 单元测试（可选/收尾）** | 按 `unit-tests.md` 要求编写单元测试，确保质量 | "如果有"——可后置 |

隐含的两条元要求：**范围收敛**（一次一个 feature）与**上下文经济**（主代理不承载实现细节）。

---

## 2. 逐条差距对照

| 你的要求 | 现状实现 | 判定 |
|---------|---------|------|
| 一次开发聚焦一个 feature | `dev plan create --scope module\|feature` 两种都支持；Phase 3 功能对齐（`dev align`）以 feature 为单位；Phase 4 模块集成以 module 为单位 | 🟠 **部分**：feature 已是一等公民，但未被定为唯一粒度；`dev integrate` 在 feature 循环内无法达成 |
| 开发前读 feature 设计 + 单测 + 模块上下文 | Phase 1 Step 3：feature 范围读 `feature-design` + `unit-tests` + `acceptance-tests` + `decision-log`；模块范围读 `architecture` + `domain-model` + `module-manifest` + `integration`；再沿 `depends_on` 补读顶层文档 | ✅ **基本具备**，但"feature 任务也要读模块上下文"没写成硬要求（按现文义是"或者"关系）；且 `acceptance-tests` 在新设计里可延后到 P4 前后 |
| P2 梳理类与方法、确认调用关系 | **无此阶段**。Step 5 直接从 §函数调用关系 推导任务清单（`functions` / `entry_function` / `signature` / `gwt_refs` / `constraint_ids`），落成 plan.md §3 表格 | 🔴 **缺失** |
| P2 只出签名 + 注释，不写实现 | 无骨架产物；`signature` 只存"入口函数签名"一个字符串；"注释说清能力"这件事现状发生在**实现阶段**（Step 2 强制 `// NEGATIVE:` / `// DECISION:` 注释） | 🔴 **缺失**（但注释纪律可平移复用，见 §3.1） |
| P3 子代理实现每个方法 | 全文无子代理；Phase 2 主代理自己 `in-progress → 实现 → 自测 → done` | 🔴 **缺失** |
| P3 主代理验收 | 现状无验收环节：任务 done 的判据是"覆盖约束对应的 GWT 场景全部真实通过"，即**自我验证**；唯一的独立检查是循环外的 `spec-code-review` | 🔴 **缺失** |
| P3 前置"签名与调用逻辑已定" | 签名信息只存在于任务卡的 `signature`（单入口）与 ProjectSpec 的 §函数调用关系（全量），未在 DevSpec 侧固化为"可派发的签名集合" | 🟠 **部分**（信息载体不足） |
| P4 单元测试收尾 | Phase 2 Step 3 **每个任务**都要把 GWT 翻译为真实测试并跑到 `unit-green` 才允许 done；Phase 3 再做验收测试与回归 | 🟠 **冲突**：顺序相反，且现状是"测试绑任务"而非"测试收尾" |
| 上下文经济 | 目标一致：Step 4 明确"计划表是开发循环的唯一工作上下文"，执行任务时只需读任务卡 + `implemented_in` 源码 | ⚠️ **目标达成不了**：`implemented_in` 不在任务卡里，实际上仍要回翻 ProjectSpec（见 §3.2） |
| ProjectSpec 只读 | 核心纪律 1（不可协商） | ✅ **一致**（新设计需保留） |

---

## 3. 三个核心缺失详解

### 3.1 缺"骨架阶段"——但设计侧已备好钩子

设计文档已经具备骨架化所需的全部输入：

| 输入 | 位置 | 提供什么 |
|------|------|---------|
| 函数级静态结构 | `feature-design.md §函数调用关系` | 全部函数（签名 + 职责 + 调用关系），入口函数标注「入口」；能力文件要求"处理流程的每个步骤应能映射到下表一个或多个函数" |
| 实现位置 | `feature-design.md` frontmatter `implemented_in: [{path, lang}]` | 源码目录与语言（"每个函数应能落到 implemented_in 声明的源码路径内"） |
| 组件/类结构 | `architecture.md §组件划分` | 类/组件的划分与职责——**这正是"类和方法"里"类"的设计来源** |
| 质量约束 | `unit-tests.md`（GWT + 覆盖约束）、`feature-design.md §边界约束`（C-xxx） | 每个方法的验收依据 |

现状把这套输入**降维**成了"任务清单"：plan.md §3 只有 `任务 | 标题 | 函数 | 覆盖约束 | 状态` 五列，没有类归属、没有文件路径、没有全量签名，也没有"骨架"这个中间产物。

> **顺带解释了一个设计疑惑**：你在 P1 强调"必须读所属模块的上下文设计"，原因不只是"了解背景"——`architecture.md §组件划分` 是"方法落在哪个类/文件"的**必要输入**。只读 feature 文档，骨架阶段无法决定类的归属。这条应在技能里写明因果，而不是当成"建议阅读"。

**注释纪律可平移**：现状 Step 2 的强制注释（`// NEGATIVE:` 负面路径策略、`// DECISION: ... (Ref: CodeNotes#<条目>)`）本质上就是"用注释说清能力"——它应当**前移到骨架阶段**作为能力声明，实现阶段改为"兑现注释承诺"，验收阶段逐条核对。这样"注释"从实现副产品变成骨架契约，正好落在你的设计意图上。

### 3.2 关键断裂：方法 → 文件映射不存在（P0-7，本次新发现）

技能中 4 处依赖 `implemented_in`：

| 位置 | 原文 | 问题 |
|------|------|------|
| 核心纪律 4（行 71） | "GWT 必须翻译成真实测试代码（`implemented_in` 声明的语言与路径）" | 拿不到 |
| Step 4 目标（行 149） | "AI 只需读 plan.md 的任务卡 + `implemented_in` 源码，无需回翻 ProjectSpec" | **陈述不成立** |
| Phase 2 Step 2（行 232） | "在 `implemented_in` 声明的源码路径实现函数" | 拿不到 |
| Phase 2 Step 5 DoD（行 261） | "位于 `implemented_in` 路径内" | 无法校验 |

实测：`TASK_ALLOWED_KEYS = (task_id, title, module, feature, functions, entry_function, signature, gwt_refs, constraint_ids, status, deviation, notes)` —— 没有 `implemented_in`；`dev task set` 对未知键**静默丢弃**（与 timeout 字段同一机制，见 P0-3/P0-8）。`plan.md §3` 渲染也不含文件列。

**这是新设计的第一块砖**：子代理派发的简报必须写明"改哪个文件的哪个方法"。建议任务卡增加 `implemented_in`（`{path, symbol}`），由骨架阶段填写——骨架阶段天然知道每个方法的落点。

### 3.3 缺子代理派发与验收协议

现状 Phase 2 的全部动作由主代理完成，**没有隔离手段**，也没有独立验收。新设计引入子代理后，需要三份新规范：

1. **派发简报（brief）规范**：每个方法一份，包含——签名（来自骨架）、能力注释原文、该方法的约束（C-xxx）、代码风格快照、目标文件与符号名、**禁止事项**（不得改 ProjectSpec、不得改其他方法签名、不得扩大公开 API、不得跑 git）。
2. **验收清单（主代理执行）**：签名与骨架一致 / 注释承诺落实（含 `// NEGATIVE:` 分支）/ 只改了声明的文件 / 编译或冒烟通过 / 未引入额外依赖。**必须由主代理亲自运行命令复核，不得采信子代理的自述**（子代理报告不是独立评估）。
3. **失败处置**：子代理失败是常态，需要有明确分档——简报缺信息→补简报重派；实现错误→带失败证据重派（限次数）；反复失败或发现设计缺口→主代理接手或升级用户裁决；每次失败记 CodeNotes。

---

## 4. 状态机与流程顺序的冲突

现状状态机是为"实现与单测绑定"设计的：

```
pending → in-progress → implemented → unit-green → done        （失败：→ fixing → in-progress）
```
`DEV_TASK_STATUSES = [pending, in-progress, implemented, unit-green, done, fixing]`

新流程是四段（骨架 → 实现 → 验收 → 测试），有两处不兼容：**① 测试后置 → `unit-green` 不该是 done 的前置；② 骨架阶段没有状态位；③ 没有"已交付待验收"与"验收通过"的区分**。

**建议状态机（草案）**：

```
                         ┌──────────── rejected（验收不通过，带失败证据）
                         ▼
pending(骨架已定) → implementing(子代理执行) → submitted(已交回) → accepted(主代理验收通过) → tested(GWT 单测真实通过) → done
                                                                                              ▲
                                                              blocked（发现设计缺口，待用户裁决）
```

- `submitted` 与 `accepted` 的分离是"主代理验收"的落点，不能合并——否则验收无法留痕。
- 精简替代方案：合并 `submitted` 进入 `implementing`（用 `notes` 记录交回时间），状态收敛为 `pending → implementing → accepted → tested → done + blocked/rejected`。
- 现有 `unit-green` 的语义要重新定义（建议：`unit-green` 保留但改由 **P4 测试阶段**统一置位，或直接由 `tested` 取代）。

---

## 5. 与前期问题清单的合流

| 前期问题 | 在新设计下的处置 |
|---------|----------------|
| **P0-1** `plan.md#2.5 代码风格快照` 不存在（update-section 实测报 `section_not_found`） | **保留且更重要**：骨架阶段就要遵守风格快照。修法二选一：`PLAN_SKELETON` 增补 `## 2.5 代码风格快照`（推荐）／技能改用 `dev plan add-section` |
| **P0-2** Phase 2 缺 `implemented` 环节 → `in-progress→unit-green` 非法 | **被状态机重构吸收**：新状态机整体替换，此项自然消失（但 CLI 侧 `DEV_TASK_TRANSITIONS` 必须同步改，否则新技能依旧跑不通） |
| **P0-3** `timeout_seconds`/`retry_count`/`retry_delay` 被 `dev task set` 静默丢弃 | **新设计更需要它**（子代理超时是常态）。二选一：补齐 CLI 字段（推荐）／删除该章节改为人工处置 |
| **P0-4** `timed_out`/`failed` 状态与 `continue`/`skip` 命令都不存在 | 同上，且必须补"子代理失败处置"的真实命令（现状技能里的 `continue <task_id>` 是凭空写的） |
| **P0-6** `<plan.md>#2. 约束整合` 占位符被当字面量（实测 `invalid_ref`） | 直接修：命令示例改为字面量 `plan.md#2. 约束整合` |
| **P0-8（新）** `dev task set` 对未知字段静默丢弃 | 建议 CLI 改为**对未知键报错**：这类"写了没生效"的坑已经出现两次（timeout、implemented_in），是系统性风险 |
| **P1-15** 引用"指南 §3.3.3 原则"，但指南不随 init 部署 → 悬空引用 | 新技能要么自包含该规则，要么把指南相关章节下沉为能力库文件 |
| **P2-18** 工具面 19 处引用、声明 18 条命令 | 新流程会重排：`dev plan read/update-section`（骨架）、`dev task update`（状态机）、`dev notes append`（失败与缺口记录）保留；`dev integrate`/`dev report-write` 的取舍取决于决策 D6 |
| **P2-22** 纪律张力：CLI 独占 vs bash fallback vs `find \| xargs cat` 读源码 | **新设计放大了它**：子代理要**写源码文件**，而 CLI 只管 ProjectSpec/DevSpec。必须把三层边界写清：ProjectSpec＝只读（经 CLI）、DevSpec＝经 CLI 读写、**源码与测试代码＝直接读写（文件工具/bash）** |
| **P2-19 分支** | feature 级循环 = 每功能一个 `dev-loop/<sid>` 分支，分支数上升、人工合并压力上升，需在技能里明确合并节奏 |

---

## 6. 新设计放大或新引入的风险

| # | 风险 | 缓解方向 |
|---|------|---------|
| R1 | **子代理"假完成"**：自述通过但实际没跑通/没改对文件 | 主代理亲自运行复核（编译 + 冒烟 + 签名比对），验收不接受自述；`accepted` 只由主代理置位 |
| R2 | **每方法一个子代理 → 调用与验收成本高** | 允许"内聚方法组"合并为一个子代理任务（骨架阶段显式标注合并理由），而非机械一方法一代理 |
| R3 | **骨架先行的前提是设计完整**；设计有缺口会在骨架阶段暴露 | 这正是骨架阶段的价值，但要定义出口：记录 CodeNotes + 升级用户裁决，**不擅自改 ProjectSpec**（沿用核心纪律 1） |
| R4 | **测试后置 → 实现偏差到最后才暴露** | 分层：实现后主代理做"方法级验收"（签名/注释/编译/冒烟，不写正式用例），GWT 单测作为功能级闸门后置 |
| R5 | **feature 级循环与模块集成（G3）冲突** | 循环内只校验"本功能涉及"的 import/export 与契约字段子集；全模块 G3 留给模块级专项 run（决策 D6） |
| R6 | 子代理可能擅自扩大改动面（顺手重构） | 简报写死目标文件与允许的符号范围；验收核对 `git diff --stat` 的文件清单 |
| R7 | 提交由谁做 | 子代理不跑 git；主代理在 `accepted` 后按方法提交（或按功能合并提交），沿用 `spec-smart-git` |

---

## 7. 待你决策的 8 个点

| # | 决策 | 选项 | 推荐 |
|---|------|------|------|
| D1 | 骨架的载体 | (a) 源码树真实 stub（可编译/可 diff）(b) plan.md 里的签名表 (c) 两者 | **(c)**：源码 stub 为准 + plan.md 摘要表 + 任务卡带 `implemented_in` |
| D2 | 任务粒度 | (a) 严格一方法一任务 (b) 沿用现状"内聚助手函数可合并" | **(b) 但需显式标注合并理由**（避免子代理调用爆炸，R2） |
| D3 | 状态机 | (a) 8 状态（含 submitted/accepted）(b) 6 状态精简 | **(a)**：`submitted/accepted` 分离才能给"主代理验收"留痕 |
| D4 | 测试时机 | (a) 全部后置 (b) 分层（方法级冒烟验收 + 功能级 GWT 后置） | **(b)**，兼顾你的"少占上下文"与 R4 |
| D5 | 验收清单 | 需确认清单项（签名/注释/文件范围/编译/冒烟/依赖）与"必须主代理亲跑" | 按 §3.3 草案确认 |
| D6 | scope | (a) 只允许 feature (b) feature 为主、module 降级为"契约/集成专项" | **(b)**：否则 G3 与模块级重构无处安放 |
| D7 | 单元测试谁写 | (a) 主代理 (b) 子代理写、主代理跑 | **(b) 但主代理必须独立执行**（测试是质量闸门，不接受自述） |
| D8 | 循环范围外的产物 | `dev align` 保留；`dev integrate`/`dev report-write`/CodeNotes 四类记录的取舍 | `dev align` 保留；CodeNotes 保留（R3 需要）；`dev integrate` 按 D6 决定 |

---

## 8. 改造后的技能轮廓（讨论稿，待 D1–D8 定稿后细化）

```
Phase 0  入口：dev status（断点检测 + 分支检查）
Phase 1  读设计（feature-design + unit-tests + 模块上下文 architecture/domain-model/manifest/contracts）
         + 代码考古（风格快照 → 修好 §2.5）+ 约束整合
Phase 2  骨架化【新】：§函数调用关系 → 类/方法 + 调用关系 + 每方法 implemented_in → 用户确认
         → 写入源码 stub（签名 + 能力注释，含 NEGATIVE/DECISION 占位）+ dev task set（每方法一卡）
Phase 3  逐方法实现【新】：按拓扑序派子代理（brief）→ submitted → 主代理验收 → accepted
         失败分档处置；全程 ProjectSpec 只读
Phase 4  单元测试（分层）：按 unit-tests.md 的 GWT 写测试并真实跑通 → tested
Phase 5  收尾：dev align（功能对齐）→ CodeNotes 整理 → 报告 → dev close/archive（提示人工合并分支）
```

**与现状的映射**：Phase 1 保留（补模块上下文硬要求 + 修 §2.5）；Phase 2 是新增（现状 Step 5 的任务提案升级为骨架）；现状 Phase 2「任务循环」拆成新 Phase 3（实现）+ Phase 4（测试）；现状 Phase 3「功能对齐」压缩进新 Phase 5；现状 Phase 4「模块集成」按 D6 处置。

**需要同步改的 CLI 侧**（否则新技能跑不通）：`DEV_TASK_STATUSES`/`DEV_TASK_TRANSITIONS`（状态机）、`TASK_ALLOWED_KEYS`（`implemented_in`、超时字段）、`PLAN_SKELETON`（§2.5 + 骨架表）、`_render_task_table`（增文件列）、`dev task set` 未知键报错、`dev status` 输出（骨架/实现/验收三段进度）。

# spec-dev-loop 改进方案（骨架化 + 子代理实现）

> 依据：用户设想（feature 级 / 骨架先行 / 子代理实现 + 主代理验收 / 测试后置）+《03-差距分析》的 3 核心缺失与 P0 清单
> 已定决策：**D6** feature 为主、module 降级专项 ｜ **D1** 源码 stub 为准 + plan.md 摘要 + 任务卡带 `implemented_in` ｜ **D4** 分层（方法级冒烟验收 + 功能级 GWT 后置）
> 待确认：D2 / D3 / D5 / D7 / D8（见 §1，均已给推荐，未否决即按推荐执行）

---

## 1. 决策汇总

| # | 决策 | 结论 |
|---|------|------|
| D1 | 骨架载体 | ✅ 已定：**源码 stub 为准** + `plan.md` §3 摘要表（CLI 从 tasks.json 渲染）+ 任务卡带 `implemented_in` |
| D2 | 派发粒度 | ✅ **派发单元 = 一个文件内的一个内聚调用链**（不是一个方法）；可并行 ⟺ 落点文件不同；**验收仍可逐方法**（派发粒度与验收粒度解耦）|
| D3 | 状态机 | ✅ 8 状态：`pending → implementing → submitted → accepted → tested → done` + `rejected` / `blocked`（`submitted`/`accepted` 分离让主代理验收留痕）|
| D4 | 测试时机 | ✅ 已定：分层——方法级**冒烟验收**（主代理亲跑）+ 功能级 **GWT 单测后置** |
| D5 | 验收清单 | ✅ 六项，**机械优先（回流主上下文要小）+ 风险分层（高风险方法才回读代码语义）**；必须主代理亲自运行复核，不采信子代理自述 |
| D6 | scope | ✅ 已定：feature 为唯一日常入口；module 降级为"契约/集成专项"（附录 C） |
| D7 | 单元测试谁写 | ✅ 可派子代理起草，但**执行与判定必须主代理做**；`tested` 只由主代理置位。**验收测试（Gherkin）与回归必须保留**，是 `dev align` 的前置 |
| D8 | 范围外产物 | ✅ `dev align` / CodeNotes / 功能报告保留；`dev integrate` 只用于模块专项 |
| **D9** | **签名变更协议**（反思新增） | ✅ 冻结基线 = `tasks.json` 的 `signature`/`calls`；私有助手由主代理确认后改基线，入口/跨任务/契约级 → `blocked` + 升级用户/回议题；**已 `accepted` 的调用方需重验** |
| **D10** | **混合实现模式**（反思新增） | ✅ 默认派发；IO/事务/锁/缓存/并发/契约触点类方法**由主代理亲自实现**（派发反而更贵） |
| **D11** | **横切工作出口**（反思新增） | ✅ 构建脚本/共享库/依赖升级/迁移框架**不走本技能**：走议题记录 + 实现 + `spec-code-review` 复核 |
| **D12** | **右尺寸规则**（反思新增） | ✅ 方法数 ≤3 且落点同文件时合并 Phase 2/3，豁免逐方法派发与逐项验收，保留"接口确认"与"主代理验收"两个闸门 |

---

## 2. 新流程

```
Phase 0  入口：dev status（断点/阶段/分支检查）
Phase 1  读设计：feature-design（行为 + §边界约束 + §函数调用关系）
                 + unit-tests + 所属模块上下文（architecture/domain-model/module-manifest/inter-module-contracts）
                 + 代码考古（风格快照）→ 约束整合（含 §2.5 代码风格快照）
Phase 2  骨架化【新】：类/方法 + 调用关系 + 每方法落点 → 用户确认 → 写入源码 stub（签名 + 能力注释）
                 → dev task set（每方法一卡，带 implemented_in / cls / symbol / calls）
Phase 3  逐方法实现【新】：按拓扑序派子代理（brief）→ submitted → 主代理验收 → accepted
                 失败分档处置；全程 ProjectSpec 只读
Phase 4  单元测试：按 unit-tests.md 的 GWT 写真实测试并跑通 → tested →（提交）done
Phase 5  收尾：dev align（功能对齐）→ CodeNotes 整理 → 功能报告 → dev close/archive（提示人工合并分支）
```

**Phase 2 是新增的核心**：它把设计文档里的 §函数调用关系「materialize」成可编译、可 diff、可派发的骨架，同时完成对设计方案的一次复核（缺口在此暴露，比在实现后暴露便宜）。

**Phase 3/4 的拆分**是 D4 的落点：`accepted`（方法级：签名/注释/编译/冒烟）与 `tested`（功能级：GWT 真实通过）是两个不同的闸门，不能合并。

---

## 3. 数据模型与 CLI 变更

### 3.1 任务卡（tasks.json）新增字段

```json
{
  "task_id": "T1",
  "title": "电压越限检测（入口）",
  "module": "protection",
  "feature": "over-voltage-trip",
  "cls": "ProtectionService",                        // 【新】骨架确定的类/结构归属
  "symbol": "detectOverVoltage",                     // 【新】主方法名
  "signature": "detectOverVoltage(samples []Sample, threshold float64) TripCmd",
  "implemented_in": {"path": "src/protection/service.go", "lang": "go"},   // 【新】落点（子代理简报的必需项）
  "calls": ["evaluateThreshold", "issueTrip"],       // 【新】骨架确认的调用关系（供拓扑序与简报自包含）
  "capability_notes": ["越限即建跳闸指令；采样缺失时保守跳闸"],              // 【新】骨架能力注释摘要
  "functions": ["detectOverVoltage", "evaluateThreshold", "issueTrip"],
  "entry_function": "detectOverVoltage",
  "merge_reason": "",                                // 【新】多方法合并为一个任务时的理由（D2）
  "gwt_refs": ["unit-tests.md#测试用例：电压越限"],
  "constraint_ids": ["C-101"],
  "timeout_seconds": 300,                            // 【新】派发超时（P0-3 修复）
  "max_attempts": 2,                                 // 【新】重派上限
  "attempts": 0,                                     // 【新】已重派次数（CLI 维护）
  "status": "pending",
  "deviation": "",
  "notes": ""
}
```

> 设计意图：`implemented_in` + `signature` + `capability_notes` + `calls` + 约束 ID 一起构成**自包含的方法简报**，主代理派发时无需回翻 ProjectSpec——这才真正兑现现状那句"计划表是唯一工作上下文"。

### 3.2 状态机（D3 推荐：8 状态）

```
pending ──► implementing ──► submitted ──► accepted ──► tested ──► done
   ▲             │  ▲            │            │           │
   │             │  └────────────┴────────────┴───────────┘
   │             ▼                （rejected：验收/测试不通过，带失败证据）
   │          blocked（发现设计缺口，待用户裁决）──► implementing
   └────────────（blocked 裁决为"不实现"时 → rejected）
```

| 状态 | 含义 | 置位者 |
|------|------|--------|
| `pending` | 骨架已确认，待实现 | Phase 2 |
| `implementing` | 子代理实现中（含 timeout 计时） | 主代理派发 |
| `submitted` | 子代理已交回，待验收 | 主代理（收到产出） |
| `accepted` | 主代理验收通过（签名/注释/编译/冒烟/文件范围） | 主代理 |
| `tested` | 该任务 GWT 用例真实通过 | 主代理（Phase 4） |
| `done` | 已提交 | 主代理 |
| `rejected` | 验收/测试不通过（note 必带失败证据） | 主代理 |
| `blocked` | 设计缺口，需用户裁决 | 主代理 |

- 迁移表：`rejected → implementing`（重派，受 `max_attempts` 限制）；`blocked → implementing | rejected`。
- **替代**旧状态：`in-progress` → `implementing`；`unit-green` → `tested`；`fixing` → `rejected`。
- **P0-2 自然消失**：新状态机不再要求 `implemented` 这个尴尬的中间态。

### 3.3 plan.md 结构调整

| 章节 | 变更 |
|------|------|
| `## 2. 约束整合` | 不变 |
| `## 2.5 代码风格快照` | **新增到 `PLAN_SKELETON`**（修 P0-1：现状 Step 3.5 的 update-section 指令必然失败） |
| `## 3. 任务清单` | 渲染列扩展为 `任务 \| 方法(类) \| 文件 \| 覆盖约束 \| 状态`，骨架信息一眼可见 |
| `## 4-6` | 不变（变更记录 / 完成标准 / 分支信息） |

### 3.4 CLI 变更清单

| # | 变更 | 对应问题 |
|---|------|---------|
| C1 | `DEV_TASK_STATUSES` / `DEV_TASK_TRANSITIONS` 换新状态机 | P0-2、D3 |
| C2 | `TASK_ALLOWED_KEYS` 增 `cls`/`symbol`/`implemented_in`/`calls`/`capability_notes`/`merge_reason`/`timeout_seconds`/`max_attempts`/`attempts` | P0-3、P0-7 |
| C3 | `dev task set` **对未知键报错**（不再静默丢弃） | P0-8（timeout、implemented_in 两次踩坑的根因） |
| C4 | `_clean_task` 校验 `implemented_in.path` 非空、`calls`/`functions` 为数组 | 派发前置条件 |
| C5 | `PLAN_SKELETON` 增 §2.5；`_render_task_table` 增列 | P0-1、D1 |
| C6 | `dev status` 输出阶段（`phase`）+ 各状态计数（骨架/待实现/待验收/已验收/待测试/done）+ 分支检查提示 | 断点续跑要能区分"卡在验收还是卡在测试" |
| C7 | `dev-spec.json` 增 `phase` 字段（`design`/`skeleton`/`implement`/`test`/`close`） | 同上 |
| C8 | `dev integrate` 保留但技能中只在模块专项提及；`dev align` 校验不变 | D6、D8 |

---

## 4. 子代理协议（本方案的核心新增）

### 4.1 派发简报模板（主代理生成，一方法一份）

```markdown
【任务】T3 / over-voltage-trip（protection 模块）
【目标文件】src/protection/service.go（仅此文件；已存在的骨架请勿改动其他方法的签名）
【方法】ProtectionService.evaluateThreshold
【签名】evaluateThreshold(samples []Sample, threshold float64) bool
【能力注释（骨架已定，必须兑现）】
  - 越限判定：电压 > 1.1×额定 且持续 > 10ms 视为越限
  - NEGATIVE: 采样为空或时间戳乱序时返回 false（保守不跳闸），并写 warning 日志
【调用】被 detectOverVoltage 调用；调用 compareSamples
【必须满足的约束】C-101（越限判定阈值与去抖动时长）、C-102（采样异常处理）
【代码风格快照】错误返回 errors.New(...)；日志 log.WithField(...)（见 plan.md §2.5）
【禁止】改 ProjectSpec 任何文件 / 改其他方法签名 / 新增公开 API / 引入新依赖 / 执行 git 命令
【交付】仅修改目标文件的指定方法体；用一句话说明实现思路与自测方式
```

> 要点：**主代理不改代码，只派发与验收**（D4 的方法级冒烟验收由主代理执行）。

### 4.2 验收清单（主代理逐项亲跑）

| # | 核对项 | 手段 |
|---|--------|------|
| 1 | 签名与骨架一致 | 读目标文件比对 / 编译 |
| 2 | 能力注释承诺落实（含 `NEGATIVE` 分支） | 人工核对代码路径 |
| 3 | `git diff --stat` 只含声明的文件 | bash |
| 4 | 编译/构建通过 | 项目构建命令 |
| 5 | 冒烟：最小可执行路径跑通（不写正式用例） | bash |
| 6 | 未新增依赖、未扩大公开 API | 读 diff |

**红线**：子代理的"已完成"自述**不作为验收依据**；任一项不过 → `rejected` + 记录证据 → 重派（受 `max_attempts` 限制）。

### 4.3 失败分档

| 档位 | 情形 | 处置 |
|------|------|------|
| 简报不足 | 子代理指出信息缺失/歧义 | 补简报重派（不计入 attempts） |
| 实现错误 | 验收 1-6 中任一项不过 | `rejected` 带证据 → 重派；超 `max_attempts` → 主代理接手 |
| 超时 | 超过 `timeout_seconds` 无产出 | `rejected`（原因 timeout）→ 缩小简报或拆任务后重派 |
| 设计缺口 | 骨架阶段或实现中发现文档矛盾/缺失 | **停止** → `blocked` → 记录 CodeNotes → 升级用户裁决（不擅自改 ProjectSpec） |

---

## 5. 三层边界（修正 P2-22 的纪律张力）

新设计下必须写清的边界，否则纪律自相矛盾：

| 对象 | 读写方式 | 说明 |
|------|---------|------|
| `ProjectSpec/` | **只读，经 CLI**（`doc structure` / `doc read`）；禁止任何写 | 设计问题只记录，修改留给循环外评审（核心纪律 1 不变） |
| `DevSpec/`（plan.md / tasks.json / code-notes.md / reports） | **经 CLI**（`dev *`） | CLI 异常时允许"只读直读 tasks.json"的降级，且必须记 CodeNotes |
| **源码与测试代码** | **直接读写**（文件工具 / bash） | 子代理与主代理都要写代码；CLI 不介入。**骨架 stub 的写入、方法实现、测试代码均属此类** |
| git | 一律 `bash`，仅主代理执行 | 子代理禁止 git（见简报【禁止】项） |

---

## 6. 保留 / 删除 / 降级

| 现状功能 | 处置 |
|---------|------|
| ProjectSpec 只读纪律 | **保留**（不可协商） |
| 代码考古 + 代码风格快照 | **保留并前移**：骨架阶段就要遵守（§2.5 修好后才有意义） |
| 分支隔离 `dev-loop/<sid>` | **保留**；feature 级循环 = 每功能一分支，合并仍人工；技能需说明"分支数会变多" |
| 任务超时/重试 | **保留但改为真实字段**（`timeout_seconds`/`max_attempts`/`attempts`），状态用 `rejected`（不再虚构 `timed_out` 状态） |
| 虚构的 `continue <task_id>` / `skip <task_id>` 命令 | **删除**（现实中不存在，改用 `dev task update` 状态迁移） |
| 偏差三分类（轻/中/重）+ CodeNotes | **保留**，并入失败分档的"设计缺口"档 |
| Phase 3 验收测试 + 回归 | **保留**（功能级闸门，挂在 `dev align` 前） |
| Phase 4 模块集成（G3） | **降级为模块专项**（附录 C），日常 feature 循环只校验本功能涉及的 contracts 子集 |
| CodeNotes / 功能报告 | **保留**（D8） |

---

## 7. 实施顺序与验收

1. **CLI 先行**：C1–C7（状态机、字段、严格校验、§2.5、渲染列、status 输出、phase）——技能改写依赖这些真实能力
2. **技能重写**：`skills/spec-dev-loop/SKILL.md`（新五阶段 + 附录 A/B/C）
3. **测试**：
   - 扩展 `tests/test_dev_loop.py`：新状态机迁移（含非法迁移拒绝）、未知键报错、`implemented_in` 持久化、§2.5 可 update、status 阶段输出
   - 新增技能文本契约测试（同 `test_session_flow.py` 的做法）：断言技能声明了骨架阶段、`submitted→accepted` 分离、子代理简报"必须主代理亲跑验收"、三层边界
   - `tests/check_skill_sync.py` 已有的命令存在性检查自动覆盖新的命令引用
4. **端到端走查**（临时项目）：建 module+feature 文档 → `dev plan create --scope feature` → 骨架 tasks.json（含 implemented_in）→ 状态机全流程 `pending→…→done`（用脚本模拟子代理产出，主代理验收 gate 由状态迁移强制）→ `dev align` → close/archive
   > 注：真正的 LLM 子代理派发无法在自动化测试里复现，测试覆盖的是**状态机 + 简报组装 + 验收 gate**；子代理行为本身靠技能的简报模板与红线约束。

**验收标准**：pytest 全绿；两个检具通过；走查覆盖 8 状态全部迁移与 4 类失败分档至少各 1 例。

---

## 8. 风险与缓解

| # | 风险 | 缓解 |
|---|------|------|
| R1 | 子代理"假完成" | §4.2 红线：不采信自述，主代理亲跑；`accepted` 只由主代理置位 |
| R2 | 子代理调用与验收成本高 | D2：允许显式合并内聚方法；简报复用骨架信息，降低每轮准备成本 |
| R3 | 设计缺口在骨架阶段暴露（概率上升） | `blocked` 状态 + CodeNotes + 用户裁决；**这是特性不是缺陷**（越早越便宜） |
| R4 | 测试后置导致偏差晚发现 | D4 分层：方法级验收含编译与冒烟，功能级 GWT 后置 |
| R5 | feature 循环无法闭合模块 G3 | 附录 C 模块专项；feature 循环内只校验本功能涉及的契约子集 |
| R6 | 子代理扩大改动面 | 简报写死文件与符号范围；验收第 3 项核对 `git diff --stat` |
| R7 | 8 状态增加认知负担 | `dev status` 输出阶段与计数；技能用一张状态图讲清 |

---

## 附录 A：子代理简报模板

见 §4.1（技能中以"可直接复制的模板"形式提供）。

## 附录 B：验收清单

见 §4.2（技能中作为 Phase 3 的强制步骤，六项逐项打勾）。

## 附录 C：模块专项（降级后的 module scope）

日常开发不走 module scope。仅以下情形开模块专项 run：
- **契约闭合（G3）**：`module-manifest` import↔export 配对 + `inter-module-contracts` 字段级校验；
- **跨功能重构**：影响同一模块多个 feature 的结构性调整；
- **集成验证**：多个 feature 已 aligned 后的模块级回归。

模块专项沿用同一套状态机，但任务粒度以"契约项/重构项"为单位，且 Phase 2 骨架化改为"模块级接口骨架"。

---

## 9. 实施记录（已完成）

### 9.1 落地清单

| 文件 | 改动 |
|------|------|
| `skills/scripts/cli.py` | 状态机换新（8 状态）；`TASK_ALLOWED_KEYS` 增 9 个骨架/派发字段；`_clean_task` **未知键报错** + `implemented_in.path` 必填 + 派发参数默认值；`PLAN_SKELETON` 增 `## 2.5 代码风格快照`、§3 改名「骨架与任务清单」；`_render_task_table` 增「方法（类）/ 实现文件」列；`dev status` 增 `phase`（派生）+ 状态分布 + 分支/方法/文件表；`_dev_phase` / `_dev_next_step_suggestions` 按阶段给下一步；CLI 提示语同步新状态名 |
| `skills/spec-dev-loop/SKILL.md` | 386 → 466 行：改为五阶段（读设计 → 骨架化 → 委托实现与验收 → 测试 → 收尾）；三层边界表；附录 A 简报模板 / B 验收清单 / C 模块专项 / D 签名变更协议 / E 右尺寸规则 / F 横切出口 |
| `tests/test_dev_loop.py` | 任务卡示例补骨架字段；状态链换新；新增 `rejected` 重派、`blocked` 裁决、`submitted` 不得跳 `done`、测试闸门在验收之后、未知字段拒绝、`implemented_in` 必填与持久化、派发参数默认值、§2.5 可写、phase 派生等用例 |
| `tests/test_dev_loop_skill.py` | 新增 20 项技能文本契约测试（骨架先行 / 验收闸门 / 测试分层 / 派发单元 / 三层边界 / D9-D12 存在性；并校验技能里的状态值与任务卡字段与 CLI 完全一致——防文本漂移）|

### 9.2 验收结果

| 验收项 | 结果 |
|--------|------|
| `python -m pytest tests/` | **217 passed**（本模块前 197 → 新增 20 项技能契约测试） |
| 端到端走查（`/tmp/dkdevloop`，feature 级全流程） | **30/30 通过**：建文档 → `dev plan create`（phase=design）→ §2.5 可写（旧版必失败）→ 骨架 stub + `dev task set`（落点/派发参数落库、未知字段被拒）→ 派发实现 → **一次 `rejected` 重派** → 六项机械验收 → `accepted` → 真实 GWT 测试 3 passed → `tested → done` → `align` → CodeNotes → 报告 → close/archive → **ProjectSpec 全程字节级未变** |
| `python tests/check_skill_sync.py` | 通过（技能名一致性 + 命令存在性） |
| `python tests/check_doc_consistency.py` | 通过 |

### 9.3 走查中发现并修正的两个问题

1. **验收第 2 项会被 DevSpec 自身污染**：`git diff --stat` 把 CLI 改写的 `tasks.json` / `plan.md` / `code-notes.md` 也算作"多余改动"，导致"只改了声明的文件"误判。已在技能附录 B 明确要求按源码路径过滤并排除 `DevSpec/`、`SessionSpec/`（走查中先复现失败、修正后通过）。
2. **CLI 提示语残留旧状态名**：`dev task set` 成功后仍提示"--status in-progress"，状态迁移报错信息与 `--status` 帮助文本也是旧状态集。已全部同步（`grep` 全仓确认无残留）。

### 9.4 未做 / 留待

- `dev status` 的阶段为**派生值**（由 tasks.json 计算，不落库）——比原计划 C7「dev-spec.json 增 phase 字段」更稳（避免与任务状态漂移），故未新增字段。
- 子代理的 LLM 行为本身无法自动化验证；走查覆盖的是**状态机闸门 + 简报组装所需数据 + 验收判据**，子代理纪律由技能附录 A/B 的红线约束。
- 模块专项（附录 C）与右侧横切出口（附录 F）只写了流程，未做端到端走查（属低频路径）。

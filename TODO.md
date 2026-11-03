# doc-kit 需求：`doc read` 路径解析缺陷修复 + 决议落盘归属的三层防护

**适用版本**：R1 已随工具链 `2026.11.1` 发布；R2 目标版本 `2026.11.2`（`.doc-kit/cli/`，CLI 单文件 + `docmodel.py` / `spec_schema.py` 等模块）
**提出背景**：memctx 项目在 2026-11-02 的 `spec-doc-repair` 议题中，因 R1 缺陷对文档内容做出过错误判断，并发现 R2 缺失导致上一议题 24 条决议中有 6 处从未写入 `ProjectSpec` 却仍被报告为"已落盘"。

---

## R1（P0，缺陷，✅ 已完成于 `2026.11.1`）：`doc read` 省略 `ProjectSpec/` 前缀或缺 `.md` 后缀时，静默解析到另一篇文档

### 1.1 现象与复现

在 memctx 项目根执行（当前有 `module-behavior-log`、`module-context`、`module-memory` 三篇同名 `architecture.md`）：

| 输入 | 实际解析结果 | 期望 |
|---|---|---|
| `doc read module-context/architecture` | `ProjectSpec/module-behavior-log/architecture.md` | `module-context/architecture.md` |
| `doc read ProjectSpec/module-context/architecture` | `ProjectSpec/module-behavior-log/architecture.md` | 同上 |
| `doc read module-behavior-log/features/store-schema/feature-design` | `.../features/filter-chain/feature-design.md` | `.../features/store-schema/feature-design.md` |
| `doc read architecture` | `ProjectSpec/module-behavior-log/architecture.md` | 报歧义错误（有 3 个同名候选） |
| `doc read module-context/architecture.md` | ✅ 正确 | — |
| `doc read ProjectSpec/module-context/architecture.md` | ✅ 正确 | — |
| `doc read features/store-schema/feature-design.md` | ✅ 正确 | — |

关键点：**没有任何告警或错误**，返回 `success: true`，`data.path` 里才是真实路径。用户若不逐个核对 `data.path`，会读到另一模块的内容并据以做判断。

### 1.2 根因

`.doc-kit/cli/docmodel.py:25-52` 的 `_find_doc()` 采用三段式回退：

1. `safe_join(docs_root, search_path)` —— 精确路径存在性检查。`module-context/architecture` 没有 `.md`，此步必然失败。
2. `docs_root.rglob(search_path)` —— 用同一不含 `.md` 的片段做 glob，同样必然失败。
3. `Path(search_path).name` / `.stem` 兜底 —— 只取**文件名**，丢弃全部目录信息，返回排序后的**第一个**同名文件。

两个结构性缺陷：

- **缺 `.md` 探针**：第 1、2 步都没有尝试 `search_path + ".md"`，于是合法的「省略后缀」写法必然掉进第 3 步。
- **第 3 步的兜底语义错误**：目录信息被丢弃、多候选时静默取第一个，把「找不到」和「找到多个」都伪装成「找到了」。`store-schema` → `filter-chain` 就是按字母序取首个的产物。

### 1.3 影响面

- 只影响读路径。`doc update-section` / `doc add-section` / `doc remove-section`（`cli.py:646`/`691`/`890`）不使用 `_find_doc`，走 `safe_join` 精确路径，缺文件即报错——**不会写错文件**，这点已确认，不必改动其行为。
- 真实发生过的事故：把三篇 `architecture.md` 判为「整份复制」，据此设计了 4 项不存在的议程，后被用户指出才纠正。
- 对 AI 调用方尤其危险：AI 通常只消费 `sections` 与 `content`，不校验 `data.path`。

### 1.4 需求

**R1-a（必须）**：解析顺序改为

1. 精确路径命中；
2. 若未带后缀，`search_path + ".md"` 命中（这是本次的核心修复）；
3. 路径后缀匹配：`ProjectSpec/**/` 下以 `search_path` 结尾的唯一文件；
4. 仅当全库该 basename **唯一**时才按文件名兜底。

**R1-b（必须）**：任何一步出现**多个候选**，一律返回错误，`suggestions` 列出全部候选路径，禁止静默取首个。

| 场景 | 错误码 | 行为 |
|---|---|---|
| 多候选 | `ERROR [doc_read.ambiguous]` | 列出候选，退出码 1 |
| 无候选 | `ERROR [doc_read.not_found]` | 现有文案保留，附「是否漏了 `.md`」提示 |

**R1-c（建议）**：`doc read` 输出增加 `data.resolved_via` 字段，取值 `exact` / `suffix_added` / `path_suffix` / `basename`，让调用方能判断这次解析是否「靠猜」。`basename` 命中时在 `suggestions` 里提示改用全路径。

**R1-d（建议）**：`doc structure` 输出的路径统一带 `.md`，与 `doc read` 建议用法对齐，减少调用方写短路径的机会。

### 1.5 验收标准

1. 上表 7 个用例全部符合「期望」列。
2. 新增单测：三篇同名 `architecture.md` 场景下，`module-context/architecture` 返回 context 篇；`architecture` 返回 ambiguous 错误且列出 3 个候选。
3. 回归：`ProjectSpec/` 前缀带或不带 `.md`、feature 级嵌套路径、顶层平铺文档，四种组合均正确。
4. 无候选时错误信息包含原文输入与 `.md` 提示。

### 1.6 兼容性

`doc read architecture`（裸文件名）目前能「成功」，改为报错属**行为破坏**。建议在 toolchain 版本号递增（本次为 `2026.11.1`）中说明，并在 `TOOLCHAIN_HISTORY` 登记；`tool status` 的版本检查会让旧项目显式提示重跑 `init`。

### 1.7 落地结果（`2026.11.1`）

已实现 `docmodel.resolve_doc()`（四段解析 + 三态返回）、`data.resolved_via`、多候选 `doc_read.ambiguous`、`doc_read.is_directory` / `doc_read.invalid_path`；顺带把 `safe_join` 由字符串前缀改为路径段判定（修掉 `<root>-evil/` 同前缀逃逸）。R1-d 无需改动：`doc structure` 的 `doc_map` 键本就来自索引的相对项目根路径，天然带 `.md`。

遗留小项（不阻断）：`doc read 'xxx.md#段落'` 现在报 `doc_read.not_found`（不再静默读错档），但文案只提示"是否漏了 `.md`"，宜补一句「`doc read` 只收文档路径，段落引用交给 `update-section`」。

---

## R2（P1，目标版本 `2026.11.2`）：决议的「可恢复性」+ 落盘归属的三层防护

### 2.0 问题定性（讨论后修订）

原 R2 把问题当成「关闭时缺一道门禁」。修订后的定性是：**根因是结构决策缺失 + 决议不可恢复**，不是 agent 主动选择漏记。

- **证据**：关闭提交 `5ab33a8` 之前，`module-behavior-log/` 下根本没有 `features/` 目录（只有 architecture / domain-model / integration / module-manifest）；本次缺的 6 处**全部**属于「应由一份 `feature_design` 承载」的内容。修复议题 spec 的决议 5 还记着：上次议题引用的「13 项功能清单」在 SessionSpec 全部历史与 ProjectSpec 中均不存在——指代式记录让信息在归档时就已丢失。
- **推论**：agent 不是判断后决定漏记，而是手上没有可落的结构，于是把细节压扁进既有段落或干脆没写。所以修的是「结构决策先行」与「决议自含」，而不是加一道更严的检查。
- **能力边界**：任何检查（CLI 确定性比对 / 语义抽查）都只能**防漏记**，不能**防错记**。本需求只承诺前者。
- **不采用**：用 `related_doc_types` 做文档类型齐备性硬检查。ProjectSpec 是从项目 → 模块 → 功能逐层完善的设计结构，不是固定骨架；类型齐备不构成完整性判据（早期项目没有 feature 文档是正常的），硬查会制造假阳性，还会诱导 agent 为过关去造空文档。

### 2.1 三层防护总览

| 层 | 时机 | 机制 | 落点 |
|---|---|---|---|
| L1 议题细分 + 决议自含 | `spec-start` / `spec-pause` | 1 条技能规则 + 1 句 schema 描述 | `skills/spec-start`、`spec_schema.py` |
| L2 结构决策 → 冻结 → 落盘 → 差集对照 | `spec-close` Step 3–4 | `targets[]` + `spec write` + `spec coverage --verify` | `skills/spec-close`、`cli.py` |
| L3 无法定位 → 人工介入 | `spec-close` Step 3 | 审核表必含「层级 / 建议新建 / 暂不承载 + 理由」列 | `skills/spec-close` |

三层是递进而非冗余：L1 减少决议数量、提高单条可恢复性；L2 固定「先想清楚再动手」的顺序并留下可机器比对的记录；L3 把做不到的情况显式交人。

### 2.2 L1：议题细分 + 决议自含

**规则 1（技能，1 段，零代码）**：`spec-start` 增加议题细分原则——一个议题只回答一个问题；用户命题覆盖多个可独立成议的决策时，主动拆出子议题，超出本议题范围的写入 `next_steps` 并说明「需另开议题」。

**规则 2（schema 描述，零技能文本）**：把 `detail` 的 description 改为自含性要求——被引用的清单、约束编号、条文必须原样写进 `detail`，禁止「上述清单第 N 项」「见前一议题」「同上」这类指代，因为议题归档后指代目标即失效；自含的决议即使当时漏记，后续任何 agent 只读 `SessionSpec` + `ProjectSpec` 就能判定缺没缺并补上。

为什么放这里：`spec schema` 是字段约束的唯一来源，且 [spec-start/SKILL.md](skills/spec-start/SKILL.md:114)（"了解 SpecStruct 的字段定义…为组装初始数据做准备"）、第 161 行（"按 `spec schema` 输出的结构组装"）与 [spec-pause/SKILL.md](skills/spec-pause/SKILL.md:140) 都已要求 agent 主动读取——改动正好落在 agent 写下决议的那一刻，技能文本零增量。

**本版不做**：CLI 侧的正则校验（`上述|见前|同上|第 N 项`）。理由：会误伤「见 C-606」「见 §5」这类合法引用，且新增一条会被 agent 感知的拒绝路径。观察下 1–2 个真实议题，若仍出现指代型决议再升级为 warning。

### 2.3 L2 数据模型：`resolutions[].targets[]`

| 字段 | 类型 | 说明 |
|---|---|---|
| `doc` | string | 目标文档，`ProjectSpec/` 相对路径，必须带 `.md`；落盘前用 `safe_join` 校验 |
| `section` | string | 段落 reference 后缀，形如 `架构设计#组件划分`（与 `doc read` 返回的 reference 同源）；`action=doc_new` 时可为空 |
| `action` | enum | `doc_new` / `doc_update_section` / `doc_add_section` / `doc_skip` |
| `reason` | string | `action=doc_skip` 时必填（≥10 字），写明为何不落文档及建议的层级 |

- 一条决议可有 **N 个** targets（1:N），如「跨模块原则要求写三处」就是 3 条 target。
- `required=False`（旧 spec 容错），业务校验只在 `status=closed` 时执行。
- `section` 用 reference 而非裸标题：同名标题在不同父章节下 reference 不同，裸标题会复现 R1 的歧义问题。

### 2.4 L2 冻结与覆盖报告

1. **冻结**：`spec-close` Step 3 用户审核通过后，立即 `spec write` 落 `targets`（`status` 仍为 `active`），再进 Step 4。这样 `--verify` 对照的是「批准过的清单」，而不是事后按检查结果倒填的清单。
2. **差集**：Step 4 末尾（`doc reindex` 之后）执行 `spec coverage --verify`；差集非空即**阻断关闭**，把 `missing` / `empty` / `ambiguous` 原样展示。
3. **快照**：Step 6 的 `status=closed` 写入时，由 **CLI 按磁盘自行重算** `coverage` 并覆写，**忽略调用方传值**——快照是用来审计「已落盘」声明的，不能由被审计方自填。
4. `coverage` 字段（仅 CLI 写，agent 不手写）：`{verified_at, ok, missing, empty, ambiguous, rows[]}`。
5. **已知边界**：无法用密码学证明 targets 未在写完后被改写。本需求只防漏记，故不为此增加机制（改写 targets 属于「错记」，见 2.0 能力边界）。

### 2.5 L2 新命令 `spec coverage`

```
spec coverage [--verify] [--id <sid>]
```

- 默认作用于当前活跃议题；`--id` 在 `SessionSpec/active/` 与 `SessionSpec/archive/` 中查找（支持归档回放）。
- 不设 `--json`：输出本身就是 CLI 统一信封，`data.rows[]` 已是机器可读形态（与 `spec status/read/schema` 的"纯文本例外"无关，故无需额外开关）。
- 输出遵循 CLI 统一信封（`success` / `message` / `data` / `suggestions`）：人读表格渲染在 `message`，`data.rows[]` 供技能与 CI 消费。
- 判定规则：

| 情形 | 状态 |
|---|---|
| `doc` 不存在 | `missing` |
| `action=doc_update_section/add_section` 且该 reference 不存在 | `missing` |
| 同名 reference 命中多处 | `ambiguous`（按 R1 规矩，禁止取首个） |
| `action=doc_new` 且文件存在 | `ok` |
| `action=doc_skip` | `skipped` |
| 正文为空 | `empty`，但「自身正文为空且后代段落有正文」**不算** empty（父章节常见） |
| 正文命中模板占位 | `empty`（复用 `doc lint` R7 的 `_placeholder_patterns`） |

- 退出码：全部 `ok`/`skipped` → 0；存在 `missing`/`empty`/`ambiguous` → 1；旧 spec 无 `targets` → warning，**退出码 0**（否则 CI 无法区分「数据缺失」与「落地缺失」）。

### 2.6 L2 `spec write` 的两处护栏

- `status=closed` 时校验每条的 targets：非空、`doc_skip` 必带 `reason`、`doc` 合法相对路径。不满足 → `ERROR [spec.targets_missing]`，**指名** `resolutions[i].topic`，退出码 1。
- 归档 id 回写拒绝：`ERROR [spec.archived_id]`。现状实测：用归档 id 执行 `spec write` 会 `success: true` 并在 `active/` **静默生成一份重复副本**（archive 保留原件），与旧 R2「回写旧 spec」的迁移设想正面冲突。

### 2.7 前置修复：schema 引擎的二级嵌套

`targets[]` 要能用，必须先补 3 处（均已实测确认是缺口）：

| 函数 | 现状 | 后果 |
|---|---|---|
| `get_schema_metadata()` | 只渲染一层，`targets` 只剩 `{"type":"list"}` | `spec schema` 不显示 `doc/section/action/reason`，agent 只能猜字段名 |
| `validate()` | 不递归，`action:"bogus"`、非 dict 元素、错拼字段全部放行 | 校验形同不存在 |
| `unknown_keys()` | 只递归一层 | `targets` 内的拼写错误不会被拦，静默写盘 |

### 2.8 L3：审核表的第三列

`spec-close` Step 3 的变更清单表保持「一行一条决议」，并明确：找不到承载位置时必须显式写「应有层级 + 建议新建 / 暂不承载 + 理由」，交用户裁定——不允许静默省略该行。人工审阅的对象是**这张由决议驱动的表**（行数恒等于决议数），而非由文档驱动的表（缺行在后者中不可见）。

### 2.9 状态可见性（替代原 R2-e）

原 R2-e（`doc lint` 新增 `R8-resolution-coverage`）**不采用**：`R8` 编号已被「depends_on 版本与目标一致」占用（`_RULE_LEVELS`，下一个可用是 R13），且让 `doc lint` 读 SessionSpec 会把纯文档门禁变成跨存储门禁（CI 无 `SessionSpec/` 时行为不明）。

替代方案（1 行改动，零新规则）：`spec status` 在有活跃议题时追加一行「M 条决议中 N 条尚无归属文档」，把缺口在讨论期就暴露。

### 2.10 实施顺序（同一版本内）

1. `spec_schema.py`：`targets` / `coverage` 字段定义 + 二级嵌套渲染与递归校验 + `detail` 描述改写 → 单测
2. `cli.py`：`spec write` 两处护栏 + `spec coverage`（含 `--id` 回放）+ `spec status` 提示 → 单测
3. `skills/spec-start` + `skills/spec-pause`：议题细分与自含规则（各 1 段）
4. `skills/spec-close`：Step 3 表格与冻结、Step 4 尾 `--verify`、Step 6 快照
5. `skills/guidance/doc-capabilities/_index.md`：`targets` 与 `coverage` 的说明
6. 版本 `2026.11.2`：`TOOLCHAIN_VERSION`、`TOOLCHAIN_HISTORY`、8 份 SKILL.md 前言、`toolchain-fingerprint.json`

### 2.11 验收标准

1. `spec coverage --id 20261102-log-capture-design`（归档回放）：无 `targets` 时给 warning、退出码 0、不崩溃。
2. 给该 spec 补齐 `targets` 后回放：能标出「新文档 / 新章节」类缺口（`missing`）。**不承诺**标出「章节存在但内容未写」的部分写入类缺口（见 2.0 能力边界，写进文档验收说明）。
3. `status=closed` 且存在决议 `targets` 为空 → 拒绝受理，错误码与具体 `topic` 同时出现。
4. `doc_skip` 缺 `reason` → 拒绝受理。
5. `--verify` 四态不误报：删掉章节 → `missing`；父章节自身空但有子正文 → **不是** `empty`；正文为空 → `empty`；同名 reference 两处 → `ambiguous`。
6. 调用方传入 `coverage` → 被忽略，以磁盘重算结果为准。
7. 用归档 id 回写 → `spec.archived_id`，且 `active/` 不产生副本。
8. `spec schema` 输出包含 `targets` 内层四个字段及 `action` 的允许值。

### 2.12 明确不做（避免规则膨胀）

- 文档类型齐备性硬检查（`related_doc_types`）—— 见 2.0。
- 决议锚点（`anchor`）检索 —— 用于抓部分写入，等该类缺口真实复发再做。
- `doc lint` 新规则 —— R13 号段留白。
- 承诺「防错记」—— 本需求只降低漏记概率，并让漏记可见、可补。
- `spec-close` 改由 subagent 落盘 —— 见 2.13。

### 2.13 观察项（下一轮再定）

- **subagent 写文档 / 主 agent 验收**：由于验收形态已改为「冻结表 vs 实际改动」的差集（差集由工具生成，非 agent 自述），多 agent 编排不改变正确性，只影响上下文开销与并行度，故本版不加。若单议题文档数偏多（如 >8 篇）或出现上下文溢出，再考虑。
- 决议自含的 CLI warning 化。
- `doc read` 收到 `#` 段落引用时的定向提示（R1 遗留小项）。

### 2.14 兼容与迁移

- 旧归档 spec 无 `targets`：`coverage` 容错为 warning；`spec write` 仅在 `status=closed` 时做业务校验（schema 用 `required=False`）。
- 归档 spec 只读：取消旧 R2 的「回写旧 spec」设想，改为 `spec coverage --id` 只读回放。
- 递增 `TOOLCHAIN_VERSION` 至 `2026.11.2` 并在 `TOOLCHAIN_HISTORY` 登记；`tool status` 会让旧项目显式提示重跑 `init`，避免新版技能配旧版 CLI 时字段被静默丢弃。

### 2.15 落地结果（`2026.11.2`）

已按 2.10 的顺序全部实现：

| 落点 | 内容 |
|---|---|
| `spec_schema.py` | 新增 `RESOLUTION_TARGET_ACTIONS` / `RESOLUTION_TARGET_SCHEMA`、`resolutions[].targets[]`、顶层 `coverage`；`validate` / `unknown_keys` / `get_schema_metadata` 支持二级嵌套；`detail` 描述改为自含性要求 |
| `cli.py` | `_validate_resolution_targets`（关闭门禁）、`_coverage_rows` / `_check_target` / `_coverage_snapshot`、`cmd_spec_coverage`、`spec.archived_id` 护栏、`spec status` 归属缺口提示 |
| 技能 | `spec-start` 细分原则 + 决议自含、`spec-pause` 自含提醒、`spec-close` Step 3 分层表与冻结 / Step 4 尾 `--verify` / Step 6 关闭快照 |
| 能力库 | `_index.md` §4.2 补 `spec coverage` 说明 |
| 版本 | `2026.11.2` + HISTORY 条目 + 8 份前言 + 指纹（59 文件） |

实现细节与计划的差异（均朝更小实现收敛）：

- `spec coverage` 不提供 `--json`（输出本就是统一信封，见 2.5）。
- `section` 接受三种写法：`组件划分`、`架构设计#组件划分`、`ProjectSpec/x.md#架构设计#组件划分`；裸标题命中多处判 `ambiguous`。
- `coverage` 快照结构为 `{verified_at, counts{ok,missing,…}, rows[{topic,doc,section,action,status}]}`；关闭时 CLI 重算并覆写，调用方传值丢弃。
- `spec write` 的关闭门禁**不阻断**已存在的 `missing`（文档事后被删是合法状态），只把缺口写进快照并在回执里明示——阻断发生在 `spec coverage --verify`（Step 4 尾）。

验证（本机）：

- 全量测试 `444 passed`；`check_doc_consistency` 原先因指南文件改名（`wiki.md`）而报错，已同步修正 `GUIDE` 常量。
- 归档回放：`spec coverage --id 20261102-log-capture-design --verify` 对 memctx 的 24 条旧决议给出 `untargeted 24` + warning，**退出码 0**，不崩溃（验收 2.11-1）。
- 行为破坏已登记：`status=closed` 缺 `targets` 现在被拒（`spec.targets_missing`），`tests/test_e2e_session.py` 的关闭用例已相应补上 `targets` 并断言快照。

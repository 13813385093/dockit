# doc-kit 需求：`doc read` 路径解析缺陷修复 + `spec-close` 决议覆盖门禁

**适用版本**：工具链 `2026.10.5`（`.doc-kit/cli/`，CLI 单文件 + `docmodel.py` 等模块）
**提出背景**：memctx 项目在 2026-11-02 的 `spec-doc-repair` 议题中，因 R1 缺陷对文档内容做出过错误判断，并发现 R2 缺失导致上一议题 24 条决议中有 6 处从未写入 `ProjectSpec` 却仍被报告为"已落盘"。

---

## R1（P0，缺陷）：`doc read` 省略 `ProjectSpec/` 前缀或缺 `.md` 后缀时，静默解析到另一篇文档

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

---

## R2（P1，新需求）：`spec-close` 强制输出并校验「决议 → 文档章节」覆盖表

### 2.1 问题与证据

`20261102-log-capture-design` 议题关闭时，`closed_reason` 写的是「24 条决议写入 ProjectSpec」。实际勘验结果：

- 关闭提交 `5ab33a8` 只改动了 7 份文档，**未创建任何 feature 设计文档**；
- 24 条决议中 6 处没有归宿：索引与迁移边界、Filter 接口签名、Filter 链配置化、跨模块原则的指定归宿（要求写三处，实落两处）、四条验收口径、restore 恢复步骤；
- 同一提交里 `触发器`、`synchronous` 零命中，`user_version` 仅出现在 backup 说明中。

即：**决议被标记为 resolved、议题被标记为 closed，但没有对应的文档变更**，且没有任何机制能发现这件事。当前 `doc lint` 只校验文档结构（占位符、编号写法等），不校验「决议是否落地」。

### 2.2 需求

**R2-a（数据模型）**：`resolutions[]` 增加必填数组 `targets[]`，每项：

| 字段 | 类型 | 说明 |
|---|---|---|
| `doc` | string | 目标文档路径（`ProjectSpec/` 相对路径，须带 `.md`） |
| `section` | string | 目标章节标题；`action=new_doc` 时可为空 |
| `action` | enum | `new_doc` / `update_section` / `add_section` / `none_doc` |
| `reason` | string | `action=none_doc` 时必填（≥10 字），说明为何不落文档 |

**R2-b（写入校验）**：`spec write` 在 `status` 为 `closed` 时校验：

- 每条 `resolutions[].targets` 非空；
- `action=none_doc` 必须带 `reason`；
- `doc` 必须是合法相对路径（沿用 `safe_join`）。

不满足即 `ERROR [spec.targets_missing]`，退出码 1，拒绝关闭。`active` 状态下 targets 可选（讨论中期允许未定）。

**R2-c（新命令）**：`spec coverage [--json] [--verify]`

- 默认输出一张表：

```
决议 topic | 目标文档 | 章节 | 动作 | 写入状态
```

- `--verify` 额外核对磁盘：`update_section` / `add_section` 的 `section` 是否真实存在于该文档（复用现有段落解析）；`new_doc` 的文件是否存在；逐项标记 `ok` / `missing` / `empty`（章节存在但正文为空）。
- 退出码：全部 `ok` 为 0；存在 `missing` / `empty` 为 1。
- `--json` 供技能与 CI 消费。

**R2-d（流程强制）**：`spec-close` 技能中把该表设为**必经步骤**：

1. Step 3 梳理变更清单时，表格必须包含全部决议且无空行；
2. Step 4 写入后、Step 5 `doc lint` 前，新增一步：执行 `spec coverage --verify`，非零退出即**阻断关闭**，把 `missing` 项原样展示；
3. Step 6 写终态时，把 verify 结果快照（时间戳 + 每项状态）写入 spec 的 `coverage` 字段，随归档长期保留，供事后审计「当初声明落地的，是否真的落地」。

**R2-e（建议）**：`doc lint` 增加规则 `R8-resolution-coverage`：若存在活跃议题且其 `resolutions` 中有未带 targets 的条目，给 warning（不阻断讨论期，但让缺口可见）。

### 2.3 验收标准

1. 用 `SessionSpec/archive/20261102-log-capture-design.spec.json` 做回放：老 spec 无 `targets` 字段时，`coverage` 给出 warning 而非崩溃（兼容旧数据），并在补齐 targets 后能精确标出上述 6 处 `missing`。
2. `spec write` 在 `status=closed` 且存在空 targets 时拒绝受理，错误信息指名是哪条决议。
3. `coverage --verify` 对「章节被删除」「章节存在但正文为模板占位」「文档根本不存在」三种情况分别给出 `missing` / `empty` / `missing`，不误报 `ok`。
4. `action=none_doc` 缺 `reason` 时写入被拒绝。

### 2.4 兼容与迁移

- 旧归档 spec 无 `targets`：`coverage` 容错为 warning；`spec write --json` 回写旧 spec 时不得因缺字段报错（schema 用 `required=False`，仅在 `status=closed` 时做业务校验）。
- 新字段需同步 `.doc-kit/skills/guidance/doc-capabilities/` 中相关说明与 `spec schema` 输出；按既有约定递增 `TOOLCHAIN_VERSION`，避免新版技能配旧版 CLI 时字段被静默丢弃（该风险已在 `TOOLCHAIN_HISTORY` 注释中说明）。


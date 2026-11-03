---
name: spec-code-smell
description: 当开发完成、提交 PR 前想检查代码形态（重复、参数过多、过度设计、命名含糊等）时使用：按显式 git 范围扫描代码异味，先打印源文件范围摘要，再按快速/深入模式给出带证据与误报理由的候选，由用户挑选深入。不适用于纯设计讨论、需要精确重构方案、或没有可比 diff 的场景。
---

# 最高优先级：

**三层边界（先看清各自走哪条路）**：

| 对象 | 读写方式 |
|------|---------|
| `ProjectSpec/`（设计文档） | **经 CLI**：`doc structure` / `doc read` 只读；本技能**不写** ProjectSpec |
| **源码、diff、工作区文件** | **只读**（`bash` / 文件工具）；本技能只给方向，不自动改代码、不写报告 |
| git 仓库操作 | **一律用 `bash`**（CLI 不执行 git）：`git status` / `git diff` / `git log` / `git rev-parse` |

**例外（能力库，仅读）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/`，包含 `doc-capabilities/` 与 `smell-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接读取，禁止写入**——按 `smell-capabilities/_index.md` 加载规则与源文件发现口径。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`；且当前目录必须是 git 仓库。任一不满足即输出终止文案——未初始化时给出「请人工执行 `doc-kit init <项目根>`，再执行 `doc-kit install-skills <agent 技能目录>`」——不再执行后续步骤。**初始化由人工完成，不要尝试任何自举安装。**

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `2026.11.2` 生成。先运行 `python .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `2026.11.2`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py tool status
python .doc-kit/cli/cli.py doc structure
python .doc-kit/cli/cli.py doc read <path>
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 四个字段；退出码 0 = 成功、1 = 业务拒绝或运行时错误、**2 = 参数错误**（未知选项 / 缺必填参数，按提示修正后重试）。
>
> 错误文本**没有统一格式**：较新的错误写作 `ERROR [<错误码>] <原因>。修复：<建议>`，但多数历史错误是散文形式（如「未找到文档: <path>，可用 doc structure 查看所有文档路径」）。**不要用正则解析错误文本**——错误原文同时出现在 `message` 与 `suggestions[0]`，按语义阅读后行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一至两行中文状态描述（**有活跃开发循环时会额外给出一行提示**），`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-code-smell — 代码异味检查

## 定位

独立的任务式技能，只做**代码形态**审查，不替代 `spec-code-review` 的文档一致性复核，也不做全量历史代码审计。

**适用**：开发完成、提交 PR 前；code review 之后想补一轮代码形态检查；重构前想知道哪些地方值得先动。

**不适用**：纯设计讨论；需要精确重构方案（本技能只给方向）；没有可比 diff；未由 doc-kit 初始化的项目。

---

## 模式

| 模式 | 何时用 | 加载的能力 |
|---|---|---|
| **快速（默认）** | 日常 feature/PR diff | Duplicated Code、Long Parameter List、Speculative Generality、Message Chains |
| **深入（按需）** | 用户说“深入检查/代码形态/重构前”；或本次是 bugfix/重构且用户同意 | 快速 4 项 + Mysterious Name、Primitive Obsession（含集合/布尔形态）、Data Clumps、Shotgun Surgery |

- 默认快速；不要在用户没要求时自动跑深入模式。
- 深入模式输出可以更多，但仍受“最多 10 条”限制。
- 能力文件按需加载：先读 `_index.md`，命中候选后才读对应 `<name>.md`；不要一次读入全部。

---

## 流程总览

```
Phase 0  前置条件 + 工具链自检
Phase 1  解析并校验显式范围（不读不写 review 锚点）
Phase 2  按文件分类识别源码 + 打印范围摘要 + 上限检查
Phase 3  加载模式能力 + 读取已知例外
Phase 4  扫描并输出候选（证据/置信度/影响/误报理由）
Phase 5  用户选 1–3 条深入；结束（不写文件）
```

---

## Phase 0：前置条件

先确认：

```bash
git --version >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1
test -f .doc-kit/cli/cli.py && echo DOC_KIT_OK
```

任一不满足，按前言的前置条件文案终止，不进入后续步骤。

然后运行 `python .doc-kit/cli/cli.py tool status`；版本/副本不一致时按前言暂停，不带着错配继续。

---

## Phase 1：范围

### 1-1 解析

接受：

- `/spec-code-smell <from>..<to>`
- `/spec-code-smell <from>...<to>`
- 自然语言：“从 v1.0 到 HEAD”“看最近 3 个提交”

**不读、不写 `review` 锚点**。范围是显式参数；用户没给起点时先问，不默认猜。

### 1-2 校验

```bash
git cat-file -e <from>^{commit}
git cat-file -e <to>^{commit}
git rev-parse --is-shallow-repository
git diff --quiet <from>..<to>; echo $?   # 1 = 有变更，0 = 空
```

- ref 无效 → 说明原因，请用户给新范围；不要继续用无效 ref。
- 浅克隆且范围不可达 → 请用户指定可用范围，或征得同意后 `git fetch --deepen`。
- 空 diff → 输出“该范围无变更”，询问换范围或结束；不要产出空报告。

---

## Phase 2：源文件发现与范围摘要

**源码不是“在 `src/` 里的文件”，而是“扩展名是源码、且不在排除目录里的文件”。**

完整规则见 `<项目根>/.doc-kit/skills/guidance/smell-capabilities/_index.md` §源文件发现；执行时必须先读它。

### 2-1 枚举变更文件

```bash
git diff --name-only --diff-filter=ACMR <from>..<to>
```

### 2-2 分类

- 按扩展名识别源码：C/C++、Python、Rust/Go/Java/Kotlin/C#、JS/TS、脚本等；
- 默认排除：tests、docs/DevSpec/ProjectSpec/ReviewSpec/SessionSpec、vendor/third_party/3rd、build/dist/out/target、generated、cache、隐藏文件/目录、日志目录；
- 不按名字排除 `lib/`、`bin/`、`tools/`、`scripts/`、`utils/`、`app/`、`packages/`；这些目录里的源码扩展名文件应纳入；
- 测试默认不扫；用户说“包含 tests”才扫，并启用测试豁免（builder/夹具/刻意复制/路径常量）；
- 未知扩展名列入“未识别”，问用户是否纳入，不静默丢弃。

### 2-3 打印范围摘要（硬要求）

```text
扫描范围（按文件分类，不绑定 src/）：
  将扫描 N 个源文件：
    <目录>   <数量>
  排除：
    tests/...  <数量>（默认排除；说“包含 tests”可开启）
    docs/...   <数量>
    vendor/... <数量>
    build/...  <数量>
  未识别扩展名：
    <path>  <数量>（默认不扫；要扫请指定）
  如不符合预期，请直接指定路径或说“包含 tests / 排除 X”。
```

用户说“只扫 X”“包含 tests”“排除 Y”时，以用户指令为准。

### 2-4 上限

- 默认上限：1,200 行或 80KB 的**源码 diff**；
- 超过时：按顶层目录拆分，或先扫用户指定的子集；不要静默截断；
- 测试/文档不计入源码上限，但要在摘要里说明。

---

## Phase 3：加载能力与已知例外

### 3-1 加载能力

读 `_index.md`，按模式取能力清单：

- 快速：`duplicated-code.md`、`long-parameter-list.md`、`speculative-generality.md`、`message-chains.md`
- 深入：快速 4 项 + `mysterious-name.md`、`primitive-obsession.md`、`data-clumps.md`、`shotgun-surgery.md`

只加载当前模式需要的文件；命中候选后才读对应文件。

### 3-2 已知例外

在报出任何候选前，先查：

1. `DevSpec/archive/<sid>/code-notes.md`（设计偏差 / 重点关注区域；若存在）；
2. 最近一份 `ReviewSpec/` 报告（同一范围或同一 feature 是否已确认）；
3. `ProjectSpec` 的契约/领域模型：`doc structure` 定位，`doc read` 读取 `global-policies.md`、`inter-module-contracts.md`、`module-*/domain-model.md` 中相关部分。

命中“已知/已确认/设计缺口”时：标注“已知”，不作为新发现；如果无法判断，向用户说明并询问。

---

## Phase 4：扫描与输出

### 4-1 逐项判断

对每个候选：

- 引用具体文件/行号和 diff 片段；
- 写清“为什么可能是误报”；
- 置信度与影响分列；
- 不把契约字段、测试夹具、已确认设计缺口当新问题；
- 快速模式只报高置信度/中置信度；低置信度只出现在深入模式，并明确标注。

### 4-2 输出模板

```markdown
## 代码异味扫描 — {from}..{to}

模式：快速 / 深入
扫描：{N} 个源文件，{M} 行源码变更；排除：tests/docs/vendor/build...
候选：{K} 条（按置信度 × 影响排序，最多 10 条）

| # | 异味 | 位置 | 置信度 | 影响 | 证据 | 为什么可能是误报 | 建议方向 |
|---|------|------|--------|------|------|------------------|----------|
| 1 | ... | path:line | 高/中/低 | 高/中/低 | ... | ... | ... |

> 以上均为 judgement call，不是必须修改的结论。请选择 1–3 条深入看，或告诉我“都先记下”。
```

零发现时：

```markdown
未发现达到报告门槛的异味。
扫描范围：...
已检查项：...
局限：仅基于 diff 与所读上下文，未做 AST/全仓库重复检测。
```

### 4-3 硬限制

- 最多 10 条；超出的低置信度项合并为一句“另有 N 条低置信度未列出”；
- **同一根因只报一次**：Long Parameter List 与 Data Clumps 重叠时优先报 Long Parameter List；其它重叠保留证据更强的一条；
- 不写 ReviewSpec/ProjectSpec；不改锚点；不自动改代码；
- 不输出完整重构方案，只给方向。

---

## Phase 5：深入

用户选定 1–3 条后，逐条展示：

- 代码片段与所在上下文；
- 判断理由；
- 误报检查结果；
- 修复方向（不展开完整重构）；
- 建议：现在改 / 记入议题 / 接受技术债。

结束后不写任何文件。

---

## 失败与边界

| 情况 | 处置 |
|---|---|
| 无 git / 不是 git 仓库 | 按前言终止 |
| 未 doc-kit init / CLI 缺失 | 按前言终止，给同步命令 |
| `tool status` 版本或副本不一致 | 按前言暂停 |
| 范围缺失 | 先问起点，不默认猜 |
| ref 无效 | 说明原因，请用户给新范围 |
| 空 diff | 说明“该范围无变更”，询问换范围或结束 |
| 分类后无源码 | 打印摘要，问是否包含 tests/未识别扩展名 |
| 未知扩展名 | 列入“未识别”，问用户是否纳入 |
| diff 超上限 | 按目录拆分或让用户指定子集，不静默截断 |
| 能力文件缺失 | 提示 `doc-kit init` 同步，不猜规则 |
| 已知设计缺口 | 标注“已知”，不作为新发现 |

---

## 非目标

- 不替代 `spec-code-review`；
- 不做全量历史代码审计（另设 mode/skill）；
- 不做 AST、不做语言专项、不做跨仓库重复检测；
- 不自动重构、不自动提交、不写报告、不改锚点；
- 不新增 CLI 命令。

---
name: spec-code-review
description: 当开发完成但关键变更尚未确认、或提交 PR 前要做一轮设计文档一致性检查时使用：从 git 变更（按评审锚点范围）出发，并排比对代码与文档、由用户逐条判定差异性质，最后写入评审报告。不适用于纯技术债清理或无文档可比的改动。
---
# 最高优先级：

**三层边界（先看清各自走哪条路）**：

| 对象 | 读写方式 |
|------|---------|
| `ProjectSpec/`（设计文档） | **经 CLI**：`doc structure` / `doc read` 只读；需要改文档时**必须先读 `_index.md` 定位 doc_type + 读能力文件 + 经用户确认**后再 `doc update-section` / `doc add-section`（改文档是不可逆的知识资产变更） |
| **源码、diff、工作区文件** | **直接读写**（`bash` / 文件工具）。CLI 不介入代码与工作区 |
| git 仓库操作 | **一律用 `bash`**（CLI 不执行 git）：`git status` / `git diff` / `git log` / `git add` / `git commit` / `git push` |

**例外（能力库，仅读）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接读取，禁止写入**——辅助判断 diff 涉及的文档类型、或按 `_index.md` §2/§3 路由文档写入位置时对照能力文件。

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
python .doc-kit/cli/cli.py doc update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py doc add-section <reference> '<标题>' [--content '<正文>'] [--level sibling|child]
python .doc-kit/cli/cli.py doc lint [--baseline <file>] [--summary]
python .doc-kit/cli/cli.py review anchor-get [--branch <分支名>]
python .doc-kit/cli/cli.py review anchor-set <commit_hash> [--session <sid>] [--branch <分支名>]
python .doc-kit/cli/cli.py review report-write [--content '<report_markdown>']   # 或 --file <path> / stdin
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 四个字段；退出码 0 = 成功、1 = 业务拒绝或运行时错误、**2 = 参数错误**（未知选项 / 缺必填参数，按提示修正后重试）。
>
> 错误文本**没有统一格式**：较新的错误写作 `ERROR [<错误码>] <原因>。修复：<建议>`，但多数历史错误是散文形式（如「未找到文档: <path>，可用 doc structure 查看所有文档路径」）。**不要用正则解析错误文本**——错误原文同时出现在 `message` 与 `suggestions[0]`，按语义阅读后行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一至两行中文状态描述（**有活跃开发循环时会额外给出一行提示**），`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-code-review — 代码评审

## 定位

独立的任务式技能，不依赖已有议题。用户通过 `/spec-code-review {描述}` 发起，AI 从 git 变更开始分析，检视新增代码与设计文档的一致性。

**适用时机**：开发完成但尚有关键变更未确认时；提交 PR 前做一轮文档一致性检查。

**不适用**：纯粹的技术债清理或重构（无需比照设计文档）；尚未开发完成。

---

## 流程总览

```
Phase 1 — 收集（AI 自动完成）
  用户描述 → 取锚点并校验 → git log/diff → 扫描关联文档

Phase 2 — 展示（AI 汇总）
  AI 标注可能偏差的热点 → 用户圈定深入评审的范围

Phase 3 — 确认（人主导）
  AI 并排展示代码 vs 文档 → 用户判断差异性质 → 收集判定

Phase 4 — 收尾
  更新评审锚点 → 汇总输出 → 写入报告 → 文档一致性检查（提示）→ 引导后续动作
```

---

## Phase 1：收集

### Step 1-0：前置条件

```bash
git --version >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1
```

**不满足条件时**，直接输出以下文案并终止流程：

```
❌ 前置条件不满足：系统未安装 git 或当前目录不是 git 仓库。

建议操作：
  • git --version 确认安装
  • git init 初始化仓库
  • cd 切换到 git 仓库目录后重试
```

### Step 1-1：解析用户描述

从 `/spec-code-review {描述}` 中提取**关注范围**（文件、模块或功能点，如「评审 auth 模块的改动」）；描述为空或无明确指向时，先向用户确认范围。

> **文档排除**：本技能聚焦**代码变更**评审。`.md`、`docs/`、`CHANGELOG`、`README` 等纯文档类文件默认从 git diff 中排除。若用户明确要求评审文档，则在 git 命令中**不加入**排除规则。

### Step 1-2：获取并校验评审锚点

调 `python .doc-kit/cli/cli.py review anchor-get`（默认读取**当前分支**的锚点）。

返回的 `data` 含 `branch` / `source` / `last_reviewed_commit`，按以下分支处理：

| 情况 | 判定 | 处置 |
|------|------|------|
| `source: branch` 且 hash 非空 | 当前分支有专属锚点 | 进入**锚点校验**（下一步） |
| `source: global` | 当前分支无专属锚点，回退到最近一次评审锚点 | 提示"该锚点可能来自其它分支"，请用户确认比对范围后仍须校验 |
| `source: none` | 首次评审 | 询问起点：指定某个 commit，或从首个 commit 开始 |
| 用户描述中指定了范围 | 如「从 v1.0 tag 开始评审」 | 优先采用用户指定的起点 |

**锚点校验（必做）**：

```bash
git cat-file -e <锚点>^{commit}
```

- 校验**失败** → 锚点已失效（常见原因：rebase、force-push、分支被删除或历史被改写）。此时**不要**继续用 `git log <锚点>..HEAD`（会直接报 `有歧义的参数`）。向用户说明原因，并请其指定新的起点（或用 `first` 从首个 commit 开始）。
- 校验**通过** → 继续 Step 1-3。

> 锚点按分支记录（`review anchor-set` 会自动带上当前分支），多分支并行评审互不覆盖；也可用 `--branch <分支名>` 显式指定。

> **记录范围**：本步骤确认的起点记为 `review_from`；Step 4-5 的「补齐代码异味检查」提示需要它。不要等到锚点推进后再回头找旧范围。

### Step 1-3：获取 git 变更

默认排除纯文档类文件（`.md`、`docs/`、`CHANGELOG*`、`README*`、`LICENSE*`），聚焦代码变更；用户要求评审文档时不加排除规则。

```bash
# 提交清单（仅代码）
git log <锚点>..HEAD --oneline -- . ':(exclude)*.md' ':(exclude)docs/' ':(exclude)CHANGELOG*' ':(exclude)README*' ':(exclude)LICENSE*'

# 变更文件概览（仅代码）
git diff --stat <锚点>..HEAD -- . ':(exclude)*.md' ':(exclude)docs/' ':(exclude)CHANGELOG*' ':(exclude)README*' ':(exclude)LICENSE*'

# 完整 diff（仅代码）
git diff <锚点>..HEAD -- . ':(exclude)*.md' ':(exclude)docs/' ':(exclude)CHANGELOG*' ':(exclude)README*' ':(exclude)LICENSE*'
```

用户描述指定了关注范围时，用 `-- <路径>` 取代上述排除规则。

> **两点说明**：① 排除规则只作用于**文件**，同时改了文档与代码的提交仍会出现在清单里（它的代码部分需要评审），这是正常的；② 纯文档提交不会出现。

**空变更处理**：若提交清单为空（自锚点以来没有代码变更），**不要**产出空报告——向用户说明"自锚点以来无新增代码变更"，并询问：换一个起点重新评审 / 结束本次流程。

展示提交清单给用户确认是否覆盖全部文件，或需进一步缩小范围。

### Step 1-4：读取相关设计文档

调 `python .doc-kit/cli/cli.py doc structure` 获取所有文档路径与 section 标题，按变更文件路径语义与用户关注点匹配相关文档（如 `auth.py` → `architecture.md` §认证流程、`non-functional-constraints.md` §安全约束；用户提到「接口变更」→ `inter-module-contracts.md`），再 `python .doc-kit/cli/cli.py doc read <path>` 读取完整内容。

> 匹配规则是启发式的——按文件名、section 标题、用户描述三者之间的语义关联，不做精确映射。

> **能力库对照**：判断文档侧是否合规（段落结构、边界约束编号、行文规则）时，可读 `<项目根>/.doc-kit/skills/guidance/doc-capabilities/<doc_type>.md` 对照其「段落结构 / 行文规则」。

---

## Phase 2：展示

### Step 2-1：AI 扫描热点

基于 diff 与设计文档做 best-effort 扫描，标注"可能存在偏差"的热点区域：

```
📋 本次评审概况

用户关注: {从描述提取的关注范围}

变更文件清单（共 N 个）:
  - src/auth/token.py   (15 行新增)
  - src/api/handlers.py (8 行新增)

关联设计文档:
  - architecture.md → §认证流程、§token 生命周期
  - non-functional-constraints.md → §安全约束

🔍 AI 标注的热点区域（仅供参考，需人工确认）:
  ① token.py:14-18 — 过期时间从 30min→60min，
     与 architecture.md §认证流程「token 有效期 30 分钟」不一致
  ② handlers.py:22-25 — 新增角色校验逻辑，文档中无此约束描述
```

风险等级：🔴 **高**（行为变更可能影响安全、稳定性、外部接口）／🟡 **中**（设计偏差，需确认是设计变更还是实现失误）／🟢 **低**（文档滞后或次要差异）。

> AI 标注仅为辅助，可能不准确或有遗漏；判定权在用户。

### Step 2-2：用户选择

询问用户：以上热点区域中哪些需要深入比对？是否有未标注的区域需要查看？用户选择后进入 Phase 3。

---

## Phase 3：确认

对用户选中的每个热点区域，逐一确认：

### Step 3-1：并排展示

```
📄 文档 — architecture.md §认证流程
> token 有效期 30 分钟，过期后需刷新。

💻 代码 — src/auth/token.py:14-18
> TOKEN_TTL = 60  # 改为 60 分钟

差异要点：...（AI 列出关键表/字段层面的对比）
```

### Step 3-2：引导用户判定

```
这是一个什么性质的差异？

A. **设计变更** — 代码有意偏离原设计，需更新文档记录新决策
B. **实现偏差** — 代码实现有误，应改回与文档一致
C. **误报** — 代码与文档一致，AI 判断有误
```

### Step 3-3：记录判定

将判定暂存在内存（一个列表），格式：

```
[差异简述] token 过期时间 30min→60min
[性质]     设计变更
[性质]     🟡 中
[后续动作]  更新 architecture.md §认证流程，记录新的过期时间及理由
```

### Step 3-4：逐条处理

重复 Step 3-1~3-3 直到所有选中的热点处理完毕。

---

## Phase 4：收尾

### Step 4-1：更新评审锚点

```bash
git rev-parse HEAD   # 记为 review_to（= HEAD），供 Step 4-5 的 smell 范围使用
python .doc-kit/cli/cli.py review anchor-set <commit_hash>
```

锚点**按当前分支记录**（多分支并行评审互不覆盖）；如评审的是其它分支，可加 `--branch <分支名>`。

### Step 4-2：汇总输出

按以下模板组织评审报告：

```markdown
# Code Review Report — {简短标题}

> **评审日期**: {YYYY-MM-DD}
> **评审范围**: {锚点}..{HEAD}（分支：{分支名}）
> **用户关注**: {从描述提取的关注范围}

## 基本信息

| 项目 | 内容 |
|------|------|
| 评审日期 | {YYYY-MM-DD} |
| 评审分支 | {分支名} |
| 评审 Git 范围 | {锚点}..{HEAD} |
| 关注范围 | {用户描述} |
| 变更文件数 | {N} 个 |

### 变更文件清单

| 文件 | 类型 | 规模 |
|------|------|------|
| path/to/file1.py | 修改 | XX 行变更 |
| path/to/file2.py | 新建 | XX 行全新 |

### 关联设计文档

- {doc-path-1} → §{相关段落}
- {doc-path-2} → §{相关段落}

## 评审热点

AI 标注的 N 个潜在偏差区域：

| # | 差异简述 | 文档位置 | 代码位置 | 风险等级 |
|---|---------|---------|---------|---------|
| ① | {简述} | {doc} §{段落} | {file}:{line} | 🔴/🟡/🟢 |

## 深入确认项

用户逐条确认后的差异判定：

| # | 差异 | 性质 | 后续动作 |
|---|------|------|---------|
| ③-a | {差异简述} | 设计变更/实现偏差/文档过时 | {具体后续动作} |

## 未深入比对项

未进行逐条比对的热点：

| # | 差异 | 风险等级 | 简要说明 |
|---|------|---------|---------|
| ① | {简述} | 🔴/🟡/🟢 | {一句话说明} |

## 后续动作

基于评审结果的可选后续步骤：

1. ...
```

> **段落要求（与 CLI 校验一致）**：**必填 3 段**——`# ` 标题、`## 基本信息`、`## 评审热点`；**建议 3 段**——`## 深入确认项`、`## 未深入比对项`、`## 后续动作`（缺失只产生 warning，报告仍会写入）。某段确无内容时写「无」并保留标题，便于后续检索。

### Step 4-3：写入评审报告

```bash
python .doc-kit/cli/cli.py review report-write --content '<report_markdown>'
```

文件自动命名为 `code-review-{YYYYMMDD-HHMMSS}.md`，写入 `ReviewSpec/`。若 CLI 返回 `warnings`（缺建议段落），照提示补齐更佳。

### Step 4-4：文档一致性检查（提示，非阻断）

```bash
python .doc-kit/cli/cli.py doc lint --summary
```

本次评审可能只改代码、不写 `ProjectSpec/`（报告写入 `ReviewSpec/`）。此步**仅提示**：若 `success=false`（存在未被 baseline 吸收的 error），把 `message` 与 `data.errors`（≤20 条）摘要作为「后续动作」的参考一并展示给用户，**不阻断评审、不改评审结论**。需要时可在「后续动作」里按能力库路由修正文档（见 Step 4-5）。

### Step 4-5：引导后续动作

```
代码评审完成。报告已写入 ReviewSpec/{filename}，评审锚点已更新（分支：{分支名}）。
```

按用户选择的后续动作分流：

| 后续动作 | 怎么做 |
|---------|--------|
| 更新设计文档 | **必须走能力库路由**：读 `_index.md` §2/§3 定位 doc_type → 读对应 `<doc_type>.md` 的能力文件（段落结构 / 行文规则）→ `python .doc-kit/cli/cli.py doc read <path>` 看目标文档现状 → **把「改哪篇文档、哪个章节、写什么」整理成清单交用户确认** → 确认后执行：
```bash
python .doc-kit/cli/cli.py doc update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py doc add-section <reference> '<标题>' --content '<正文>' [--level sibling|child]
``` |
| 记入议题追踪 | 用 `spec-start` 开启新议题（注意：创建议题会**先确认本次要讨论的议程**，议题名与议程需用户确认） |
| 仅留档 | 无需额外动作，报告已落 `ReviewSpec/` |
| 💡 补齐代码异味检查（可选） | 本轮只做了文档一致性复核。若需同时检查代码形态，可跑 `/spec-code-smell <review_from>..<review_to>`；该技能只读、不写报告、不改锚点。 |

> 改文档是不可逆的知识资产变更：未经用户确认不要写入；文档间归属判断以 `_index.md` §2/§3 为准，能力文件的「行文规则·禁止」只作落笔前的边界提醒。

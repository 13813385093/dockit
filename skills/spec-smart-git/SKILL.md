---
name: spec-smart-git
description: 当开发完成准备提交、或有多个不相干的改动需要分开提交时使用：按 feat/fix/docs/refactor/chore 标签把工作区变更分解为若干语义独立的提交并逐个执行。不适用于尚未开发完成、存在未解决冲突、或只是一次微调。
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
python3 .doc-kit/cli/cli.py spec read
python3 .doc-kit/cli/cli.py doc structure
python3 .doc-kit/cli/cli.py doc read <path>
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 四个字段；退出码 0 = 成功、1 = 业务拒绝或运行时错误、**2 = 参数错误**（未知选项 / 缺必填参数，按提示修正后重试）。
>
> 错误文本**没有统一格式**：较新的错误写作 `ERROR [<错误码>] <原因>。修复：<建议>`，但多数历史错误是散文形式（如「未找到文档: <path>，可用 doc structure 查看所有文档路径」）。**不要用正则解析错误文本**——错误原文同时出现在 `message` 与 `suggestions[0]`，按语义阅读后行动。
>
> 例外：`spec status` / `spec read` / `spec schema` 三个命令直接输出文本——`spec status` 是一至两行中文状态描述（**有活跃开发循环时会额外给出一行提示**），`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。
>
> 未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `review` / `dev`）之前。
---

# spec-smart-git — 智能分解与提交

## 定位

将工作区中的待提交变更按文件粒度分析、按约定标签（`feat` / `fix` / `docs` / `refactor` / `chore`）分类，生成一组语义独立的 git 提交。

**适用时机**：开发完成准备提交时；有多个不相干的改动需要分开提交时。

**不适用**：尚未开发完成；有未解决的冲突；只在某个文件做了一次微调。

---

## 流程总览

```
Phase 1 — 收集（AI 自动完成）
  安全检查 → 分析 staged / unstaged / untracked → 按标签分类

Phase 2 — 提案（AI 展示，人确认）
  展示分解方案 → 用户确认 / 调整 / 合并 / 跳过

Phase 3 — 执行（AI 执行）
  逐个提交（pathspec 形式）→ 可选推送（开发分支默认不推）

Phase 4 — 收尾
  输出完成摘要
```

---

## Phase 1：收集

### Step 1-0：前置条件

```bash
git --version >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1
```

**不满足条件时**，直接输出以下文案并终止流程（不再执行后续 Steps）：

```
❌ 前置条件不满足：系统未安装 git 或当前目录不是 git 仓库。

建议操作：
  • git --version 确认安装
  • git init 初始化仓库
  • cd 切换到 git 仓库目录后重试
```

### Step 1-1：获取变更概览

```bash
git diff --staged --stat      # 已暂存
git diff --stat               # 已修改未暂存
git status --porcelain        # 全部状态与未跟踪文件
```

> **冲突检查**：若出现 `UU` 等未解决冲突状态，提示用户先解决冲突并终止流程。

展示给用户的摘要格式：

```
📋 变更概览

已暂存（staged）: N 个文件
  src/app/feature.py  (+15 / -3)

未暂存（unstaged）: M 个文件
  src/app/utils.py    (+8 / -0)

未跟踪（untracked）: K 个文件
  new_file.py
```

### Step 1-2：检查 .gitignore 遗漏

分析**未跟踪文件**，判断是否有明显应被 `.gitignore` 排除的类型：

| 特征 | 举例 |
|------|------|
| Python 缓存 | `__pycache__/`, `*.pyc`, `*.pyo` |
| 编辑器/IDE 配置 | `.vscode/`（项目级除外）、`*.swp` |
| 日志文件 | `*.log` |
| 操作系统文件 | `Thumbs.db`, `.DS_Store` |
| 临时文件 | `*.tmp`, `*~` |
| 构建产物 | `dist/`, `build/`, `*.egg-info/` |
| **工具状态**（doc-kit 机器状态，不该进业务仓库） | `.doc-kit/`（config / registry / index.json / code-review-state.json / CLI 与技能副本）——未忽略时评审锚点会被误提交，且会阻塞分支切换；`SessionSpec/active/`、`DevSpec/active/` 属工作区状态，是否入库由用户决定（`archive/` 里的 CodeNotes 与报告通常值得保留） |

**如果发现遗漏**，列出文件并询问用户（用自然语言回答即可，无需按键）：

```
检测到未跟踪文件中包含应被 .gitignore 排除的文件：
  · __pycache__/util_cache.pyc
  · .vscode/settings.json（非项目级 IDE 配置）
  · Thumbs.db

建议在 .gitignore 中添加对应规则。
请选择：① 继续本次提交（这些文件不会进入任何提交）；② 先补 .gitignore，我再重新开始。
```

- 用户选 ① → 继续流程，这些文件**不列入任何提交**
- 用户选 ② → 终止流程，让用户更新 `.gitignore` 后重新执行

**如果没有遗漏**，继续到 Step 1-3。

### Step 1-3：读取上下文并分类

先运行 `python3 .doc-kit/cli/cli.py doc structure` 获取项目文档结构，映射变更文件可能关联的设计文档。

对每个变更文件读取其完整 diff（`git diff --staged -- <file>` 或 `git diff -- <file>`），**按需**运行 `python3 .doc-kit/cli/cli.py doc read <path>` 读取关联设计文档，综合判断标签。

**标签体系**（精简版 Conventional Commits）：

| 标签 | 含义 | 典型场景 |
|------|------|---------|
| `feat` | 新功能 | 新增模块、新增函数、新增接口 |
| `fix` | 缺陷修复 | 修 bug、异常处理、边界修正 |
| `docs` | 纯文档 | 改 README、注释、Markdown |
| `refactor` | 重构 | 重命名、提取函数、调整结构（行为不变） |
| `chore` | 杂项 | 构建配置、依赖管理、CI/CD、构建脚本变更 |

**映射规则**：

- **优先按文件路径语义**：`.md` 文件（非测试文档）→ `docs`；`requirements*.txt`、`.github/`、`Makefile`、打包脚本 → `chore`；`tests/` 下的文件归入关联的 `feat`/`fix` 提交而非独立标签
- **路径语义不明确时，按 diff 内容**判断是新增逻辑（`feat`）、修复（`fix`）还是重构（`refactor`）
- **同一文件的多个异类修改**：标注为「混合改动」，放入待确认组，由用户决定归属
- **无法确定标签或置信度低**：归入「待确认」

**staged 文件处理（重要）**：

- staged 文件**保留其暂存状态，不释放**（尊重用户手动 `add` 的意图）
- staged 文件若属于不同标签，按标签拆到不同提交中
- 由于 `git commit` 会提交**索引中的全部内容**，执行提交时必须使用 **pathspec 形式**（见 Phase 3），否则会把其它分组的已暂存文件卷进本次提交

**输出格式**：

```
按标签分类结果

feat: （2 个文件）
  · src/app/feature.py     [staged]
  · src/app/handler.py     [staged]

fix: （1 个文件）
  · src/app/bugfix.py      [unstaged]

docs: （1 个文件）
  · README.md              [unstaged]

待确认—混合改动（1 个文件）:
  · src/app/mixed.py       [unstaged]  ← 同时包含 feat 和 fix 改动
```

---

## Phase 2：提案

### Step 2-1：展示分解方案

```
────────────────────────────────────────────────
提案：以下分组将产生 N 个提交
────────────────────────────────────────────────

提交 1/3  feat: 添加依赖图面板功能
  文件:
    · src/app/dep-graph.py  【staged】 (+120 / -0)
  建议 message:
    feat: 添加依赖图面板功能

    - 实现依赖图可视化
    - 支持展开/折叠节点

提交 2/3  fix: 修复依赖树展开异常
  文件:
    · src/app/dep-graph.py  【unstaged】 (+5 / -8)
  建议 message:
    fix: 修复依赖树展开异常

    - 修正递归展开时栈溢出判断条件

待确认组（未分配的文件）:
  · src/utils/helper.py    【unstaged】 — 无法确定标签
  · src/app/config.py      【unstaged】 — 混合改动（feat + refactor）
────────────────────────────────────────────────
```

### Step 2-2：用户确认

用**自然语言**与用户交互（AI 平台无法接收按键，因此不要求"输入数字"）——明确告诉用户可以这样表达：

```
请确认以上分解方案。你可以直接说：
  · 「看 1 的完整 diff」            —— 展示某个提交的完整 diff
  · 「合并 1 和 2」                —— 合并两个提交
  · 「改 3 的信息为 ...」           —— 修改某个提交的 message
  · 「跳过 4」                     —— 跳过某个提交
  · 「把 helper.py 归到 fix」       —— 为待确认文件指定标签
  · 「确认」/「取消」               —— 执行或中止
```

> 用户每次操作后，更新提案并重新展示摘要，直到用户「确认」或「取消」。

特殊场景：

- **所有文件都属于同一个标签** → 只生成一个提交，但仍展示给用户确认
- **待确认组为空** → 直接展示完整提案
- **用户跳过全部提交** → 视为取消

---

## Phase 3：执行

### Step 3-1：逐个提交（必须用 pathspec 形式）

> **⚠️ 关键约束**：必须使用 `git commit ... -- <本分组文件>` 的 pathspec 形式。
>
> 原因：不带 pathspec 的 `git commit` 会提交**索引中的全部内容**。当用户手工 `git add` 过、且这些已暂存文件属于**其它标签分组**时，普通提交会把它们一起卷进本次提交——实测三个分组会混成一个提交。这与"保留用户暂存状态、按标签分解"的目标直接冲突。
>
> pathspec 形式只提交指定路径，**其余文件（含已暂存的）状态原样保留**。

```bash
# 1. 本分组中尚未暂存的文件先 add（已在暂存区的文件跳过 add）
git add <file1> <file2>

# 2. 提交时显式列出本分组文件
git commit -m "feat: xxx

- 具体改动1
- 具体改动2" -- <file1> <file2>
```

**注意事项**：

- 多个提交**按顺序逐个执行**，每执行完一个输出结果，再执行下一个
- 一个提交内的文件必须来自同一个标签分组
- commit message 正文（body）**必须**包含简要变更说明（bullet points），不能只有标题行
- 分组内已在暂存区的文件无需 `git reset`，pathspec 提交同样生效
- **限制说明（同一文件内混合暂存）**：若某文件同时存在"已暂存 + 未暂存"的修改，git 会提交该文件的**全部改动**——本技能不支持按 hunk 拆分；需要精细控制时，请用户先用 `git add -p` 处理后再执行本技能

**commit message 规范**（标签后用 ASCII 冒号，符合 Conventional Commits）：

```
<标签>: <简短标题>

- <具体改动1>
- <具体改动2>
```

**利用议题上下文**：可运行 `python3 .doc-kit/cli/cli.py spec read` 读取活跃议题（无活跃议题时静默跳过），把议题背景融入 message body。

每个提交完成后输出：

```
✅ 提交成功
  commit abc1234def
  feat: 添加依赖图面板功能

  2 个文件变更，+125 / -8
```

**提交失败处理**：

| 失败原因 | 处理方式 |
|---------|---------|
| `git add` 失败（文件不存在） | 跳过该文件，继续当前提交，输出警告 |
| `git commit` 失败（pathspec 不匹配、空提交、hook 拒绝） | 输出错误信息，暂停流程，询问用户是否继续 |
| 其它异常 | 暂停流程，输出错误信息 |

### Step 3-2：可选推送（开发分支默认不推送）

> **默认不推送。** 若当前分支是 `dev-loop/<sid>`（`spec-dev-loop` 的开发分支），**循环内一律不推送**——按 dev-loop 的分支策略，评审通过后的合并与推送由人工在循环外完成。
>
> 其它分支：所有提交完成后**询问用户**是否推送（默认不推送）：

```
所有提交已完成（当前分支：<分支名>）。是否推送到远程？
  · 「推送」—— git push（首次推送用 git push -u origin <分支>）
  · 「不用」—— 仅本地提交
```

推送失败时只输出错误信息、不阻断流程（用户可自行处理）。

---

## Phase 4：收尾

### Step 4-1：输出完成摘要

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 智能提交完成

当前分支: <分支名>
全部完成 3 个提交：
  abc1234  feat: 添加依赖图面板功能
  def5678  fix: 修复依赖树展开异常
  789abcd  docs: 更新 README 使用说明

推送到远程: 是 / 否
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> 若当前分支是 `dev-loop/<sid>`，追加一句提示：**代码位于开发分支，请人工评审/验收通过后再合并回主分支**（与 `spec-dev-loop` 的收尾一致）。

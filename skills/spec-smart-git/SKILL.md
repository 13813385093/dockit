---
name: spec-smart-git
description: 按标签分解待提交变更，生成规范化的 git 提交
---

# 最高优先级：

在本次 Skill 执行过程中，所有 git 操作一律使用 `bash` 工具执行。

允许调用的 MCP 工具（**只读用途，不得写入**）：
- `mcp__spec_mcp_tools__doc_structure` — 获取项目文档结构，辅助变更分类
- `mcp__spec_mcp_tools__read_doc` — 读取设计文档内容，辅助理解 diff 上下文
- `mcp__spec_mcp_tools__spec_read` — 读取活跃议题上下文，辅助生成 commit message
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
  逐个提交 → 可选推送

Phase 4 — 收尾
  输出完成摘要
```

---

## Phase 1：收集

### Step 1-0：前置条件

在开始任何操作之前，确认环境就绪：

```bash
git --version >nul 2>&1 && git rev-parse --git-dir >nul 2>&1
```

**不满足条件时**，直接输出以下文案并终止流程（不再执行后续 Steps）：

```
❌ 前置条件不满足：系统未安装 git 或当前目录不是 git 仓库。

建议操作：
  • git --version 确认安装
  • git init 初始化仓库
  • cd 切换到 git 仓库目录后重试
```

执行成功后继续到 Step 1-1。

### Step 1-1：获取变更概览

获取三种状态的变更信息：

```bash
# staged 变更（用户已 git add）
git diff --staged --stat

# unstaged 变更（已修改但未 git add）
git diff --stat

# 全部变更和未跟踪文件
git status --porcelain
```

> **注意**：如果工作区有未解决的冲突（`git status` 显示 `UU` 等状态），提示用户先解决冲突，终止流程。

展示给用户的摘要格式：

```
📋 变更概览

已暂存（staged）: N 个文件
  src/app/feature.py  (+15 / -3)
  ...

未暂存（unstaged）: M 个文件
  src/app/utils.py    (+8 / -0)
  ...

未跟踪（untracked）: K 个文件
  new_file.py
  ...
```

### Step 1-2：检查 .gitignore 遗漏

分析所有**未跟踪文件（untracked）**，判断是否存在**明显应该被 `.gitignore` 排除**的文件类型：

| 特征 | 举例 |
|------|------|
| Python 缓存 | `__pycache__/`, `*.pyc`, `*.pyo` |
| 编辑器/IDE 配置 | `.vscode/`（项目级除外）、`*.swp` |
| 日志文件 | `*.log` |
| 操作系统文件 | `Thumbs.db`, `.DS_Store` |
| 临时文件 | `*.tmp`, `*~` |
| 构建产物 | `dist/`, `build/`, `*.egg-info/` |

**如果有遗漏**，输出：

```
️  检测到未跟踪文件中包含应被 .gitignore 排除的文件：
  · __pycache__/util_cache.pyc
  · .vscode/settings.json（非项目级 IDE 配置）
  · Thumbs.db

建议在 .gitignore 中添加对应规则后重新执行本 skill。
是否继续当前流程（不跟踪这些文件）？ [Y/n]
```

- 用户确认后，继续流程（这些文件不会被列入提交）
- 用户否，终止流程，让用户先更新 .gitignore

**如果没有遗漏**，继续到 Step 1-3。

### Step 1-3：读取上下文并分类

AI 先调 `mcp__spec_mcp_tools__doc_structure()` 获取项目文档结构，映射出变更文件可能关联的设计文档。

对于每个变更文件，AI 读取其完整 diff（`git diff --staged -- <file>` 或 `git diff -- <file>`），同时**按需调 `mcp__spec_mcp_tools__read_doc()` 读取关联的设计文档**，综合判断属于哪个类型标签。

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
- **路径语义不明确时，按 diff 内容**：AI 读取 diff 判断是新增逻辑（`feat`）还是修复（`fix`）还是重构（`refactor`）
- **同一文件的多个异类修改**：AI 标注为「混合改动」，放入待确认组，由用户决定归属

**staged 文件处理**：

- staged 的文件**保留其暂存状态**，不释放（尊重用户手动 add 的意图）
- staged 的文件如果属于不同标签，按标签拆到不同提交中
- 执行提交时，只 `git add` 当前分组中**已在 staged 中的文件**（它们已经 add 了，跳过 add 步骤直接 commit）

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

️  待确认—混合改动（1 个文件）:
  · src/app/mixed.py       [unstaged]  ← 同时包含 feat 和 fix 改动
```

> 如果某个文件无法确定标签，或 AI 置信度低，归入「待确认」。

---

## Phase 2：提案

### Step 2-1：展示分解方案

合并 Step 1-3 的分类结果，展示预提案：

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

提交 3/3  docs: 更新 README 使用说明
  文件:
    · README.md  【unstaged】 (+20 / -5)
  建议 message:
    docs: 更新 README 使用说明

    - 补充依赖图功能的操作步骤

⚠️  待确认组（未分配的文件）:
  · src/utils/helper.py  【unstaged】  — 无法确定标签
  · src/app/config.py   【unstaged】  — 混合改动（feat + refactor）
────────────────────────────────────────────────
```

### Step 2-2：用户确认

提示用户：

```
请确认以上分解方案：
  ✅ 输入数字查看某个提交的完整 diff
  🔀 输入 merge <编号1> <编号2> 合并两个提交
  ✏️  输入 edit <编号> 修改该提交的 message
  ❌ 输入 skip <编号> 跳过某个提交
  ➕ 输入 assign <文件> <标签> 为待确认文件指定标签
  ✅ 输入 confirm 确认并执行
  ❌ 输入 abort 取消
```

> 用户每次操作后，AI 更新提案并重新展示摘要，直到用户输入 `confirm` 或 `abort`。

特殊场景处理：

- **所有文件都属于同一个标签** → 只生成一个提交，但仍展示给用户确认
- **待确认组为空** → 直接展示完整提案
- **用户选择 skip 所有提交** → 视为 abort

---

## Phase 3：执行

### Step 3-1：逐个提交

对于提案中的每个分组，按以下步骤执行：

```bash
# 1. git add 该分组中尚未 staged 的文件
git add <file1> <file2> ...

# 2. git commit（staged 的文件自动包含在内）
git commit -m "feat: xxx

- 具体改动1
- 具体改动2"
```

**注意事项**：

- 如果用户提案阶段确认了多个提交，**按顺序逐个执行**，每执行完一个输出结果，再执行下一个
- 所有文件必须来自同一个标签分组
- commit message 的正文（body）**必须**包含简要的变更说明（bullet points），不能只有标题行

**commit message 规范**：

```
<标签>: <简短标题>

- <具体改动1>
- <具体改动2>
```

**利用议题上下文**：AI 可调 `mcp__spec_mcp_tools__spec_read()` 尝试读取活跃议题（无活跃议题时静默跳过），有议题时将议题描述中的背景信息融入 commit message body，让信息更有依据。

**staged 文件处理**：

- 对于一个分组中的所有 staged 文件，它们已经在暂存区，执行 commit 时会被自动包含
- 确保同一个提交中不会包含不属于本分组但已被 staged 的其他文件——分组的 staged 文件必须是其子集

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
| `git commit` 失败（空提交、hook 拒绝） | 输出错误信息，暂停流程，询问用户是否继续 |
| 其他异常 | 暂停流程，输出错误信息 |

### Step 3-2：可选推送

所有提交完成后，询问用户：

```
所有提交已完成。是否推送到远程？
  Y — git push（默认）
  n — 仅本地提交
```

如果选 Y，执行：

```bash
git push
```

> **注意**：push 失败时只输出错误信息，不阻断流程。用户可以之后自行处理。

---

## Phase 4：收尾

### Step 4-1：输出完成摘要

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 智能提交完成

全部完成 3 个提交：
  abc1234  feat: 添加依赖图面板功能
  def5678  fix: 修复依赖树展开异常
  789abcd  docs: 更新 README 使用说明

推送到远程: 是 / 否
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

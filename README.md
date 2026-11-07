# doc-kit

> 面向 AI 时代的项目文档体系工具链：一个桌面 App + 一套随项目分发的 CLI + 8 个 AI 技能（skills），共同维护 `ProjectSpec/` 分层文档与议题/开发循环工作流。

- [English](README.en.md)

---

## 目录

1. [如何编译](#1-如何编译)
2. [在新项目中使用 init 初始化](#2-在新项目中使用-init-初始化)
3. [在已初始化项目中更新到新版本](#3-在已初始化项目中更新到新版本)
4. [Skills 简介](#4-skills-简介)
5. [App 简介](#5-app-简介)

---

## 1. 如何编译

### 1.1 环境准备

```bash
pip install -r requirements.txt        # 运行时依赖（PySide6 / qt-material / PyYAML / Markdown）
pip install -r requirements-dev.txt    # 打包依赖（pyinstaller）
```

### 1.2 打包

打包脚本位于 `src/app/doc_kit.spec`，会把 `templates/`、`resources/`、`skills/` 一并打入发布包：

```bash
pyinstaller src/app/doc_kit.spec
```

产物在 `dist/doc_kit/` 下，可执行文件为 `doc_kit`（Windows 下为 `doc_kit.exe`）。

---

## 2. 在新项目中使用 init 初始化

`init` 会在目标项目根生成完整的文档骨架与工具链副本。

### 2.1 命令

```bash
doc-kit init <项目根路径> [--name <项目名称>]
```

### 2.2 初始化后生成的内容

| 路径 | 作用 |
|---|---|
| `ProjectSpec/` | 7 篇顶层文档骨架（business-context、technical-framework、non-functional-constraints、global-policies、inter-module-contracts、stakeholders、release-policy） |
| `.doc-kit/config.yaml` | 项目名、创建时间 |
| `.doc-kit/registry.yaml` | 15 种文档类型注册表（top / module / feature 三级） |
| `.doc-kit/templates/` | 各文档类型的 Markdown 模板 |
| `.doc-kit/cli/` | 工具链 CLI（`cli.py` + 辅助模块），skills 的统一执行体 |
| `.doc-kit/skills/` | 8 个 skill 的 `SKILL.md` 副本 + `guidance/` 能力库（供人工搬运到 agent 的 skills 目录） |
| `.doc-kit/index.json` | 文档索引（路径、类型、依赖关系） |
| `.doc-kit/toolchain.json` | 工具链版本与各副本的 sha256 清单，用于版本一致性校验 |

### 2.3 让 AI agent 用上这些 skills

`init` 把 skills 副本放在项目的 `.doc-kit/skills/` 下，但大多数 agent 只扫描自己固定的 skills 目录。**推荐用软连接**而非复制：把 `.doc-kit/skills/` 下的每个 skill 目录链接到 agent 的 skills 目录，这样项目升级后链接自动指向新版本，无需重复安装。

#### 方式一（推荐）：让 agent 自己建立软连接

直接告诉 AI：

> 请把当前项目 `.doc-kit/skills/` 下的所有 `spec-*` 目录，以软连接的方式安装到你自己的 skills 目录中。

agent 会：
1. 自行定位其 skills 目录（如 `~/.trae-cn/skills/`、`~/.claude/skills/`、`~/.reasonix/skills/` 等）；
2. 对 `.doc-kit/skills/spec-*` 逐个建立软连接（而非复制）；
3. 跳过已存在的同名链接/目录，避免覆盖自定义 skill。

软连接的好处是项目侧 `doc-kit init` 升级后，agent 侧自动拿到新版 skills，无需再次执行安装。

#### 方式二：手动软连接（以 TRAE 为例）

```bash
AGENT_SKILLS_DIR=~/.trae-cn/skills          # 换成你的 agent skills 目录
mkdir -p "$AGENT_SKILLS_DIR"
for skill in <项目根>/.doc-kit/skills/spec-*; do
  name=$(basename "$skill")
  ln -sfn "$skill" "$AGENT_SKILLS_DIR/$name"
done
```

> `ln -sfn` 中的 `-n` 可避免把链接链接到已存在的目录内部；若 agent 不支持软连接（部分 Windows 场景），再改用 `doc-kit install-skills` 的复制方式。

#### 方式三：复制安装（不推荐，升级后需重装）

```bash
doc-kit install-skills <agent 的 skills 目录>
```

复制方式每次升级都要重新执行，且容易出现「项目侧已升级、agent 侧还是旧版」的错配，仅在软连接不可用时使用。

---

## 3. 在已初始化项目中更新到新版本

工具链采用「快照复制」模型：`init` 把 CLI / skills / templates 的当时版本复制进项目，此后仓库与项目各自演化。升级时**先删除项目下的 `.doc-kit/`，再重新 init**，让 CLI 基于现有 `ProjectSpec/` 重建全部资源。

### 3.1 检查是否需要升级

```bash
python3 .doc-kit/cli/cli.py tool status
```

输出会告诉你当前 CLI 版本 vs 项目记录版本、落后几个版本、期间改了什么，以及副本是否被改动或缺失。

### 3.2 执行升级

```bash
# 1. 删除旧的工具链副本
rm -rf <项目根>/.doc-kit

# 2. 重新初始化（基于现有 ProjectSpec/ 重建 .doc-kit/，不改动 ProjectSpec/）
doc-kit init <项目根>

# 3. 从 ProjectSpec/ 重建文档索引（init 只为本次新建的文档建索引，已有文档需 reindex）
python3 <项目根>/.doc-kit/cli/cli.py doc reindex

# 4. 刷新 agent 侧的 skills
doc-kit install-skills <agent 的 skills 目录>
```

完成后重新开始本次议题/开发流程即可。

---

## 4. Skills 简介

共 8 个 skill，分为「议题侧」和「开发执行侧」两组，统一通过 `.doc-kit/cli/cli.py` 操作项目状态。

### 议题侧（讨论 → 决议 → 落盘）

| Skill | 作用 |
|---|---|
| **spec-start** | 议题唯一入口。新对话续接上次议题（复述待决议议程），或在无议题时确认议程后创建 |
| **spec-pause** | 临时收口：把当前讨论落盘为会议纪要（只写 `SessionSpec/`，不写 `ProjectSpec/`、不改状态） |
| **spec-close** | 收尾。保留成果 → 落盘纪要 → 梳理决议的文档归宿 → 审核后写入 `ProjectSpec/` → 归档；或作废（只记原因直接归档） |
| **spec-archive** | 归档兜底：关闭/作废后未归档的残局清理（正常流程已内联在 spec-close 末尾） |

### 开发执行侧（实现 → 验证 → 提交）

| Skill | 作用 |
|---|---|
| **spec-dev-loop** | 把 `ProjectSpec/` 里的设计忠实实现成代码：读设计 → 骨架化 → 委托实现 → 测试 → 对齐收尾。全程 `ProjectSpec/` 只读 |
| **spec-code-review** | 提交 PR 前的设计文档一致性检查：按 git 评审锚点范围，并排比对代码与文档，逐条判定差异，写入评审报告 |
| **spec-code-smell** | 代码异味扫描（重复代码、长参数列表、命名含糊等），支持快速/深入双模式，带证据与误报理由 |
| **spec-smart-git** | 智能提交：把工作区变更按 feat/fix/docs/refactor/chore 拆成语义独立的提交并逐个执行 |

---

## 5. App 简介

doc-kit 桌面 App（PySide6）是项目文档体系的**可视化管理界面**，与 CLI/skills 共享同一套 `ProjectSpec/` 数据。

### 主要功能区（左侧文档树 + 右侧 Tab）

| Tab | 功能 |
|---|---|
| **仪表盘** | 项目文档概览、模块/功能分布、快速入口 |
| **md 编辑器** | 所见即所得的 Markdown 编辑，frontmatter（doc_type / version / status / depends_on）与正文分栏维护 |
| **JSON 编辑器** | 直接编辑文档的 frontmatter 字段，适合批量改元数据 |
| **依赖图** | 基于 `depends_on` 绘制文档间依赖关系，支持反向依赖查询 |
| **生命周期** | 管理文档 active → deprecated → archived 的状态流转，批量归档 |
| **设置** | 项目配置、工具链版本查看 |

### 启动方式

```bash
doc-kit [项目根路径]      # 可选：直接加载指定项目
```

App 与 CLI 共用 `IndexManager`、`FrontmatterParser` 等核心引擎（`src/app/engine/`），任一侧的改动都会通过 `index.json` 同步到另一侧。

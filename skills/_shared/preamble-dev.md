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

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `{{TOOLCHAIN_VERSION}}` 生成。先运行 `python .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `{{TOOLCHAIN_VERSION}}`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

{{TOOLS}}

{{OUTPUT_CONVENTION}}

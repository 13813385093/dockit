# 最高优先级：

**三层边界（先看清各自走哪条路）**：

| 对象 | 读写方式 |
|------|---------|
| `ProjectSpec/`（设计文档） | **经 CLI**：`doc structure` / `doc read` 只读；本技能**不写** ProjectSpec |
| **源码、diff、工作区文件** | **只读**（`bash` / 文件工具）；本技能只给方向，不自动改代码、不写报告 |
| git 仓库操作 | **一律用 `bash`**（CLI 不执行 git）：`git status` / `git diff` / `git log` / `git rev-parse` |

**例外（能力库，仅读）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/`，包含 `doc-capabilities/` 与 `smell-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接读取，禁止写入**——按 `smell-capabilities/_index.md` 加载规则与源文件发现口径。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`；且当前目录必须是 git 仓库。任一不满足即输出终止文案——未初始化时给出「请人工执行 `doc-kit init <项目根>`，再执行 `doc-kit install-skills <agent 技能目录>`」——不再执行后续步骤。**初始化由人工完成，不要尝试任何自举安装。**

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `{{TOOLCHAIN_VERSION}}` 生成。先运行 `python3 .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `{{TOOLCHAIN_VERSION}}`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

> 若 `python3` 不在 PATH（部分 Windows 环境只有 `python` 或 `py -3`），把命令中的 `python3` 替换为可用解释器；`command not found` 不代表工具链损坏。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

{{TOOLS}}

{{OUTPUT_CONVENTION}}

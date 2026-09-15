# 最高优先级：

**三层边界（先看清各自走哪条路）**：

| 对象 | 读写方式 |
|------|---------|
| `ProjectSpec/`（设计文档） | **经 CLI**：`doc structure` / `doc read` 只读；需要改文档时（仅 `spec-code-review` 的后续动作）必须先读 `_index.md` 定位 doc_type + 读能力文件 + **经用户确认**后再 `doc update-section` / `doc add-section` |
| **源码、diff、工作区文件** | **直接读写**（`bash` / 文件工具）。CLI 不介入代码与工作区 |
| git 仓库操作 | **一律用 `bash`**（CLI 不执行 git）：`git status` / `git diff` / `git log` / `git add` / `git commit` / `git push` |

**例外（能力库，仅读）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接 read_file 读取，禁止写入**——辅助判断 diff 涉及的文档类型、或按 `_index.md` §2/§3 路由文档写入位置时对照能力文件。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`；且当前目录必须是 git 仓库。任一不满足即输出终止文案，不再执行后续步骤。

**工具链版本自检（进入流程先做）**：本技能随工具链版本 `{{TOOLCHAIN_VERSION}}` 生成。先运行 `python .doc-kit/cli/cli.py tool status`：

- `data.toolchain_version` **等于** `{{TOOLCHAIN_VERSION}}`，且 `data.stale` 为 `false`、`data.consistent` 为 `true` → 继续本次流程；
- 否则（版本不等 / `stale` / 副本被改动或缺失 / 无 toolchain.json）→ **暂停本次流程**，把 `suggestions` 原文转述给用户，请其运行 `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>` 同步（只刷新 `.doc-kit/`，不改动 `ProjectSpec/`），同步完成后再重新开始；
- **若 `tool status` 命令本身不存在、参数不认识，或 CLI 直接抛 Python 错误**（如 `invalid choice: 'tool'`、`unrecognized arguments`、`ModuleNotFoundError`）→ 说明项目内的 CLI 比本技能旧、或副本被删改（此时它自己已无法自检）：同样**暂停本次流程**，告知用户「项目 `.doc-kit/` 与当前技能版本不配套」，并请其重跑上述两条同步命令。

为什么必须有这一步：`init` 是把工具链**快照复制**进项目，之后两边各自演化；而新版技能配旧版 CLI 时，旧 CLI 会**静默丢弃**它不认识的字段（命令仍报"已保存"），导致关键信息凭空消失。

工具调用（从项目根执行）：

{{TOOLS}}

{{OUTPUT_CONVENTION}}

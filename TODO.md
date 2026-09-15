# 待办：技能与工具链（评审遗留）

> 来源：2026-09 技能评审（原 `skills-review/` 记录已按结论归档删除）
> 记录时的工具链版本：**2026.09.2**（`skills/scripts/cli.py` 的 `TOOLCHAIN_VERSION`）
> 已完成的改造（议题类技能、spec-dev-loop 骨架化、模块三评审、共享前言生成、工具链版本机制）
> 其结论都已落进 `skills/`、`src/`、`tests/`，本文件只保留**尚未执行**的事项。

## 相关约定（改工具链前必读）

改 `skills/**` 或 `src/app/templates/**` 后按 5 步走，缺一步会被检具拦住：

```bash
# 1 改内容 → 2 递增 cli.py 的 TOOLCHAIN_VERSION（YYYY.MM.N）
python tests/render_skill_preamble.py                   # 3 把新版本注入 9 份 SKILL.md
python tests/check_toolchain_version.py --update --note "<一句变更说明>"   # 4 更新指纹 + 追加版本历史
python -m pytest tests/                                 # 5 四个检具 + 全量测试
```

> 完整说明见 `tests/check_toolchain_version.py` 头部注释。

---

## A. 入口与路由

### A1 缺初始化技能（原 B4）

- **现状**：9 份 SKILL.md 的前置条件都是"未初始化即终止"，而初始化只能人工执行
  `doc-kit init <项目根>` 与 `doc-kit install-skills <agent 技能目录>`；`skills/` 下没有初始化类技能。
- **影响**：AI 在未初始化的项目里无法自举，只能终止流程让用户手工操作。
- **建议**：新增 `spec-init` 技能（指导跑上述两条命令 + `tool status` 自检）；
  或维持现状，但把终止话术写成可直接执行的命令。

### A2 缺总路由（原 B5）

- **现状**：`spec-load` 明确"不做 DevSpec 状态检查"（正文边界第 2 条）；开发循环进行中开新对话时，
  没有任何技能同时看 `spec status` 与 `dev status`。
- **影响**：有活跃开发循环时，AI 可能走错岔路（去开新议题/新循环）。
- **建议**：把 `spec-load` 升级为总路由（加一步 dev 状态检查并复述开发进度），或新增独立 router 技能。

## B. 检具与契约

### B1 `spec status` 缺机器可读输出（原 B8）

- **现状**：`spec status` 只输出一行中文散文；`spec-load` 已改按 `spec read` 的 JSON 判定，
  但 `spec-start` Step 0、`spec-archive` Step 1 仍读中文串。
- **影响**：CLI 文案一改，技能路由即失效（隐式耦合）。
- **建议**：加 `spec status --json`（`{success, data:{session_spec_id, status}}`），技能改按字段路由。

### B2 检具覆盖不足（原 B9）

- **现状**：`tests/check_skill_sync.py` 只查"命令是否存在 + 技能名一致性"；
  "状态值/任务卡字段/占位符格式"这类检查仅存在于 dev-loop 专用测试（`tests/test_dev_loop_skill.py`）。
- **影响**：同类问题在其它 8 份技能里不会在 CI 被拦住。
- **建议**：把规则提升到 `check_skill_sync.py` 覆盖 9 个技能（允许值可直接从 CLI 导出：
  `DEV_TASK_STATUSES`、`SPEC_SCHEMA`）。

## C. 项目卫生

### C1 `init` 不生成 `.gitignore`（原 B12）

- **现状**：`init` 不写 `.gitignore`；`.doc-kit/` 一旦被 `git add -A` 提交，实测
  `git checkout <分支>` 会因"本地修改将被检出操作覆盖"**直接失败**，并污染 `git diff --stat`
  （会让 dev-loop 的"只改了声明的文件"验收误判）。
- **现状缓解**：`spec-smart-git` 的忽略检查清单已加入工具状态目录。
- **建议**：`init` 生成/追加 `.gitignore`（至少 `.doc-kit/`），或在 GUI/README 明确提示；
  `SessionSpec/active/`、`DevSpec/active/` 是否入库由用户决定（`archive/` 里的 CodeNotes 与报告通常值得保留）。

## D. 版本管理的延伸

### D1 数据格式版本 + 通用迁移表

- **现状**：工具链有了版本，但**数据格式**（`tasks.json`、`*.spec.json`、`plan.md` 章节名）没有版本；
  目前只有一处手写兼容：`DEV_LEGACY_TASK_STATUSES` 把 `in-progress/unit-green/fixing`
  映射到 `implementing/tested/rejected`（读取时映射，写操作落盘迁移）。
- **影响**：下次结构变更仍会重演"在途会话死锁"——旧数据配新 CLI 无法推进，
  `task update` 报非法迁移、`task set` 补救又要求新字段。
- **建议**：各数据文件带 `schema_version`，CLI 读取时按迁移表升级并在输出中提示已迁移。

### D2 工具链分发：一条命令同步（B10 后续）

- **现状**：同步仍是两步——`doc-kit init <项目根>`（只刷新 `.doc-kit/`，不动 ProjectSpec）
  + `doc-kit install-skills <agent 技能目录>`；已验证有效，但用户不知道要跑。
- **建议**：新增 `doc-kit sync <项目> [--agent-dir <目录>]`，一次刷新两侧并打印版本差异摘要；
  GUI 检测到项目 `toolchain.json` 版本与程序版本不一致时给出提示。

### D3 接入 CI

- **现状**：仓库没有任何 CI 配置（无 `.github/workflows`、`.gitlab-ci.yml`、`.gitee/`），
  四个检具只能手动跑。
- **建议**：接入下面五条（仓库在 Gitee 用 `.workflow/`，GitHub 用 `.github/workflows/`）：

```bash
python -m pytest tests/
python tests/check_skill_sync.py
python tests/check_doc_consistency.py
python tests/check_toolchain_version.py
python tests/render_skill_preamble.py --check
```

## E. 已评估、暂不改（保留结论，避免重复讨论）

### E1 技能命名体系

- **现状**：`spec-` 前缀同时指 SessionSpec（start/load/pause/close/abort/archive）、
  DevSpec（dev-loop）、ReviewSpec（code-review）。
- **结论**：**不改**。改名要动 9 个目录 + 检具 + `install-skills` + 用户习惯与文档，
  收益只是"名字更清楚"；替代方案（各技能开头写明作用于哪个 Spec）已部分具备。

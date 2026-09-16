# 待办：技能与工具链

> **本文件只记录尚未解决的问题。** 已解决的不保留——历史见 `skills/scripts/cli.py` 的
> `TOOLCHAIN_VERSION` 版本历史（每次发布都带一句变更说明）与 git 提交记录。
> 已判定"不改"的事项同样不保留，避免与待办混淆；将来若要重新评估，按下面的格式新开一条。

## 怎么记录一个问题

每条待办写四个字段。**写不出「现象」就不要记**——那说明还没到能动手的程度，先继续观察；
**写不出「触发条件」就说明它可能不该现在做**。

| 字段 | 要求 |
|---|---|
| **现象** | 可复现的事实：触发步骤 + 观察到的结果。实测优先于推测；没验证过的部分要标明"未验证" |
| **影响** | 具体后果：哪一步会失败、谁会误判、是否可逆。区分「会导致错误」与「只是不便」 |
| **触发条件** | 什么可观测的事件发生后，这条才值得动手。这是防止待办腐烂的关键字段 |
| **建议方案** | 首选做法 + **被否掉的做法及原因**（避免下次重复讨论同一组选项） |

命名：用**一句话标题**（如「技能正文里 CLI 调用的选项级校验」），**不要编号**——本文件按"解决即删除"维护，编号会随时间漂移，做不了稳定引用。
**解决后直接删除该条目**（不要改成"已完成"留着）。

---

## 相关约定（改工具链前必读）

改 `skills/**` 或 `src/app/templates/**` 后按 5 步走，缺一步会被检具拦住：

```bash
# 1 改内容 → 2 递增 cli.py 的 TOOLCHAIN_VERSION（YYYY.MM.N）
python tests/render_skill_preamble.py                   # 3 把新版本注入 7 份 SKILL.md
python tests/check_toolchain_version.py --update --note "<一句变更说明>"   # 4 更新指纹 + 追加版本历史
python -m pytest tests/                                 # 5 全量测试
```

- `python -m pytest tests/` **确实覆盖全部四个检具**：`check_skill_sync`（由
  `tests/test_skill_sync_collected.py` 包装）、`check_toolchain_version`（`test_toolchain.py`）、
  前言生成物一致性（`test_skill_preamble.py`）、`check_doc_consistency`（`test_doc_types.py`）。
  另有三组内容级检具同在其中：`test_cli_usage_contract.py`（USAGE 表 ↔ 真实 argparse 树）、
  `test_cli_self_consistency.py`（CLI 自己给出的建议必须能被 CLI 自己接受）、
  `test_skill_content_rules.py`（状态枚举、非真实状态名、前言断言、输出归属、描述预算）。
- **本仓库不接 CI**（2026-09-16 决定）：由作者本人维护，检具的价值在"改完立刻能跑"，
  而不在"有人替我记得跑"；多一条流水线只是给上面这套流程再加一层需要维护的配置。

---

## 待办

### 升级时不会清理已下线的技能副本（9→7 合并后需手工删）

- **现象**：`copy_skills()`（`src/app/engine/commands/init_utils.py:180`）与
  `_cmd_install_skills()`（`src/app/main.py:68`）**都只 `glob("spec-*")` + `copy2`，不含任何删除**；
  同文件里 `LEGACY_TEMPLATE_FILES` / `LEGACY_CAPABILITY_FILES` 两套"已下线文件"清理清单
  **没有对应的技能版本**。而 `tool status` 只按 `.doc-kit/toolchain.json` 里记录的清单核对，
  **多出来的陈旧文件它看不见**（只会报 `mismatched` / `missing`）。
- **影响**：2026-09 把 9 份技能合并为 7 份后：
  ① `<项目根>/.doc-kit/skills/` 里会残留 `spec-load/`、`spec-abort/`——**任何直接读这个目录的 agent 都会看到两份已作废的技能**；
  ② 若 agent 侧是**复制**式安装（`install-skills <目录>` 或人工搬运），陈旧副本还会长期存在，并与合并后的技能给出**互相矛盾**的指令
  （旧 `spec-start` 写"已有活跃议题改走 spec-load 续接"、旧 `spec-close` 写"不要成果请改用 spec-abort"）。
- **触发条件**：每次发生技能下线、合并或改名时。（下次仍会出现，不是一次性问题。）
- **现状缓解**：agent 侧改为**指向** `<项目根>/.doc-kit/skills`（目录软链，或 DSH 的 `customSkillDirs`），
  而不是持有副本——此时"源里删掉即消失"，第 ② 类影响不存在；第 ① 类仍需手工删一次。
- **建议方案**：加 `LEGACY_SKILL_DIRS = ("spec-load", "spec-abort")`（按版本累积），
  由 `copy_skills()` 清理 `<项目根>/.doc-kit/skills/` 下的已下线目录；`_cmd_install_skills()` 同样清理，
  给仍走复制式的场景兜底。
  （被否：只靠文档要求人工删除——已验证会漏。）

### 技能正文里 CLI 调用的**选项级**正确性不在检具覆盖内

- **现象**：往 `skills/spec-dev-loop/SKILL.md` 正文写入一个不存在的选项
  （`` `python .doc-kit/cli/cli.py dev task update T1 --status pending --bogus-flag x` ``）后，
  `pytest tests/` 全绿——唯一失败的是版本指纹守卫，与选项无关。
- **覆盖边界**：`check_skill_sync` 只校验**命令路径**（正则最多匹配"命令组 + 2 个单词"）；
  `test_cli_usage_contract` 只校验 **USAGE 表**，而 USAGE 表只覆盖技能**声明**的工具清单，
  正文里的具体调用不在其中。
- **影响**：技能正文写错选项无人发现，AI 会照着调用并失败。属「会导致错误」一级。
- **触发条件**：下次在技能正文里新增或修改 CLI 调用时。
- **建议方案**：把校验对象从 USAGE 表扩展到"全部 SKILL.md 正文里的 `cli.py` 调用"——
  抽出每个调用用到的选项，逐个对照真实 argparse 树。
  （被否：暂无可否方案；成本不高，只是目前没做。）

### `init` 不生成 `.gitignore`（暂缓）

- **现象**：`init` 不写 `.gitignore`；`.doc-kit/` 一旦被 `git add -A` 提交，实测
  `git checkout <分支>` 会因"本地修改将被检出操作覆盖"直接失败，并污染 `git diff --stat`。
- **影响**：① 分支切换失败；② `spec-dev-loop` 验收清单第 2 项（只改了声明的文件；排除规则只有
  `DevSpec/` 与 `SessionSpec/`）会把 `.doc-kit/` 的改动当成"改了多余文件"而**误判不合格**——
  即验收闸门出现假报警。
- **现状缓解**：`spec-smart-git` 的忽略检查清单已含工具状态目录。
- **触发条件**：实际遇到上述任一失败时。
- **暂缓理由（2026-09-16 决定）**：`.gitignore` 本就该由人掌握，`.doc-kit/` 也不该提交进仓库；
  让开发人员自己掌握没有坏处。
- **建议方案**（真要做时）：优先改 `spec-dev-loop` 验收清单第 2 项，补 `':(exclude).doc-kit/'`
  ——它不依赖用户是否记得忽略，比让 `init` 写 `.gitignore` 更稳。
  （被否：让 `init` 生成/追加 `.gitignore`——把本该由人掌握的东西自动化。）

### 数据格式版本 + 通用迁移表（暂缓）

- **现象**：工具链有了版本，但**数据格式**（`tasks.json`、`*.spec.json`、`plan.md` 章节名）没有版本；
  目前只有一处手写兼容：`DEV_LEGACY_TASK_STATUSES` 把 `in-progress/unit-green/fixing` 映射到
  `implementing/tested/rejected`（读取时映射，写操作落盘迁移）。
- **影响**：结构再变时会重演"在途会话死锁"——旧数据配新 CLI 无法推进，`task update` 报非法迁移、
  `task set` 补救又要求新字段。属「会导致错误」一级。
- **触发条件**：下一次改动上述任一数据结构时。
- **暂缓理由**：现在写迁移表等于猜；届时变更形状是已知的，建表才有意义。
- **备注**：2026-09 的 `spec write` 未知字段校验刻意做成"拒绝**新增**未知字段、放行磁盘上已存在的"，
  正是按这条的教训办事——不让在途会话因为新校验被卡住。
- **建议方案**：各数据文件带 `schema_version`，CLI 读取时按迁移表升级并在输出中提示已迁移。

### 工具链分发：一条命令同步（暂缓）

- **现象**：同步仍是两步——`doc-kit init <项目根>`（只刷新 `.doc-kit/`，不动 `ProjectSpec/`）
  + `doc-kit install-skills <agent 技能目录>`；已验证有效，但用户不知道要跑。
- **影响**：不便（不是错误）：版本落后时只刷新了一侧，技能与 CLI 不配套。
- **触发条件**：下游项目变多，或同步动作变得频繁。参考量级：2026-09-16 单日发布 8 个版本，
  停留在旧版本的项目会在 `tool status` 看到"落后 8 版 + 8 条变更说明"。
- **建议方案**：新增 `doc-kit sync <项目> [--agent-dir <目录>]`，一次刷新两侧并打印版本差异摘要；
  GUI 检测到项目 `toolchain.json` 版本与程序版本不一致时给出提示。

---
name: spec-pause
description: 保存当前议题进度，提取决议并写入文档，不改变状态
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**CLI 定位（按优先级，执行前先确认）**：
1. 项目内已部署：`<项目根>/.doc-kit/cli/cli.py`
2. 项目内 skill 目录：`<项目根>/skills/scripts/cli.py`
3. 全局 skills 目录：`$REASONIX_HOME/skills/`（Windows 默认 `%APPDATA%\reasonix`，macOS/Linux `~/.reasonix`）下任意 `*/scripts/cli.py`（可用 `find` 在 workspace 与上述目录中搜索）

**首次自举**：若 1 不存在，先运行 `python <定位到的 cli.py> deploy`，将 CLI 部署到 `<项目根>/.doc-kit/cli/`。部署后一律从项目根调用：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
python .doc-kit/cli/cli.py spec schema
python .doc-kit/cli/cli.py doc structure
python .doc-kit/cli/cli.py doc read <path>
python .doc-kit/cli/cli.py doc update-section <reference> --content '<正文>'
python .doc-kit/cli/cli.py doc add-section <reference> '<标题>' --content '<正文>' [--level sibling|child]
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败；纯文本输出（spec read / spec schema）以「错误:」开头即失败。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根。
---

# spec-pause — 保存当前议题进度

## 定位

会议暂停时保存进度，不改变状态。数据变更需先经用户确认。

操作矩阵：

| 分项 | 允许的操作 | 说明 |
|------|-----------|------|
| 决议 | 仅新增 | 决议不可修改或删除，修正需另开议题 |
| 待定决议 | 新增 + 状态改为 resolved | 不存在删除，不需要讨论的标记为 resolved |
| 后续计划 | 新增 + 删除 | 按文本精确匹配删除 |

> 以上操作在 skill 层通过 `spec read` → 内存修改 → `spec write --json '<spec_json>'` 实现。

## 在哪选

`active` 状态下，当用户说「就到这里」「先保存」「下次继续」时。

## 选择判断

### Step 1：提取变更

从本次对话中提取：

- 哪些议题达成了明确结论 → `resolutions[]` 新增
- 哪些待定决议有了进展或已有明确答案 → `pending_decisions[].status` 变更
- 哪些新问题悬而未决 → `pending_decisions[]` 新增
- 下一步要做什么 → `next_steps[]` 新增
- 哪些旧的后续计划已不需要 → `next_steps[]` 删除

### Step 2：完整化 Detail（必填，≥150 字）

`detail` 是**必填字段**，最少 **150 字**。它是后续写入文档段落的主要信息来源。

对每条决议，AI 应主动引导用户补充 detail。一个好 detail 包含以下要素：

| 要素 | 说明 | 适用于 |
|------|------|--------|
| 决策理由/Why | 为什么选这个方案？解决了什么问题？ | 所有决议 |
| 替代方案 | 不选什么？为什么不选？ | 技术/功能决策 |
| 约束条件 | 有什么 MUST/SHOULD 限制？ | 技术/约束类 |
| 影响范围 | 影响哪些模块或功能？ | 跨模块决策 |
| 具体配置/参数 | 如版本号、阈值、协议参数 | 技术选型类 |

AI 也可根据对话上下文中已有的信息主动整理 detail 让用户确认。

### Step 3：决议写入文档

对每条已确认的决议，按以下流程动态决定写入位置：

1. 调 `python .doc-kit/cli/cli.py doc structure` 查看当前 ProjectSpec/ 下所有文档及其 section 结构
2. 根据决议内容和文档的 `level`（top/module/feature）判断适合的文档
3. 调 `python .doc-kit/cli/cli.py doc read <path>` 查看目标文档当前内容
4. 判断是更新已有 section（`doc update-section <reference> --content '<正文>'`）还是新增 section（`doc add-section <reference> '<标题>' --content '<正文>'`）
5. 汇总所有待写入操作，形成清单

> **缓存提示**：`doc structure` 的结果在 Step 6 中同样需要用到，建议将返回缓存在内存中，无需重复调用。

> **约束一致性**：决议中的 `[MUST]` / `[SHOULD]` / `[MAY]` 标记应忠实地保留到目标文档中，不可降级或升格。

### Step 4：用户确认

展示变更清单给用户确认。格式示例：

```
📋 今天的变更清单，请确认：

✅ 新增决议（共 N 条）：
  ① 决议标题（简要）
     detail：…（N 字 ✅/❌）
     → 计划写入：xxx.md → §段落名（doc update-section / doc add-section）

❓ 待定决议：
  - 议题 [needs_discussion]：备注（新增）
  - 议题 [resolved]：备注（已解决）

📌 后续计划：
  + 新增项
  - 删除项
```

以上是否正确？各条 detail 是否需要调整？

### Step 5：组装完整 spec

调 `python .doc-kit/cli/cli.py spec read` 获取当前议题的完整数据，然后根据 Step 1 的提取结果修改内存中的 spec：

| 变更操作 | 做法 |
|---------|------|
| 新增决议 | `spec["resolutions"].append({"topic": ..., "decision": ..., "detail": ...})` |
| 变更待定决议状态 | 按 `topic` 匹配后改 `status` |
| 新增待定决议 | `spec["pending_decisions"].append({"topic": ..., "status": "needs_discussion", "note": ...})` |
| 新增后续计划 | `spec["next_steps"].append(...)` |
| 删除后续计划 | `spec["next_steps"].remove(...)` 或 list comprehension |

> 调用 `python .doc-kit/cli/cli.py spec schema` 可以获取各字段的详细约束（如 `detail` 最小 150 字）。

### Step 6：调用工具

用户确认后：

1. **先**调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'` — 将完整 spec 写回（全量替换模式，保存决议/待定/计划到 SessionSpec/）
2. **后**按用户确认的写入清单，逐条调 `doc update-section` 或 `doc add-section` 写入文档（写入 ProjectSpec/）

> **写入时机**：spec write 调用后才写入文档，确保会议纪要已安全保存。

## 边界

- 不改变 status（保持 `active`）
- Topic 名称是待定决议匹配的 key，必须精确一致
- **每条决议的 `detail` 必须 ≥150 字符**，否则 spec_write 的 Schema 校验会拒绝保存
- 决议→文档映射通过 `doc structure` 动态判断，不预置硬编码映射
- 写入文档的操作必须经用户确认后再执行

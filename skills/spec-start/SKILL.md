---
name: spec-start
description: 开启新议题，提取 topic / scenario 并生成 session_spec_id
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）：

```bash
cd <项目根目录>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python skills/scripts/cli.py spec status
python skills/scripts/cli.py spec read
python skills/scripts/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
python skills/scripts/cli.py spec schema
python skills/scripts/cli.py doc structure
python skills/scripts/cli.py doc read <path>
python skills/scripts/cli.py doc update-section <reference> --content '<正文>'
python skills/scripts/cli.py doc add-section <reference> '<标题>' --content '<正文>' [--level sibling|child]
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败；纯文本输出（spec status / spec read / spec schema）以「错误:」开头即失败。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根。
---
# spec-start — 开启新议题

## 定位

当用户提出一个需求或想法、当前没有活跃议题时，选择此岔路。

## 在哪选

这是 `idle` 状态下的唯一岔路。如果没有活跃议题，这就是第一步。

## 选择判断

### Step 0：确认当前状态

调 `python skills/scripts/cli.py spec status` 确认。如果返回「当前有活跃议题」，则引导用户先处理已有议题。

### Step 1：获取数据模板

调 `python skills/scripts/cli.py spec schema` 了解 SpecStruct 的字段定义（类型、允许值、约束），为组装初始数据做准备。

### Step 2：提取议题信息

从用户描述中提取：
- **topic**（2-6 个英文词概括）→ 用于生成 `session_spec_id`
- **scenario**：
  - 纯需求讨论、业务背景、目标用户 → `spec-scribe`
  - 技术选型、模块划分、架构设计 → `tech-ref`
  - 功能规格、测试用例、实现细节 → `feature-dev`

### Step 3：生成 session_spec_id

按格式 `{当天日期}-{topic-kebab}` 生成，例如 `20260618-cert-auth`。

向用户提议议题名称，等待确认。

### Step 4：组装初始 spec 并写入

按 spec schema 输出的结构组装完整的 spec JSON，调 `python skills/scripts/cli.py spec write --json '<spec_json>'`。

> 注意：`project`、`created_at`、`related_doc_types` 等字段由服务端自动填充，无需传入。

### 创建后的引导

议题创建完成后，调 `python skills/scripts/cli.py doc structure` 查看当前项目的文档结构。
每个文档节点带有 `level` 字段（top / module / feature），可作为引导用户的参考：

| scenario | 建议优先关注的文档层级 |
|----------|----------------------|
| spec-scribe（需求讨论） | `top` 或 `module` |
| tech-ref（技术评审）   | `top` 或 `module` |
| feature-dev（功能设计）  | `feature` |

根据文档结构引导用户选择要填写的文档方向。
后续在 spec-pause 或 spec-close 阶段再通过 `doc read` / `doc update-section` / `doc add-section` 完成具体写入。

## 成功后的状态

进入 `active`。`spec write` 返回的摘要包含当前决议、待定决议和后续计划（全空）。

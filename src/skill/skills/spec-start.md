# spec-start — 开启新议题

## 定位

当用户提出一个需求或想法、当前没有活跃议题时，选择此岔路。

字段定义见运行时生成的 `.reasonix/spec-template.json`。

## 在哪选

这是 `idle` 状态下的唯一岔路。如果没有活跃议题，这就是第一步。

## 选择判断

调 `spec_status()` 确认当前状态。当返回「没有活跃议题」时：

1. 从用户描述中提取 **topic**（2-6 个英文词概括）
2. 判断 **scenario**：
   - 纯需求讨论、业务背景、目标用户 → `spec-scribe`
   - 技术选型、模块划分、架构设计 → `tech-ref`
   - 功能规格、测试用例、实现细节 → `feature-dev`
3. 向用户提议议题名称，等待确认
4. 用户确认后，调 `spec_start(topic, scenario)` 完成创建

## 创建后的引导

议题创建完成后，调 `doc_structure()` 查看当前项目的文档结构。
每个文档节点带有 `level` 字段（top / module / feature），可作为引导用户的参考：

| scenario | 建议优先关注的文档层级 |
|----------|----------------------|
| spec-scribe（需求讨论） | `top` 或 `module` |
| tech-ref（技术评审）   | `top` 或 `module` |
| feature-dev（功能设计）  | `feature` |

根据文档结构引导用户选择要填写的文档方向。
后续在 spec-pause 或 spec-close 阶段再通过 `read_doc()` / `update_section()` / `add_section()` 完成具体写入。

## 成功后的状态

进入 `active`。MCP 返回的状态摘要包含当前决议、待定决议和后续计划（全空）。

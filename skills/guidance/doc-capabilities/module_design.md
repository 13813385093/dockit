# 能力说明：module_design（module-design.md）

> 指南：§3.6.5 / §3.7 / 类型 T-C2（维护索引，供指南更新时同步本文件；AI 无需访问）
> 层级：Level 1（module）· **精简模式复合** · 位于 `module-<模块名>/`

## 定位

精简模式复合模块设计：architecture + domain_model + module_manifest 合一（integration 可选）。模块骨架文档——`doc new module_design --module <名>` 创建它时自动建立 `module-<名>/` 目录。

## 承载的决议主题

| 决议主题 | 目标章节 |
|---------|---------|
| 模块职责 / 组件划分 / 接口清单 / 关键流程 | ## 架构设计 |
| 聚合根 / 实体 / 值对象 / 领域约束 | ## 领域模型 |
| exports / imports 能力声明 | ## 模块清单 |
| 外部系统集成（可选） | ## 外部集成 |

## 段落结构

每个 `##` 章节对应一个基础类型，内部章节与对应基础类型能力文件一致：

- ## 架构设计 → 模块概述 / 核心能力 / 组件划分 / 对外接口 / 对内接口 / 关键流程（同 `architecture`）
- ## 领域模型 → 聚合根 / 实体 / 值对象 / 领域约束（同 `domain_model`）
- ## 模块清单 → Exports / Imports（同 `module_manifest`，import↔export 配对）
- ## 外部集成（可选）→ 外部系统概览 / 集成方式与协议 / 数据流与同步策略 / 错误处理与降级（同 `integration`）

写作规则与对应基础类型能力文件相同。

## 行文规则

**必须**
- **约束 ID 在整个文档内唯一**（跨章节不重复）
- `contains` frontmatter 与正文章节保持一致；integration 可选，不在列表即视为省略
- 拆分（§3.7）时各 `##` 章节成为独立基础文档，版本初始化为 0.1.0

**禁止**
- ❌ 模块骨架已建（module-design.md 存在）后，在精简模式下继续创建模块级独立基础文档（architecture 等，`doc new` 以 `new_doc.minimal_profile` 拒绝）→ 先拆分或写入本文档

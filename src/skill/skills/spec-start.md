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

## Scenario → 文档模板映射

根据 scenario 类型，创建议题后应引导用户使用对应的文档模板开始编写。

选择使用**复合模板**（精简模式）或**拆分模板**（完整模式）取决于项目规模和成熟度：
- 项目初期或小型项目：使用复合模板（charter / module-design / feature-package）
- 项目成熟或大型项目：使用拆分模板（每个 doc_type 独立文件）

### spec-scribe（需求讨论）

对应的文档模板——**业务需求与干系人分析**：

| 文档类型 | doc_type | 模板路径 | 核心填写章节 |
|---------|---------|---------|------------|
| 业务背景 | `business_context` | `templates/business-context.md` | 项目动因、项目目标、目标用户、关键术语表 |
| 干系人分析 | `stakeholders` | `templates/stakeholders.md` | 角色定义、关注点、参与方式、信息需求（可选） |
| **精简模式** | `charter` | `templates/charter.md` | 合并上述内容到 ## 业务背景 和可选章节 |

**填写指引**（按 resolutions 中的议题讨论结果填充）：

| 决议主题方向 | 对应章节 |
|------------|---------|
| 项目起源/问题背景 | `business-context.md` → §项目动因 |
| 核心目标/KPI | `business-context.md` → §项目目标 |
| 用户画像/目标用户 | `business-context.md` → §目标用户 ↔ `stakeholders.md` |
| 术语定义 | `business-context.md` → §关键术语表 |
| 干系人与决策权 | `stakeholders.md` → §干系人总览 |

### tech-ref（技术评审）

对应的文档模板——**技术架构与模块设计**：

| 文档类型 | doc_type | 模板路径 | 核心填写章节 |
|---------|---------|---------|------------|
| 技术框架 | `technical_framework` | `templates/technical-framework.md` | 语言与运行时、框架与中间件、数据存储、通信协议 |
| 技术约束 | `technical_constraints` | `templates/technical-constraints.md` | 性能指标、可用性与可靠性、安全要求、合规与标准、兼容性 |
| 全局策略 | `global_policies` | `templates/global-policies.md` | 架构模式、安全与认证、可观测性、数据一致性、异常处理、合规与审计、代码规范、命名约定、依赖管理 |
| 模块间契约 | `inter_module_contract` | `templates/inter-module-contracts.md` | 模块边界概览、同步接口定义、异步消息与事件、共享数据结构 |
| 模块架构 | `architecture` | `templates/architecture.md` | 模块概述、核心能力、组件划分、对外接口、关键流程 |
| 领域模型 | `domain_model` | `templates/domain-model.md` | 聚合根、实体、值对象、领域约束 |
| 外部集成 | `integration` | `templates/integration.md` | 外部系统概览、集成方式与协议、数据流与同步、错误处理与降级（可选） |
| 模块清单 | `module_manifest` | `templates/module-manifest.md` | Exports（对外能力）、Imports（依赖能力） |
| **精简模式** | `module_design` | `templates/module-design.md` | 合并架构+领域模型+清单+集成到一个文件 |

**填写指引**（按 resolutions 中的议题讨论结果填充）：

| 决议主题方向 | 对应章节 |
|------------|---------|
| 编程语言/运行时 | `technical-framework.md` → §语言与运行时 |
| 框架/中间件选型 | `technical-framework.md` → §框架与中间件 |
| 数据库/存储选型 | `technical-framework.md` → §数据存储 |
| 通信协议选择 | `technical-framework.md` → §通信协议 ← `inter-module-contracts.md` |
| 性能指标要求 | `technical-constraints.md` → §性能指标 |
| 安全/合规要求 | `technical-constraints.md` → §安全要求 / §合规与标准 |
| 架构模式决策 | `global-policies.md` → §架构模式 |
| 认证/授权策略 | `global-policies.md` → §安全与认证 |
| 日志/监控策略 | `global-policies.md` → §可观测性 |
| 模块划分/职责 | `architecture.md` → §模块概述 / §核心能力 / §组件划分 |
| 模块接口定义 | `inter-module-contracts.md` → §同步接口定义 / §异步消息与事件 |
| 领域实体定义 | `domain-model.md` → §聚合根 / §实体 / §值对象 |
| namespace/kebab-case 等 | `global-policies.md` → §命名约定 |

### feature-dev（功能设计与测试）

对应的文档模板——**功能规格与测试验证**：

| 文档类型 | doc_type | 模板路径 | 核心填写章节 |
|---------|---------|---------|------------|
| 功能设计 | `feature_design` | `templates/feature-design.md` | 功能描述、触发条件、前置条件、处理流程、异常路径、边界约束 |
| 决策日志 | `decision_log` | `templates/decision-log.md` | 问题描述、业务Why、技术Why、替代方案分析、最终决策 |
| 单元测试 | `unit_test` | `templates/unit-tests.md` | GWT 测试用例（Given-When-Then） |
| 验收测试 | `acceptance_test` | `templates/acceptance-tests.md` | Gherkin 功能场景（BDD） |
| **精简模式** | `feature_package` | `templates/feature-package.md` | 合并上述 4 种到一个文件 |

**填写指引**（按 resolutions 中的议题讨论结果填充）：

| 决议主题方向 | 对应章节 |
|------------|---------|
| 功能核心行为 | `feature-design.md` → §功能描述 / §处理流程 |
| 触发边界条件 | `feature-design.md` → §触发条件 / §边界约束 |
| 异常/降级处理 | `feature-design.md` → §异常路径 |
| 选型/方案对比 | `decision-log.md` → §问题描述 / §替代方案分析 / §最终决策 |
| 选型的业务理由 | `decision-log.md` → §业务Why |
| 选型的技术理由 | `decision-log.md` → §技术Why |
| 代码级验证场景 | `unit-tests.md` → GWT 测试用例 |
| 业务级验证场景 | `acceptance-tests.md` → Gherkin 场景 |
| 约束在测试中的断言 | `unit-tests.md` → Then 预期结果（约束标记 → 断言） |

### 整体依赖关系

文档之间的依赖关系（方便 AI 确定文档创建/更新顺序）：

```
spec-scribe:  业务背景 → 干系人（可选）
                    ↓
tech-ref:  技术框架 → 技术约束 → 全局策略 → 模块间契约
                    ↓
              模块架构 → 领域模型 → 模块清单
                    ↓
feature-dev: 功能设计 → 决策日志 → 单元测试 → 验收测试
```

## 成功后的状态

进入 `active`。MCP 返回的状态摘要包含当前决议、待定决议和后续计划（全空）。

建议根据 scenario 类型，后续步骤引导用户：
- **spec-scribe** → 引导用户填写 `business-context.md`（或 `charter.md`）中的业务背景章节
- **tech-ref** → 引导用户填写 `technical-framework.md`（或 `module-design.md`）的相关章节
- **feature-dev** → 引导用户填写 `feature-design.md`（或 `feature-package.md`）中的功能描述

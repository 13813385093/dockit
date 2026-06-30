# spec-pause — 保存当前议题进度

## 定位

物理会议结束时保存进度，不改变状态。数据变更需先经用户确认。

操作矩阵：

| 分项 | 允许的操作 | 说明 |
|------|-----------|------|
| 决议 | 仅新增 | 决议不可修改或删除，修正需另开议题 |
| 待定决议 | 新增 + 状态改为 resolved | 不存在删除，不需要讨论的标记为 resolved |
| 后续计划 | 新增 + 删除 | 按文本精确匹配删除 |

## 在哪选

`active` 状态下，当用户说「今天就到这里」「先保存」「下次继续」时。

## 选择判断

### Step 1：提取变更

从本次对话中提取：

- 哪些议题达成了明确结论 → `new_resolutions[]`
- 哪些待定决议有了进展或已有明确答案 → `pending_status_changes[]`
- 哪些新问题悬而未决 → `new_pending[]`
- 下一步要做什么 → `new_next_steps[]`
- 哪些旧的后续计划已不需要 → `remove_next_steps[]`

### Step 2：完整化 Detail（必填，≥150 字）

> ⚠️ `detail` 现在是**必填字段**，最少 **150 字**。
> 它不是「补充说明」，而是在 spec-docs 阶段生成文档段落的主要信息来源。
> **detail 越充分，spec-docs 生成的文档质量越高。**

#### detail 应该包含什么？

对每条决议，AI 应主动引导用户补充 detail。一个好 detail 包含以下要素：

| 要素 | 说明 | 适用于 |
|------|------|--------|
| **决策理由/Why** | 为什么选这个方案？解决了什么问题？ | 所有决议 |
| **替代方案** | 不选什么？为什么不选？ | 技术/功能决策 |
| **约束条件** | 有什么 MUST/SHOULD 限制？ | 技术/约束类 |
| **影响范围** | 影响哪些模块或功能？ | 跨模块决策 |
| **具体配置/参数** | 如版本号、阈值、协议参数 | 技术选型类 |

#### 构造 detail 的引导方式

当用户说了一条决议但 detail 不足时，AI 应追问补充：

```
> 好的，决议「认证方式：采用 OAuth2」已记录。
> 为了后续能自动生成文档，detail 还需要补充一些信息：
>
> - 为什么选择 OAuth2 而不是其他方案？（比如 JWT 自签发）
> - 授权模型是什么？RBAC 还是 ABAC？
> - 传输加密有什么要求？
> - 涉及哪些模块？
>
> 请补充以上信息，我将整理为 detail（需 ≥150 字）。
```

如果用户不愿意补充太多细节，AI 也可根据对话上下文中已有的信息主动整理 detail 让用户确认。

#### 常见决议的 detail 模板

| 决议类型 | detail 应包含 |
|---------|-------------|
| 项目目标 | 目标描述、期望的量化指标（MUST/SHOULD）、对业务的影响 |
| 技术选型 | 选型理由、对比过的方案、版本号、适用场景 |
| 性能指标 | 指标名称、目标值、约束级别（MUST/SHOULD）、在什么条件下测量 |
| 功能行为 | 触发条件、处理步骤、异常路径、预期结果 |
| 架构决策 | 决策背景、备选方案、选择这个方案的理由、影响范围 |

### Step 3：决议 → 文档段落映射

根据当前议题的 `scenario` 类型，判断已决议的内容是否应写入对应的文档模板。

#### spec-scribe（需求讨论）

决议内容写入 `templates/business-context.md` 或精简模式的 `templates/charter.md`：

| 决议 topic 关键词 | 目标文档 | 目标章节 | 写入方式 |
|------------------|---------|---------|---------|
| 项目动因、起源、问题 | business-context.md | §项目动因 | 一段话描述项目要解决的问题 |
| 项目目标、核心指标、KPI | business-context.md | §项目目标 | `[MUST]` / `[SHOULD]` 列表 |
| 用户、角色、目标用户 | business-context.md | §目标用户 | 表格形式（角色、特点、关注点） |
| 术语、定义、名词 | business-context.md | §关键术语表 | 术语表格式 |
| 干系人、利益相关方 | stakeholders.md | §干系人总览 | 表格形式（角色、职责、关注点、决策权） |

#### tech-ref（技术评审）

决议内容写入对应的技术文档模板：

| 决议 topic 关键词 | 目标文档 | 目标章节 | 写入方式 |
|------------------|---------|---------|---------|
| 语言选型、运行时、版本 | technical-framework.md | §语言与运行时 | 表格 + 选型理由 |
| 框架、中间件、消息队列 | technical-framework.md | §框架与中间件 | 表格 + 用途 + 备选方案 |
| 数据库、存储方案 | technical-framework.md | §数据存储 | 表格 + 用途 + 规模预估 |
| 通信协议、网络协议 | technical-framework.md | §通信协议 | 表格 + 方向 + 约束 |
| 性能指标、延迟、吞吐量 | technical-constraints.md | §性能指标 | 表格 + `[MUST]/[SHOULD]` |
| 可用性、可靠性、冗余 | technical-constraints.md | §可用性与可靠性 | 表格 + `[MUST]/[SHOULD]` |
| 安全、认证、加密 | technical-constraints.md 或 global-policies.md | §安全要求 / §安全与认证 | 表格 + 约束级别 |
| 合规、标准、法规 | technical-constraints.md | §合规与标准 | `[MUST]` / `[SHOULD]` 列表 |
| 架构模式、分层、微服务 | global-policies.md | §架构模式 | 表格 + 选型 + 说明 |
| 日志、监控、可观测性 | global-policies.md | §可观测性 | 表格 + 策略 + 说明 |
| 模块划分、职责边界 | architecture.md | §模块概述 / §核心能力 / §组件划分 | 表格（组件、职责、依赖） |
| 模块接口、API 定义 | inter-module-contracts.md | §同步接口定义 / §异步消息与事件 | 表格 + 签名 + 约束 |
| 领域实体、聚合根、值对象 | domain-model.md | §聚合根 / §实体 / §值对象 | 类型 + 属性表格 + 行为 + 约束 |
| 外部系统、第三方集成 | integration.md | §外部系统概览 / §集成方式 | 表格 + 协议 + 数据格式 |
| 模块依赖、exports/imports | module-manifest.md | §Exports / §Imports | 表格 + 签名 + 稳定性 |
| 命名规范、代码风格 | global-policies.md | §命名约定 / §代码规范 | 表格 + 约定 + 示例 |

#### feature-dev（功能设计与测试）

决议内容写入对应的功能文档模板：

| 决议 topic 关键词 | 目标文档 | 目标章节 | 写入方式 |
|------------------|---------|---------|---------|
| 功能描述、核心逻辑 | feature-design.md | §功能描述 | 一段话概括 |
| 触发条件、阈值、边界 | feature-design.md | §触发条件 / §边界约束 | 表格 + 阈值 + 约束级别 |
| 处理流程、业务步骤 | feature-design.md | §处理流程 | 编号列表 + 可选 Mermaid |
| 异常路径、降级、容错 | feature-design.md | §异常路径 | 表格（异常场景、处理方式、通知方式）|
| 前置条件、前提状态 | feature-design.md | §前置条件 | 列表 |
| 选型决策、方案对比 | decision-log.md | §问题描述 / §替代方案分析 / §最终决策 | 表格 + Why + 评估结果 |
| 测试场景、预期行为 | unit-tests.md | GWT 测试用例 | Given → When → Then |
| BDD 业务场景 | acceptance-tests.md | Gherkin 场景 | `功能:` `场景:` `假设/当/那么` |

> **写入原则**：决议写入 `spec.json` 后，应调 `doc_structure()` 查看 ProjectSpec/ 文档结构，
> 再通过 `update_section()` / `add_section()` 将决议内容同步到对应文档段落中。
> 两种操作均在 spec-pause 时完成，确保会议纪要 + 项目文档同时更新。

> **约束标记一致性**：决议中的 `[MUST]` / `[SHOULD]` / `[MAY]` 标记应忠实地保留到目标文档中，不可降级或升格。

### Step 4：用户确认

展示给用户确认，格式示例：

```
📋 今天的变更清单，请确认：

✅ 新增决议（共 2 条）：
  ① 认证方式：采用 OAuth2 + JWT
     detail：选择 OAuth2 是为了满足第三方系统安全接入要求，
     同时已有团队基础设施支持。授权模型采用 RBAC。
     传输加密使用 TLS 1.3。[MUST] 所有 API 必须携带 Bearer token。
     涉及模块：API 网关、用户服务、设备管理。
     （162 字 ✅）
     → 关联文档：global-policies.md §安全与认证

  ② 架构模式：微服务架构，消息总线选择 Kafka
     detail：采用微服务架构是为了支持各模块独立部署和扩展。
     消息总线选择 Kafka 而非 RabbitMQ，因为 Kafka 更适合
     高吞吐量场景（预估峰值 50000 msg/s）。Kafka 集群
     至少 3 节点。[MUST] 消息投递保证 at-least-once。
     涉及模块：所有业务模块。
     （138 字 ❌ 不足 150 字，请补充）

❓ 待定决议：
  - 日志方案 [needs_discussion]：ELK vs Loki（新增）
  - 缓存策略 [resolved]：留到功能设计（已解决）

📌 后续计划：
  + 调研 ELK 和 Loki

以上是否正确？各条 detail 是否需要调整？
```

### Step 5：调用工具

用户确认后，构造 JSON 参数（每条决议必须包含 `detail`，且 ≥150 字）：

```json
{
  "new_resolutions": [
    {
      "topic": "认证方式",
      "decision": "采用 OAuth2 + JWT",
      "detail": "选择 OAuth2 是为了满足第三方系统安全接入要求，同时已有团队基础设施支持。授权模型采用 RBAC。传输加密使用 TLS 1.3。[MUST] 所有 API 必须携带 Bearer token。涉及模块：API 网关、用户服务、设备管理。"
    },
    {
      "topic": "架构模式",
      "decision": "微服务架构 + Kafka",
      "detail": "采用微服务架构支持各模块独立部署和扩展。消息总线选择 Kafka 而非 RabbitMQ，因为 Kafka 更适合高吞吐量场景（预估峰值 50000 msg/s）。Kafka 集群至少 3 节点。[MUST] 消息投递保证 at-least-once。"
    }
  ],
  "pending_status_changes": [
    {"topic": "缓存策略", "status": "resolved"}
  ],
  "new_pending": [
    {"topic": "ELK vs Loki", "note": "调研两种日志方案的优劣"}
  ],
  "new_next_steps": ["调研 ELK 和 Loki"],
  "remove_next_steps": []
}
```

> **detail 长度校验**：AI 应在构造 JSON 前检查每条 detail 是否 ≥150 字符。不足时应继续追问用户补充，或根据对话上下文主动补充后让用户确认。

调 `spec_pause(spec_json)` 完成保存。MCP 的 `validate()` 会校验每条 detail 的长度，不足时会返回错误。

## 边界

- 不改变 status（保持 active）
- Topic 名称是待定决议匹配的 key，必须精确一致
- 字段为空数组时可以不传
- **每条决议的 `detail` 必须 ≥150 字符**，否则 MCP 校验会拒绝保存
- 决议→文档映射为**建议性**的，是否写入及何时写入由用户决定
- 用户也可要求在 spec-pause 时同步写入文档文件，此时按 Step 3 映射关系，调 `doc_structure()` 查看结构后，用 `update_section()` / `add_section()` 写入

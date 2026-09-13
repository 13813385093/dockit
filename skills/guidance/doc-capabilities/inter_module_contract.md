# 能力说明：inter_module_contract（inter-module-contracts.md）

> 指南：§3.1.2 / 类型 T-05（维护索引，供指南更新时同步本文件；AI 无需访问）
> 层级：Level 0（top）· `module: project-charter` · 推荐 · 编写顺序第 5 · 位于 `ProjectSpec/` 根（平铺，不建子目录）

## 定位

模块间接口**字段级**契约：请求/响应结构、共享事件 payload、共享数据结构。是 AI 生成代码和人工评审的唯一事实依据——接口定义精确到字段级。不写单个模块的内部接口与能力存在性声明（→ 归 architecture / module_manifest）。

## 承载的决议主题

| 决议主题 | 落点（章节 / 新增记录） |
|---------|---------|
| 模块间接口的请求/响应格式、错误语义、超时/重试 | §模块间接口定义 |
| 共享事件：发布方、订阅方、触发条件、payload | §共享事件定义 |
| 跨模块共享数据结构（字段级） | §共享数据结构 |

## 段落结构（3 个章节，顺序固定）

### §模块间接口定义

每个接口包含：**提供方** / **消费方** / **通信方式**（同步 RPC / 异步消息 / 事件广播）/ **数据格式** + 请求/响应结构（JSON 代码块）+ 约束（[MUST]/[SHOULD] 编号）。

- 格式：提供方 / 消费方 / 通信方式 / 数据格式 + 请求-响应 JSON 代码块 + 约束（`[MUST]`/`[SHOULD]` 编号，逐字给出字段名与类型）
- 正例：请求 `{"order_id": "string (必填)", "items": ["array (扣减条目)"]}`；响应 `{"success": "boolean", "error_code": "int (0=成功, 1=超时, 2=格式错误)", "error_msg": "string"}`；约束 `[MUST] C-601` 超时 ≤ 500ms、`[SHOULD] S-601` 指数退避重试最多 3 次。

### §共享事件定义

每个事件包含：**发布方** / **订阅方**（全部列出）/ **触发条件** + Payload（JSON 代码块）。事件名须与 `module_manifest.md` §Exports（类型 = event）的名称逐一对应。

- 格式：发布方 / 订阅方 / 触发条件 + Payload（JSON 代码块）
- 正例：payload `{"event_id": "string (UUID)", "timestamp": "uint64", "payload": {...}}`。

### §共享数据结构

每个结构包含：**定义归属**（哪个模块负责更新版本）/ **使用范围** + 字段表（字段 | 类型 | 必填 | 说明）。

- 格式：定义归属 / 使用范围 + 字段表（字段 | 类型 | 必填 | 说明）
- 正例：OrderStatus（定义归属 order 模块；使用范围 order、inventory）：order_id (string, 必填)、status (enum: pending_payment/paid/cancelled, 必填)、updated_at (string, ISO 8601, 必填)。

## 行文规则

> 本节「禁止」＝ 指南 §3.1.2 中本文档的「约束」（写作边界）；指南中的「约束」不指 [MUST]/[SHOULD] 内容级标记。

**必须**
- 落笔格式：接口定义精确到**字段级**（AI 生成代码的唯一事实依据）
- 编号与命名：契约约束用 `[MUST] C-6xx` / `[SHOULD] S-6xx` 编号。编号在**本文档内唯一**；跨文档引用用完整形式（语法见指南 §3.5.5）：`<doc_type>@project-charter:C-101`（顶层）／`<doc_type>@<模块名>:C-101`（模块层）／`<doc_type>@<模块名>.<功能名>:C-101`（功能层）。
- 完备性：每个接口/事件/结构按本节要素填满，不留空项；结构化数据一律用 JSON 代码块（跨模型解析最稳定）
- 与他文档的衔接：能力名称与 `module_manifest` 的 exports/imports 名称**保持一致**（本文档定义「长什么样」，manifest 声明「是否存在、由谁提供」）。同一能力的**签名**归 `module_manifest.md` §Exports，本文档只定义字段级请求/响应、错误语义与接口级约束。
- 判断是否写入：输入/输出结构复杂（3+ 字段或嵌套）、有错误语义、有版本协商/兼容要求、事件被 3+ 模块消费

**禁止**
- ❌ 单个模块的内部接口 → 归模块 `architecture`
- ❌ 能力存在性声明（import/export 配对）→ 归 `module_manifest`
- ❌ 全局架构模式/安全策略 → 归 `global_policies`
- ❌ 简单参数接口（单个 ID/布尔）→ 在 `module_manifest` 描述列注明即可
- ❌ 质量禁忌：模糊表述（「若干字段」）、不可验证的契约、无来源的字段定义

---
doc_type: inter_module_contract
module: project-charter
level: top
version: 0.1.0
last_updated: $now            # 生成时由工具替换为 ISO 8601 日期
author: $author               # 文档负责人（团队角色或人名）
status: active
deprecated_at:                   # 废弃日期（status=deprecated 时必填）
deprecated_reason:               # 废弃原因（status=deprecated 时必填）
superseded_by:                   # 替代文档列表（废弃且存在替代时必填）
  - doc: <替代文档>
    module: <所属模块>
archived_at:                     # 归档日期（status=archived 时必填）
depends_on: []                # 顶层入口文档，无文档依赖；引用其他文档需在此声明（见 §3.5.7）
---

# 模块间契约

<!-- 
模块间接口契约定义各模块之间的 API 边界、事件协议和共享数据结构，精确到字段级——
这是 AI 生成代码和人工评审的唯一事实依据。
与 module-manifest.md 的分工：module-manifest 声明能力「是否存在、由谁提供」，
本文档定义能力「长什么样、出错怎么办」；同一能力在两份文档中的名称必须保持一致。
全局架构模式、安全策略等跨模块设计决策请参考 global-policies.md。
-->

## 模块间接口定义

### [接口名称]

**提供方**：[模块名]  **消费方**：[模块名列表]
**通信方式**：同步 RPC / 异步消息 / 事件广播
**数据格式**：JSON / Protobuf / 自定义二进制

<!-- 请求/响应结构精确到字段级，字段标注类型与必填（见 §3.1.2）。 -->

**请求结构**：
```json
{
  "order_id": "string (必填, 订单唯一标识)",
  "items": ["array (扣减条目, 每项含 sku_id 与数量)"]
}
```

**响应结构**：
```json
{
  "success": "boolean",
  "error_code": "int (0=成功, 1=超时, 2=格式错误)",
  "error_msg": "string"
}
```

**约束**：
- [MUST] C-101 超时 ≤ 500ms
- [SHOULD] S-101 实现指数退避重试，最多 3 次

## 共享事件定义

### [事件名称]

**发布方**：[模块名]
**订阅方**：[模块名列表]
**触发条件**：[什么场景下发这个事件]

**Payload**：
```json
{
  "event_id": "string (UUID)",
  "timestamp": "uint64",
  "payload": { ... }
}
```

## 共享数据结构

### [结构名称]

**定义归属**：[负责维护此结构的模块]
**使用范围**：[哪些模块使用]

| 字段     | 类型     | 必填 | 说明                         |
|----------|----------|------|------------------------------|
| id       | string   | ✅   | 全局唯一标识                 |
| name     | string   | ✅   | 显示名称                     |
| status   | enum     | ✅   | active / inactive / archived |

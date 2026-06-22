---
doc_type: inter_module_contract
module: project-charter
level: top
version: 0.1.0
last_updated: $now
status: active
depends_on:
  - doc: global-policies.md
    module: project-charter
    version: "0.1.0"
---

# 模块间契约

<!-- 
模块间接口契约定义各模块之间的 API 边界、事件协议和共享数据结构。
全局架构模式、安全策略等跨模块设计决策请参考 global-policies.md。
每个模块的 architecture.md 应引用本文件中的接口定义。
依赖方向规则：模块间不直接依赖，契约统一上提到顶层管理。
-->

## 模块边界概览

<!-- 
列出所有模块及其核心职责。
正例：
  模块A (iec61850)：IEC 61850 协议接入，负责 SV/GOOSE/MMS 通信
  模块B (data-storage)：时序数据存储与查询
-->

| 模块 | 职责 | 依赖的外部模块 |
|------|------|---------------|
| <!-- 模块名 --> | <!-- 职责描述 --> | <!-- 依赖的模块 --> |

## 同步接口定义

<!-- 
模块间的同步调用接口（REST/gRPC/函数调用）。
正例：
  receive_sv_data(stream_id, dataset) → (status, parsed_data)
    提供方：iec61850    消费方：protection
    约束：延迟 [MUST] ≤ 1ms
-->

| 接口名称 | 提供方 | 消费方 | 签名 | 约束 |
|---------|-------|-------|------|------|
| <!-- 接口名 --> | <!-- 模块 --> | <!-- 模块 --> | `<!-- 入参 → 出参 -->` | <!-- 延迟/可靠性 --> |

## 异步消息与事件

<!-- 
模块间的异步消息和事件定义。
正例：
  事件：VoltageThresholdExceeded
    发布方：protection    订阅方：alarm, logging
    载荷：{ voltage, threshold, timestamp }
-->

| 事件/消息 | 类型 | 发布方 | 订阅方 | 载荷说明 | 投递保证 |
|----------|------|--------|--------|---------|---------|
| <!-- 事件名 --> | event/command | <!-- 模块 --> | <!-- 模块 --> | <!-- 数据结构 --> | at-least-once/exactly-once |

## 共享数据结构

<!-- 
跨模块共享的核心数据结构定义，确保各模块对同一数据的理解一致。
正例：
  SVSample {
    stream_id: string,
    voltage: float,
    current: float,
    timestamp: uint64
  }
-->

| 数据结构        | 定义                  | 使用方           |
| ----------- | ------------------- | ------------- |
| <!-- 名称 --> | ```<!-- 结构定义 -->``` | <!-- 模块列表 --> |

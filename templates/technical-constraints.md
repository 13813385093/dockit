---
doc_type: technical_constraints
module: project-charter
level: top
version: 0.1.0
last_updated: $now
status: active
depends_on:
  - doc: business-context.md
    module: project-charter
    version: "0.1.0"
---

# 技术约束

<!-- 
约束标记规范：
  [MUST]   强制要求 — 不可违反
  [SHOULD] 推荐做法 — 建议遵守
  [MAY]    可选择实现 — 灵活处理
-->

## 性能指标

<!-- 
正例：
  通信延迟 [MUST] ≤ 4ms
  报文重传 [SHOULD] 设置为 3 次
-->

| 指标 | 约束值 | 约束级别 | 说明 |
|------|--------|---------|------|
| <!-- 指标名 --> | <!-- 目标值 --> | [MUST]/[SHOULD] | <!-- 说明 --> |

## 可用性与可靠性

<!-- 
正例：
  系统 [MUST] 支持双网口冗余（PRP/HSR）
  可用性 [MUST] ≥ 99.99%
-->

| 要求 | 约束级别 | 说明 |
|------|---------|------|
| <!-- 要求描述 --> | [MUST]/[SHOULD] | <!-- 说明 --> |

## 安全要求

<!-- 
正例：
  认证 [MUST] 支持 OAuth2
  传输 [MUST] 使用 TLS 1.3
-->

| 要求 | 约束级别 | 说明 |
|------|---------|------|
| <!-- 安全要求 --> | [MUST]/[SHOULD] | <!-- 说明 --> |

## 合规与标准

<!-- 
正例：
  [MUST] 遵循 MISRA C 安全编码规范
  [MUST] 符合 IEC 62304 医疗软件标准
-->

- [MUST] <!-- 必须遵守的行业标准或法规 -->
- [SHOULD] <!-- 建议遵循的规范 -->

## 兼容性约束

<!-- 
正例：
  [MUST] 兼容 Windows 10+ / macOS 12+ / Ubuntu 20.04+
  [MUST] 支持 Chrome 和 Firefox 最新两个大版本
-->

| 维度 | 约束级别 | 目标平台/版本 |
|------|---------|-------------|
| 操作系统 | [MUST] | <!-- 支持的 OS --> |
| 浏览器 | [SHOULD] | <!-- 支持的浏览器 --> |
| 硬件 | [MUST] | <!-- 最低硬件要求 --> |

---
doc_type: module_manifest
module: $module
level: module
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
depends_on: []                # 声明依赖的其他文档（见 §3.5.7）
---

# 模块清单

<!-- 
模块清单声明本模块对外提供（exports）和依赖（imports）的能力。
核心不变式：**import 必须配对 export**——每条 imports 必须能在来源模块的 exports 中找到对应条目（见 §3.2.2）。
能力名称应与 inter-module-contracts.md 中的接口一一对应（能力存在性归本文档，字段级契约归 inter-module-contracts.md）。
工具据此检测循环依赖和调用链异常。
-->

## Exports — 对外提供的能力

<!-- 
本模块向其他模块提供的接口、事件或能力。
每条 exports 可被其他模块的 imports 引用。
正例：
  receive_sv_data(stream_id, dataset) → (status, parsed_data)
    功能：接收 SV 采样值
    类型：interface / event / capability
    稳定性：stable / unstable / deprecated
-->

| 能力名称        | 类型              | 签名            | 功能描述        | 稳定性    |
| ----------- | --------------- | ------------- | ----------- | ------ |
| <!-- 名称 --> | interface/event | `<!-- 签名 -->` | <!-- 描述 --> | stable |

## Imports — 依赖的外部能力

<!-- 
本模块依赖的其他模块提供的能力。
每条 imports 应指向目标模块 exports 中的具体条目。
正例：
  来源模块：data-storage
  能力名称：store_sample
  用途：保存 SV 采样值
-->

| 来源模块 | 能力名称 | 签名 | 用途 | 约束 |
|---------|---------|------|------|------|
| <!-- 模块 --> | <!-- 能力 --> | <!-- 签名 --> | <!-- 用途说明 --> | [MUST] C-1xx <!-- 延迟/可靠性 --> |

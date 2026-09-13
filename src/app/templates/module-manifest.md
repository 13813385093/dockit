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
能力名称（含**事件名**）应与 inter-module-contracts.md 中的接口/事件名称一一对应（能力存在性归本文档，字段级契约归 inter-module-contracts.md）。
**签名是能力签名的唯一权威来源**：architecture.md §模块接口 只列能力名与用途，不重复签名；inter-module-contracts.md 定义同一能力的字段级请求/响应与错误码。
工具据此检测循环依赖和调用链异常。
-->

## Exports — 对外提供的能力

<!-- 
本模块向其他模块提供的接口、事件或能力。
每条 exports 可被其他模块的 imports 引用。
「类型」取值固定为 interface | event | data_structure | capability。
正例：
  receive_sv_data(stream_id, dataset) → (status, parsed_data)
    功能：接收 SV 采样值
    类型：interface
    稳定性：stable / unstable / deprecated
-->

| 能力名称        | 类型              | 签名            | 描述            | 稳定性    |
| ----------- | --------------- | ------------- | ------------- | ------ |
| <!-- 名称 --> | <!-- interface / event / data_structure / capability --> | `<!-- 签名 -->` | <!-- 描述 --> | <!-- stable / unstable / deprecated --> |

## Imports — 依赖的外部能力

<!-- 
本模块依赖的其他模块提供的能力。
每条 imports 应指向目标模块 exports 中的具体条目。
接口级约束（超时 / 重试等）归 inter-module-contracts.md，本文档不重复。
正例：
  来源模块：data-storage
  能力名称：store_sample
  用途：保存 SV 采样值
-->

| 来源模块 | 能力名称 | 用途 |
|---------|---------|------|
| <!-- 模块 --> | <!-- 能力 --> | <!-- 用途说明 --> |

# 能力说明：module_manifest（module-manifest.md）

> 指南：§3.2.2 / 类型 T-10（维护索引，供指南更新时同步本文件；AI 无需访问）
> 层级：Level 1（module）· 必选 · 编写顺序第 10 · 位于 `module-<模块名>/`

## 定位

声明模块对外提供的能力（exports）与依赖的其他模块能力（imports）。工具链据此生成依赖图、检测循环依赖与调用链异常。**核心不变式：import 必须配对 export**。

## 承载的决议主题

| 决议主题 | 目标章节 |
|---------|---------|
| 本模块对外提供的接口/事件/能力 | §Exports |
| 本模块依赖的其他模块能力 | §Imports |

## 段落结构（2 个章节）

### §Exports — 对外提供的能力

表格列出（格式：能力名称 | 类型 | 签名 | 功能描述 | 稳定性）。

- 正例：`receive_sv_data(stream_id, dataset) → (status, parsed_data)`，类型 interface，稳定性 stable。

### §Imports — 依赖的外部能力

表格列出（格式：来源模块 | 能力名称 | 签名 | 用途 | 约束）。每条 imports 必须指向目标模块 exports 中的具体条目。

- 正例：来源模块 data-storage、能力名称 store_sample、用途 保存 SV 采样值。

## 行文规则

**必须**
- **import 必须配对 export**：消费方声明的每个 import（来源模块 + 能力名称）必须能在来源模块 exports 中找到对应条目，否则视为非法依赖（等价于 import 不存在的符号）
- 能力名称与 `inter_module_contract` 中的接口名称**一一对应**（本文档声明「是否存在、由谁提供」，契约文档定义「长什么样、出错怎么办」）
- 稳定性标注：stable / unstable / deprecated

**禁止**
- ❌ 内部实现细节或仅供模块内部使用的非公开能力
- ❌ 字段级契约（请求/响应结构、错误码）→ 归 `inter_module_contract`
- ❌ 跨模块的文档引用声明（`depends_on`）与能力依赖（imports）是两个独立维度，互不替代

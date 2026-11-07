# 能力说明：module_manifest（module-manifest.md）

> 指南：§3.2.2 / 类型 T-10（维护索引，供指南更新时同步本文件；AI 无需访问）
> 层级：Level 1（module）· 必选 · 编写顺序第 10 · 位于 `module-<模块名>/`

## 定位

声明模块对外提供的能力（exports）与依赖的其他模块能力（imports）。工具链据此生成依赖图、检测循环依赖与调用链异常。**核心不变式：import 必须配对 export**。不写字段级契约（→ inter_module_contract）与 depends_on 文档依赖声明。

## 承载的决议主题

| 决议主题 | 落点（章节 / 新增记录） |
|---------|---------|
| 本模块对外提供的接口/事件/能力 | §Exports |
| 本模块依赖的其他模块能力 | §Imports |

## 段落结构（2 个章节，顺序固定）

### §Exports — 对外提供的能力

表格列出本模块对外提供的能力、事件与数据结构。「类型」取值固定为 `interface | event | data_structure | capability`。

- 格式：能力名称 | 类型 | 签名 | 描述 | 稳定性
- 正例：`receive_sv_data(stream_id, dataset) → (status, parsed_data)`，类型 interface，稳定性 stable。

### §Imports — 依赖的外部能力

表格列出本模块依赖的其他模块能力。每条 imports 必须指向目标模块 exports 中的具体条目。接口级约束（超时/重试等）归 `inter_module_contract`，本文档不重复。

- 格式：来源模块 | 能力名称 | 用途
- 正例：来源模块 data-storage、能力名称 store_sample、用途 保存 SV 采样值。

## 行文规则

> 本节「禁止」＝ 指南 §3.2.2 中本文档的「约束」（写作边界）；指南中的「约束」不指 [MUST]/[SHOULD] 内容级标记。

**必须**
- 落笔格式：按 §段落结构 的 2 个章节顺序落笔（§Exports → §Imports）；两节均为表格，每节先写一句话说明，再给格式与正例
- 编号与命名：能力名称（含**事件名**）与 `inter_module_contract` 中的接口/事件名称**一一对应**（本文档声明「是否存在、由谁提供」，契约文档定义「长什么样、出错怎么办」）。稳定性标注：stable / unstable / deprecated
- **import 必须配对 export**：消费方声明的每个 import（来源模块 + 能力名称）必须能在来源模块 exports 中找到对应条目，否则视为非法依赖（等价于 import 不存在的符号）
- 完备性：每条 exports 写全 `能力名称 / 类型 / 签名 / 描述 / 稳定性` 五列，缺一不可；每条 imports 的「用途」一句话说明消费场景
- 与他文档的衔接：**签名是能力签名的唯一权威来源**；`architecture.md` §模块接口 只列能力名与用途，不重复签名；`inter-module-contracts.md` 定义同一能力的字段级请求/响应与错误码。

**禁止**
- ❌ 内部实现细节或仅供模块内部使用的非公开能力
- ❌ 字段级契约（请求/响应结构、错误码）→ 归 `inter_module_contract`
- ❌ 跨模块的文档引用声明（`depends_on`）与能力依赖（imports）是两个独立维度，互不替代
- ❌ 质量禁忌：模糊表述（「工具函数」「其他能力」）、不可验证的依赖声明、无来源的签名

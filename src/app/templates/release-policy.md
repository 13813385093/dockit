---
doc_type: release_policy
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
depends_on: []                # 顶层文档：可依赖 T-01 / T-02 / T-03 / T-05（business-context / technical-framework / non-functional-constraints / inter-module-contracts）；引用其他文档需在此声明（见 §3.5.7、§3.6.1）
---

# 发布策略

<!-- 
定义项目发布域的权威规则：发布状态机、发布单元划分、发布门禁、发布流水线、发布号规则与回滚策略。
状态机、门禁与流程的默认定义在 §3.8，项目可在本文档中自定义（见 §3.1.2）。
约束：不写部署操作细节（部署模型归 technical-framework.md）；
不写某次具体发布的内容（发布记录为工具链生成的派生制品，不属于 Spec 文档）。
-->

## 发布状态

<!-- 
默认状态机（见 §3.8.1）：draft（草稿）→ in-review（评审中）→ ready（门禁通过）→ released（已发布）→ superseded（被新发布替代）。
如需增删状态，必须同时说明与门禁的对应关系。
-->

| 状态 | 含义 | 进入条件 |
|------|------|---------|
| draft | 草稿 | <!-- Spec 变更提交 --> |
| in-review | 评审中 | <!-- 提交评审 --> |
| ready | 门禁通过 | <!-- P1 静态门禁 + P2 动态门禁全绿 --> |
| released | 已发布 | <!-- P4 发布验证通过并完成 P5 固化 --> |
| superseded | 被新发布替代 | <!-- 出现更新的 released 发布单元 --> |

## 发布单元划分

<!-- 
定义发布的最小粒度。默认：一个功能（`features/<功能名>/` 下的 4 份文档）+ 其 depends_on 依赖链（见 §3.8.2）。
-->
- 

## 发布门禁

<!-- 
在 §3.8.3 的 G1~G6 基础上按需增删；删除或新增门禁须注明理由。
默认门禁（见 §3.8.3）：
  G1 文档健康 / G2 依赖一致 / G3 契约闭合 / G4 约束覆盖 / G5 测试全绿 / G6 实现映射
G4 覆盖率范围 = 发布单元内 feature-design.md §边界约束 的编号 [MUST]；顶层/模块层文档的编号约束不纳入 G4。
-->

| 门禁 | 校验内容 | 依据机制 |
|------|---------|---------|
| G1 文档健康 | <!-- 发布单元内文档全部 active --> | §3.7 |
| G2 依赖一致 | <!-- depends_on 精确版本、无漂移/循环/反向依赖 --> | §3.5.7 |
| G3 契约闭合 | <!-- imports ↔ exports 配对、契约无悬空接口 --> | §3.2.2 |
| G4 约束覆盖 | <!-- feature_design §边界约束 的编号 [MUST] 均被 unit-tests 引用 --> | §3.5.5、§3.5.6 |
| G5 测试全绿 | <!-- unit-tests + acceptance-tests 执行通过 --> | §3.3.3 |
| G6 实现映射 | <!-- implemented_in 声明的路径真实存在 --> | §3.5.9 |
| <!-- 自定义门禁 --> | <!-- 校验内容 --> | <!-- 依据 --> |

## 发布流水线

<!-- 
描述发布流程的阶段划分。默认（见 §3.8.4）：
  P0 变更检测 → P1 静态门禁 → P2 动态门禁 → P3 制品生成 → P4 发布验证 → P5 固化
-->
- 

## 发布号规则

<!-- 
发布号建议采用 YYYY.MM.n 格式，与 Spec 版本（§3.5.7）相互独立（见 §3.1.2 编写要点）。
-->
- 

## 回滚策略

<!-- 
定义发布失败时的回滚机制与回滚触发条件。
-->
- 

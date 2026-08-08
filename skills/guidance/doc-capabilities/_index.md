# 文档能力索引（doc-capabilities 入口）

> 路由向导：议题决议 → 目标文档类型 → 对应能力文件（`doc-capabilities/<doc_type>.md`）。
> 写入 ProjectSpec（更新章节 / 新增文档）之前，先读本文档定位目标，再读对应能力文件获取段落要求与行文规则。

## 使用流程

1. **定位**：先 `doc structure` 查看现有文档，再按 §2（议题场景）或 §3（决议主题）定位 doc_type，并按 §4 判断「新增 vs 更新」。**文档间归属差异在此层判定完毕，能力文件不重复文档间边界。**
2. **加载**：`read_file doc-capabilities/<doc_type>.md`。
3. **执行**：
   - 更新已有章节 → `doc update-section <reference>`
   - 新增章节 → `doc add-section <reference> '<标题>' [--level sibling|child]`
   - 新增文档 → `doc new`（能力文件提供骨架）后填充
   - frontmatter 元数据（`version` / `last_updated` / `author` / `depends_on` 等）由 doc-kit 工具与人工维护，AI 写入正文时不修改这些字段。

## 1. 文档类型总览（18 种）

### Level 0 — 顶层（`module: project-charter`，平铺 ProjectSpec/ 根）

| doc_type | 文件名 | 必选 | 一句话能力 |
|----------|--------|------|-----------|
| `business_context` | business-context.md | ✅ | 项目为什么存在：业务动因、目标、范围、用户、术语 |
| `technical_framework` | technical-framework.md | ✅ | 全局技术选型与架构风格：语言、框架、中间件、部署、工具链 |
| `non_functional_constraints` | non-functional-constraints.md | ✅ | 不可突破的量化底线：性能、安全、合规、兼容、编码规范指标 |
| `global_policies` | global-policies.md | ✅ | 影响 ≥2 模块的统一策略：认证、日志、错误码、一致性、命名 |
| `inter_module_contract` | inter-module-contracts.md | 推荐 | 模块间接口字段级契约：请求/响应、共享事件 payload、共享结构 |
| `stakeholders` | stakeholders.md | 可选 | 干系人角色、关注点、决策权、参与方式 |
| `release_policy` | release-policy.md | 推荐 | 发布域规则：发布单元、门禁、流水线、发布号、回滚 |
| `charter` | charter.md | —（精简模式） | 复合宪章：business_context + technical_framework + non_functional_constraints + global_policies（+ inter_module_contract / stakeholders） |

### Level 1 — 模块层（`module-<模块名>/`）

| doc_type | 文件名 | 必选 | 一句话能力 |
|----------|--------|------|-----------|
| `architecture` | architecture.md | ✅ | 模块组件划分、职责、组件间关系与关键流程 |
| `domain_model` | domain-model.md | ✅ | 领域实体、值对象、聚合根及其业务不变条件 |
| `integration` | integration.md | 可选 | 外部系统集成：协议、数据流、错误处理与降级 |
| `module_manifest` | module-manifest.md | ✅ | exports / imports 能力声明，import 必须配对 export |
| `module_design` | `<模块名>-module-design.md` | —（精简模式） | 复合模块设计：architecture + domain_model + module_manifest（+ integration） |

### Level 2 — 功能层（`module-<模块名>/features/<功能名>/`）

| doc_type | 文件名 | 必选 | 一句话能力 |
|----------|--------|------|-----------|
| `feature_design` | feature-design.md | ✅ | 功能行为规格：功能描述、触发条件、处理流程、边界约束（What） |
| `decision_log` | decision-log.md | ✅ | 设计决策理由与替代方案（Why，只追加不改写） |
| `unit_test` | unit-tests.md | ✅ | GWT 单元测试用例（代码正确性），「覆盖约束」行引用约束 ID |
| `acceptance_test` | acceptance-tests.md | ✅ | Gherkin 验收场景（业务符合性） |
| `feature_package` | `<功能名>-feature-package.md` | —（精简模式） | 复合功能包：feature_design + decision_log + unit_test + acceptance_test |

## 2. 议题场景 → 候选文档（第一级路由）

| scenario | 含义 | 候选 doc_type |
|----------|------|--------------|
| `spec-scribe` | 需求讨论 | `business_context`, `stakeholders`, `charter` |
| `tech-ref` | 技术评审 | `technical_framework`, `non_functional_constraints`, `global_policies`, `inter_module_contract`, `release_policy`, `architecture`, `domain_model`, `module_manifest`, `integration`, `module_design` |
| `feature-dev` | 功能设计 | `feature_design`, `decision_log`, `unit_test`, `acceptance_test`, `feature_package` |

## 3. 决议主题 → 目标文档 → 典型章节（第二级路由）

| 决议主题类别 | 目标文档 | 典型章节 |
|-------------|---------|---------|
| 业务动因 / 目标 / 范围 / 术语 | `business_context` | §项目动因 / §项目目标 / §业务范围 / §关键术语表 |
| 技术选型 / 架构风格 / 工具链 | `technical_framework` | §技术栈概览 / §架构风格 / §开发环境与工具链 |
| 性能 / 安全 / 合规 / 兼容指标 | `non_functional_constraints` | §性能约束 / §安全约束 / §平台兼容性 |
| 认证 / 日志 / 错误码 / 一致性 / 命名 | `global_policies` | §安全与认证 / §可观测性 / §异常处理 / §命名约定 |
| 模块间接口字段 / 事件 / 共享结构 | `inter_module_contract` | §模块间接口定义 / §共享事件定义 / §共享数据结构 |
| 模块能力存在性 / 依赖关系 | `module_manifest` | §Exports / §Imports |
| 模块组件 / 内部流程 | `architecture` | §组件划分 / §关键流程 |
| 领域实体 / 业务不变条件 | `domain_model` | §聚合根 / §实体 / §领域约束 |
| 外部系统对接 / 降级 | `integration` | §外部系统概览 / §错误处理与降级 |
| 功能行为 / 触发 / 边界约束 | `feature_design` | §功能描述 / §触发条件 / §边界约束 |
| 选型理由 / 方案对比 / 权衡 | `decision_log` | 追加一条新决策记录（不改写旧记录） |
| 单元测试用例 | `unit_test` | 新增 GWT 用例（含「覆盖约束」行） |
| 业务验收场景 | `acceptance_test` | 新增 Gherkin 场景 |
| 发布门禁 / 流水线 / 回滚 | `release_policy` | §发布门禁 / §回滚策略 |
| 干系人角色与关注 | `stakeholders` | §角色定义 / §信息需求矩阵 |

## 4. 写入动作与工具

### 4.1 新增 vs 更新判断

| 情形 | 动作 |
|------|------|
| 目标文档存在，决议主题属于其已有章节 | `doc update-section <reference>` |
| 目标文档存在，无对应章节 | `doc add-section <reference> '<标题>' [--level sibling\|child]` |
| 目标文档不存在（新模块 / 新功能） | `doc new`（见 §4.2），按能力文件骨架填充 |
| 项目为精简模式（存在 charter / module-design / feature-package） | 写入复合文档对应章节；未拆分前不新建独立基础文档 |

> **新建顺序**：新模块 / 新功能先建骨架（`doc new module_design --module <名>` / `doc new feature_package --module <名> --feature <功能名>`），再创建基础文档；`doc new` 遇目录缺失返回 `new_doc.module_not_found` / `new_doc.feature_not_found` 并带修复建议。
> **拆分（§3.7）**：复合 → 基础文档的拆分为**人工操作**（app 看板），AI 不执行，仅提示用户。

### 4.2 工具

| 工具 | 用途 |
|------|------|
| `doc structure` | 查看项目全部文档：路径 / 层级 / 章节标题 / depends_on（定位目标、判断新增 vs 更新的依据） |
| `doc read <path>` | 读取单篇文档的段落级内容，返回各段落 reference（供 update / remove-section 引用） |
| `doc update-section <reference> --content <正文>` | 更新已有段落 |
| `doc add-section <reference> '<标题>' [--content <正文>] [--level sibling\|child]` | 新增段落 |
| `doc new <doc_type> [--module <模块名>] [--feature <功能名>]` | 新增文档：CLI 按注册表自动定位模板（`.doc-kit/templates/`）与目标目录 |
| `doc remove-section <reference>` | 删除段落及其子段落 |

> 错误信息统一为 `ERROR [<错误码>] <原因>。修复：<建议>`，AI 读到后直接按建议行动。模块/功能目录不存在、精简模式等场景由 CLI 返回对应错误码与修复建议（如 `new_doc.module_not_found`、`new_doc.minimal_profile`）。


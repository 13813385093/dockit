---
smell: speculative-generality
mode: quick
evidence_scope: repo+spec
default_confidence: medium
---
# 为未来而设计（Speculative Generality）

## 识别症状

本次 diff 新增了抽象/参数/hook/配置项，但**当前没有真实调用方**：

- 新接口只有一个实现，且只被同一次 diff 的一处调用；
- 新参数在所有调用点都传默认值/空值；
- 新 hook/扩展点没有外部注册者，只有测试在驱动；
- 新 `DataMap`/`ProbeValue` 能力只能由白盒测试使用，公开路径恒传空。

```cpp
// 公开路径始终传空；只有白盒测试能构造非空 data
sink->write_event(..., DataMap(), seq);
```

## 最小证据门槛

- 新抽象/参数/hook 在**本次 diff 之外**没有非测试调用；
- 当前 `ProjectSpec` / `feature-design` 没有要求它；
- 不是公开 API 的兼容承诺或已记录的扩展点。

三者同时成立才报；缺少任一条，降为低置信度或直接不报。

## 误报排除

1. **契约明确要求的字段/能力**：ProjectSpec 的 `[MUST]` 字段即使当前无公开入参，也可能是为后续 ABI 预留；查契约后再判断。
2. **已记录的“设计缺口/已知取舍”**：`DevSpec/*/code-notes.md` 或 `ReviewSpec/` 已说明“公开路径恒为空、内部/白盒验证”，不重复报。
3. **公开 API/插件接口的兼容承诺**：已发布接口的扩展点，即使当前调用少，也不按“投机”处理。
4. **测试/诊断专用能力**：明确标注为白盒或诊断用途的 hook，若已有测试覆盖，不报。

## 修复方向

删除未使用的抽象/参数/hook，内联回真实调用；等第二个真实调用出现再抽象。若是契约要求，则保留并在 Spec 中写清“当前无公开入口”的取舍。

```diff
- void write_event(..., const DataMap& data, ...);
+ void write_event(...);  // 等公开 data 入口的真实需求
```

## 何时不问

- ProjectSpec 明确要求该字段/能力；
- 已有 `code-notes` / `ReviewSpec` 记录为已知设计缺口；
- 是已发布 API 的扩展点；
- 只在测试/白盒中使用，且项目接受这种验证方式。

---
smell: shotgun-surgery
mode: deep
evidence_scope: diff+spec
default_confidence: low
---
# 散弹式修改（Shotgun Surgery）

## 识别症状

一个逻辑变更被迫散落到很多文件/模块，每处都要做相似的小改动；新增一个字段/环境变量/路径时尤其明显：

- 同一环境变量读取块在两个服务 `main.cpp` 各写一遍；
- 新增一个日志目录，测试、配置、文档、多个服务都要同步改；
- 修一个行为，要在 ≥3 个生产模块重复改同一条件。

## 最小证据门槛

- 同一逻辑变更散在 ≥3 个**生产模块**；
- 各 hunk 语义上确实关联同一逻辑，而不是一个连贯 feature 的自然分层；
- 没有单一归属模块/适配层可以承载该变更。

## 误报排除

1. **连贯 feature 的正常跨层改动**：controller/service/repo/test 一起改，是设计使然，不报。
2. **数据迁移/批量重命名**：一次性脚本/迁移，不报。
3. **测试/文档/配置的同步改动**：默认排除；不计入“生产模块”。
4. **架构上刻意分散**：ProjectSpec/global-policies 明确采用该分布方式，不报。

## 修复方向

把变更点聚合到一个模块/适配层，调用方统一走新接口；若是横切配置，抽共享 helper。

```diff
- // 两个服务 main.cpp 各写一遍
- if (const char* mode = std::getenv("LOG_PROBE_MODE")) log_probe_set_mode(mode);
+ // 服务侧共享 helper
+ init_probe_from_env();
```

## 何时不问

- 这是一个连贯 feature 的正常分层改动；
- 变更点 <3 个生产模块；
- 有明确的单一归属，只是本次还没来得及抽；
- 数据迁移/批量重命名。

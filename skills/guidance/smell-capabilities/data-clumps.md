---
smell: data-clumps
mode: deep
evidence_scope: file+diff
default_confidence: medium
---
# 数据泥团（Data Clumps）

## 识别症状

同一组字段/参数总是在一起出现，却没有被捆成一个类型：

```cpp
void write_event(const std::string& svc, const std::string& node,
                 const std::string& biz, log_level_t level,
                 const char* event, const DataMap& data,
                 unsigned long long seq);
```

`svc/node/biz` 在所有调用点一起出现；`level/event/data/seq` 也总是一起传递。

## 最小证据门槛

- 同一组 ≥3 字段/参数在**本次 diff 的 ≥2 处**一起出现；
- 或一个签名里 ≥3 个参数明显属于同一领域概念；
- 项目已有或明显适合一个值对象（如 `ProbeRecord`）。

## 误报排除

1. **DTO/Payload 跨层传递**：接口契约要求扁平字段，不报。
2. **测试 builder/夹具**：测试辅助参数，不报。
3. **框架回调签名**：参数由框架规定，不报。
4. **参数组只在 1 处出现**：没有重复，不报；交给 Long Parameter List 判断。

## 修复方向

捆成一个值对象/参数对象，传递该对象；若契约已定义签名，先记入 Spec 变更。

```diff
- void write_event(const std::string& svc, const std::string& node,
-                 const std::string& biz, log_level_t level,
-                 const char* event, const DataMap& data,
-                 unsigned long long seq);
+ void write_event(const ProbeRecord& record);
```

## 何时不问

- 契约/ABI 固定了扁平签名；
- 只在测试/工具代码中出现；
- 参数组没有重复出现，或语义上并不属于同一概念。

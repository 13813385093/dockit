---
smell: long-parameter-list
mode: quick
evidence_scope: diff
default_confidence: high
---
# 参数过多（Long Parameter List）

## 识别症状

生产代码的函数/方法参数数量过多，尤其是同一组参数总是一起出现：

```cpp
void write_event(const std::string& svc, const std::string& node, const std::string& biz,
                 log_level_t level, const char* event, const DataMap& data,
                 unsigned long long seq);
```

## 最小证据门槛

- 新增或修改的**生产函数**参数 ≥5 个；
- 或参数虽为 4 个，但其中 ≥3 个是同一组总一起传递的字段（与 Data Clumps 联动）；
- 测试 builder、夹具、mock 构造器不计入门槛（测试默认不扫）。

## 误报排除

1. **契约/ABI 已定义的签名**：ProjectSpec / inter-module-contracts 明确规定的公开签名，标为“设计层”而不是“必须改”；修改需同步契约。
2. **测试 builder / 参数化夹具**：如 `_probe_event(t, ev, seq, lvl, svc, node, biz, data, v)`，全部有默认值，测试可读性优先，不报。
3. **框架回调/事件签名**：参数由框架规定（如 `main(int argc, char** argv)`、日志格式化回调），不报。
4. **参数语义彼此独立、调用点很少**：为 5 个独立参数强行建 struct 只会增加跳转，标为低置信度。

## 修复方向

优先把“总一起出现”的字段捆成值对象/参数对象；若契约已定义，则先记入 Spec 变更，不直接改 ABI。

```diff
- void write_event(const std::string& svc, const std::string& node,
-                 const std::string& biz, log_level_t level,
-                 const char* event, const DataMap& data, unsigned long long seq);
+ void write_event(const ProbeRecord& record);
```

## 何时不问

- 签名由 ProjectSpec/ABI 明确规定，且本次不打算改契约；
- 测试 builder/夹具；
- 参数数量刚过门槛但语义独立、调用点极少。

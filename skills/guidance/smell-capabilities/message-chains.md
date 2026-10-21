---
smell: message-chains
mode: quick
evidence_scope: diff+file
default_confidence: medium
---
# 过长链式调用（Message Chains）

## 识别症状

一行/一段里出现 4+ 个连续调用，调用方被迫了解整条对象导航路径：

```cpp
auto total = session.get_user().get_cart().get_items().front().price();
```

## 最小证据门槛

- 4+ 个连续 `.`/`->` 调用；
- 链跨越 ≥2 个不同对象/类型（不是同一个对象的 fluent 配置）；
- 调用方不拥有链上对象，只是“借道导航”。

## 误报排除

1. **Fluent API / Builder**：每步返回 `self` 或同类型，链是 API 设计本身（如 `builder.set_a().set_b().build()`），不报。
2. **ORM/查询 DSL**：`query.filter(...).order_by(...).limit(...)` 是框架惯用法，不报。
3. **标准库/容器链**：`str.substr(...).find(...)` 这类短链、标准库惯用法，不报。
4. **测试断言链**：测试里的 `EXPECT_EQ(...)` / mock 链，测试默认不扫；用户要求扫测试时也不报。

## 修复方向

在链首对象上暴露一个语义化方法，把导航封装在拥有数据的对象里：

```diff
- auto total = session.get_user().get_cart().get_items().front().price();
+ auto total = session.cart_total();
```

## 何时不问

- 链是 fluent/Builder/ORM 的正当用法；
- 链在单个模块内部，且调用方就是数据拥有者；
- 链很短（<4）或只是标准库操作。

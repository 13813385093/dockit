---
smell: primitive-obsession
mode: deep
evidence_scope: file+spec
default_confidence: medium
---
# 原始类型迷恋（Primitive Obsession）

## 识别症状

用裸 `str`/`int`/`bool`/`map` 表示有明确领域含义的概念：

```cpp
std::map<std::string, bool> connected_peers_;  // bool 恒为 true，实际是 set
connected_peers_[peer_id] = true;
```

也包括：

- `std::string` 表示 user_id / status / mode，且项目已有值对象；
- `bool` 作为集合成员（map-as-set），值从未取 false；
- 用裸 `std::string` 承载 number 字面量，且没有校验。

## 最小证据门槛

- 该裸类型在**新增/修改代码**中承担领域概念，且项目 `domain-model` 已有对应值对象/不变量；
- 或集合形态明显：`map<K,bool>` 只用于存在性判断、值恒为 true；
- 或同一裸类型在 ≥2 处需要相同校验/格式化。

## 误报排除

1. **契约/ABI 明确要求裸类型**：`inter-module-contracts` 的字段类型，不报；改类型需同步契约。
2. **内部实现细节、不跨模块**：局部变量、短生命周期参数，不报。
3. **C++11 基线的限制**：没有 `std::variant` 时用 tagged union 是合理替代，不因“不是 variant”而报。
4. **集合形态只是测试/诊断工具**：测试夹具里的 mock map，不报。

## 修复方向

给概念建小值对象；集合形态改为 `std::set` / `std::unordered_set`；必要时把校验放进构造函数。

```diff
- std::map<std::string, bool> connected_peers_;
+ std::set<std::string> connected_peers_;
```

## 何时不问

- 裸类型由契约/ABI 固定；
- 只在单模块内部使用，且没有对应领域值对象；
- 测试/工具代码。

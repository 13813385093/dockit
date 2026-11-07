---
smell: duplicated-code
mode: quick
evidence_scope: diff
default_confidence: high
---
# 重复代码（Duplicated Code）

## 识别症状

同一段逻辑形态在**本次 diff 的不同位置**重复出现：变量名可能不同，但语句顺序、分支结构、调用序列一致。典型：

```cpp
// A 处
if (!connected) {
    close_peer(peer_id);
    disconnect_nodes(peer_id);
    return;
}
// B 处
if (!connected) {
    close_peer(peer_id);
    disconnect_nodes(peer_id);
    return;
}
```

## 最小证据门槛

- 新增/修改代码中，两处以上出现同形态逻辑；
- 每处 ≥6 行，或 ≥3 条可独立执行的语句；
- 或同一个**非平凡谓词/调用序列**在本次 diff 中出现 ≥3 次（例如重复的 `find(...) != end()` + 同一处置）。

低于门槛的 1–2 行相似，不报。

## 误报排除

1. **测试夹具/测试探针的刻意复制**：测试文件注释明确写“照抄以避开耦合”时，不报；测试默认不扫，用户要求扫测试时也要尊重此类注释。
2. **生成代码/模板批量产物**：`*.generated.*`、`*_pb2.*`、脚手架产物不报。
3. **两段代码只是“长得像”但语义不同**：例如一个是“清理并断开”，另一个是“清理但不断开”；要求能指出共同的语义，而不是只对比形状。
4. **有意的平台分支/编译分支**：同一逻辑在 Windows/Linux 两套实现中重复，若项目没有抽象层约定，标为低置信度而不是直接建议合并。

## 修复方向

提取公共函数/私有 helper，两端调用；若重复的是谓词，抽成语义化查询函数。

```diff
- if (pair_notified_.find(peer_id) == pair_notified_.end()) { return; }
+ if (!is_connected(peer_id)) { return; }
```

## 何时不问

- 重复发生在测试夹具且已有“刻意复制”说明；
- 两处代码的演化方向明显不同，合并会制造条件分支；
- 重复量小于门槛，抽 helper 反而降低可读性。

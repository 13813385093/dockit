# spec-abort — 作废当前议题

## 定位

非正常终止议题。前置条件不足、方向变更、不再有价值时使用。

## 在哪选

`active` 状态下，当用户说「这个议题算了」「不讨论了」「作废」时。

## 选择判断

### Step 1：确认意图

用户发起作废请求时，先确认：

```
⚠️ 请确认：议题 {session_spec_id} 将作废（原因：{用户提供的原因}）。
作废不可撤销。
```

### Step 2：调工具

用户确认后：调 `spec_abort(reason="作废原因", confirm=True)`

> 第一次调时不传 confirm，MCP 会要求二次确认。第二次带上 confirm=True 才执行。

### 成功后

- MCP 标记为 abandoned，移出活跃状态，直接移至 SessionSpec/archive/
- 不再占用 active 位置，可立刻开启新议题
- 下次 `spec_status()` 返回「没有活跃议题」

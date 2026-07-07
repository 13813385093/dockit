---
name: spec-abort
description: 作废当前议题，非正常终止时使用
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**使用以下 MCP 专用工具：
- `mcp__spec_mcp_tools__spec_write`
- `mcp__spec_mcp_tools__spec_write`

---

# spec-abort — 作废当前议题

## 定位

非正常终止议题。前置条件不足、方向变更、不再有价值时使用。

## 在哪选

`active` 状态下，当用户说「这个议题算了」「不讨论了」「作废」时。

## 选择判断

### Step 1：确认意图

用户发起作废请求时，先确认意图。如果用户尚未提供作废原因，先询问原因再确认。

```
请确认：议题 {session_spec_id} 将作废（原因：{用户提供的原因}）。
作废不可撤销，请确认。
```

### Step 2：读取当前议题

调 `spec_read()` 获取完整的议题数据。

### Step 3：修改为作废状态

在 spec 上设置：
- `status` → `"abandoned"`
- `closed_at` → 当前时间 ISO 8601
- `closed_reason` → 用户提供的原因

### Step 4：写入并归档

1. 调 `spec_write(spec_json)` 保存作废状态
2. 调 `spec_archive()` 归档

### 成功后

- MCP 标记为 abandoned，移至 SessionSpec/archive/
- 下次 `spec_status()` 返回「没有活跃议题」

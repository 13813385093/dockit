---
name: spec-load
description: 查看当前议题状态，决定下一步走哪个岔路
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**使用以下 MCP 专用工具：
- `mcp__spec_mcp_tools__doc_structure`
- `mcp__spec_mcp_tools__read_doc`
- `mcp__spec_mcp_tools__add_section`
- `mcp__spec_mcp_tools__update_section`
- `mcp__spec_mcp_tools__spec_read`
- `mcp__spec_mcp_tools__spec_write`

---

# spec-load — 查看当前议题状态

## 定位

每次新对话的第一步。调 `spec_status()` 了解当前在哪，然后决定下一步走哪个岔路。

## 在哪选

这是每次对话的必选前导动作，非独立岔路。

## 选择判断

直接调 `spec_status()` 查看返回文案：

| 返回包含 | 含义 | 下一步 |
|----------|------|--------|
| 「无活跃议题」或「已初始化」 | 当前无进行中的会议 | 引导用户：可选 `spec_start` 开启新议题 |
| 「有活跃议题：**{id}**」 | 有议题进行中 | 调 `spec_read()` 获取完整内容后展示给用户，由用户决定下一步：`spec_pause` / `spec_close` / `spec_abort` |
| 「有已关闭/已作废但未归档」 | 有已结束但未归档的议题 | 引导用户调 `spec_archive()` 归档 |

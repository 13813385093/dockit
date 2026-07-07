---
name: spec-archive
description: 归档已关闭或已作废的议题（从 active 移至 archive）
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**使用以下 MCP 专用工具：
- `mcp__spec_mcp_tools__spec_write`
- `mcp__spec_mcp_tools__spec_archive`

---

# spec-archive — 归档已关闭或已作废的议题

## 定位

将已关闭（closed）或已作废（abandoned）的议题从 `active/` 移至 `archive/`。

## 在哪选

当议题已 closed 或已 abandoned，用户说「归档」「清理」时。

## 选择判断

1. 调 `spec_status()` 确认当前议题状态为 **closed** 或 **abandoned**。如仍为 active，应先调 `spec_close` 或 `spec_abort`。
2. 确认后调 `spec_archive()` 完成归档。

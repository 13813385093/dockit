---
name: spec-archive
description: 归档已关闭或已作废的议题（从 active 移至 archive）
---

# spec-archive — 归档已关闭或已作废的议题

## 定位

将已关闭（closed）或已作废（abandoned）的议题从 `active/` 移至 `archive/`。

## 在哪选

当议题已 closed 或已 abandoned，用户说「归档」「清理」时。

## 选择判断

1. 调 `spec_status()` 确认当前议题状态为 **closed** 或 **abandoned**。如仍为 active，应先调 `spec_close` 或 `spec_abort`。
2. 确认后调 `spec_archive()` 完成归档。

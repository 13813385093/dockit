---
name: spec-close
description: 关闭当前议题，包含决议完整性检查和文档写入确认
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**使用以下 MCP 专用工具：
- `mcp__spec_mcp_tools__read_doc`
- `mcp__spec_mcp_tools__add_section`
- `mcp__spec_mcp_tools__update_section`
- `mcp__spec_mcp_tools__spec_write`

---

# spec-close — 关闭当前议题

## 定位

结束整个议题。议题关闭后不可续接，需开启新议题。

## 在哪选

`active` 状态下，当用户说「这个议题讨论完了」「关闭」时。

## 选择判断

在调 `spec_write()` 之前，先检查和确认以下事项：

### 1. 读取当前议题

调 `spec_read()` 获取完整的议题数据（含 resolutions、pending_decisions、next_steps）。

### 2. 提取本次对话的变更

从本次对话中提取所有未保存的决议、待定决议和后续计划，结构同 spec-pause Step 1：

- 已达成明确结论的 → 追加到 `resolutions[]`
- 悬而未决的新问题 → 追加到 `pending_decisions[]`
- 下一步计划 → 追加到 `next_steps[]`

> 以下 Step 3–5 的检查均基于「已有数据 + 本次新增」的合并结果。

### 3. 待定决议检查

检查合并后的 `pending_decisions[]`：

- 如果还有 **未 resolved 的待定决议**，提示用户：
  > 仍有 X 项待定决议未解决，建议继续讨论后再关闭。
  > 如需强行关闭，将这些未解决项的 status 改为 resolved 即可清除。

- 用户可选择继续讨论或强行关闭。

### 4. 决议 Detail 完整性检查

检查合并后的每条决议的 `detail` 是否 ≥150 字。不足时提示用户：

  > ⚠️ 以下决议的 detail 不足 150 字，写入文档时可能信息不足：
  >
  > 建议用 spec_write() 补充后再关闭。

> 注意：`detail` 的最小长度校验由 `spec_write()` 自动执行。

### 5. 文档写入检查

确认所有已决议的内容（已有 + 本次新增）已写入 ProjectSpec/ 对应文档：

1. 调 `doc_structure()` 查看当前文档结构（结果可缓存复用）
2. 对每条未写入的决议，按 spec-pause Step 3 的流程（doc_structure → read_doc → 判断 update/add）确定写入位置
3. 汇总待写入清单，向用户确认
4. 用户确认后，一次性调 `update_section()` / `add_section()` 写入

### 6. 组装关闭 spec 并写入

修改 spec：

- `status`: `"closed"`
- `closed_at`: `"当前时间 ISO 8601"`
- `closed_reason`: `"关闭原因"`
- 如有需要强行清除未解决的待定决议，将其 status 改为 `resolved`

调 `spec_write(spec_json)` 保存关闭状态。

### 7. 归档

调 `spec_archive()` 将已关闭的议题从 active 移至 archive。

## 成功后

- MCP 标记为 closed，移至 archive
- 下次 `spec_status()` 返回「没有活跃议题」
- 如需再次讨论，需开启新议题

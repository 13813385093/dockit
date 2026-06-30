# spec-close — 关闭当前议题

## 定位

结束整个议题。议题关闭后不可续接，需开启新议题。

## 在哪选

`active` 状态下，当用户说「这个议题讨论完了」「关闭」时。

## 选择判断

在调 `spec_close` 之前，先检查和确认以下事项：

### 1. 待定决议检查

调 `spec_status()` 查看 `pending_decisions[]`。

- 如果还有 **未 resolved 的待定决议**，提示用户：
  > ⚠️ 仍有 X 项待定决议未解决：
  > - 日志方案 [needs_discussion]
  > - 缓存策略 [deferred]
  >
  > 建议继续讨论解决后再关闭。如强行关闭，这些待定决议将被自动清除。

- 用户可选择：
  - **继续讨论** — 解决所有待定项后再关闭
  - **强行关闭** — 调 `spec_close(reason="...", force=True)`，MCP 将自动清除所有未 resolved 的待定决议

### 2. 决议 Detail 完整性检查

检查每条决议的 `detail` 是否 ≥150 字。

- 如果有决议 detail 不足 150 字，提示用户：
  > ⚠️ 以下决议的 detail 不足 150 字，写入文档时可能信息不足：
  > - 「认证方式」：detail 仅 45 字
  >
  > 建议用 `spec_pause` 补充后再关闭。

- 用户可选择：
  - **先补充 detail** — 调 `spec_pause` 更新后再关闭
  - **强行关闭** — 允许 detail 不足的决议通过

### 3. 最终确认

确认无误后，调 `spec_close(reason="关闭原因")`。

如果用户选择强行关闭（有待定决议或 detail 不足），调 `spec_close(reason="关闭原因", force=True)`。

## 成功后

- MCP 标记为 closed，移出活跃状态
- 未 resolved 的待定决议被自动清除（如有）
- 下次 `spec_status()` 返回「没有活跃议题」
- **关闭前确认所有决议已通过 `update_section()` / `add_section()` 写入对应文档**
- 如需再次讨论，需开启新议题

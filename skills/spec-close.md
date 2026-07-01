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
  > 仍有 X 项待定决议未解决，建议继续讨论后再关闭。
  > 如需强行关闭，请确认后调 specClose(reason="...", force=True)。

- 用户可选择继续讨论或强行关闭。

### 2. 决议 Detail 完整性检查

检查每条决议的 `detail` 是否 ≥150 字。不足时提示用户：

  > ⚠️ 以下决议的 detail 不足 150 字，写入文档时可能信息不足：
  > - 「认证方式」：detail 仅 45 字
  >
  > 建议用 spec_pause 补充后再关闭，或强行关闭。

- 用户可选择先补充 detail 或强行关闭。

### 3. 文档写入检查

确认所有已决议的内容已写入 ProjectSpec/ 对应文档：

1. 调 `doc_structure()` 查看当前文档结构
2. 对每条未写入的决议，按 spec-pause Step 3 的流程（doc_structure → read_doc → 判断 update/add）确定写入位置
3. 汇总待写入清单，向用户确认
4. 用户确认后，一次性调 `update_section()` / `add_section()` 写入

### 4. 最终关闭

确认无误后，调 `spec_close(reason="关闭原因")`。

如用户选择强行关闭（有待定决议或 detail 不足），调 `spec_close(reason="关闭原因", force=True)`。

## 成功后

- MCP 标记为 closed，移出活跃状态
- 未 resolved 的待定决议被自动清除（如有）
- 下次 `spec_status()` 返回「没有活跃议题」
- 如需再次讨论，需开启新议题

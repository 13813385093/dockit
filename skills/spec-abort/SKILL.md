---
name: spec-abort
description: 作废当前议题，非正常终止时使用
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**例外（能力库）**：能力库根 = `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`（技能资产，非 ProjectSpec 文档），**允许直接 read_file 读取**（仅读，禁止写入）。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「请先运行 doc-kit 初始化该项目」，终止流程，不尝试任何自举安装。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py spec read
python .doc-kit/cli/cli.py spec write --json '<完整 spec JSON>'   # 全量写入，也可从 stdin 读入
python .doc-kit/cli/cli.py spec archive
```

> 输出约定：JSON 结果含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败；纯文本输出（spec read）以「错误:」开头即失败。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根。
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

调 `python .doc-kit/cli/cli.py spec read` 获取完整的议题数据。

### Step 3：修改为作废状态

在 spec 上设置：
- `status` → `"abandoned"`
- `closed_at` → 当前时间 ISO 8601
- `closed_reason` → 用户提供的原因

### Step 4：写入并归档

1. 调 `python .doc-kit/cli/cli.py spec write --json '<spec_json>'` 保存作废状态
2. 调 `python .doc-kit/cli/cli.py spec archive` 归档

### 成功后

- 议题被标记为 abandoned，移至 SessionSpec/archive/
- 下次 `python .doc-kit/cli/cli.py spec status` 返回「没有活跃议题」

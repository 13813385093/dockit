---
name: spec-abort
description: 作废当前议题，非正常终止时使用
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**CLI 定位（按优先级，执行前先确认）**：
1. 项目内已部署：`<项目根>/.doc-kit/cli/cli.py`
2. 项目内 skill 目录：`<项目根>/skills/scripts/cli.py`
3. 全局 skills 目录：`$REASONIX_HOME/skills/`（Windows 默认 `%APPDATA%\reasonix`，macOS/Linux `~/.reasonix`）下任意 `*/scripts/cli.py`（可用 `find` 在 workspace 与上述目录中搜索）

**首次自举**：若 1 不存在，先运行 `python <定位到的 cli.py> deploy`，将 CLI 部署到 `<项目根>/.doc-kit/cli/`。部署后一律从项目根调用：

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

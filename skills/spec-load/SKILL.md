---
name: spec-load
description: 加载活跃议题并复述待决议议程，重开上下文续接讨论
---
# 最高优先级：

在本次 Skill 执行过程中，任何文件读取或写入操作，**一律必须**通过 doc-kit 共享 CLI 执行（禁止直接 read_file / write_file 操作这些文件）。

**前置条件（不满足直接退出，无兜底）**：项目必须已由 doc-kit 初始化，CLI 已安装于 `<项目根>/.doc-kit/cli/cli.py`（由 doc-kit 工具 `init` 生成）。若该文件不存在，输出「请先运行 doc-kit 初始化该项目」，终止流程，不尝试任何自举安装。

工具调用（从项目根执行）：

```bash
cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录
python .doc-kit/cli/cli.py spec status
python .doc-kit/cli/cli.py spec read
```

> 输出约定：`spec status` / `spec read` / `spec schema` 直接输出文本——`spec status` 是一行中文状态描述，`spec read` 是议题 JSON（无活跃议题时输出中文提示），`spec schema` 是字段定义 JSON；三者失败时以「错误:」开头。其余命令输出 JSON 信封，含 `success` / `message` / `data` / `suggestions` 字段，退出码 0 = 成功、1 = 失败。未指定 `--root` 时 CLI 从当前目录向上自动查找项目根；`--root` 是全局参数，必须写在命令组（`spec` / `doc` / `dev`）之前。
---

# spec-load — 重开上下文，续接议题

## 定位

用于**上一次讨论把上下文占满、需要重开一段对话**的场景。

加载活跃议题，**首先把待决议的议程逐条复述出来**，让用户与 AI 找回讨论位置，然后接着往下谈。本技能是只读前导动作，不落盘、不改状态。

## 在哪选

每次新对话的第一步。若当前没有活跃议题，本技能只做引导，不代替用户创建议题。

## 选择判断

### Step 1：看状态

调 `python .doc-kit/cli/cli.py spec status`，把结果作为一句话现状告诉用户。

### Step 2：路由（按 `spec read` 的输出形态判定，不做中文字符串匹配）

调 `python .doc-kit/cli/cli.py spec read`：

| 输出形态 | 含义 | 下一步 |
|---------|------|--------|
| 能解析为 JSON（含 `session_spec_id`） | 有活跃议题 | 进入 Step 3 复述议程 |
| 以「错误:」开头 | 数据或 CLI 异常 | 原文报告错误，终止流程 |
| 其它（如「当前没有活跃议题…」） | 无活跃议题 | 引导用户用 `spec-start` 开启新议题 |

### Step 3：复述议程（本技能的关键动作，必做）

从 `spec read` 的 JSON 中取 `pending_decisions` / `resolutions` / `next_steps`，**先列议程，再列已决议与后续计划**：

```
📌 议题 20260618-cert-auth ｜场景：技术评审 ｜状态：active

待决议议程（3 项）：
 ① 认证协议选型 —— needs_discussion
    待澄清：OAuth2 与自签 JWT 的取舍，是否引入第三方 IdP
 ② token 有效期策略 —— needs_discussion
 ③ 与网关的鉴权边界 —— deferred（上次搁置）

已决议（2 项）：
 - 认证失败统一返回 401 —— 由网关拦截并记录审计日志
 - 用户表沿用现有 user_id 主键 —— 不引入外部身份主键

后续计划（1 项）：
 1. 下次议事先定 token 有效期

请选择要推进的议题（也可以直接抛出新话题，我会把它加入议程）。
```

规则：

- **议程 = `pending_decisions` 中 `status != "resolved"` 的全部条目**，逐条列出 `topic` + `status` + `note`，**一条都不能省略**——这是重开上下文时唯一的信息重建块。
- 已决议只列 `topic：decision` 摘要，不必展开 `detail`。
- 议程已清空（全部 resolved）时，提示用户可执行 `spec-close` 做结清与文档写入。

### Step 4：续接讨论

按用户选择继续推进对应议题。并说明本次讨论的落盘规则：

- 讨论期间**不落盘**；需要保存时说一句，执行 `spec-pause`；
- 需要结束议题时执行 `spec-close`（届时统一写入 `ProjectSpec/`）或 `spec-abort`。

## 边界

- **只读**：本技能只允许 `spec status` / `spec read`，不调用任何写命令
- 不做 DevSpec 的状态检查（开发循环由 `spec-dev-loop` 负责）
- 不代替用户做决议：复述议程是"提问"，不是"复述结论"

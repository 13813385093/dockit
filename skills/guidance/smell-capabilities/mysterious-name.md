---
smell: mysterious-name
mode: deep
evidence_scope: file+spec
default_confidence: medium
---
# 神秘命名（Mysterious Name）

## 识别症状

新增或语义变化的公开符号名字不透露用途/领域含义：

- `tmp`、`x`、`obj`、`result`、`Handler`、`Manager` 这类泛化名；
- 名字暗示旧语义，但本次 diff 改变了它的行为（例如 `is_paired` 现在“半连也算 true”）；
- 名字是特性编号（`f2_`、`F6`）而不是领域语义。

## 最小证据门槛

- 只报**新增或语义变化的公开符号**（导出函数/类/模块级 API）；
- 名字无法从 ProjectSpec / domain-model / inter-module-contracts 中找到语义；
- 不是项目约定的缩写（`ctx`、`req`、`err`、`i`）或契约字段名（`svc`、`biz`、`ev`、`lvl`、`seq`）。

## 误报排除

1. **契约字段/领域术语**：`inter-module-contracts` 或 `domain-model` 中已定义的字段名，即使短（`svc`/`biz`/`ev`），不报。
2. **约定缩写**：`ctx`、`req`、`err`、`i`、`it`、`kv` 等项目/语言惯例，不报。
3. **短生命周期局部变量**：3 行循环里的 `i`、临时 `tmp`，若作用域极小且立即使用，不报。
4. **名字是旧语义但本次未改行为**：只改注释/格式，不报。

## 修复方向

重命名为业务语义名；如果想不出诚实名字，说明设计本身还含糊，先重新界定职责。

```diff
- bool is_paired(const std::string& peer_id) const;  // 半连也为 true，名字误导
+ bool has_inbound_handshake(const std::string& peer_id) const;
```

## 何时不问

- 名字已在契约/领域模型中定义；
- 项目有强命名规范且 linter 已覆盖（可跳过，避免与工具重复）；
- 只是局部临时变量，作用域不足以造成误解。

# 代码异味能力索引（smell-capabilities 入口）

> 用途：`spec-code-smell` 的加载入口。先读本文档，按模式与源文件发现规则确定扫描范围，再按需加载单个能力文件。
> 本文档定义当前行为规则：快速/深入双模式；源码按文件分类，**不绑定 `src/`**；测试默认不扫。

## 1. 加载规则

1. **只加载索引**：启动时只读本文件，不要一次读入全部能力文件。
2. **按模式取清单**：快速模式 4 项，深入模式 8 项（见 §3）。
3. **命中后加载**：先用 §4 的最小证据门槛筛候选；命中候选后，才读对应 `<name>.md` 的误报排除与修复方向。
4. **已知例外优先**：报出前先查 §5；命中“已知/已确认”的不作为新发现。
5. **能力文件只读**：`smell-capabilities/` 是技能资产，禁止写入；不要把它当 ProjectSpec 文档修改。

## 2. 源文件发现（不绑定 `src/`）

### 2.1 原则

**源码是文件属性，不是目录名。** 不得默认“源码在 `src/`”。一个文件是不是源码，由**扩展名 + 排除规则**决定；无论它在 `src/`、`include/`、`cmd/`、`internal/`、`packages/*/src`、`app/`、`lib/` 还是仓库根目录。

常见布局：

| 项目类型 | 常见源码位置 |
|---|---|
| C/C++ | `src/`、`include/`、根目录 `.cpp/.h`、`modules/`、`components/` |
| Python | 根目录包、`src/` 布局、`app/`、`scripts/` |
| Go | `cmd/`、`internal/`、`pkg/`、根目录 `.go` |
| Rust | `src/`、`crates/*/src` |
| JS/TS | `src/`、`app/`、`pages/`、`packages/*/src`、`lib/` |
| Java/Kotlin | `src/main/java`、`modules/` |
| Monorepo | `packages/*`、`services/*`、`apps/*` |

### 2.2 枚举

```bash
git diff --name-only --diff-filter=ACMR <from>..<to>
```

只判断变更文件；不需要先建立全仓库源码根。

### 2.3 源码扩展名（默认）

- C/C++：`.c` `.cc` `.cpp` `.cxx` `.h` `.hh` `.hpp` `.hxx` `.ipp` `.inl`
- Python：`.py` `.pyi`
- Rust/Go/Java/Kotlin/C#：`.rs` `.go` `.java` `.kt` `.kts` `.cs`
- JS/TS：`.ts` `.tsx` `.js` `.jsx` `.mjs` `.cjs` `.vue` `.svelte`
- 其它：`.rb` `.php` `.swift` `.m` `.mm` `.scala`
- 脚本（低优先级）：`.sh` `.bash` `.zsh` `.ps1`
- 构建/配置（默认不扫）：`CMakeLists.txt`、`*.cmake`、`package.json`、`pyproject.toml`、`go.mod` 等

### 2.4 默认排除

- 文档/项目资产：`docs/`、`doc/`、`DevSpec/`、`ProjectSpec/`、`ReviewSpec/`、`SessionSpec/`、`.doc-kit/`、`*.md`、`*.rst`、`README*`、`CHANGELOG*`、`LICENSE*`
- 测试（默认排除，用户可显式开启）：`tests/`、`test/`、`__tests__/`、`test_*.py`、`*_test.*`、`*_spec.*`
- 构建/产物：`build/`、`build-*`、`dist/`、`out/`、`target/`、`cmake-build-*`、`*.min.*`、`*.generated.*`、`*_pb2.py`
- 依赖/vendor：`vendor/`、`third_party/`、`3rd/`、`external/`、`deps/`、`node_modules/`
- 缓存/环境：`.git/`、`.venv/`、`venv/`、`__pycache__/`、`.pytest_cache/`、`.cache/`、`logs/`；其它以 `.` 开头的隐藏文件/目录默认视为配置/缓存

**不要**凭名字排除 `lib/`、`bin/`、`tools/`、`scripts/`、`utils/`、`app/`、`packages/`：它们可能是源码，也可能是产物；让扩展名和用户指令决定。

### 2.5 歧义

- 未知扩展名（`.inc`、`.tpp`、`.cu`、`.m4` 等）→ 列入“未识别”，问用户是否纳入，不静默丢弃；
- `lib/`、`bin/`、`tools/` 等有源码扩展名的文件 → 纳入，并在摘要里标出；
- 生成物但有源码扩展名（如 `*.pb.cc`）→ 按生成物模式排除，并在摘要里列出；
- 用户指令最高优先：`只扫 include/ utils/`、`包含 tests`、`排除 3rd/` 等自然语言覆盖默认值。

### 2.6 范围摘要（硬要求）

扫描前必须输出，让用户能纠错：

```text
扫描范围（按文件分类，不绑定 src/）：
  将扫描 N 个源文件：
    <目录>   <数量>
  排除：
    tests/...  <数量>（默认排除；说“包含 tests”可开启）
    docs/...   <数量>
    vendor/... <数量>
    build/...  <数量>
  未识别扩展名：
    <path>  <数量>（默认不扫；要扫请指定）
  如不符合预期，请直接指定路径或说“包含 tests / 排除 X”。
```

### 2.7 上限

- 源码 diff 上限：1,200 行或 80KB；
- 超出：按顶层目录拆分，或先扫用户指定子集；不静默截断；
- 测试/文档不计入源码上限，但摘要要说明。

## 3. 模式

| 模式 | 何时用 | 能力 |
|---|---|---|
| **快速（默认）** | 日常 feature/PR diff | `duplicated-code`、`long-parameter-list`、`speculative-generality`、`message-chains` |
| **深入（按需）** | 用户说“深入/代码形态/重构前”；bugfix/重构且用户同意 | 快速 4 项 + `mysterious-name`、`primitive-obsession`、`data-clumps`、`shotgun-surgery` |

- 默认快速；不要自动跑深入。
- 深入模式仍最多 10 条；低置信度项可合并说明。

## 4. 能力清单

| 能力文件 | 异味 | 模式 | 证据范围 | 默认置信度 | 最小证据门槛 |
|---|---|---|---|---|---|
| `duplicated-code.md` | 重复代码 | quick | diff | 高 | 同形态新增代码 ≥6 行或 ≥3 条语句；不同位置重复 |
| `long-parameter-list.md` | 参数过多 | quick | diff/file | 高 | 生产函数 ≥5 个参数；测试 builder/夹具豁免 |
| `speculative-generality.md` | 为未来而设计 | quick | repo/spec | 中 | 新抽象/参数/hook 在 diff 外无调用，且 ProjectSpec 未要求；已知设计缺口豁免 |
| `message-chains.md` | 过长链式调用 | quick | diff/file | 中 | 4+ 连续调用；排除 fluent/Builder/ORM；跨对象导航 |
| `mysterious-name.md` | 神秘命名 | deep | file/spec | 中 | 新增或语义变化的公开符号；排除契约字段/领域术语/约定缩写 |
| `primitive-obsession.md` | 原始类型迷恋 | deep | file/spec | 中 | 裸类型承担领域概念；或 map-as-set / 恒真 bool 等集合形态 |
| `data-clumps.md` | 数据泥团 | deep | file/diff | 中 | 同一组 ≥3 字段/参数在 ≥2 处一起出现；排除 DTO/Payload |
| `shotgun-surgery.md` | 散弹式修改 | deep | diff/spec | 低 | 同一逻辑变更散在 ≥3 个生产模块，且无单一归属；排除 tests/docs/config |

> 快速模式只报高/中置信度；低置信度只在深入模式出现，并明确标注。

## 5. 已知例外

报出前先查以下来源；命中则标注“已知”，不作为新发现：

1. `DevSpec/archive/<sid>/code-notes.md`：设计偏差 / 重点关注区域 / 已在开发循环确认的取舍；
2. 最近一份 `ReviewSpec/` 报告：同一范围或同一 feature 是否已确认；
3. `ProjectSpec`：`global-policies.md`（代码规范/命名/架构模式）、`inter-module-contracts.md`（字段/签名）、`module-*/domain-model.md`（值对象/领域术语）。

规则：

- 只命中“已记录”时，不报新问题；可在输出里用一句“已知项：…（不重复展开）”；
- 无法判断是否已知时，向用户说明并询问，不擅自 suppress；
- 不得用“项目风格如此”作为无证据的 override；必须引用 policy 章节/编号/原文或已知记录。

## 6. 输出与上限

- 最多 10 条；按置信度 × 影响排序；
- 每条：`异味`、`位置`、`置信度`、`影响`、`证据`、`为什么可能是误报`、`建议方向`；
- 零发现也要说明扫描范围、已检查项、局限；
- **同一根因只报一次**：Long Parameter List 与 Data Clumps 重叠时优先报 Long Parameter List（更机械）；Speculative Generality 与 Data Clumps 等重叠时保留证据更强的一条；
- 不写 ReviewSpec/ProjectSpec、不改锚点、不自动改代码。

## 7. 语言专项预留

当前不提供语言专项；未来扩展时：

- 在根目录加 `<language>-<smell>.md`，不要建空子目录；
- 在本表增加“语言/框架”列与加载条件；
- 只有检测到对应语言/框架且用户开启时才加载。

## 8. 参考

- Fowler, *Refactoring* (2018), ch.3 的异味清单；
- Matt Pocock `code-review` 的 12 项 baseline（2018 版子集）；
- 本项目 `skill-rubric.md` 的 D7 / 渐进披露原则。

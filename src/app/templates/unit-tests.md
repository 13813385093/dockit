---
doc_type: unit_test
module: $module
feature: $feature
level: feature
version: 0.1.0
last_updated: $now            # 生成时由工具替换为 ISO 8601 日期
author: $author               # 文档负责人（团队角色或人名）
status: active
deprecated_at:                   # 废弃日期（status=deprecated 时必填）
deprecated_reason:               # 废弃原因（status=deprecated 时必填）
superseded_by:                   # 替代文档列表（废弃且存在替代时必填）
  - doc: <替代文档>
    module: <所属模块>
archived_at:                     # 归档日期（status=archived 时必填）
implemented_in:                  # 实现位置，工具校验路径存在性（见 §3.5.9）
  - path: <测试源码目录>
    lang: <语言>
depends_on: []                # 声明依赖的其他文档（见 §3.5.7）
---

# 单元测试

<!-- 每一个 $feature 对应一组单元测试用例（GWT 结构，语言无关、纯描述性，见 §3.5.6）。
不写 mock 细节或框架调用——那些归源码测试文件（见 §3.3.2）。
「覆盖约束」行声明本用例验证的约束 ID；门禁 G4 据此机械校验每个编号的 [MUST] 约束至少被一个场景引用（见 §3.9.3）。 -->

## $feature

### 测试用例：<!-- 用例名称 -->

覆盖约束: [引用的约束 ID，如 C-101；无则省略]

#### Given 前置条件

<!-- 
描述测试的初始状态和数据准备。
正例：
  模拟电压异常场景，电压值为额定值的 120%
-->

- <!-- 前置条件1 -->
- <!-- 前置条件2 -->

#### When 触发动作

<!-- 
描述测试的触发动作；调用函数时引用 feature-design.md「函数调用关系」章节的函数名（见 §3.5.6）。
正例：
  保护装置监测到电压异常
  调用 detectOverVoltage(samples, threshold)
-->

- <!-- 触发动作 -->

#### Then 预期结果

<!-- 
描述测试的断言或预期输出。
正例：
  系统在 4ms 内发出 GOOSE 跳闸报文
  跳闸报文重传次数为 3 次
-->

- <!-- 预期结果1 -->
- <!-- 预期结果2 -->

---

### 更多用例

<!-- 复制上述模板，一个测试用例一个 ###  -->

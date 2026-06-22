---
doc_type: unit_test
module: $module
feature: $feature
level: feature
version: 0.1.0
last_updated: $now
status: active
depends_on:
$depends_on_yaml
---

# 单元测试

<!-- 每一个 $feature 对应一组单元测试用例。 -->

## $feature

### 测试用例：<!-- 用例名称 -->

**前置条件** (Given)：

<!-- 
描述测试的初始状态和数据准备。
正例：
  模拟电压异常场景，电压值为额定值的 120%
-->

- <!-- 前置条件1 -->
- <!-- 前置条件2 -->

**触发条件** (When)：

<!-- 
描述测试的触发动作。
正例：
  保护装置监测到电压异常
-->

- <!-- 触发动作 -->

**预期结果** (Then)：

<!-- 
描述测试的断言或预期输出。
正例：
  系统在 4ms 内发出 GOOSE 跳闸报文
  跳闸报文重传次数为 3 次
-->

- <!-- 预期结果1 -->
- <!-- 预期结果2 -->

#### 测试代码

<!-- 
使用 Given-When-Then 注释标记测试代码结构。
正例：
  def test_voltage_over_threshold_triggers_trip():
      # Given: 模拟电压异常场景
      sv_data = create_sv_data(voltage=1.2 * RATED_VOLTAGE)
      
      # When: 保护装置监测到异常
      result = protection_monitor.process(sv_data)
      
      # Then: 验证 GOOSE 报文生成
      assert result.goose_command.pos_ctl_val == False
      assert result.latency <= 0.004  # ≤4ms
-->

```python
def test_<!-- 用例名称 -->():
    # Given:
    
    # When:
    
    # Then:
    assert 
```

---

### 更多用例

<!-- 复制上述模板，一个测试用例一个 ###  -->

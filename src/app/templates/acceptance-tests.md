---
doc_type: acceptance_test
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

# 验收测试

<!-- 每一个 $feature 对应一组验收测试场景（BDD/Gherkin 格式，见 §3.5.8）。
文件组织（§3.5.8）：所有场景写入同一份 acceptance-tests.md，不建议按场景拆分文件；
场景数量过多时适当精简描述粒度。 -->

## $feature

```gherkin
# language: zh-CN
功能: <!-- 功能名称 -->
  作为 <!-- 角色 -->
  我希望 <!-- 期望功能 -->
  以便 <!-- 业务价值 -->

  场景: <!-- 正常路径 -->
    假设 <!-- 前置条件 -->
    当  <!-- 触发动作 -->
    那么 <!-- 预期结果1 -->
    并且 <!-- 预期结果2 -->

  场景: <!-- 异常路径 -->
    假设 <!-- 前置条件 -->
    当  <!-- 触发动作 -->
    那么 <!-- 系统应做出的响应 -->
```

<!-- 
正例：
  功能: 电压异常跳闸保护
    作为 电网调度员
    我希望 系统在电压异常时快速跳闸
    以便 保护设备安全

    场景: 电压过阈值触发跳闸
      假设 A相电压为额定电压的120%
      当 保护装置进行故障检测
      那么 系统在4ms内发出GOOSE跳闸报文
      并且 跳闸报文的重传次数为3次

    场景: 电压正常不应跳闸
      假设 A相电压为额定电压的100%
      当 保护装置进行故障检测
      那么 不应生成跳闸指令
-->

---

### 更多场景

<!-- 每个功能可以有多个场景，复制上方模板 -->

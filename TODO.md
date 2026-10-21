# 待办：技能与工具链

> **本文件只记录尚未解决的问题。** 已解决的不保留——历史见 `skills/scripts/cli.py` 的
> `TOOLCHAIN_VERSION` 版本历史（每次发布都带一句变更说明）与 git 提交记录。
> 已判定"不改"的事项同样不保留，避免与待办混淆；将来若要重新评估，按下面的格式新开一条。

## 怎么记录一个问题

每条待办写四个字段。**写不出「现象」就不要记**——那说明还没到能动手的程度，先继续观察；
**写不出「触发条件」就说明它可能不该现在做**。

| 字段 | 要求 |
|---|---|
| **现象** | 可复现的事实：触发步骤 + 观察到的结果。实测优先于推测；没验证过的部分要标明"未验证" |
| **影响** | 具体后果：哪一步会失败、谁会误判、是否可逆。区分「会导致错误」与「只是不便」 |
| **触发条件** | 什么可观测的事件发生后，这条才值得动手。这是防止待办腐烂的关键字段 |
| **建议方案** | 首选做法 + **被否掉的做法及原因**（避免下次重复讨论同一组选项） |

命名：用**一句话标题**（如「技能正文里 CLI 调用的选项级校验」），**不要编号**——本文件按"解决即删除"维护，编号会随时间漂移，做不了稳定引用。
**解决后直接删除该条目**（不要改成"已完成"留着）。

---

## 相关约定（改工具链前必读）

改 `skills/**` 或 `src/app/templates/**` 后按 5 步走，缺一步会被检具拦住：

```bash
# 1 改内容 → 2 递增 cli.py 的 TOOLCHAIN_VERSION（YYYY.MM.N）
python tests/render_skill_preamble.py                   # 3 把新版本注入 8 份 SKILL.md
python tests/check_toolchain_version.py --update --note "<一句变更说明>"   # 4 更新指纹 + 追加版本历史
python -m pytest tests/                                 # 5 全量测试
```

- `python -m pytest tests/` **确实覆盖全部四个检具**：`check_skill_sync`（由
  `tests/test_skill_sync_collected.py` 包装）、`check_toolchain_version`（`test_toolchain.py`）、
  前言生成物一致性（`test_skill_preamble.py`）、`check_doc_consistency`（`test_doc_types.py`）。
  另有三组内容级检具同在其中：`test_cli_usage_contract.py`（USAGE 表 ↔ 真实 argparse 树）、
  `test_cli_self_consistency.py`（CLI 自己给出的建议必须能被 CLI 自己接受）、
  `test_skill_content_rules.py`（状态枚举、非真实状态名、前言断言、输出归属、描述预算）。
- **本仓库不接 CI**（2026-09-16 决定）：由作者本人维护，检具的价值在"改完立刻能跑"，
  而不在"有人替我记得跑"；多一条流水线只是给上面这套流程再加一层需要维护的配置。

---

## 待办

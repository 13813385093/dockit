"""spec-dev-loop 技能文本契约测试。

锁定《04-spec-dev-loop-改进方案》与《05-设想反思》中经用户确认的设计决策，
防止后续改动把流程悄悄改回"主代理自己实现 + 自测即完成"的旧形态：

  B1 骨架先行：任务必须带 implemented_in（实现落点）
  B2 委托实现有验收闸门：submitted → accepted 只能由主代理置位，且禁止采信子代理自述
  B3 测试与验收分离：GWT 单元测试在验收之后（tested），验收测试（Gherkin）是 align 的前置
  B4 派发单元 = 内聚调用链/单文件，可并行的条件是落点文件不同（不是"一方法一代理"）
  B5 三层边界：ProjectSpec 只读经 CLI / DevSpec 经 CLI / 源码与测试直接读写
  B6 签名变更协议、右尺寸规则、横切工作出口必须存在
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL_MD = REPO / "skills" / "spec-dev-loop" / "SKILL.md"
SCRIPTS = REPO / "skills" / "scripts"


@pytest.fixture(scope="module")
def text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def tool_block(md: str) -> str:
    blocks = re.findall(r"```bash\n(.*?)```", md, re.S)
    return "\n".join(blocks)


class TestSkeletonFirst:
    def test_implemented_in_is_mandatory_in_flow(self, text):
        assert "implemented_in" in text
        assert "骨架" in text and "Phase 2" in text
        # 骨架阶段必须产出落点，并且明确禁止无落点开工
        assert "没有 `implemented_in`" in text or "没有 implemented_in" in text

    def test_skeleton_has_user_confirmation_gate(self, text):
        assert "用户确认骨架" in text

    def test_style_snapshot_reference_is_literal(self, text):
        """§2.5 引用必须是可执行的字面量（旧版 '<plan.md>#...' 占位符会被 CLI 拒绝）。"""
        assert "plan.md#2.5 代码风格快照" in text
        assert "<plan.md>" not in text, "占位符写法会被 dev plan update-section 拒绝"


class TestDelegationAndAcceptance:
    def test_dispatch_unit_is_cohesive_not_per_method(self, text):
        assert "派发单元 = 一个文件内的一个内聚调用链" in text
        assert "可并行 ⟺ 各单元落点文件互不相同" in text

    def test_subagent_selfreport_not_accepted(self, text):
        assert "不得采信子代理的自述" in text
        assert "不作为验收依据" in text

    def test_acceptance_checklist_exists_and_is_mechanical_first(self, text):
        assert "附录 B" in text and "验收清单" in text
        assert "机械" in text and "高风险" in text

    def test_mixed_mode_keeps_high_risk_with_main_agent(self, text):
        assert "主代理亲自" in text

    def test_subagents_forbidden_from_git_and_projectspec(self, text):
        assert "子代理禁止" in text or "子代理不" in text
        assert "执行 git 命令" in text  # 简报【禁止】项


class TestTestGates:
    def test_unit_tests_after_acceptance(self, text):
        """tested 必须在 accepted 之后（分层闸门），且 done 需先 tested。"""
        assert "--status tested" in text
        assert "--status accepted" in text
        # 状态机描述顺序
        assert text.index("Phase 3：逐方法实现") < text.index("Phase 4：单元测试")

    def test_acceptance_tests_retained_for_align(self, text):
        assert "acceptance-tests.md" in text
        assert "Gherkin" in text
        assert "dev align" in text

    def test_fake_green_still_forbidden(self, text):
        assert "假绿" in text


class TestBoundaries:
    def test_three_layer_boundary_table(self, text):
        assert "三层边界" in text
        assert "源码与测试代码" in text and "直接读写" in text
        assert "只读，经 CLI" in text

    def test_projectspec_readonly_discipline_kept(self, text):
        assert "ProjectSpec 全程只读" in text

    def test_signature_change_protocol(self, text):
        assert "附录 D" in text and "签名变更协议" in text
        assert "冻结基线" in text

    def test_right_sizing_rule(self, text):
        assert "附录 E" in text and "右尺寸" in text

    def test_cross_cutting_exit(self, text):
        assert "附录 F" in text
        assert "不走本技能" in text

    def test_module_scope_demoted(self, text):
        assert "附录 C" in text and "模块专项" in text
        # 日常入口只有 feature
        assert "--scope feature" in text


class TestSkillCliConsistency:
    """技能里写的状态值必须与 CLI 状态机一致（防止文本再次漂移）。"""

    def cli_statuses(self) -> list[str]:
        import sys

        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import cli

        return list(cli.DEV_TASK_STATUSES)

    def test_skill_uses_only_real_statuses(self, text):
        statuses = self.cli_statuses()
        used = set(re.findall(r"--status ([a-z-]+)", text))
        # tasks-done 之外的已知里程碑状态（dev align/integrate 用）不算任务状态
        milestones = {"aligned", "integrated", "documented"}
        unknown = used - set(statuses) - milestones
        assert not unknown, f"技能引用了不存在的状态: {unknown}；CLI 允许: {statuses}"

    def test_old_statuses_are_gone(self, text):
        for stale in ("in-progress", "unit-green", "fixing"):
            assert f"--status {stale}" not in text, f"残留旧状态 {stale}"

    def test_task_card_example_matches_schema(self, text):
        """技能里的任务卡示例字段必须全部是 CLI 允许的字段（否则写入即报错）。"""
        import sys

        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import cli

        block = re.search(r"```json\n(\{.*?\})\n```", text, re.S)
        assert block, "技能中应包含任务卡 JSON 示例"
        card = json.loads(block.group(1))
        unknown = [k for k in card if k not in cli.TASK_ALLOWED_KEYS]
        assert not unknown, f"任务卡示例含 CLI 不接受的字段: {unknown}"
        # 必备的骨架字段
        for key in ("implemented_in", "cls", "symbol", "calls", "capability_notes"):
            assert key in card, f"任务卡示例缺少骨架字段 {key}"


# ═══════════════════════════════════════════════════════════════
#  2026.11.3 反馈修复：表外产物 / Red-Green / 静态诊断 / 任务粒度 / 分支断言
# ═══════════════════════════════════════════════════════════════

class TestOutOfTableArtifacts:
    """DEV-2：表外产物（DDL/迁移、共享类型、隐含写入）必须有正式位置。"""

    def test_phase2_lists_out_of_table_artifacts(self, text):
        assert "表外产物" in text
        assert "helper" in text
        assert "入口签名冻结不适用" in text  # 与附录 D 的关系
        assert "表外产物：" in text  # 骨架确认模板新增行

    def test_helper_card_convention(self, text):
        for phrase in ("[helper]", "HELPER:", "允许为空", "不豁免"):
            assert phrase in text, f"表外产物 helper 约定缺：{phrase}"


class TestRedGreenLoop:
    """DEV-4：每任务 Red-Green 闭环，红灯不达标不得置 tested。"""

    def test_phase3_has_red_step(self, text):
        assert "测试先行" in text and "Red" in text
        assert "_red.log" in text
        assert "有效红灯" in text
        assert "编译失败、导入失败、语法错误不算有效红灯" in text
        assert "VERIFY:" in text  # 无 gwt_refs 的任务必须有可执行验证方式

    def test_phase4_is_green_acceptance(self, text):
        assert "Green" in text and "_green.log" in text
        assert "红绿测试名" in text or "测试名/用例 ID 必须一致" in text
        assert "不得置 `tested`" in text or "不得置 tested" in text

    def test_phase4_command_has_pipefail(self, text):
        start = text.index("## Phase 4")
        assert "set -o pipefail" in text[start:], "Phase 4 测试命令必须在 pipefail 下运行"

    def test_brief_forbids_test_assertions(self, text):
        assert "不得包含测试断言" in text
        assert "不得包含测试代码或断言" in text

    def test_baseline_change_reopens_red(self, text):
        assert "基线变更后重开红灯" in text


class TestStaticDiagnostics:
    """DEV-5：静态诊断前置，只拦本次新增，未配置则跳过。"""

    def test_appendix_b_has_static_diagnostics(self, text):
        assert "静态诊断" in text
        assert "lint" in text and "typecheck" in text
        assert "历史问题不得阻断" in text
        assert "skipped: not configured" in text
        assert "--new-from-rev" in text  # 增量参数示例
        assert "_static.log" in text


class TestTaskGranularity:
    """DEV-6：默认按单文件内聚调用链切分，附录 E 只管流程开销。"""

    def test_cohesive_chain_and_split_criteria(self, text):
        assert "内聚调用链" in text
        for phrase in ("被多个入口调用", "独立 `gwt_refs`", "高风险", "超过 3 个方法", "独立验收"):
            assert phrase in text, f"拆分判据缺：{phrase}"

    def test_appendix_e_is_process_size_not_granularity(self, text):
        assert "与任务粒度无关" in text

    def test_appendices_support_multi_function_cards(self, text):
        assert "伴生函数清单" in text
        assert "全部函数签名" in text
        assert '"signatures"' in text


class TestDevTaskPatchText:
    """DEV-3：轻 = patch，重 = set。"""

    def test_light_and_heavy_paths(self, text):
        assert "dev task patch" in text
        assert "轻 = `dev task patch" in text
        assert "重 = `dev task set`" in text


class TestBranchAssertionText:
    """DEV-7：只读 .git/HEAD、读命令始终允许、例外矩阵、dev branch set。"""

    def test_read_only_head_and_read_commands(self, text):
        normalized = text.replace("`", "")
        assert "只读 .git/HEAD" in normalized
        assert "读命令始终允许" in text
        assert "--allow-branch-mismatch" in text
        assert "dev branch set" in text
        assert "dev_branch.mismatch" in text

    def test_phase0_uses_structured_branch_fields(self, text):
        assert "data.branch" in text and "data.branch_matches" in text


class TestStateMachineTable:
    """DEV-1：技能里的状态转移表必须与 CLI 的 DEV_TASK_TRANSITIONS 一致。"""

    def _block(self, text):
        m = re.search(r"### 任务状态机.*?```text\n(.*?)```", text, re.S)
        assert m, "技能中缺少任务状态机表"
        return m.group(1)

    def test_all_statuses_present(self, text):
        import sys

        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import cli

        block = self._block(text)
        for status in cli.DEV_TASK_STATUSES:
            assert status in block, f"状态表缺状态：{status}"

    def test_all_transitions_present(self, text):
        import sys

        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import cli

        block = self._block(text)
        for src, dests in cli.DEV_TASK_TRANSITIONS.items():
            for dst in dests:
                assert f"{src} → {dst}" in block, f"状态表缺迁移：{src} → {dst}"

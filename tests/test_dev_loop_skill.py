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

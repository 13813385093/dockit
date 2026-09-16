"""议题（SessionSpec）类技能改造后的行为契约回归测试。

对应议题类技能的改造基线（三条，均已固化在本测试与 SKILL.md 中）：

  B1 两个落盘点 —— 讨论期间不落盘；只有 spec-start（建议题）与 spec-pause（保存）写
      SessionSpec/active/。
  B2 ProjectSpec 单点写入 —— 议题链路上只有 spec-close 写 ProjectSpec/；
      start / load / pause / abort 一律不碰。
  B3 议程驱动 —— pending_decisions 就是议程：建立 → 复述 → 推进 → 结清。

测试分两部分：
  1. 行为契约：用 CLI 走一遍 start → pause → close/abort，断言文件副作用边界；
  2. 技能文本契约：断言 SKILL.md 与上述边界一致（防止技能描述再次漂移回"pause 写文档"）。
"""
from __future__ import annotations

import hashlib
import re
import json
from pathlib import Path

import pytest

from conftest import make_index, make_md

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"

DETAIL = (
    "选择自签 JWT 而不引入第三方 IdP：项目已有用户表与密钥管理能力，引入外部 IdP 会增加运维面、"
    "联调成本与合规评审工作量；代价是需自行实现密钥轮换与令牌吊销，已作为后续议程记录。"
    "约束：令牌签名算法固定 RS256，密钥有效期 90 天，过期前 7 天轮换。影响范围：认证模块与网关鉴权；"
    "网关侧需同步调整鉴权白名单与错误码映射，相关契约变更随本议题一并记录并纳入下一轮评审。"
)

AGENDA = [
    {"topic": "认证协议选型", "status": "needs_discussion", "note": "OAuth2 与自签 JWT 的取舍"},
    {"topic": "token 有效期策略", "status": "needs_discussion", "note": "30min 还是 60min"},
]


def docs_fingerprint(project: Path) -> str:
    """ProjectSpec/ 全文指纹，用于断言"文档是否被改动"。"""
    h = hashlib.sha256()
    for f in sorted((project / "ProjectSpec").rglob("*.md")):
        h.update(f.relative_to(project).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def read_spec(cli_env) -> dict:
    return json.loads(cli_env.spec_read())


def write_spec(cli_env, spec: dict) -> dict:
    return json.loads(cli_env.spec_write(json.dumps(spec, ensure_ascii=False)))


# ── fixtures ──

@pytest.fixture
def project(cli_env, tmp_project):
    """带项目规格文档与索引的临时项目（spec write / doc structure 的前置条件）。"""
    make_md(tmp_project, "ProjectSpec/technical-framework.md",
            "---\nversion: 1\nlast_updated: 2026-01-01\nauthor: t\ndepends_on: []\n---\n"
            "# 技术框架\n\n## 技术栈概览\n\n待补充\n\n## 主要框架与中间件\n\n待补充\n")
    make_index(tmp_project, [{
        "path": "ProjectSpec/technical-framework.md",
        "doc_type": "technical_framework",
        "level": "top",
        "module": "project-charter",
        "name": "technical-framework.md",
        "depends_on": [],
        "sections": ["技术栈概览", "主要框架与中间件"],
    }])
    return tmp_project


def start_issue(cli_env, project, sid="20260618-cert-auth", agenda=None) -> dict:
    """模拟 spec-start：建立议题并把议程落地。"""
    return write_spec(cli_env, {
        "session_spec_id": sid,
        "scenario": "tech-ref",
        "status": "active",
        "resolutions": [],
        "pending_decisions": agenda if agenda is not None else AGENDA,
        "next_steps": [],
    })


# ── 1. 行为契约 ──

class TestAgendaLandsAtStart:
    """B3：spec-start 建立议程。"""

    def test_start_lands_agenda(self, cli_env, project):
        result = start_issue(cli_env, project)
        assert result["success"] is True
        spec = read_spec(cli_env)
        assert [p["topic"] for p in spec["pending_decisions"]] == ["认证协议选型", "token 有效期策略"]
        assert all(p["status"] == "needs_discussion" for p in spec["pending_decisions"])
        assert spec["resolutions"] == [] and spec["next_steps"] == []

    def test_related_doc_types_autofilled(self, cli_env, project):
        start_issue(cli_env, project)
        spec = read_spec(cli_env)
        assert spec["related_doc_types"], "related_doc_types 应由 scenario 自动推导"
        assert spec["project"] and spec["created_at"]


class TestPauseIsOnlyLandingPoint:
    """B1 + B2：pause 只写会议纪要，不碰 ProjectSpec。"""

    def test_pause_does_not_touch_projectspec(self, cli_env, project):
        start_issue(cli_env, project)
        before = docs_fingerprint(project)

        spec = read_spec(cli_env)
        spec["resolutions"].append({"topic": "认证协议选型", "decision": "采用自签 JWT", "detail": DETAIL})
        for p in spec["pending_decisions"]:
            if p["topic"] == "认证协议选型":
                p["status"] = "resolved"
        spec["next_steps"].append("下次议事先定 token 有效期")
        assert write_spec(cli_env, spec)["success"] is True

        assert docs_fingerprint(project) == before, "spec-pause 不得改动 ProjectSpec"
        reloaded = read_spec(cli_env)
        assert len(reloaded["resolutions"]) == 1
        assert [p["status"] for p in reloaded["pending_decisions"]] == ["resolved", "needs_discussion"]
        assert reloaded["next_steps"] == ["下次议事先定 token 有效期"]

    def test_detail_below_150_is_rejected(self, cli_env, project):
        """detail 不足 150 字必须被 Schema 拒绝（pause 的硬约束）。"""
        start_issue(cli_env, project)
        spec = read_spec(cli_env)
        spec["resolutions"].append({"topic": "t", "decision": "d", "detail": "太短"})
        result = write_spec(cli_env, spec)
        assert result["success"] is False
        assert "150" in json.dumps(result, ensure_ascii=False)


class TestCloseFlow:
    """spec-close：落盘 → 结清 → 写文档 → 关闭 → 归档。"""

    def close_payload(self, spec: dict, **overrides) -> dict:
        spec.update({
            "status": "closed",
            "closed_at": "2026-06-18T10:00:00+08:00",
            "closed_reason": "本轮讨论完成",
        })
        spec.update(overrides)
        return spec

    def test_close_warns_when_agenda_unresolved(self, cli_env, project):
        """S3 护栏：关闭时尚有未 resolved 议程必须如实提示（禁止谎报 resolved）。"""
        start_issue(cli_env, project)
        result = write_spec(cli_env, self.close_payload(read_spec(cli_env)))
        assert result["success"] is True
        message = result["message"]
        assert "2 项议程未 resolved" in message
        assert "认证协议选型" in message and "deferred" in message

    def test_close_writes_projectspec_then_archives(self, cli_env, project):
        start_issue(cli_env, project)
        before = docs_fingerprint(project)

        # Step 3-4：清单制写入（此处取一条 update-section 作为代表）
        updated = json.loads(cli_env.update_section(
            "ProjectSpec/technical-framework.md#主要框架与中间件",
            "| 组件 | 选型 |\n|------|------|\n| 认证 | 自签 JWT (RS256) |",
        ))
        assert updated["success"] is True
        assert docs_fingerprint(project) != before

        # Step 5：诚实结清议程后关闭 + 归档
        spec = read_spec(cli_env)
        for p in spec["pending_decisions"]:
            p["status"] = "deferred"
        assert write_spec(cli_env, self.close_payload(spec))["success"] is True
        archived = json.loads(cli_env.spec_archive())
        assert archived["success"] is True
        assert (project / "SessionSpec" / "archive" / "20260618-cert-auth.spec.json").exists()
        assert not list((project / "SessionSpec" / "active").glob("*.spec.json"))

    def test_close_requires_reason(self, cli_env, project):
        """closed_reason 必填（CLI 强校验）——技能要求"缺原因先问用户，不编造"。"""
        start_issue(cli_env, project)
        spec = read_spec(cli_env)
        spec.update({"status": "closed", "closed_at": "2026-06-18T10:00:00+08:00"})
        result = write_spec(cli_env, spec)
        assert result["success"] is False
        assert "closed_reason" in json.dumps(result, ensure_ascii=False)

    def test_deferred_and_blocked_are_honest_endings(self, cli_env, project):
        """deferred / blocked 是关闭时的合法处置，不需要（也不允许）谎报 resolved。"""
        start_issue(cli_env, project)
        spec = read_spec(cli_env)
        spec["pending_decisions"][0]["status"] = "deferred"
        spec["pending_decisions"][1]["status"] = "blocked"
        spec["pending_decisions"][1]["note"] = "阻塞原因：等待网关团队确认"
        result = write_spec(cli_env, self.close_payload(spec))
        assert result["success"] is True
        assert "未 resolved" in result["message"]  # 提示仍在，但状态如实


class TestAbortHasNoDocSideEffect:
    """B2：abort 直接归档，零文档副作用。"""

    def test_abort_keeps_projectspec_untouched(self, cli_env, project):
        start_issue(cli_env, project, sid="20260618-payment-split")
        before = docs_fingerprint(project)

        spec = read_spec(cli_env)
        spec.update({
            "status": "abandoned",
            "closed_at": "2026-06-18T11:00:00+08:00",
            "closed_reason": "需求方撤回",
        })
        assert write_spec(cli_env, spec)["success"] is True
        assert json.loads(cli_env.spec_archive())["success"] is True

        assert docs_fingerprint(project) == before, "作废分支不得改动 ProjectSpec"
        archived_spec = json.loads(
            (project / "SessionSpec" / "archive" / "20260618-payment-split.spec.json").read_text(encoding="utf-8")
        )
        assert len(archived_spec["pending_decisions"]) == 2, "作废不清空议程（保留讨论痕迹）"

    def test_abort_requires_reason(self, cli_env, project):
        start_issue(cli_env, project)
        spec = read_spec(cli_env)
        spec.update({"status": "abandoned", "closed_at": "2026-06-18T11:00:00+08:00"})
        assert write_spec(cli_env, spec)["success"] is False


class TestStatusRouting:
    """spec-start（续接分支）与 spec-archive 的路由依据。"""

    def test_status_reports_active_even_without_archive_dir(self, tmp_path):
        """回归：archive/ 尚未创建时，spec status 也必须如实报告活跃议题。

        旧实现把"archive/ 不存在"当作"项目刚初始化"直接返回无议题，
        与 spec read 的 JSON 结果互相矛盾（会让 AI 误判岔路）。
        """
        import cli

        proj = tmp_path / "fresh"
        make_md(proj, "ProjectSpec/business-context.md", "# 业务上下文\n")
        active = proj / "SessionSpec" / "active"
        active.mkdir(parents=True)
        (active / "20260618-cert-auth.spec.json").write_text(
            json.dumps({
                "session_spec_id": "20260618-cert-auth", "project": "p", "scenario": "tech-ref",
                "related_doc_types": ["architecture"], "created_at": "2026-01-01T00:00:00+00:00",
                "resolutions": [], "pending_decisions": [], "next_steps": [],
                "status": "active", "closed_at": None, "closed_reason": None,
            }, ensure_ascii=False), encoding="utf-8",
        )
        assert not (proj / "SessionSpec" / "archive").is_dir()

        status = cli.cmd_spec_status(proj)
        assert "当前有活跃议题" in status and "20260618-cert-auth" in status
        assert "无活跃议题" not in status

    def test_status_first_time_wording(self, tmp_path):
        """真正的首次调用（无任何议题）保留"已初始化"话术。"""
        import cli

        proj = tmp_path / "brand-new"
        proj.mkdir()
        status = cli.cmd_spec_status(proj)
        assert "已初始化" in status and "无活跃议题" in status


# ── 2. 技能文本契约（防止职责边界再次漂移）──

DOC_WRITE_COMMANDS = ("doc new", "doc update-section", "doc add-section", "doc remove-section")
NO_DOC_WRITE_SKILLS = ["spec-start", "spec-pause", "spec-archive"]


class TestSkillTextContract:
    def skill_text(self, name: str) -> str:
        return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")

    def tool_block(self, name: str) -> str:
        """只取 SKILL.md 中 ```bash 工具清单块（正文提到命令名不算调用）。"""
        blocks = re.findall(r"```bash\n(.*?)```", self.skill_text(name), re.S)
        return "\n".join(blocks)

    @pytest.mark.parametrize("name", NO_DOC_WRITE_SKILLS)
    def test_only_close_writes_projectspec(self, name):
        """B2：除 spec-close 外，议题类技能不得出现写 ProjectSpec 的命令。"""
        text = self.skill_text(name)
        for cmd in DOC_WRITE_COMMANDS:
            assert f"cli.py {cmd}" not in text, f"{name} 不应调用 {cmd}（ProjectSpec 写入集中在 spec-close）"

    def test_close_owns_projectspec_write(self):
        """spec-close 承接文档写入，且带能力库读取纪律。"""
        text = self.skill_text("spec-close")
        tools = self.tool_block("spec-close")
        for cmd in ("doc structure", "doc read", "doc new", "doc update-section", "doc add-section"):
            assert f"cli.py {cmd}" in tools, f"spec-close 工具清单缺少 {cmd}"
        assert "doc remove-section" not in tools, "删除段落不在 spec-close 职责内"
        assert "doc-capabilities" in text, "spec-close 必须声明能力库（_index.md + 能力文件）读取流程"

    def test_pause_is_the_only_landing_point(self):
        """spec-pause 是讨论进行中唯一的保存通道，且不写 ProjectSpec。

        措辞在 2026.09.5 由「唯一落盘点」改为「唯一保存通道」：原措辞与前言
        「落盘点只有三处（spec-start / spec-pause / spec-close）」的定义冲突，
        会让 AI 在 spec-start 里以为"落盘是 pause 的事"而漏写议程。
        """
        text = self.skill_text("spec-pause")
        assert "唯一保存通道" in text
        assert "不写 `ProjectSpec/`" in text

    def test_start_lands_agenda(self):
        text = self.skill_text("spec-start")
        assert "pending_decisions" in text and "议程" in text

    def test_start_resume_branch_replays_agenda_readonly(self):
        """续接分支（原 spec-load 的职责）必须在 spec-start 内，且声明为只读。

        2026.09.10：`spec-load` 并入 `spec-start` —— 新对话只有一个入口，
        有议题走续接（Step 0b）、无议题走创建；续接分支全程只读。
        """
        text = self.skill_text("spec-start")
        assert "复述议程" in text
        assert "Step 0b" in text
        assert "只读" in text
        assert "spec read" in text

    def test_close_has_abandon_branch(self):
        """作废分支（原 spec-abort 的职责）必须在 spec-close 内，四纪律齐全。

        2026.09.10：`spec-abort` 并入 `spec-close` —— 关闭路径保留成果，
        作废分支放弃成果，两者共用一份前言而不必各带一套。
        """
        text = self.skill_text("spec-close")
        assert "作废分支" in text
        assert "spec archive" in text
        assert "不写 `ProjectSpec/`" in text
        assert "先分流" in text
        assert "终态不可回退" in text

    def test_archive_is_fallback_only(self):
        text = self.skill_text("spec-archive")
        assert "兜底" in text
        assert "spec archive" in text

"""`spec coverage` 与关闭门禁的契约 —— R2 的回归测试。

背景（2026-11-02 的 log-capture 议题）：24 条决议里有 6 处从未写入 ProjectSpec，
spec 却报「24 条决议写入 ProjectSpec」并通过关闭；缺的 6 处全部属于「该由一份
feature_design 承载」的内容——当时 `module-behavior-log/` 下连 `features/` 目录都
不存在。agent 不是选择漏记，而是没找到可落的结构。

本文件锁住三层防护里可自动化的部分：

  1. 关闭（status=closed）时每条决议必须有 targets（`spec.targets_missing`）；
  2. `spec coverage --verify` 对磁盘给出 ok / missing / empty / ambiguous；
  3. `coverage` 快照由 CLI 按磁盘重算，调用方传什么都会被丢弃；
  4. 归档 spec 只读（`spec.archived_id`），回放走 `--id`。

能力边界（写死在测试里）：只防「漏记」，不防「错记」——正文内容对错不在核对面内。
"""

import json

import pytest

import cli
from conftest import make_md, make_spec

DETAIL = "字" * 160

ARCH_DOC = """---
doc_type: architecture
module: module-order
level: module
version: 1.0.0
last_updated: 2026-01-01
status: active
---
# 订单模块架构

## 概述

订单模块负责下单与查询。

## 组件划分

### 概述

子级同名标题：与一级「概述」构成歧义。

### 空段落

## 架构设计

架构设计正文落在这里。
"""

DOMAIN_DOC = """---
doc_type: domain_model
module: module-order
level: module
version: 1.0.0
last_updated: 2026-01-01
status: active
---
# 订单领域模型

## 实体

订单实体说明。
"""


# ═══════════════════════════════════════════════════════════════
#  夹具
# ═══════════════════════════════════════════════════════════════

def _build_docs(project) -> None:
    make_md(project, "ProjectSpec/module-order/architecture.md", ARCH_DOC)
    make_md(project, "ProjectSpec/module-order/domain-model.md", DOMAIN_DOC)


def _target(doc, section="", action="doc_update_section", reason=""):
    return {"doc": doc, "section": section, "action": action, "reason": reason}


def _resolution(topic, targets=None, **extra):
    res = {"topic": topic, "decision": f"{topic} 的决定", "detail": DETAIL}
    if targets is not None:
        res["targets"] = targets
    res.update(extra)
    return res


def _spec(sid="test-001", status="active", resolutions=None, **extra):
    data = {
        "session_spec_id": sid,
        "scenario": "feature-dev",
        "status": status,
        "resolutions": resolutions or [],
        "pending_decisions": [],
        "next_steps": [],
    }
    data.update(extra)
    return data


def _write(cli_env, spec: dict) -> dict:
    return json.loads(cli_env.spec_write(json.dumps(spec, ensure_ascii=False)))


def _coverage(cli_env, verify=True, sid=None) -> dict:
    return json.loads(cli_env.spec_coverage(verify=verify, sid=sid))


def _statuses(payload: dict) -> list[str]:
    return [row["status"] for row in payload["data"]["rows"]]


# ═══════════════════════════════════════════════════════════════
#  关闭门禁（R2-b）
# ═══════════════════════════════════════════════════════════════

class TestCloseGate:
    def test_active_allows_missing_targets(self, tmp_project, cli_env):
        """讨论中期（status=active）允许归宿未定：Step 3 才梳理。"""
        _build_docs(tmp_project)
        payload = _write(cli_env, _spec(resolutions=[_resolution("订单状态机")]))
        assert payload["success"] is True

    def test_closed_rejects_missing_targets(self, tmp_project, cli_env):
        """关闭时缺 targets → 拒绝，且错误里**指名**是哪条决议。"""
        _build_docs(tmp_project)
        _write(cli_env, _spec(resolutions=[_resolution("订单状态机")]))
        payload = _write(
            cli_env,
            _spec(status="closed", closed_reason="做完了",
                  resolutions=[_resolution("订单状态机")]),
        )
        assert payload["success"] is False
        assert "spec.targets_missing" in payload["message"]
        assert "订单状态机" in payload["message"]

    def test_closed_rejects_skip_without_reason(self, tmp_project, cli_env):
        """doc_skip 是显式声明「不落文档」，必须写明理由，否则等于细粒度漏记。"""
        _build_docs(tmp_project)
        payload = _write(
            cli_env,
            _spec(status="closed", closed_reason="做完了",
                  resolutions=[_resolution(
                      "内部口径",
                      [_target("module-order/architecture.md", "架构设计",
                               action="doc_skip", reason="短")],
                  )]),
        )
        assert payload["success"] is False
        assert "reason" in payload["message"]

    def test_closed_rejects_doc_without_md(self, tmp_project, cli_env):
        _build_docs(tmp_project)
        payload = _write(
            cli_env,
            _spec(status="closed", closed_reason="做完了",
                  resolutions=[_resolution(
                      "订单状态机",
                      [_target("module-order/architecture", "架构设计")],
                  )]),
        )
        assert payload["success"] is False
        assert ".md" in payload["message"]

    def test_closed_rejects_traversal_doc(self, tmp_project, cli_env):
        _build_docs(tmp_project)
        payload = _write(
            cli_env,
            _spec(status="closed", closed_reason="做完了",
                  resolutions=[_resolution(
                      "订单状态机",
                      [_target("../outside.md", "架构设计")],
                  )]),
        )
        assert payload["success"] is False
        assert "越界" in payload["message"]

    def test_closed_accepts_complete_targets(self, tmp_project, cli_env):
        _build_docs(tmp_project)
        payload = _write(
            cli_env,
            _spec(status="closed", closed_reason="做完了",
                  resolutions=[_resolution(
                      "订单状态机",
                      [_target("module-order/architecture.md", "架构设计")],
                  )]),
        )
        assert payload["success"] is True


# ═══════════════════════════════════════════════════════════════
#  磁盘核对（R2-c）：四态不误报
# ═══════════════════════════════════════════════════════════════

class TestVerify:
    def _store(self, cli_env, targets, topic="订单状态机"):
        return _write(cli_env, _spec(resolutions=[_resolution(topic, targets)]))

    def test_section_exists_is_ok(self, tmp_project, cli_env):
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/architecture.md", "架构设计")])
        payload = _coverage(cli_env)
        assert _statuses(payload) == ["ok"]
        assert payload["success"] is True

    def test_missing_doc(self, tmp_project, cli_env):
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/query-export.md", action="doc_new")])
        payload = _coverage(cli_env)
        assert _statuses(payload) == ["missing"]
        assert payload["success"] is False

    def test_new_doc_that_exists_is_ok(self, tmp_project, cli_env):
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/domain-model.md", action="doc_new")])
        assert _statuses(_coverage(cli_env)) == ["ok"]

    def test_deleted_section_is_missing(self, tmp_project, cli_env):
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/architecture.md", "不存在的段落")])
        assert _statuses(_coverage(cli_env)) == ["missing"]

    def test_empty_section(self, tmp_project, cli_env):
        """章节存在但正文为空 → empty（占位残留也算空）。"""
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/architecture.md", "组件划分#空段落")])
        payload = _coverage(cli_env)
        assert _statuses(payload) == ["empty"]
        assert payload["success"] is False

    def test_parent_section_with_child_body_is_not_empty(self, tmp_project, cli_env):
        """一级章节自身无正文、子段落有正文 —— 不得误报 empty（否则门禁变噪音）。"""
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/architecture.md", "组件划分")])
        assert _statuses(_coverage(cli_env)) == ["ok"]

    def test_duplicate_heading_is_ambiguous(self, tmp_project, cli_env):
        """同名标题命中多处 → ambiguous，禁止按 R1 前的旧习惯取首个。"""
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/architecture.md", "概述")])
        payload = _coverage(cli_env)
        assert _statuses(payload) == ["ambiguous"]
        assert payload["success"] is False

    def test_doc_skip_is_skipped_not_verified(self, tmp_project, cli_env):
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/architecture.md", action="doc_skip",
                                     reason="内部讨论口径，只在会议纪要里保留")])
        payload = _coverage(cli_env)
        assert _statuses(payload) == ["skipped"]
        assert payload["success"] is True

    def test_unverified_when_flag_absent(self, tmp_project, cli_env):
        """不带 --verify 时只列归属，不碰磁盘，也不因缺文档而失败。"""
        _build_docs(tmp_project)
        self._store(cli_env, [_target("module-order/nope.md", action="doc_new")])
        payload = _coverage(cli_env, verify=False)
        assert _statuses(payload) == ["unverified"]
        assert payload["success"] is True


# ═══════════════════════════════════════════════════════════════
#  旧 spec 容错与归档回放（验收 2.11-1）
# ═══════════════════════════════════════════════════════════════

class TestLegacyAndArchive:
    def test_legacy_spec_warns_but_exits_zero(self, tmp_project, cli_env):
        """旧 spec 没有 targets：warning 而非失败——「没有记录」≠「没有落盘」。"""
        _build_docs(tmp_project)
        make_spec(tmp_project, "20260101-old", {
            "status": "closed",
            "closed_reason": "旧数据",
            "resolutions": [{"topic": "旧决议", "decision": "d", "detail": DETAIL}],
        })
        payload = _coverage(cli_env, sid="20260101-old")
        assert payload["success"] is True
        assert "尚未记录 targets" in payload["message"]
        assert _statuses(payload) == ["untargeted"]
        assert cli._exit_code(cli.cmd_spec_coverage(tmp_project, True, "20260101-old")) == 0

    def test_archived_id_is_readable_but_not_writable(self, tmp_project, cli_env):
        """归档 spec 只读：回放可读，写入被拒绝，且不在 active/ 造副本。"""
        _build_docs(tmp_project)
        make_spec(tmp_project, "20260101-done", {
            "status": "closed",
            "closed_reason": "已完成",
            "resolutions": [{"topic": "旧决议", "decision": "d", "detail": DETAIL}],
        })
        archived = tmp_project / "SessionSpec" / "archive" / "20260101-done.spec.json"
        archived.write_text(
            (tmp_project / "SessionSpec" / "active" / "20260101-done.spec.json").read_text(
                encoding="utf-8"),
            encoding="utf-8",
        )
        (tmp_project / "SessionSpec" / "active" / "20260101-done.spec.json").unlink()

        replay = _coverage(cli_env, sid="20260101-done")
        assert replay["data"]["session_spec_id"] == "20260101-done"
        assert "archive/" in replay["message"]

        payload = _write(cli_env, _spec(sid="20260101-done",
                                        resolutions=[_resolution("再议")]))
        assert payload["success"] is False
        assert "spec.archived_id" in payload["message"]
        assert not (tmp_project / "SessionSpec" / "active" / "20260101-done.spec.json").exists()

    def test_unknown_id_fails_loudly(self, tmp_project, cli_env):
        payload = _coverage(cli_env, sid="20991231-nope")
        assert payload["success"] is False
        assert "未找到议题" in payload["message"]


# ═══════════════════════════════════════════════════════════════
#  快照不可伪造（R2-d：被审计方不自填）
# ═══════════════════════════════════════════════════════════════

def test_coverage_snapshot_is_recomputed_by_cli(tmp_project, cli_env):
    """调用方传进来的 coverage 一律丢弃，磁盘重算结果写回 spec。"""
    _build_docs(tmp_project)
    _write(cli_env, _spec(resolutions=[
        _resolution("订单状态机", [_target("module-order/architecture.md", "架构设计")]),
    ]))
    forged = {"verified_at": "1999-01-01T00:00:00+00:00",
              "counts": {"ok": 999}, "rows": []}
    payload = _write(
        cli_env,
        _spec(status="closed", closed_reason="做完了", coverage=forged,
              resolutions=[
                  _resolution("订单状态机", [_target("module-order/architecture.md", "架构设计")]),
              ]),
    )
    assert payload["success"] is True

    saved = json.loads(
        (tmp_project / "SessionSpec" / "active" / "test-001.spec.json").read_text(
            encoding="utf-8")
    )
    assert saved["coverage"]["verified_at"] != forged["verified_at"]
    assert saved["coverage"]["counts"]["ok"] == 1
    assert saved["coverage"]["counts"]["missing"] == 0
    assert saved["coverage"]["rows"][0]["status"] == "ok"


def test_status_reports_untargeted_count(tmp_project, cli_env):
    """讨论期就要看见缺口，而不是等关闭时才被拒。"""
    _build_docs(tmp_project)
    _write(cli_env, _spec(resolutions=[_resolution("订单状态机"), _resolution("接口签名")]))
    text = cli_env.spec_status()
    assert "2/2 条决议尚无文档归宿" in text

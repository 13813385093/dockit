"""spec-dev-loop 开发执行循环测试 — DevSpec 生命周期 + ProjectSpec 只读保障。

测试链路:
  dev plan create → dev task set → dev task update（状态机）→ dev align →
  dev integrate → dev notes append → dev report-write → dev close/abort → dev archive

核心纪律测试：整个循环过程中 ProjectSpec/ 必须保持字节级不变（只读）。
"""

import json
import subprocess

from conftest import make_md


# ═══════════════════════════════════════════════════════════════
#  测试辅助
# ═══════════════════════════════════════════════════════════════

def _make_project(tmp_project):
    """搭建最小 ProjectSpec：顶层文档 + 模块 + 功能。"""
    make_md(tmp_project, "ProjectSpec/business-context.md",
            "---\ndoc_type: business_context\nmodule: project-charter\nlevel: top\n"
            "version: 0.1.0\nstatus: active\n---\n# 业务背景\n\n## 项目动因\n\n订单业务\n")
    make_md(tmp_project, "ProjectSpec/global-policies.md",
            "---\ndoc_type: global_policies\nmodule: project-charter\nlevel: top\n"
            "version: 0.1.0\nstatus: active\n---\n# 全局策略\n\n## 异常处理\n\n错误码体系\n")
    make_md(tmp_project, "ProjectSpec/module-order/architecture.md",
            "---\ndoc_type: architecture\nmodule: order\nlevel: module\n"
            "version: 0.1.0\nstatus: active\n---\n# 订单模块\n\n## 模块概述\n\n订单模块\n")
    make_md(tmp_project, "ProjectSpec/module-order/module-manifest.md",
            "---\ndoc_type: module_manifest\nmodule: order\nlevel: module\n"
            "version: 0.1.0\nstatus: active\n---\n# 模块清单\n\n## Exports\n\n## Imports\n")
    make_md(tmp_project, "ProjectSpec/module-order/features/order-timeout-cancel/feature-design.md",
            "---\ndoc_type: feature_design\nmodule: order\nfeature: order-timeout-cancel\nlevel: feature\n"
            "version: 0.1.0\nstatus: active\n---\n# 功能设计\n\n## 功能描述\n\n超时取消\n\n## 边界约束\n"
            "\n- [MUST] C-101 扫描周期 ≤ 5 分钟\n")
    return tmp_project


def _parse(result):
    """解析 CLI 返回的 JSON。"""
    return json.loads(result)


def _snapshot_project_spec(root):
    """对 ProjectSpec/ 做字节级快照。"""
    snap = {}
    base = root / "ProjectSpec"
    for p in sorted(base.rglob("*")):
        if p.is_file():
            snap[str(p.relative_to(root))] = p.read_bytes()
    return snap


TASKS_JSON = json.dumps([
    {
        "task_id": "T1",
        "title": "扫描并取消超时订单（入口）",
        "module": "order",
        "feature": "order-timeout-cancel",
        "cls": "OrderTimeoutService",
        "symbol": "cancelExpiredOrders",
        "implemented_in": {"path": "src/order/timeout_service.go", "lang": "go"},
        "calls": ["findExpiredOrders", "cancelOrder"],
        "capability_notes": ["扫描周期 5 分钟；取消成功后释放库存"],
        "functions": ["cancelExpiredOrders", "findExpiredOrders", "cancelOrder", "releaseStock"],
        "entry_function": "cancelExpiredOrders",
        "signature": "cancelExpiredOrders(ctx context.Context) error",
        "gwt_refs": ["unit-tests.md#测试用例：超时订单被扫描"],
        "constraint_ids": ["C-101", "C-102"],
    },
    {
        "task_id": "T2",
        "title": "释放库存",
        "module": "order",
        "feature": "order-timeout-cancel",
        "cls": "OrderTimeoutService",
        "symbol": "releaseStock",
        "implemented_in": {"path": "src/order/stock.go", "lang": "go"},
        "functions": ["releaseStock"],
        "signature": "releaseStock(order Order) error",
        "constraint_ids": ["C-102"],
    },
], ensure_ascii=False)

# 新状态机的合法推进链（骨架 → 实现 → 交回 → 验收 → 测试 → 完成）
TASK_CHAIN = ("implementing", "submitted", "accepted", "tested", "done")


def _create_feature_session(cli_env):
    """创建 order-timeout-cancel 功能会话并写入任务清单。"""
    result = _parse(cli_env.dev_plan_create(
        "feature", "order-timeout-cancel", module="order", title="订单超时取消开发"))
    assert result["success"] is True, result
    cli_env.dev_task_set(TASKS_JSON)
    return result["data"]["session_id"]


# ═══════════════════════════════════════════════════════════════
#  dev plan create
# ═══════════════════════════════════════════════════════════════

class TestDevPlanCreate:
    def test_create_module_scope(self, tmp_project, cli_env):
        _make_project(tmp_project)
        result = _parse(cli_env.dev_plan_create("module", "order", title="订单模块开发"))
        assert result["success"] is True
        sid = result["data"]["session_id"]
        assert sid.startswith("20") and sid.endswith("order")
        session_dir = tmp_project / "DevSpec" / "active" / sid
        assert session_dir.is_dir()
        for name in ("dev-spec.json", "plan.md", "tasks.json", "code-notes.md", "evidence", "reports"):
            assert (session_dir / name).exists(), name
        dev_spec = json.loads((session_dir / "dev-spec.json").read_text(encoding="utf-8"))
        assert dev_spec["scope_type"] == "module"
        assert dev_spec["scope_target"] == "order"
        assert dev_spec["status"] == "active"
        # 分支信息：dev-spec.json 记录建议分支名，plan.md §6 记录分支章节
        assert dev_spec["branch"] == f"dev-loop/{sid}"
        plan_text = (session_dir / "plan.md").read_text(encoding="utf-8")
        assert "## 6. 分支信息" in plan_text
        assert f"dev-loop/{sid}" in plan_text

    def test_create_feature_scope(self, tmp_project, cli_env):
        _make_project(tmp_project)
        result = _parse(cli_env.dev_plan_create("feature", "order-timeout-cancel", module="order"))
        assert result["success"] is True
        assert result["data"]["scope_target"] == "order-timeout-cancel"

    def test_feature_scope_requires_module(self, tmp_project, cli_env):
        _make_project(tmp_project)
        result = _parse(cli_env.dev_plan_create("feature", "order-timeout-cancel"))
        assert result["success"] is False
        assert "missing_module" in result["suggestions"][0]

    def test_scope_not_found(self, tmp_project, cli_env):
        _make_project(tmp_project)
        result = _parse(cli_env.dev_plan_create("module", "nonexistent"))
        assert result["success"] is False
        assert "scope_not_found" in result["suggestions"][0]

    def test_serial_constraint(self, tmp_project, cli_env):
        """已存在活跃循环时禁止再创建（串行约束）。"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        result = _parse(cli_env.dev_plan_create("module", "order"))
        assert result["success"] is False
        assert "active_exists" in result["suggestions"][0]

    def test_duplicate_session_id(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        # 串行约束：有活跃循环时再创建被拒（含同名）
        result = _parse(cli_env.dev_plan_create(
            "feature", "order-timeout-cancel", module="order", session="dup-session"))
        assert result["success"] is False
        assert "active_exists" in result["suggestions"][0]
        cli_env.dev_close("完成")
        cli_env.dev_archive()
        # 归档后同名 id 可复用
        result = _parse(cli_env.dev_plan_create(
            "feature", "order-timeout-cancel", module="order", session="dup-session"))
        assert result["success"] is True
        cli_env.dev_close("完成")
        cli_env.dev_archive()
        # 残留目录（无 dev-spec.json，不被检测为活跃）触发 session_exists
        (tmp_project / "DevSpec" / "active" / "leftover").mkdir(exist_ok=True)
        result = _parse(cli_env.dev_plan_create(
            "feature", "order-timeout-cancel", module="order", session="leftover"))
        assert result["success"] is False
        assert "session_exists" in result["suggestions"][0]


# ═══════════════════════════════════════════════════════════════
#  计划表与任务
# ═══════════════════════════════════════════════════════════════

class TestDevPlanTasks:
    def test_plan_sections_and_update(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        result = _parse(cli_env.dev_plan_read())
        assert result["success"] is True
        headings = [s["heading"] for s in result["data"]["sections"]]
        assert "1. 范围与目标" in headings and "2. 约束整合" in headings and "3. 骨架与任务清单" in headings
        # 更新约束整合段落（reference 支持裸 plan.md 前缀）
        upd = _parse(cli_env.dev_plan_update_section(
            "plan.md#2. 约束整合",
            "- [MUST] C-101 扫描周期 ≤ 5 分钟（来源 feature-design §边界约束）"))
        assert upd["success"] is True
        again = _parse(cli_env.dev_plan_read())
        sec2 = next(s for s in again["data"]["sections"] if s["heading"] == "2. 约束整合")
        assert "C-101" in sec2["content"]

    def test_plan_update_empty_content_rejected(self, tmp_project, cli_env):
        """空 content 会清空 plan 段落，应拒绝且段落不变（与 doc update-section 同口径）"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        before = _parse(cli_env.dev_plan_read())
        sec_before = next(s for s in before["data"]["sections"] if s["heading"] == "2. 约束整合")
        upd = _parse(cli_env.dev_plan_update_section("plan.md#2. 约束整合", "   "))
        assert upd["success"] is False
        after = _parse(cli_env.dev_plan_read())
        sec_after = next(s for s in after["data"]["sections"] if s["heading"] == "2. 约束整合")
        assert sec_after["content"] == sec_before["content"]

    def test_task_set_refreshes_plan_table(self, tmp_project, cli_env):
        """tasks.json 是唯一数据源，plan.md §3 由 CLI 自动渲染。"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        result = _parse(cli_env.dev_plan_read())
        sec3 = next(s for s in result["data"]["sections"] if s["heading"] == "3. 骨架与任务清单")
        assert "| T1 |" in sec3["content"]
        assert "cancelExpiredOrders" in sec3["content"]
        assert "C-101" in sec3["content"]

    def test_task_list(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        result = _parse(cli_env.dev_task_list())
        assert result["success"] is True
        tasks = result["data"]["tasks"]
        assert len(tasks) == 2
        assert tasks[0]["entry_function"] == "cancelExpiredOrders"
        assert tasks[0]["status"] == "pending"

    def test_status_reports_branch(self, tmp_project, cli_env):
        """dev status 输出开发分支名，供断点续跑时比对当前 git 分支。"""
        _make_project(tmp_project)
        sid = _create_feature_session(cli_env)
        result = _parse(cli_env.dev_status())
        assert result["success"] is True
        assert result["data"]["branch"] == f"dev-loop/{sid}"
        assert f"**开发分支**: dev-loop/{sid}" in result["message"]
        assert any("git branch --show-current" in s for s in result["suggestions"])


class TestDevTaskTransitions:
    def _ready(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)

    def test_valid_transition_chain(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        for status in TASK_CHAIN:
            result = _parse(cli_env.dev_task_update("T1", status, note=f"step {status}"))
            assert result["success"] is True, result
        tasks = _parse(cli_env.dev_task_list())["data"]["tasks"]
        assert tasks[0]["status"] == "done"
        assert "[20" in tasks[0]["notes"]  # 备注带日期前缀

    def test_rejected_loop(self, tmp_project, cli_env):
        """验收不通过 → rejected（带失败证据）→ 重派 implementing。"""
        self._ready(tmp_project, cli_env)
        cli_env.dev_task_update("T1", "implementing")
        cli_env.dev_task_update("T1", "submitted")
        # 验收不通过 → rejected
        fix = _parse(cli_env.dev_task_update("T1", "rejected", note="单元测试失败：C-101 未满足"))
        assert fix["success"] is True
        # rejected → implementing 重新实现
        assert _parse(cli_env.dev_task_update("T1", "implementing"))["success"] is True

    def test_blocked_requires_user_decision_then_resumes(self, tmp_project, cli_env):
        """设计缺口/签名变更 → blocked，裁决后回到 implementing 或 rejected。"""
        self._ready(tmp_project, cli_env)
        cli_env.dev_task_update("T1", "implementing")
        blocked = _parse(cli_env.dev_task_update("T1", "blocked", note="签名需变更：需增加 tenantID 参数"))
        assert blocked["success"] is True
        assert _parse(cli_env.dev_task_update("T1", "implementing"))["success"] is True

    def test_submitted_cannot_jump_to_done(self, tmp_project, cli_env):
        """submitted 必须经 accepted 才能推进（防止绕过主代理验收）。"""
        self._ready(tmp_project, cli_env)
        cli_env.dev_task_update("T1", "implementing")
        cli_env.dev_task_update("T1", "submitted")
        result = _parse(cli_env.dev_task_update("T1", "done"))
        assert result["success"] is False
        assert "invalid_transition" in result["suggestions"][0]

    def test_testing_requires_acceptance_first(self, tmp_project, cli_env):
        """测试闸门在验收之后：未 accepted 不得置 tested。"""
        self._ready(tmp_project, cli_env)
        cli_env.dev_task_update("T1", "implementing")
        result = _parse(cli_env.dev_task_update("T1", "tested"))
        assert result["success"] is False

    def test_invalid_transition(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        result = _parse(cli_env.dev_task_update("T1", "done"))
        assert result["success"] is False
        assert "invalid_transition" in result["suggestions"][0]
        # 状态未变
        tasks = _parse(cli_env.dev_task_list())["data"]["tasks"]
        assert tasks[0]["status"] == "pending"

    def test_invalid_status_and_unknown_task(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        assert _parse(cli_env.dev_task_update("T1", "bogus"))["success"] is False
        assert _parse(cli_env.dev_task_update("T99", "implementing"))["success"] is False

    def test_annotate_keeps_status(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        result = _parse(cli_env.dev_task_annotate("T1", "设计偏差记录（详见 CodeNotes）"))
        assert result["success"] is True
        tasks = _parse(cli_env.dev_task_list())["data"]["tasks"]
        assert tasks[0]["status"] == "pending"
        assert "设计偏差记录" in tasks[0]["notes"]

    def test_task_set_validation(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        bad = _parse(cli_env.dev_task_set(json.dumps([
            {"task_id": "T1", "title": "x", "status": "bogus",
             "implemented_in": {"path": "a.go"}}])))
        assert bad["success"] is False
        dup = _parse(cli_env.dev_task_set(json.dumps([
            {"task_id": "T1", "title": "a", "implemented_in": {"path": "a.go"}},
            {"task_id": "T1", "title": "b", "implemented_in": {"path": "b.go"}}])))
        assert dup["success"] is False
        missing = _parse(cli_env.dev_task_set(json.dumps([{"task_id": "T1"}])))
        assert missing["success"] is False

    def test_unknown_task_field_is_rejected(self, tmp_project, cli_env):
        """未知字段必须报错而非静默丢弃（timeout_seconds / implemented_in 的历史坑）。"""
        self._ready(tmp_project, cli_env)
        result = _parse(cli_env.dev_task_set(json.dumps([
            {"task_id": "T1", "title": "x", "implemented_in": {"path": "a.go"},
             "typo_field": 1}])))
        assert result["success"] is False
        assert "typo_field" in result["suggestions"][0]

    def test_implemented_in_is_required(self, tmp_project, cli_env):
        """实现落点是骨架化的核心产物，缺失即拒绝。"""
        self._ready(tmp_project, cli_env)
        result = _parse(cli_env.dev_task_set(json.dumps([{"task_id": "T1", "title": "x"}])))
        assert result["success"] is False
        assert "implemented_in" in result["suggestions"][0]

    def test_implemented_in_persisted_and_rendered(self, tmp_project, cli_env):
        """落点进入 tasks.json 与 plan.md，供子代理简报使用。"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        tasks = _parse(cli_env.dev_task_list())["data"]["tasks"]
        assert tasks[0]["implemented_in"]["path"] == "src/order/timeout_service.go"
        assert tasks[0]["cls"] == "OrderTimeoutService"
        assert tasks[0]["symbol"] == "cancelExpiredOrders"
        assert tasks[0]["calls"] == ["findExpiredOrders", "cancelOrder"]
        plan = _parse(cli_env.dev_plan_read())
        sec3 = next(s for s in plan["data"]["sections"] if s["heading"] == "3. 骨架与任务清单")
        assert "src/order/timeout_service.go" in sec3["content"]
        assert "cancelExpiredOrders" in sec3["content"]

    def test_dispatch_params_defaulted(self, tmp_project, cli_env):
        """派发参数（超时/重试上限/已试次数）落库，不再被静默丢弃。"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        tasks = _parse(cli_env.dev_task_list())["data"]["tasks"]
        assert tasks[0]["timeout_seconds"] == 300
        assert tasks[0]["max_attempts"] == 2
        assert tasks[0]["attempts"] == 0

    def test_style_snapshot_section_exists(self, tmp_project, cli_env):
        """§2.5 代码风格快照必须存在于骨架里（否则 Phase 1 Step 3.5 指令必然失败）。"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        result = _parse(cli_env.dev_plan_read())
        headings = [s["heading"] for s in result["data"]["sections"]]
        assert "2.5 代码风格快照" in headings
        upd = _parse(cli_env.dev_plan_update_section(
            "plan.md#2.5 代码风格快照", "错误返回 errors.New(...)；日志 log.WithField(...)"))
        assert upd["success"] is True

    def test_status_reports_phase_and_counts(self, tmp_project, cli_env):
        """阶段由任务状态派生：design → implement → test → close。"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        st = _parse(cli_env.dev_status())
        assert st["data"]["phase"] == "implement"
        assert st["data"]["status_counts"]["pending"] == 2
        # T1 走完全程，T2 仍 pending → 阶段仍是 implement
        for status in TASK_CHAIN:
            assert _parse(cli_env.dev_task_update("T1", status))["success"] is True
        st = _parse(cli_env.dev_status())
        assert st["data"]["phase"] == "implement"
        assert st["data"]["status_counts"]["done"] == 1
        # T2 验收通过 → 全部任务是 accepted/tested/done → 进入测试阶段
        for status in ("implementing", "submitted", "accepted"):
            assert _parse(cli_env.dev_task_update("T2", status))["success"] is True
        st = _parse(cli_env.dev_status())
        assert st["data"]["phase"] == "test"
        assert any("GWT" in s for s in st["suggestions"])
        # 全部 done → 收尾阶段
        for status in ("tested", "done"):
            assert _parse(cli_env.dev_task_update("T2", status))["success"] is True
        st = _parse(cli_env.dev_status())
        assert st["data"]["phase"] == "close"

    def test_status_phase_design_without_tasks(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _parse(cli_env.dev_plan_create("feature", "order-timeout-cancel", module="order"))
        st = _parse(cli_env.dev_status())
        assert st["data"]["phase"] == "design"
        assert any("骨架化" in s for s in st["suggestions"])


# ═══════════════════════════════════════════════════════════════
#  功能对齐 / 模块集成
# ═══════════════════════════════════════════════════════════════

class TestDevMilestones:
    def _finish_all_tasks(self, cli_env):
        for tid in ("T1", "T2"):
            for status in TASK_CHAIN:
                assert _parse(cli_env.dev_task_update(tid, status))["success"] is True

    def test_align_requires_tasks_done(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        # 任务未完成 → 对齐被拒
        result = _parse(cli_env.dev_align("order-timeout-cancel", "order", "aligned"))
        assert result["success"] is False
        assert "tasks_not_done" in result["suggestions"][0]

    def test_align_and_integrate_flow(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        self._finish_all_tasks(cli_env)
        # 功能尚未对齐时集成被拒
        result = _parse(cli_env.dev_integrate("order", "integrated"))
        assert result["success"] is False
        assert "features_not_aligned" in result["suggestions"][0]
        # aligned → done → 集成
        assert _parse(cli_env.dev_align("order-timeout-cancel", "order", "aligned"))["success"] is True
        assert _parse(cli_env.dev_align("order-timeout-cancel", "order", "done"))["success"] is True
        assert _parse(cli_env.dev_integrate("order", "integrated"))["success"] is True
        assert _parse(cli_env.dev_integrate("order", "documented"))["success"] is True
        assert _parse(cli_env.dev_integrate("order", "done"))["success"] is True

    def test_milestone_invalid_transition(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        self._finish_all_tasks(cli_env)
        # aligned → done 直接跳过 allowed；但 aligned 后不能再回到 aligned
        assert _parse(cli_env.dev_align("order-timeout-cancel", "order", "aligned"))["success"] is True
        again = _parse(cli_env.dev_align("order-timeout-cancel", "order", "aligned"))
        assert again["success"] is False
        assert "invalid_transition" in again["suggestions"][0]


# ═══════════════════════════════════════════════════════════════
#  CodeNotes 与报告
# ═══════════════════════════════════════════════════════════════

class TestDevNotesReport:
    def test_notes_append(self, tmp_project, cli_env):
        _make_project(tmp_project)
        sid = _create_feature_session(cli_env)
        result = _parse(cli_env.dev_notes_append(
            "### 流量冲击测试层级错位\n- **发现**：unit-tests 设计了 1 小时流量冲击场景\n"
            "- **判断**：测试层级错位\n- **建议的 Spec 修改**：feature-design@order-timeout-cancel:C-101",
            section="设计文档遗漏与偏差"))
        assert result["success"] is True
        notes = (tmp_project / "DevSpec" / "active" / sid / "code-notes.md").read_text(encoding="utf-8")
        assert "流量冲击测试层级错位" in notes
        assert "设计文档遗漏与偏差" in notes
        # 追加不改写：再次追加后既有内容仍在
        cli_env.dev_notes_append("### 第二个问题\n- 内容", section="设计文档遗漏与偏差")
        notes2 = (tmp_project / "DevSpec" / "active" / sid / "code-notes.md").read_text(encoding="utf-8")
        assert "流量冲击测试层级错位" in notes2
        assert "第二个问题" in notes2

    def test_report_write(self, tmp_project, cli_env):
        _make_project(tmp_project)
        sid = _create_feature_session(cli_env)
        result = _parse(cli_env.dev_report_write(
            "module", "order", "# 模块开发报告\n\n## 完成情况\n"))
        assert result["success"] is True
        report = tmp_project / "DevSpec" / "active" / sid / "reports" / "module-order.md"
        assert report.exists()
        assert "模块开发报告" in report.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
#  生命周期：close / abort / archive
# ═══════════════════════════════════════════════════════════════

class TestDevLifecycle:
    def test_close_and_archive(self, tmp_project, cli_env):
        _make_project(tmp_project)
        sid = _create_feature_session(cli_env)
        # active 不能归档
        assert _parse(cli_env.dev_archive())["success"] is False
        # 缺 reason 不能关闭
        assert _parse(cli_env.dev_close(""))["success"] is False
        assert _parse(cli_env.dev_close("模块完成"))["success"] is True
        assert _parse(cli_env.dev_archive())["success"] is True
        assert not (tmp_project / "DevSpec" / "active" / sid).exists()
        assert (tmp_project / "DevSpec" / "archive" / sid / "dev-spec.json").exists()
        # 归档后可以开启新循环
        result = _parse(cli_env.dev_plan_create("module", "order"))
        assert result["success"] is True

    def test_abort_and_archive(self, tmp_project, cli_env):
        _make_project(tmp_project)
        sid = _create_feature_session(cli_env)
        assert _parse(cli_env.dev_abort("方向变更"))["success"] is True
        assert _parse(cli_env.dev_archive())["success"] is True
        dev_spec = json.loads(
            (tmp_project / "DevSpec" / "archive" / sid / "dev-spec.json").read_text(encoding="utf-8"))
        assert dev_spec["status"] == "abandoned"
        assert dev_spec["closed_reason"] == "方向变更"


# ═══════════════════════════════════════════════════════════════
#  核心纪律：ProjectSpec 只读
# ═══════════════════════════════════════════════════════════════

class TestProjectSpecReadOnly:
    def test_dev_commands_never_write_project_spec(self, tmp_project, cli_env):
        """执行完整的开发循环后，ProjectSpec/ 必须字节级不变。"""
        _make_project(tmp_project)
        snapshot = _snapshot_project_spec(tmp_project)

        # 完整循环：plan → tasks → LOOP → align → integrate → notes → report → close → archive
        _create_feature_session(cli_env)
        cli_env.dev_plan_update_section(
            "plan.md#2. 约束整合", "- [MUST] C-101 扫描周期 ≤ 5 分钟（来源 feature-design §边界约束）")
        cli_env.dev_plan_add_section("plan.md#5. 完成标准", "补充说明", "--content 占位")
        for tid in ("T1", "T2"):
            for status in TASK_CHAIN:
                cli_env.dev_task_update(tid, status, note=f"{tid} {status}")
        cli_env.dev_task_annotate("T1", "记录偏差")
        cli_env.dev_align("order-timeout-cancel", "order", "aligned")
        cli_env.dev_align("order-timeout-cancel", "order", "done")
        cli_env.dev_integrate("order", "integrated")
        cli_env.dev_notes_append("### 偏差记录\n- 内容", section="设计文档遗漏与偏差")
        cli_env.dev_report_write("module", "order", "# 模块开发报告")
        cli_env.dev_integrate("order", "documented")
        cli_env.dev_integrate("order", "done")
        # 再触发一次失败路径（也不得写入 ProjectSpec）
        cli_env.dev_task_update("T1", "rejected")  # done → rejected 不合法，失败
        cli_env.dev_align("order-timeout-cancel", "order", "aligned")  # done → aligned 不合法，失败
        cli_env.dev_integrate("order", "integrated")  # done → integrated 不合法，失败
        cli_env.dev_close("模块完成")
        cli_env.dev_archive()

        assert _snapshot_project_spec(tmp_project) == snapshot, (
            "ProjectSpec/ 被 dev 命令修改了！spec-dev-loop 全程必须只读。"
        )


# ═══════════════════════════════════════════════════════════════
#  任务卡局部更新（dev task patch）与多函数签名（signatures）
# ═══════════════════════════════════════════════════════════════

class TestDevTaskPatch:
    """patch 只覆盖给出的字段：状态、尝试次数、备注与其它任务卡不得被重置。"""

    def _ready(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        cli_env.dev_task_annotate("T1", "已有备注：设计偏差")
        assert _parse(cli_env.dev_task_update("T1", "implementing"))["success"] is True

    def test_patch_preserves_status_attempts_notes_and_other_tasks(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        before = {t["task_id"]: t for t in _parse(cli_env.dev_task_list())["data"]["tasks"]}
        result = _parse(cli_env.dev_task_patch(
            "T1", json.dumps({"signature": "cancelExpiredOrders(ctx context.Context, limit int) error"})))
        assert result["success"] is True, result
        tasks = {t["task_id"]: t for t in _parse(cli_env.dev_task_list())["data"]["tasks"]}
        assert tasks["T1"]["signature"] == "cancelExpiredOrders(ctx context.Context, limit int) error"
        assert tasks["T1"]["status"] == "implementing"
        assert tasks["T1"]["attempts"] == before["T1"]["attempts"]
        assert "已有备注" in tasks["T1"]["notes"]
        assert tasks["T2"] == before["T2"]

    def test_patch_implemented_in_is_replaced_whole(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        result = _parse(cli_env.dev_task_patch(
            "T1", json.dumps({"implemented_in": {"path": "src/order/new_service.go"}})))
        assert result["success"] is True, result
        t1 = _parse(cli_env.dev_task_list())["data"]["tasks"][0]
        assert t1["implemented_in"] == {"path": "src/order/new_service.go"}  # lang 未被隐式保留

    def test_patch_refreshes_plan_table(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        assert _parse(cli_env.dev_task_patch(
            "T1", json.dumps({"constraint_ids": ["C-999"]})))["success"] is True
        plan = _parse(cli_env.dev_plan_read())
        sec3 = next(s for s in plan["data"]["sections"] if s["heading"] == "3. 骨架与任务清单")
        assert "C-999" in sec3["content"]

    def test_patch_unknown_field_lists_allowed_fields(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        result = _parse(cli_env.dev_task_patch("T1", json.dumps({"typo_field": 1})))
        assert result["success"] is False
        assert "typo_field" in result["message"]
        assert "允许的字段" in result["message"] and "signature" in result["message"]

    def test_patch_rejects_status_and_identity_fields(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        for bad in ("status", "task_id", "module", "feature", "attempts", "notes", "deviation"):
            result = _parse(cli_env.dev_task_patch("T1", json.dumps({bad: "x"})))
            assert result["success"] is False, bad
            assert "不允许修改字段" in result["message"], bad

    def test_patch_requires_json_object(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        assert _parse(cli_env.dev_task_patch("T1", "[]"))["success"] is False
        assert _parse(cli_env.dev_task_patch("T1", "not-json"))["success"] is False
        assert _parse(cli_env.dev_task_patch("T9", json.dumps({"title": "x"})))["success"] is False

    def test_patch_signatures(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        sigs = {
            "cancelExpiredOrders": "cancelExpiredOrders(ctx context.Context) error",
            "findExpiredOrders": "findExpiredOrders(ctx context.Context) []Order",
            "cancelOrder": "cancelOrder(ctx context.Context, o Order) error",
            "releaseStock": "releaseStock(o Order) error",
        }
        assert _parse(cli_env.dev_task_patch(
            "T1", json.dumps({"signatures": sigs})))["success"] is True
        t1 = _parse(cli_env.dev_task_list())["data"]["tasks"][0]
        assert t1["signatures"] == sigs


class TestTaskSignatures:
    MULTI = json.dumps([{
        "task_id": "T1",
        "title": "迁移入口（内聚调用链）",
        "module": "order",
        "feature": "order-timeout-cancel",
        "implemented_in": {"path": "src/store/migrations.ts", "lang": "ts"},
        "functions": ["applyMigrations", "buildIndexDDL", "enableTriggers"],
        "entry_function": "applyMigrations",
        "signature": "applyMigrations(opts: MigrateOptions): Promise<void>",
        "signatures": {
            "applyMigrations": "applyMigrations(opts: MigrateOptions): Promise<void>",
            "buildIndexDDL": "buildIndexDDL(): string",
            "enableTriggers": "enableTriggers(): void",
        },
        "merge_reason": "同一文件内的内聚调用链",
    }], ensure_ascii=False)

    def test_set_accepts_multi_function_signatures(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        assert _parse(cli_env.dev_task_set(self.MULTI))["success"] is True
        task = _parse(cli_env.dev_task_list())["data"]["tasks"][0]
        assert task["signatures"]["buildIndexDDL"] == "buildIndexDDL(): string"

    def test_signature_keys_must_belong_to_functions(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        bad = json.dumps([{
            "task_id": "T1", "title": "x",
            "implemented_in": {"path": "a.ts"},
            "functions": ["a"],
            "signatures": {"b": "b(): void"},
        }])
        result = _parse(cli_env.dev_task_set(bad))
        assert result["success"] is False
        assert "functions" in result["message"]

    def test_signatures_must_be_object_of_nonempty_strings(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        not_object = json.dumps([{
            "task_id": "T1", "title": "x", "implemented_in": {"path": "a.ts"},
            "functions": ["a"], "signatures": ["a"]}])
        assert _parse(cli_env.dev_task_set(not_object))["success"] is False
        empty_value = json.dumps([{
            "task_id": "T1", "title": "x", "implemented_in": {"path": "a.ts"},
            "functions": ["a"], "signatures": {"a": "  "}}])
        assert _parse(cli_env.dev_task_set(empty_value))["success"] is False

    def test_helper_task_without_symbol_or_functions(self, tmp_project, cli_env):
        """表外产物 helper（DDL/迁移）允许 functions/symbol 为空，仍走同一状态机。"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        helper = json.dumps([{
            "task_id": "T0",
            "title": "[helper] 创建 store 索引与触发器",
            "module": "order",
            "feature": "order-timeout-cancel",
            "implemented_in": {"path": "src/store/migrations.sql", "lang": "sql"},
            "capability_notes": ["HELPER: 兑现 C-106~C-114"],
            "constraint_ids": ["C-106", "C-107"],
            "calls": [],
            "symbol": "",
            "functions": [],
        }], ensure_ascii=False)
        assert _parse(cli_env.dev_task_set(helper))["success"] is True
        task = _parse(cli_env.dev_task_list())["data"]["tasks"][0]
        assert task["task_id"] == "T0"
        assert task["functions"] == [] and task["symbol"] == ""
        # align 不受影响：仍按"任务全 done"判断（此处未完成 → 正常拒绝，而不是 schema 错误）
        res = _parse(cli_env.dev_align("order-timeout-cancel", "order", "aligned"))
        assert res["success"] is False and "tasks_not_done" in res["suggestions"][0]


# ═══════════════════════════════════════════════════════════════
#  分支写操作前置断言（只读 .git/HEAD）
# ═══════════════════════════════════════════════════════════════

def _git(project, *args):
    p = subprocess.run(["git", *args], cwd=str(project), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def _init_git(project):
    _git(project, "init", "-q", ".")
    _git(project, "config", "user.email", "t@example.com")
    _git(project, "config", "user.name", "t")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")


class TestDevBranchGuard:
    def _ready(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _init_git(tmp_project)
        sid = _create_feature_session(cli_env)
        default = _git(tmp_project, "rev-parse", "--abbrev-ref", "HEAD")
        return sid, default

    def _on_expected(self, tmp_project, sid):
        _git(tmp_project, "checkout", "-q", "-b", f"dev-loop/{sid}")

    def _on_default(self, tmp_project, default):
        _git(tmp_project, "checkout", "-q", default)

    def test_no_git_branch_matches_is_null(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        st = _parse(cli_env.dev_status())
        assert st["data"]["branch_matches"] is None
        # 非 git 项目：写命令行为与之前一致
        assert _parse(cli_env.dev_task_update("T1", "implementing"))["success"] is True

    def test_matching_branch_allows_forward_transition(self, tmp_project, cli_env):
        sid, default = self._ready(tmp_project, cli_env)
        self._on_expected(tmp_project, sid)
        st = _parse(cli_env.dev_status())
        assert st["data"]["branch_matches"] is True
        assert "**当前分支**" in st["message"]
        assert _parse(cli_env.dev_task_update("T1", "implementing"))["success"] is True

    def test_mismatch_blocks_forward_but_allows_failure_records(self, tmp_project, cli_env):
        sid, default = self._ready(tmp_project, cli_env)
        self._on_expected(tmp_project, sid)
        assert _parse(cli_env.dev_task_update("T1", "implementing"))["success"] is True
        assert _parse(cli_env.dev_task_update("T2", "implementing"))["success"] is True
        self._on_default(tmp_project, default)

        st = _parse(cli_env.dev_status())
        assert st["data"]["branch_matches"] is False
        assert "dev_branch.mismatch" in st["suggestions"][0]
        # 读命令始终放行
        assert _parse(cli_env.dev_task_list())["success"] is True
        assert _parse(cli_env.dev_plan_read())["success"] is True
        # 前进状态被阻断
        blocked = _parse(cli_env.dev_task_update("T1", "submitted"))
        assert blocked["success"] is False
        assert "dev_branch.mismatch" in blocked["suggestions"][0]
        assert _parse(cli_env.dev_task_patch("T1", json.dumps({"title": "x"})))["success"] is False
        # 记录失败 / 设计缺口放行
        assert _parse(cli_env.dev_task_update("T1", "rejected", note="分支外的失败记录"))["success"] is True
        assert _parse(cli_env.dev_task_update("T2", "blocked", note="设计缺口"))["success"] is True
        # 备注类写操作也放行
        assert _parse(cli_env.dev_task_annotate("T1", "备注"))["success"] is True

    def test_detached_head_blocks_writes(self, tmp_project, cli_env):
        sid, default = self._ready(tmp_project, cli_env)
        self._on_expected(tmp_project, sid)
        _git(tmp_project, "checkout", "-q", "--detach", "HEAD")
        st = _parse(cli_env.dev_status())
        assert st["data"]["branch_matches"] is False
        assert _parse(cli_env.dev_task_update("T1", "implementing"))["success"] is False

    def test_branch_set_updates_spec_and_plan(self, tmp_project, cli_env):
        sid, default = self._ready(tmp_project, cli_env)
        self._on_default(tmp_project, default)
        result = _parse(cli_env.dev_branch_set(default))
        assert result["success"] is True, result
        session_dir = tmp_project / "DevSpec" / "active" / sid
        dev_spec = json.loads((session_dir / "dev-spec.json").read_text(encoding="utf-8"))
        assert dev_spec["branch"] == default
        plan = _parse(cli_env.dev_plan_read())
        sec6 = next(s for s in plan["data"]["sections"] if s["heading"] == "6. 分支信息")
        assert default in sec6["content"]
        # 记录后断言通过
        assert _parse(cli_env.dev_status())["data"]["branch_matches"] is True
        assert _parse(cli_env.dev_task_update("T1", "implementing"))["success"] is True

    def test_branch_set_rejects_empty(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        assert _parse(cli_env.dev_branch_set("   "))["success"] is False

    def test_align_allows_explicit_mismatch_with_reason(self, tmp_project, cli_env):
        sid, default = self._ready(tmp_project, cli_env)
        self._on_expected(tmp_project, sid)
        for tid in ("T1", "T2"):
            for status in TASK_CHAIN:
                assert _parse(cli_env.dev_task_update(tid, status))["success"] is True
        self._on_default(tmp_project, default)
        failed = _parse(cli_env.dev_align("order-timeout-cancel", "order", "aligned"))
        assert failed["success"] is False
        assert "dev_branch.mismatch" in failed["suggestions"][0]
        no_reason = _parse(cli_env.dev_align(
            "order-timeout-cancel", "order", "aligned", allow_branch_mismatch=True))
        assert no_reason["success"] is False
        assert "missing_reason" in no_reason["suggestions"][0]
        ok = _parse(cli_env.dev_align(
            "order-timeout-cancel", "order", "aligned",
            allow_branch_mismatch=True, reason="分支已合并，收尾"))
        assert ok["success"] is True, ok
        # integrate 同矩阵
        assert _parse(cli_env.dev_integrate("order", "integrated"))["success"] is False
        assert _parse(cli_env.dev_integrate(
            "order", "integrated", allow_branch_mismatch=True, reason="分支已合并，收尾"))["success"] is True

    def test_lifecycle_commands_allowed_on_mismatch(self, tmp_project, cli_env):
        """abort / close 是恢复通道，分支不匹配时也允许。"""
        sid, default = self._ready(tmp_project, cli_env)
        self._on_expected(tmp_project, sid)
        self._on_default(tmp_project, default)
        assert _parse(cli_env.dev_close("收尾"))["success"] is True
        assert _parse(cli_env.dev_archive())["success"] is True

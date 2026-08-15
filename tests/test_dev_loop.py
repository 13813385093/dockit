"""spec-dev-loop 开发执行循环测试 — DevSpec 生命周期 + ProjectSpec 只读保障。

测试链路:
  dev plan create → dev task set → dev task update（状态机）→ dev align →
  dev integrate → dev notes append → dev report-write → dev close/abort → dev archive

核心纪律测试：整个循环过程中 ProjectSpec/ 必须保持字节级不变（只读）。
"""

import json

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
        "functions": ["cancelExpiredOrders", "findExpiredOrders", "cancelOrder", "releaseStock"],
        "entry_function": "cancelExpiredOrders",
        "signature": "(ctx context.Context) error",
        "gwt_refs": ["unit-tests.md#测试用例：超时订单被扫描"],
        "constraint_ids": ["C-101", "C-102"],
    },
    {
        "task_id": "T2",
        "title": "释放库存",
        "module": "order",
        "feature": "order-timeout-cancel",
        "functions": ["releaseStock"],
        "signature": "(order Order) error",
        "constraint_ids": ["C-102"],
    },
], ensure_ascii=False)


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
        assert "1. 范围与目标" in headings and "2. 约束整合" in headings and "3. 任务清单" in headings
        # 更新约束整合段落（reference 支持裸 plan.md 前缀）
        upd = _parse(cli_env.dev_plan_update_section(
            "plan.md#2. 约束整合",
            "- [MUST] C-101 扫描周期 ≤ 5 分钟（来源 feature-design §边界约束）"))
        assert upd["success"] is True
        again = _parse(cli_env.dev_plan_read())
        sec2 = next(s for s in again["data"]["sections"] if s["heading"] == "2. 约束整合")
        assert "C-101" in sec2["content"]

    def test_task_set_refreshes_plan_table(self, tmp_project, cli_env):
        """tasks.json 是唯一数据源，plan.md §3 由 CLI 自动渲染。"""
        _make_project(tmp_project)
        _create_feature_session(cli_env)
        result = _parse(cli_env.dev_plan_read())
        sec3 = next(s for s in result["data"]["sections"] if s["heading"] == "3. 任务清单")
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


class TestDevTaskTransitions:
    def _ready(self, tmp_project, cli_env):
        _make_project(tmp_project)
        _create_feature_session(cli_env)

    def test_valid_transition_chain(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        for status in ("in-progress", "implemented", "unit-green", "done"):
            result = _parse(cli_env.dev_task_update("T1", status, note=f"step {status}"))
            assert result["success"] is True, result
        tasks = _parse(cli_env.dev_task_list())["data"]["tasks"]
        assert tasks[0]["status"] == "done"
        assert "[20" in tasks[0]["notes"]  # 备注带日期前缀

    def test_fixing_loop(self, tmp_project, cli_env):
        self._ready(tmp_project, cli_env)
        cli_env.dev_task_update("T1", "in-progress")
        # 测试失败 → fixing
        fix = _parse(cli_env.dev_task_update("T1", "fixing", note="单元测试失败：C-101 未满足"))
        assert fix["success"] is True
        # fixing → in-progress 重新开发
        assert _parse(cli_env.dev_task_update("T1", "in-progress"))["success"] is True

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
        assert _parse(cli_env.dev_task_update("T99", "in-progress"))["success"] is False

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
            {"task_id": "T1", "title": "x", "status": "bogus"}])))
        assert bad["success"] is False
        dup = _parse(cli_env.dev_task_set(json.dumps([
            {"task_id": "T1", "title": "a"}, {"task_id": "T1", "title": "b"}])))
        assert dup["success"] is False
        missing = _parse(cli_env.dev_task_set(json.dumps([{"task_id": "T1"}])))
        assert missing["success"] is False


# ═══════════════════════════════════════════════════════════════
#  功能对齐 / 模块集成
# ═══════════════════════════════════════════════════════════════

class TestDevMilestones:
    def _finish_all_tasks(self, cli_env):
        for tid in ("T1", "T2"):
            for status in ("in-progress", "implemented", "unit-green", "done"):
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
            for status in ("in-progress", "implemented", "unit-green", "done"):
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
        cli_env.dev_task_update("T1", "fixing")  # done → fixing 不合法，失败
        cli_env.dev_align("order-timeout-cancel", "order", "aligned")  # done → aligned 不合法，失败
        cli_env.dev_integrate("order", "integrated")  # done → integrated 不合法，失败
        cli_env.dev_close("模块完成")
        cli_env.dev_archive()

        assert _snapshot_project_spec(tmp_project) == snapshot, (
            "ProjectSpec/ 被 dev 命令修改了！spec-dev-loop 全程必须只读。"
        )

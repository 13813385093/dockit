"""主窗口 — 协调侧边栏文档树、工具栏和主内容区切换。"""
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QSettings, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve
from PySide6.QtGui import QAction, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QStatusBar,
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTabWidget,
    QFrame, QToolButton, QMenu, QWidgetAction,
)

from src.app.icon_utils import get_icon, set_button_icon
from src.app.meta_store import AppMeta
from src.app.style_utils import load_stylesheet
from src.app.doc_tree import DocTreePanel
from src.app.dashboard import DashboardPanel
from src.app.editor import DocEditor
from src.app.json_editor import JsonEditor
from src.app.dep_graph import DepGraphPanel
from src.app.lifecycle import LifecyclePanel
from src.app.settings import SettingsPanel
from src.app.dialogs.init_dialog import InitDialog
from src.app.dialogs.global_search import GlobalSearchDialog
from src.app.engine.index import IndexManager, IndexEntry
from src.app.engine.frontmatter import FrontmatterParser
from src.app.engine.registry import Registry
from src.app.engine.commands.init_utils import init_project


class MainWindow(QMainWindow):
    """应用主窗口。

    布局:
        ┌──────────────────────────────────────────────┐
        │  菜单栏                                        │
        ├──────────────────────────────────────────────┤
        │  [☰] │  最近项目: ▼__________ │ [🔄] [✓]  │  ← 全局工具栏
        ├──────────┬───────────────────────────────────┤
        │ 文档树    │  主内容区 (QTabWidget)             │
        │          │  ┌─────────────────────────────┐  │
        │          │  │ 仪表盘 / 编辑器 / 依赖图 /   │  │
        │          │  │ 生命周期 / 设置              │  │
        │          │  └─────────────────────────────┘  │
        ├──────────┴───────────────────────────────────┤
        │  状态栏                                        │
        └──────────────────────────────────────────────┘
    """

    MAX_RECENT = 5

    def __init__(self):
        super().__init__()
        self.setWindowTitle("doc_kit")
        
        # 当前项目状态
        self._project_root: Path | None = None
        self._index: IndexManager | None = None
        self._registry: Registry | None = None
        self._sidebar_visible = True
        self._sidebar_width = 280  # 侧栏展开时宽度 (px)，拖拽分栏时动态更新
        self._current_project_path: str | None = None  # 当前项目路径，用于菜单✓标记
        self._current_doc_rel: str | None = None  # 当前打开的文档相对路径

        # 最近项目列表持久化（exe 同级 .meta/，替代注册表）
        self._meta = AppMeta()
        self._migrate_legacy_settings()
        self._recent_projects: list[str] = list(
            self._meta.get("projects", "recent_projects", []) or []
        )
        self._recent_project_actions: dict[str, QWidgetAction] = {}  # 用于动态更新菜单

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_status_bar()
        load_stylesheet()

        # 全局搜索快捷键
        self._shortcut_global_search = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        self._shortcut_global_search.setContext(Qt.ApplicationShortcut)
        self._shortcut_global_search.activated.connect(self._on_global_search)

        # 自动打开上次的项目
        last_project = self._meta.get("projects", "last_project")
        if last_project:
            last_path = Path(last_project)
            if last_path.exists():
                self.load_project(last_path)

        self.showMaximized()
    # ── UI 搭建 ──────────────────────────────────────────────

    def _prompt_save(self) -> bool:
        """检查编辑器是否有未保存的修改，提示用户保存。
        
        返回 True 表示可以继续操作，False 表示用户取消了操作。
        """
        # 检查 md 编辑器
        if self.editor.is_modified():
            reply = QMessageBox.question(
                self,
                "未保存的修改",
                "Markdown 编辑器中有未保存的修改，是否保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            if reply == QMessageBox.Save:
                self.editor.save()
                if self.editor.is_modified():
                    # 保存失败（如 JSON 格式错误），取消操作
                    return False
            elif reply == QMessageBox.Cancel:
                return False
            # Discard: 不保存，继续操作
        
        # 检查 json 编辑器
        if self.json_editor.is_modified():
            reply = QMessageBox.question(
                self,
                "未保存的修改",
                "JSON 编辑器中有未保存的修改，是否保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            if reply == QMessageBox.Save:
                self.json_editor.save()
                if self.json_editor.is_modified():
                    # 保存失败（如 JSON 格式错误），取消操作
                    return False
            elif reply == QMessageBox.Cancel:
                return False
            # Discard: 不保存，继续操作
        
        return True

    def _setup_ui(self):
        """搭建主界面布局。"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 可拖拽分割器（侧栏 + 主区域）
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setObjectName("main_splitter")

        # 左侧：文档树
        self.doc_tree = DocTreePanel(self)
        self.doc_tree.document_selected.connect(self._on_doc_selected)
        self.doc_tree.setMinimumWidth(180)
        self.doc_tree.setMaximumWidth(500)
        self._splitter.addWidget(self.doc_tree)

        # 右侧：标签页
        self.tabs = QTabWidget()
        self.dashboard = DashboardPanel(self)
        self.editor = DocEditor(self)
        self.json_editor = JsonEditor(self)
        self.dep_graph = DepGraphPanel(self)
        self.lifecycle = LifecyclePanel(self)
        self.settings = SettingsPanel(self)

        self.tabs.addTab(self.dashboard, get_icon("trello"), "仪表盘")
        self._tab_idx_editor = self.tabs.addTab(self.editor, get_icon("edit"), "md 编辑器")
        self._tab_idx_json = self.tabs.addTab(self.json_editor, get_icon("code"), "JSON 编辑器")
        self.tabs.addTab(self.dep_graph, get_icon("graph"), "依赖图")
        self.tabs.addTab(self.lifecycle, get_icon("refresh"), "生命周期")
        self.tabs.addTab(self.settings, get_icon("gear"), "设置")
        self._splitter.addWidget(self.tabs)

        # 编辑器保存后 → 自动 check + 刷新仪表盘
        self.editor.document_saved.connect(self._on_doc_saved)
        self.editor.navigate_to_doc.connect(self._on_navigate_to_doc)
        self.editor.navigate_to_doc_anchor.connect(self._on_navigate_to_doc_anchor)

        # 仪表盘双击导航
        self.dashboard.navigate_to_doc.connect(self._on_navigate_to_doc)

        # 标签页切换时，仪表盘被激活则执行检查
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self._splitter.setSizes([280, 1000])
        layout.addWidget(self._splitter, 1)

    def _toggle_sidebar(self):
        """切换侧栏显示/隐藏 — 带动态缩放动画。"""
        self._sidebar_visible = not self._sidebar_visible
        self._sidebar_btn.setIcon(get_icon("sidebar-hidden" if not self._sidebar_visible else "sidebar-visible"))
        self._sidebar_btn.setToolTip("显示侧栏" if not self._sidebar_visible else "隐藏侧栏")

        # 同时对 minimumWidth 和 maximumWidth 做动画，
        # QSplitter 会自动跟随约束变化分配空间，不受 setMinimumWidth 限制。
        if self._sidebar_visible:
            # 展开：从 0 → 目标宽度
            start_w, end_w = 0, self._sidebar_width
        else:
            # 收起：从当前实际宽度 → 0，并保存供下次展开使用
            self._sidebar_width = self.doc_tree.width()
            start_w, end_w = self._sidebar_width, 0

        anim_min = QPropertyAnimation(self.doc_tree, b"minimumWidth", self)
        anim_min.setDuration(250)
        anim_min.setStartValue(start_w)
        anim_min.setEndValue(end_w)
        anim_min.setEasingCurve(QEasingCurve.OutCubic)

        anim_max = QPropertyAnimation(self.doc_tree, b"maximumWidth", self)
        anim_max.setDuration(250)
        anim_max.setStartValue(start_w)
        anim_max.setEndValue(end_w)
        anim_max.setEasingCurve(QEasingCurve.OutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(anim_min)
        group.addAnimation(anim_max)

        def _on_finish():
            """展开完毕恢复可拖拽约束；收起时保持约束 0，已无需 setVisible。"""
            if self._sidebar_visible:
                self.doc_tree.setMinimumWidth(180)
                self.doc_tree.setMaximumWidth(500)

        group.finished.connect(_on_finish)
        group.start()

    def _setup_toolbar(self):
        """搭建全局工具栏 — 侧栏切换 + 最近项目 + 快捷操作。"""
        toolbar = self.addToolBar("全局工具栏")
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)

        # 侧栏切换按钮
        self._sidebar_btn = QToolButton()
        self._sidebar_btn.setCheckable(True)
        self._sidebar_btn.setChecked(True)
        self._sidebar_btn.setIcon(get_icon("sidebar-visible"))
        self._sidebar_btn.setToolTip("隐藏侧栏")
        self._sidebar_btn.clicked.connect(self._toggle_sidebar)
        toolbar.addWidget(self._sidebar_btn)

        # 分隔线
        toolbar.addSeparator()

        # 项目选择按钮（弹出菜单 = 打开项目 + 最近项目列表）
        self._recent_btn = QToolButton()
        self._recent_btn.setText(" 打开项目 ")
        self._recent_btn.setToolTip("打开项目或选择最近的项目")
        self._recent_btn.setPopupMode(QToolButton.InstantPopup)
        self._recent_btn.setFixedWidth(160)
        self._refresh_recent_menu()
        toolbar.addWidget(self._recent_btn)

        # 分隔线
        toolbar.addSeparator()
        
        # 保存按钮（放在项目选择右侧）
        self._toolbar_save_btn = QToolButton()
        self._toolbar_save_btn.setIcon(get_icon("save"))
        self._toolbar_save_btn.setToolTip("保存 (Ctrl+S)")
        self._toolbar_save_btn.clicked.connect(self._on_global_save)
        toolbar.addWidget(self._toolbar_save_btn)

        # 分隔线
        toolbar.addSeparator()

        # 全局搜索按钮
        self._toolbar_search_btn = QToolButton()
        self._toolbar_search_btn.setIcon(get_icon("search"))
        self._toolbar_search_btn.setToolTip("全局搜索 (Ctrl+Shift+F)")
        self._toolbar_search_btn.clicked.connect(self._on_global_search)
        toolbar.addWidget(self._toolbar_search_btn)


    def _refresh_recent_menu(self):
        """重建最近项目弹出菜单 — QToolButton 弹出式。"""
        menu = QMenu(self)

        # 顶部固定项：打开项目
        open_act = menu.addAction(get_icon("folder"), " 打开项目...")
        open_act.triggered.connect(self._on_open_project)

        menu.addSeparator()

        # 清理不存在的项目路径，并持久化
        alive = [p for p in self._recent_projects if Path(p).exists()]
        changed = len(alive) < len(self._recent_projects)
        self._recent_projects = alive
        if changed:
            self._save_recent_projects()

        # 清空旧的 action 映射
        self._recent_project_actions.clear()

        # 最近项目列表
        for path_str in self._recent_projects:
            project_path = Path(path_str)
            name = project_path.name
            is_current = (path_str == self._current_project_path)

            action = QWidgetAction(self)
            widget = QWidget()
            widget.setObjectName("RecentMenuItem")
            h_layout = QHBoxLayout(widget)
            h_layout.setContentsMargins(8, 4, 8, 4)
            h_layout.setSpacing(8)

            v_layout = QVBoxLayout()
            v_layout.setSpacing(1)
            name_label = QLabel(name)
            name_label.setObjectName("RecentMenuItemName")
            path_label = QLabel(path_str)
            path_label.setObjectName("RecentMenuItemPath")
            v_layout.addWidget(name_label)
            v_layout.addWidget(path_label)
            h_layout.addLayout(v_layout, 1)

            item_btn = QPushButton(self)
            item_btn.setObjectName("RecentMenuItemBtn")
            h_layout.addWidget(item_btn)

            if is_current:
                item_btn.setIcon(get_icon("check").pixmap(16, 16))
            else:
                item_btn.setIcon(get_icon("trash").pixmap(16, 16))
                item_btn.clicked.connect(lambda checked, p=path_str: self._remove_recent_project(p))

            action.setDefaultWidget(widget)
            action.triggered.connect(lambda checked, p=project_path: self.load_project(p))
            menu.addAction(action)
            
            # 保存 action 引用用于动态删除
            self._recent_project_actions[path_str] = action

        if not self._recent_projects:
            empty_act = menu.addAction("  (暂无最近项目)")
            empty_act.setEnabled(False)

        self._recent_btn.setMenu(menu)

    def _migrate_legacy_settings(self):
        """一次性迁移：把注册表 QSettings 中的旧项目记录导入 .meta/projects.json。"""
        if self._meta.get("projects", "migrated_from_registry", False):
            return
        legacy = QSettings("doc-kit", "doc-kit-ui")
        recent = legacy.value("recent_projects", None)
        last = legacy.value("last_project", None)
        changed = False
        if recent:
            self._meta.set("projects", "recent_projects", list(recent))
            changed = True
        if last:
            self._meta.set("projects", "last_project", str(last))
            changed = True
        self._meta.set("projects", "migrated_from_registry", True)
        if changed:
            print(f"已从注册表迁移项目记录到 {self._meta.meta_dir / 'projects.json'}")

    def _save_recent_projects(self):
        """持久化最近项目列表。"""
        self._meta.set("projects", "recent_projects", self._recent_projects)

    def _push_recent_project(self, project_root: Path):
        """将项目推入最近列表首位（去重，上限 MAX_RECENT）。"""
        path_str = str(project_root.resolve())
        self._recent_projects = [p for p in self._recent_projects if p != path_str]
        self._recent_projects.insert(0, path_str)
        self._recent_projects = self._recent_projects[:self.MAX_RECENT]
        self._save_recent_projects()

    def _remove_recent_project(self, path_str: str):
        """从最近项目列表中移除指定项目。"""
        if path_str in self._recent_projects:
            self._recent_projects.remove(path_str)
            self._save_recent_projects()
            
            if path_str in self._recent_project_actions:
                action = self._recent_project_actions[path_str]
                menu = self._recent_btn.menu()
                if menu:
                    menu.removeAction(action)
                del self._recent_project_actions[path_str]
            
            if not self._recent_projects:
                menu = self._recent_btn.menu()
                if menu:
                    empty_act = menu.addAction("  (暂无最近项目)")
                    empty_act.setEnabled(False)

    def _setup_menu(self):
        """搭建菜单栏。"""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")
        open_act = QAction(" 打开项目...", self)
        open_act.setIcon(get_icon("folder"))
        open_act.triggered.connect(self._on_open_project)
        file_menu.addAction(open_act)
        file_menu.addSeparator()
        exit_act = QAction("退出", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        tool_menu = menubar.addMenu("工具(&T)")
        sync_act = QAction(" 同步索引 (sync)", self)
        sync_act.setIcon(get_icon("refresh"))
        sync_act.triggered.connect(self._on_sync)
        tool_menu.addAction(sync_act)
        check_act = QAction(" 运行检查 (check)", self)
        check_act.setIcon(get_icon("check"))
        check_act.triggered.connect(self._on_check)
        tool_menu.addAction(check_act)

        help_menu = menubar.addMenu("帮助(&H)")
        about_act = QAction("关于 doc_kit", self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

    def _setup_status_bar(self):
        """搭建状态栏。"""
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("就绪 — 请打开一个项目 (文件 > 打开项目)，未初始化的目录会自动初始化")

    # ── 槽函数 ───────────────────────────────────────────────

    @Slot()
    def _on_open_project(self):
        """打开项目目录。若未初始化则弹出 init 对话框。"""
        # 先检查是否有未保存的修改
        if not self._prompt_save():
            return
        
        directory = QFileDialog.getExistingDirectory(self, "选择项目根目录")
        if not directory:
            return
        project_root = Path(directory)

        kit_dir = project_root / ".doc-kit"
        if not kit_dir.exists():
            dlg = InitDialog(project_root, self)
            if not dlg.exec():
                return
            try:
                name = init_project(
                    project_root,
                    project_name=dlg.project_name,
                )
                QMessageBox.information(
                    self, "初始化完成",
                    f"项目「{name}」文档骨架已创建。\n"
                    f"路径: {project_root / 'ProjectSpec'}",
                )
            except Exception as e:
                QMessageBox.critical(self, "初始化失败", str(e))
                return

        self.load_project(project_root)

    def load_project(self, project_root: Path):
        """加载指定项目。"""
        # 先检查是否有未保存的修改
        if not self._prompt_save():
            return
        
        kit_dir = project_root / ".doc-kit"
        if not kit_dir.exists():
            QMessageBox.warning(self, "无效项目", f"未找到 .doc-kit/ 目录: {project_root}")
            return

        self._push_recent_project(project_root)
        self._meta.set("projects", "last_project", str(project_root.resolve()))

        self._project_root = project_root
        self._current_project_path = str(project_root.resolve())
        self._recent_btn.setText(f" {project_root.name} ")
        self._refresh_recent_menu()
        index_path = kit_dir / "index.json"
        self._index = IndexManager(index_path)

        # 以 ProjectSpec/ 实际文档为准全量重建索引并落盘，
        # 避免 index.json 过期/缺失导致文件树与实际文档不一致。
        self._index.rebuild(project_root / "ProjectSpec")
        self._index.save()

        # 创建文档类型注册表
        reg_path = kit_dir / "registry.yaml"
        self._registry = Registry(reg_path) if reg_path.exists() else Registry()

        self.doc_tree.load_project(project_root, self._index)
        self.dashboard.load_project(project_root, self._index)
        self.dep_graph.load_project(project_root, self._index, self._registry)
        self.lifecycle.load_project(project_root, self._index)
        self.settings.load_project(project_root, self._index)

        self.tabs.setCurrentWidget(self.dashboard)
        self.status.showMessage(f"已加载项目: {project_root.name}")

    @Slot()
    def _on_doc_selected(self, rel_path: str):
        """文档树中选择文件 → 按类型在对应编辑器中打开。"""
        # 先检查是否有未保存的修改
        if not self._prompt_save():
            return
        
        if not self._project_root or not self._index:
            return
        self._current_doc_rel = rel_path
        full_path = self._project_root / rel_path
        if not full_path.exists():
            return
        if full_path.suffix.lower() == ".json":
            self._switch_editor_visibility(json_mode=True)
            self.json_editor.open_file(full_path, rel_path)
            self.tabs.setCurrentWidget(self.json_editor)
        else:
            self._switch_editor_visibility(json_mode=False)
            self.editor.open_document(full_path, rel_path, self._index, self._registry)
            self.tabs.setCurrentWidget(self.editor)

    def _switch_editor_visibility(self, json_mode: bool):
        """按文件类型显示对应编辑器标签页、隐藏另一个。

        json_mode=True：显示 JSON 编辑器、隐藏 md 编辑器；反之亦然。
        """
        self.tabs.tabBar().setTabVisible(self._tab_idx_editor, not json_mode)
        self.tabs.tabBar().setTabVisible(self._tab_idx_json, json_mode)

    @Slot()
    def _on_global_save(self):
        """根据当前激活标签页调用对应的 save() 方法。"""
        current = self.tabs.currentWidget()
        save_fn = getattr(current, "save", None)
        if save_fn:
            save_fn()
        else:
            self.status.showMessage("当前标签页不支持保存", 3000)

    @Slot()
    def _on_navigate_to_doc(self, rel_path: str) -> bool:
        """跳转到依赖表中引用的目标文档；返回是否跳转成功。"""
        if not self._project_root:
            return False
        full_path = self._project_root / rel_path
        if full_path.exists():
            self._switch_editor_visibility(json_mode=False)
            self.editor.open_document(full_path, rel_path, self._index, self._registry)
            self.tabs.setCurrentWidget(self.editor)
            return True
        self.status.showMessage(f"未找到目标文档: {rel_path}", 4000)
        return False

    @Slot(str, str)
    def _on_navigate_to_doc_anchor(self, rel_path: str, anchor: str):
        """预览链接跳转：打开目标文档后定位到锚点（{#锚点} 标记的标题）。"""
        if self._on_navigate_to_doc(rel_path) and anchor:
            self.editor.jump_to_anchor(anchor)

    @Slot()
    def _on_doc_saved(self, rel_path: str):
        """文档保存后：同步索引 → 运行 check → 留在编辑器，状态栏显示结果。"""
        if not self._project_root or not self._index:
            return
        from src.app.engine.deps import check_version_drift, check_deprecated_deps

        self._index.rebuild(self._project_root / "ProjectSpec")
        self._index.save()

        drifts = check_version_drift(self._index)
        deprecated = check_deprecated_deps(self._index)
        self.dashboard.show_check_results(drifts, deprecated)

        self.status.showMessage(
            f"已保存 {rel_path} — 检查: {len(drifts)} 个漂移, {len(deprecated)} 个废弃依赖",
            5000,
        )

    @Slot(int)
    def _on_tab_changed(self, index: int):
        """标签页切换时，仪表盘被激活则执行检查，依赖图被激活则显示当前文档依赖。"""
        # 先检查是否有未保存的修改
        if not self._prompt_save():
            return
        
        current_widget = self.tabs.widget(index)
        if current_widget == self.dashboard and self._index:
            from src.app.engine.deps import check_version_drift, check_deprecated_deps
            drifts = check_version_drift(self._index)
            deprecated = check_deprecated_deps(self._index)
            self.dashboard.show_check_results(drifts, deprecated)
        elif current_widget == self.dep_graph and self._current_doc_rel:
            self.dep_graph.show_doc_deps(self._current_doc_rel)

    # ── 新建功能 ────────────────────────────────────────────

    def _on_new_module(self):
        """打开新建模块对话框。"""
        if not self._project_root or not self._index:
            QMessageBox.information(self, "提示", "请先打开一个项目")
            return
        from src.app.dialogs.new_module_dialog import NewModuleDialog
        from src.app.engine.commands.new_utils import render_template, resolve_path
        from src.app.engine.registry import Registry
        from src.app.engine.index import IndexEntry

        dlg = NewModuleDialog(self._index, self)
        if not dlg.exec():
            return

        module_path = dlg.full_module_path
        doc_types = dlg.doc_types
        now = FrontmatterParser.now_iso()
        project_docs = self._project_root / "ProjectSpec"
        kit_dir = self._project_root / ".doc-kit"
        created = []

        for doc_type_key in doc_types:
            reg = Registry(kit_dir / "registry.yaml" if (kit_dir / "registry.yaml").exists() else None)
            doc_type_def = reg.get(doc_type_key)
            if not doc_type_def:
                continue
            target_path = resolve_path(project_docs, doc_type_def, module_path, None)
            if target_path.exists():
                continue
            depends_on: list[dict] = []
            try:
                content = render_template(
                    doc_type_def.template, module_path, None,
                    depends_on, now, kit_dir,
                )
            except FileNotFoundError:
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            features_dir = target_path.parent / "features"
            features_dir.mkdir(exist_ok=True)
            created.append(target_path)

        if not created:
            return

        for target_path in created:
            rel_path = str(target_path.relative_to(self._project_root)).replace("\\", "/")
            meta, _ = FrontmatterParser.read_file(target_path)
            entry = IndexEntry(
                path=rel_path,
                doc_type=meta.get("doc_type", "unknown"),
                module=module_path,
                level=meta.get("level", "module"),
                version=str(meta.get("version", "0.1.0")),
                status=meta.get("status", "active"),
                depends_on=meta.get("depends_on", []),
            )
            self._index.add_entry(entry)
        self._index.save()

        self._reload_all_panels()
        QMessageBox.information(
            self, "模块创建完成",
            f"模块「{module_path}」已创建\n文档: {len(created)} 个",
        )

    def _on_new_feature(self):
        """打开新建功能对话框。"""
        if not self._project_root or not self._index:
            QMessageBox.information(self, "提示", "请先打开一个项目")
            return
        from src.app.dialogs.new_feature_dialog import NewFeatureDialog
        from src.app.engine.commands.new_utils import render_template, resolve_path
        from src.app.engine.registry import Registry
        from src.app.engine.index import IndexEntry

        dlg = NewFeatureDialog(self._index, self)
        if not dlg.exec():
            return

        module_name = dlg.module_name
        feature_name = dlg.feature_name
        doc_types = dlg.doc_types
        now = FrontmatterParser.now_iso()
        project_docs = self._project_root / "ProjectSpec"
        kit_dir = self._project_root / ".doc-kit"
        created = []

        for doc_type_key in doc_types:
            reg = Registry(kit_dir / "registry.yaml" if (kit_dir / "registry.yaml").exists() else None)
            doc_type_def = reg.get(doc_type_key)
            if not doc_type_def:
                continue
            target_path = resolve_path(project_docs, doc_type_def, module_name, feature_name)
            if target_path.exists():
                continue
            depends_on: list[dict] = []
            try:
                content = render_template(
                    doc_type_def.template, module_name, feature_name,
                    depends_on, now, kit_dir,
                )
            except FileNotFoundError:
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            created.append(target_path)

        if not created:
            return

        for target_path in created:
            rel_path = str(target_path.relative_to(self._project_root)).replace("\\", "/")
            meta, _ = FrontmatterParser.read_file(target_path)
            entry = IndexEntry(
                path=rel_path,
                doc_type=meta.get("doc_type", "unknown"),
                module=module_name,
                level=meta.get("level", "feature"),
                version=str(meta.get("version", "0.1.0")),
                status=meta.get("status", "active"),
                depends_on=meta.get("depends_on", []),
            )
            self._index.add_entry(entry)
        self._index.save()

        self._reload_all_panels()
        QMessageBox.information(
            self, "功能创建完成",
            f"功能「{feature_name}」已创建于模块 {module_name}\n文档: {len(created)} 个",
        )

    def _on_new_doc(self):
        """打开新建文档对话框（智能模式）。"""
        if not self._project_root or not self._index:
            QMessageBox.information(self, "提示", "请先打开一个项目")
            return
        from src.app.dialogs.new_doc import NewDocDialog
        from src.app.engine.registry import Registry

        kit_dir = self._project_root / ".doc-kit"
        reg_path = kit_dir / "registry.yaml"
        reg = Registry(reg_path) if reg_path.exists() else Registry()

        dlg = NewDocDialog(reg, self._project_root, self._index, parent=self)
        if dlg.exec():
            self._reload_all_panels()

    def _reload_all_panels(self):
        """刷新所有面板。"""
        if not self._project_root or not self._index:
            return
        self.doc_tree.load_project(self._project_root, self._index)
        self.dashboard.load_project(self._project_root, self._index)
        self.status.showMessage("面板已刷新", 3000)

    @Slot()
    def _on_sync(self):
        """执行索引同步 → 刷新所有面板。"""
        if not self._project_root or not self._index:
            return
        from src.app.engine.frontmatter import FrontmatterParser
        self._index.rebuild(self._project_root / "ProjectSpec")
        self._index.save()
        self.doc_tree.load_project(self._project_root, self._index)
        self.dashboard.load_project(self._project_root, self._index)
        self.status.showMessage("索引已同步", 3000)

    @Slot()
    def _on_check(self):
        """执行版本一致性检查 → 在状态栏显示结果。"""
        if not self._index:
            return
        from src.app.engine.deps import check_version_drift, check_deprecated_deps
        drifts = check_version_drift(self._index)
        deprecated = check_deprecated_deps(self._index)
        self.dashboard.show_check_results(drifts, deprecated)
        self.tabs.setCurrentWidget(self.dashboard)
        msg = f"检查完成: {len(drifts)} 个漂移, {len(deprecated)} 个废弃依赖"
        self.status.showMessage(msg, 5000)

    @Slot()
    def _on_global_search(self):
        """打开全局搜索对话框。"""
        if not self._project_root or not self._index:
            QMessageBox.information(self, "提示", "请先打开一个项目")
            return

        entries = self._index.list_entries()
        if not entries:
            QMessageBox.information(self, "全局搜索", "项目中没有文档")
            return

        dlg = GlobalSearchDialog(self._project_root, entries, self)
        dlg.navigate_to.connect(self._on_search_navigate)
        dlg.exec()

    @Slot(str, int)
    def _on_search_navigate(self, rel_path: str, line_number: int):
        """从全局搜索结果跳转到文档的指定行。"""
        if not self._project_root:
            return
        full_path = self._project_root / rel_path
        if not full_path.exists():
            QMessageBox.warning(self, "跳转失败", f"文件不存在: {rel_path}")
            return

        self._current_doc_rel = rel_path
        self.editor.open_document(full_path, rel_path, self._index, self._registry)
        self.editor.jump_to_line(line_number)
        self.tabs.setCurrentWidget(self.editor)

    @Slot()
    def _on_about(self):
        QMessageBox.about(
            self, "关于 doc_kit",
            "doc_kit v1.1.0\n\n"
            "面向AI时代的新型项目文档体系配套管理工具。\n\n"
            "版权所有 (C) 2026\n\n"
            "本软件采用 MIT 许可证授权。\n"
            "您可以自由使用、复制、修改、合并、发布、分发、\n"
            "授权和/或出售本软件的副本，前提是在所有副本中\n"
            "保留上述版权声明和本许可声明。"
        )

    def closeEvent(self, event):
        """关闭窗口时检查是否有未保存的修改。"""
        if not self._prompt_save():
            event.ignore()
            return
        event.accept()

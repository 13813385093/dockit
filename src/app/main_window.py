"""主窗口 — 协调侧边栏文档树、工具栏和主内容区切换。"""
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QSettings
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QStatusBar,
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTabWidget, QComboBox,
    QToolButton, QMenu,
)

from resources.icons import get_icon, set_button_icon
from src.app.doc_tree import DocTreePanel
from src.app.dashboard import DashboardPanel
from src.app.editor import DocEditor
from src.app.dep_graph import DepGraphPanel
from src.app.lifecycle import LifecyclePanel
from src.app.settings import SettingsPanel
from src.app.dialogs.init_dialog import InitDialog
from src.engine.index import IndexManager, IndexEntry
from src.engine.frontmatter import FrontmatterParser
from src.engine.commands.init_utils import init_project


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
        self.setWindowTitle("doc-kit UI")
        self.resize(1280, 800)

        # 当前项目状态
        self._project_root: Path | None = None
        self._index: IndexManager | None = None
        self._sidebar_visible = True

        # 最近项目列表持久化
        self._settings = QSettings("doc-kit", "doc-kit-ui")
        self._recent_projects: list[str] = self._settings.value("recent_projects", [], type=list)

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_status_bar()

    # ── UI 搭建 ──────────────────────────────────────────────

    def _setup_ui(self):
        """搭建主界面布局。"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 可拖拽分割器（侧栏 + 主区域）
        self._splitter = QSplitter(Qt.Horizontal)

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
        self.dep_graph = DepGraphPanel(self)
        self.lifecycle = LifecyclePanel(self)
        self.settings = SettingsPanel(self)

        self.tabs.addTab(self.dashboard, get_icon("grid"), "仪表盘")
        self.tabs.addTab(self.editor, get_icon("edit"), "编辑器")
        self.tabs.addTab(self.dep_graph, get_icon("graph"), "依赖图")
        self.tabs.addTab(self.lifecycle, get_icon("refresh"), "生命周期")
        self.tabs.addTab(self.settings, get_icon("gear"), "设置")
        self._splitter.addWidget(self.tabs)

        # 编辑器保存后 → 自动 check + 刷新仪表盘
        self.editor.document_saved.connect(self._on_doc_saved)

        self._splitter.setSizes([280, 1000])
        layout.addWidget(self._splitter, 1)

    def _toggle_sidebar(self):
        """切换侧栏显示/隐藏。"""
        self._sidebar_visible = not self._sidebar_visible
        self.doc_tree.setVisible(self._sidebar_visible)
        self._sidebar_btn.setIcon(get_icon("sidebar-hidden" if not self._sidebar_visible else "sidebar-visible"))
        self._sidebar_btn.setToolTip("显示侧栏" if not self._sidebar_visible else "隐藏侧栏")

    def _setup_toolbar(self):
        """搭建全局工具栏 — 侧栏切换 + 最近项目 + 快捷操作。"""
        toolbar = self.addToolBar("全局工具栏")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background: #f5f5f5;
                border-bottom: 1px solid #d0d0d0;
                padding: 2px 4px;
                spacing: 6px;
            }
            QToolButton {
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QToolButton:hover {
                background: #e0e0e0;
                border-color: #c0c0c0;
            }
            QToolButton:checked {
                background: #d0d0d0;
                border-color: #a0a0a0;
            }
            QComboBox {
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                padding: 3px 6px;
                background: white;
                min-width: 200px;
            }
            QLabel {
                color: #555;
                font-size: 12px;
            }
        """)

        # 侧栏切换按钮
        self._sidebar_btn = QToolButton()
        self._sidebar_btn.setCheckable(True)
        self._sidebar_btn.setChecked(True)
        self._sidebar_btn.setIcon(get_icon("sidebar-visible"))
        self._sidebar_btn.setToolTip("隐藏侧栏")
        self._sidebar_btn.clicked.connect(self._toggle_sidebar)
        toolbar.addWidget(self._sidebar_btn)

        # 分隔线
        sep = QLabel("|")
        sep.setStyleSheet("color: #ccc; padding: 0 2px;")
        toolbar.addWidget(sep)

        # 最近项目
        label = QLabel("  最近项目 ")
        toolbar.addWidget(label)

        self._recent_combo = QComboBox()
        self._recent_combo.setMinimumWidth(250)
        self._recent_combo.setPlaceholderText("选择最近打开的项目...")
        self._recent_combo.currentIndexChanged.connect(self._on_recent_selected)
        self._refresh_recent_combo()
        toolbar.addWidget(self._recent_combo)

        toolbar.addSeparator()

        # 新建下拉菜单
        self._new_btn = QToolButton()
        self._new_btn.setText(" 新建 ")
        self._new_btn.setIcon(get_icon("plus"))
        self._new_btn.setToolTip("新建文档、模块或功能")
        self._new_btn.setPopupMode(QToolButton.InstantPopup)
        new_menu = QMenu(self)
        act_module = new_menu.addAction(" 新建模块...")
        act_module.setIcon(get_icon("module"))
        act_module.triggered.connect(self._on_new_module)
        act_feature = new_menu.addAction(" 新建功能...")
        act_feature.setIcon(get_icon("plus"))
        act_feature.triggered.connect(self._on_new_feature)
        new_menu.addSeparator()
        act_doc = new_menu.addAction(" 新建文档...")
        act_doc.setIcon(get_icon("file"))
        act_doc.triggered.connect(self._on_new_doc)
        self._new_btn.setMenu(new_menu)
        toolbar.addWidget(self._new_btn)

        toolbar.addSeparator()

        # 快捷操作
        self._sync_btn = QToolButton()
        self._sync_btn.setIcon(get_icon("refresh"))
        self._sync_btn.setToolTip("同步索引")
        self._sync_btn.clicked.connect(self._on_sync)
        toolbar.addWidget(self._sync_btn)

        self._check_btn = QToolButton()
        self._check_btn.setIcon(get_icon("check"))
        self._check_btn.setToolTip("运行检查")
        self._check_btn.clicked.connect(self._on_check)
        toolbar.addWidget(self._check_btn)

    def _refresh_recent_combo(self):
        """刷新最近项目下拉列表。"""
        self._recent_combo.blockSignals(True)
        self._recent_combo.clear()
        for path in self._recent_projects:
            name = Path(path).name
            self._recent_combo.addItem(get_icon("folder"), f"  {name}", path)
        self._recent_combo.blockSignals(False)

    def _save_recent_projects(self):
        """持久化最近项目列表。"""
        self._settings.setValue("recent_projects", self._recent_projects)

    def _push_recent_project(self, project_root: Path):
        """将项目推入最近列表首位（去重，上限 MAX_RECENT）。"""
        path_str = str(project_root.resolve())
        self._recent_projects = [p for p in self._recent_projects if p != path_str]
        self._recent_projects.insert(0, path_str)
        self._recent_projects = self._recent_projects[:self.MAX_RECENT]
        self._save_recent_projects()
        self._refresh_recent_combo()

    @Slot(int)
    def _on_recent_selected(self, index: int):
        """从最近列表选择项目 → 加载。"""
        if index < 0:
            return
        path_str = self._recent_combo.itemData(index)
        if not path_str:
            return
        project_root = Path(path_str)
        if not project_root.exists():
            QMessageBox.warning(self, "项目不存在", f"目录已移动或删除:\n{project_root}")
            self._recent_projects.pop(index)
            self._save_recent_projects()
            self._refresh_recent_combo()
            return
        self.load_project(project_root)

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
        about_act = QAction("关于 doc-kit UI", self)
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
                    profile=dlg.profile,
                )
                QMessageBox.information(
                    self, "初始化完成",
                    f"项目「{name}」文档骨架已创建。\n"
                    f"模式: {dlg.profile}\n"
                    f"路径: {project_root / 'ProjectSpec'}",
                )
            except Exception as e:
                QMessageBox.critical(self, "初始化失败", str(e))
                return

        self.load_project(project_root)

    def load_project(self, project_root: Path):
        """加载指定项目。"""
        kit_dir = project_root / ".doc-kit"
        if not kit_dir.exists():
            QMessageBox.warning(self, "无效项目", f"未找到 .doc-kit/ 目录: {project_root}")
            return

        self._push_recent_project(project_root)

        self._project_root = project_root
        index_path = kit_dir / "index.json"
        self._index = IndexManager(index_path)

        self.doc_tree.load_project(project_root, self._index)
        self.dashboard.load_project(project_root, self._index)
        self.dep_graph.load_project(project_root, self._index)
        self.lifecycle.load_project(project_root, self._index)
        self.settings.load_project(project_root, self._index)

        self.tabs.setCurrentWidget(self.dashboard)
        self.status.showMessage(f"已加载项目: {project_root.name}")

    @Slot()
    def _on_doc_selected(self, rel_path: str):
        """文档树中选择文档 → 在编辑器中打开。"""
        if not self._project_root or not self._index:
            return
        full_path = self._project_root / rel_path
        if full_path.exists():
            self.editor.open_document(full_path, rel_path, self._index)
            self.tabs.setCurrentWidget(self.editor)

    @Slot()
    def _on_doc_saved(self, rel_path: str):
        """文档保存后：同步索引 → 运行 check → 留在编辑器，状态栏显示结果。"""
        if not self._project_root or not self._index:
            return
        from src.engine.deps import check_version_drift, check_deprecated_deps

        self._index.rebuild(self._project_root / "ProjectSpec")
        self._index.save()

        drifts = check_version_drift(self._index)
        deprecated = check_deprecated_deps(self._index)
        self.dashboard.show_check_results(drifts, deprecated)

        self.status.showMessage(
            f"已保存 {rel_path} — 检查: {len(drifts)} 个漂移, {len(deprecated)} 个废弃依赖",
            5000,
        )

    # ── 新建功能 ────────────────────────────────────────────

    def _on_new_module(self):
        """打开新建模块对话框。"""
        if not self._project_root or not self._index:
            QMessageBox.information(self, "提示", "请先打开一个项目")
            return
        from src.app.dialogs.new_module_dialog import NewModuleDialog
        from src.engine.deps import derive_initial_depends_on
        from src.engine.commands.new_utils import render_template, resolve_path
        from src.engine.registry import Registry
        from src.engine.index import IndexEntry

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
            depends_on = derive_initial_depends_on(
                doc_type_def, module_path, self._index, project_docs
            )
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
                mtime=now,
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
        from src.engine.deps import derive_initial_depends_on
        from src.engine.commands.new_utils import render_template, resolve_path
        from src.engine.registry import Registry
        from src.engine.index import IndexEntry

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
            depends_on = derive_initial_depends_on(
                doc_type_def, module_name, self._index, project_docs
            )
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
                mtime=now,
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
        from src.engine.registry import Registry

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
        from src.engine.frontmatter import FrontmatterParser
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
        from src.engine.deps import check_version_drift, check_deprecated_deps
        drifts = check_version_drift(self._index)
        deprecated = check_deprecated_deps(self._index)
        self.dashboard.show_check_results(drifts, deprecated)
        self.tabs.setCurrentWidget(self.dashboard)
        msg = f"检查完成: {len(drifts)} 个漂移, {len(deprecated)} 个废弃依赖"
        self.status.showMessage(msg, 5000)

    @Slot()
    def _on_about(self):
        QMessageBox.about(
            self, "关于 doc-kit UI",
            "doc-kit UI v0.1.0\n\n"
            "面向AI时代的新型项目文档体系配套管理工具。\n"
            "基于 PySide6 构建。"
        )

"""文档树面板 — 左侧导航，展示 ProjectSpec/ 的层级结构。"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget,
    QVBoxLayout, QLabel, QMenu, QMessageBox,
)

from resources.icons import get_icon
from src.engine.index import IndexManager, IndexEntry
from src.engine.registry import Registry
from src.engine.frontmatter import FrontmatterParser
from src.engine.commands.new_utils import render_template, resolve_path


class DocTreePanel(QWidget):
    """左侧文档树。

    信号:
        document_selected(str): 用户点击某文档时发射，参数为 project-root-relative 路径。
    """
    document_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_root: Path | None = None
        self._index: IndexManager | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        label = QLabel(" 文档导航")
        label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

    def load_project(self, project_root: Path, index: IndexManager):
        """从 index 重建文档树。"""
        self._project_root = project_root
        self._index = index
        self.tree.clear()

        entries = index.list_entries()
        entries.sort(key=lambda e: e.path)

        # 按模块分组
        modules: dict[str, list] = {}
        for e in entries:
            modules.setdefault(e.module, []).append(e)

        # 顶层文档
        if "project-charter" in modules:
            charter_item = QTreeWidgetItem(self.tree, ["顶层文档"])
            charter_item.setIcon(0, get_icon("folder"))
            charter_item.setFlags(charter_item.flags() & ~Qt.ItemIsSelectable)
            for e in modules["project-charter"]:
                self._add_file_item(charter_item, e)

        # 模块节点
        for mod_name in sorted(modules.keys()):
            if mod_name == "project-charter":
                continue
            item_text = mod_name
            mod_item = QTreeWidgetItem(self.tree, [item_text])
            mod_item.setIcon(0, get_icon("module"))
            mod_item.setFlags(mod_item.flags() & ~Qt.ItemIsSelectable)

            # 将条目分为模块级文件和功能级文件
            module_files = []
            features: dict[str, list] = {}  # feature_name → [entries]

            for e in modules[mod_name]:
                path_str = e.path
                # 判断是否在 features/ 下
                if "/features/" in path_str:
                    # 提取功能名: .../features/{feat-name}/xxx.md
                    parts = path_str.split("/features/")
                    if len(parts) >= 2:
                        feat_parts = parts[1].split("/")
                        feat_name = feat_parts[0]
                        features.setdefault(feat_name, []).append(e)
                else:
                    module_files.append(e)

            # 模块级文件
            for e in module_files:
                self._add_file_item(mod_item, e)

            # features/ 子目录
            if features:
                feat_folder = QTreeWidgetItem(mod_item, ["features"])
                feat_folder.setIcon(0, get_icon("folder"))
                feat_folder.setFlags(feat_folder.flags() & ~Qt.ItemIsSelectable)

                for feat_name in sorted(features.keys()):
                    feat_item = QTreeWidgetItem(feat_folder, [feat_name])
                    feat_item.setIcon(0, get_icon("module"))
                    feat_item.setFlags(feat_item.flags() & ~Qt.ItemIsSelectable)
                    for e in features[feat_name]:
                        self._add_file_item(feat_item, e)
                    feat_item.setExpanded(True)

                feat_folder.setExpanded(True)

            self.tree.expandItem(mod_item)

    def _add_file_item(self, parent: QTreeWidgetItem, entry):
        """在树节点下添加一个文档文件项。"""
        label = Path(entry.path).name
        item = QTreeWidgetItem(parent, [label])
        item.setIcon(0, get_icon("file"))
        item.setData(0, Qt.UserRole, entry.path)

        if entry.status == "deprecated":
            item.setForeground(0, Qt.gray)
            item.setIcon(0, get_icon("warning"))
        elif entry.status == "archived":
            item.setForeground(0, Qt.lightGray)
            item.setIcon(0, get_icon("archive"))

    def _on_item_clicked(self, item, column):
        """单击展开/收起文件夹，单击文件打开文档。"""
        path = item.data(0, Qt.UserRole)
        if path:
            self.document_selected.emit(path)
        else:
            # 文件夹/模块节点 → 切换展开/收起
            item.setExpanded(not item.isExpanded())

    def _on_context_menu(self, pos):
        """右键菜单：新建文档 / 新建功能 / 新建模块 / 废弃 …"""
        item = self.tree.itemAt(pos)
        # 获取右键位置的上下文路径（用于新建文档时预选）
        context_path = item.data(0, Qt.UserRole) if item else None

        menu = QMenu(self)

        new_doc = menu.addAction(" 新建文档...")
        new_doc.setIcon(get_icon("file"))
        new_feat = menu.addAction(" 新建功能...")
        new_feat.setIcon(get_icon("plus"))
        new_mod = menu.addAction(" 新建模块...")
        new_mod.setIcon(get_icon("module"))
        menu.addSeparator()

        if context_path:
            deprecate = menu.addAction(" 废弃此文档")
            deprecate.setIcon(get_icon("warning"))
            deprecate.triggered.connect(lambda: self._deprecate_doc(item))
            archive = menu.addAction(" 归档此文档")
            archive.setIcon(get_icon("archive"))
            archive.triggered.connect(lambda: self._archive_doc(item))

        new_doc.triggered.connect(lambda: self._on_new_doc(context_path))
        new_feat.triggered.connect(self._on_new_feature)
        new_mod.triggered.connect(self._on_new_module)
        menu.exec(self.tree.mapToGlobal(pos))

    def _on_new_doc(self, context_path: str | None = None):
        """打开新建文档对话框（智能模式），传递右键上下文路径。"""
        if not self._project_root or not self._index:
            return
        from src.app.dialogs.new_doc import NewDocDialog
        from src.engine.registry import Registry

        kit_dir = self._project_root / ".doc-kit"
        reg_path = kit_dir / "registry.yaml"
        reg = Registry(reg_path) if reg_path.exists() else Registry()

        dlg = NewDocDialog(reg, self._project_root, self._index,
                           context_path=context_path, parent=self)
        if dlg.exec():
            self.load_project(self._project_root, self._index)

    def _on_new_feature(self):
        """打开新建功能对话框。"""
        if not self._project_root or not self._index:
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

        self.load_project(self._project_root, self._index)
        QMessageBox.information(
            self, "功能创建完成",
            f"功能「{feature_name}」已创建于模块 {module_name}",
        )

    def _on_new_module(self):
        """新建模块：弹出对话框 → 创建文档骨架 → 刷新树。"""
        if not self._project_root or not self._index:
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

        self.load_project(self._project_root, self._index)
        QMessageBox.information(
            self, "模块创建完成",
            f"模块「{module_path}」已创建\n文档: {len(created)} 个",
        )

    def _deprecate_doc(self, item):
        path = item.data(0, Qt.UserRole)
        if not path or not self._project_root:
            return
        QMessageBox.information(self, "废弃文档", f"废弃: {path}\n此功能待实现")

    def _archive_doc(self, item):
        path = item.data(0, Qt.UserRole)
        if not path or not self._project_root:
            return
        QMessageBox.information(self, "归档文档", f"归档: {path}\n此功能待实现")

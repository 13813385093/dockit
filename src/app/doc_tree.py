"""文档树面板 — 左侧导航，展示 ProjectSpec/ 的层级结构。"""
from pathlib import Path
import os
import shutil
import subprocess
import sys

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QInputDialog, QToolButton,
)

from src.app.icon_utils import get_icon
from src.app.engine.index import IndexManager, IndexEntry
from src.app.engine.registry import Registry
from src.app.engine.frontmatter import FrontmatterParser
from src.app.engine.commands.new_utils import render_template, resolve_path
from src.app.engine.validation import parse_module_path

# 树节点角色常量（存储在 Qt.UserRole + 1）
_NODE_FILE = "file"
_NODE_MODULE = "module"
_NODE_PROJECT_SPEC = "project_spec"
_NODE_FEATURES_FOLDER = "features_folder"
_NODE_FEATURE = "feature"
_NODE_EXT_DIR = "ext_dir"
_NODE_EXT_FILE = "ext_file"


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
        self._registry: Registry | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(" 文档导航")
        title_layout.addWidget(label)
        title_layout.addStretch()

        refresh_btn = QToolButton()
        refresh_btn.setIcon(get_icon("refresh-cw"))
        refresh_btn.setToolTip("刷新文档树")
        refresh_btn.clicked.connect(self._refresh_tree)
        title_layout.addWidget(refresh_btn)

        collapse_btn = QToolButton()
        collapse_btn.setIcon(get_icon("folder-minus"))
        collapse_btn.setToolTip("折叠所有节点")
        collapse_btn.clicked.connect(self._collapse_all)
        title_layout.addWidget(collapse_btn)

        layout.addLayout(title_layout)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

    def _refresh_tree(self):
        """刷新文档树 — 重新扫描 ProjectSpec 同步 index，再重建树。"""
        if self._project_root and self._index:
            self._index.rebuild(self._project_root / "ProjectSpec")
            self._index.save()
            self.load_project(self._project_root, self._index)

    def _collapse_all(self):
        """折叠所有树节点。"""
        self.tree.collapseAll()

    def load_project(self, project_root: Path, index: IndexManager):
        """从 index 重建文档树。"""
        self._project_root = project_root
        self._index = index
        kit_dir = project_root / ".doc-kit"
        reg_path = kit_dir / "registry.yaml"
        self._registry = Registry(reg_path) if reg_path.exists() else Registry()
        self.tree.clear()

        entries = index.list_entries()
        entries.sort(key=lambda e: e.path)

        # 按模块分组
        modules: dict[str, list] = {}
        for e in entries:
            modules.setdefault(e.module, []).append(e)

        # 顶层文件夹：ProjectSpec/（与磁盘目录层级一致，容纳全部文档）
        ps_item = QTreeWidgetItem(self.tree, ["ProjectSpec"])
        ps_item.setIcon(0, get_icon("folder"))
        ps_item.setFlags(ps_item.flags() & ~Qt.ItemIsSelectable)
        ps_item.setData(0, Qt.UserRole + 1, _NODE_PROJECT_SPEC)
        ps_item.setExpanded(True)

        # 顶层文档（frontmatter module=project-charter，磁盘上无此目录层级）
        # 直接平铺在 ProjectSpec 文件夹下。
        for e in modules.get("project-charter", []):
            self._add_file_item(ps_item, e)

        # 外部目录（SessionSpec/ ReviewSpec/）：镜像磁盘结构，仅展示
        for ext_name in ("SessionSpec", "ReviewSpec"):
            ext_item = QTreeWidgetItem(self.tree, [ext_name])
            ext_item.setIcon(0, get_icon("folder"))
            ext_item.setFlags(ext_item.flags() & ~Qt.ItemIsSelectable)
            ext_item.setData(0, Qt.UserRole + 1, _NODE_EXT_DIR)
            ext_item.setExpanded(True)
            self._mirror_disk_dir(ext_item, project_root / ext_name)

        # 模块节点
        for mod_name in sorted(modules.keys()):
            if mod_name == "project-charter":
                continue
            item_text = mod_name
            # 子模块（带点号）→ 创建嵌套节点
            if "." in mod_name:
                main_module, sub_path = parse_module_path(mod_name)
                sub_name = sub_path.split("/")[-1] if sub_path else mod_name
                # 查找或创建父模块节点（在 ProjectSpec 文件夹下）
                parent_item = None
                for i in range(ps_item.childCount()):
                    child = ps_item.child(i)
                    if child.text(0) == main_module:
                        parent_item = child
                        break
                if parent_item is None:
                    parent_item = QTreeWidgetItem(ps_item, [main_module])
                    parent_item.setIcon(0, get_icon("grid"))
                    parent_item.setFlags(parent_item.flags() & ~Qt.ItemIsSelectable)
                    parent_item.setData(0, Qt.UserRole + 1, _NODE_MODULE)
                    parent_item.setData(0, Qt.UserRole + 2, main_module)
                mod_item = QTreeWidgetItem(parent_item, [sub_name])
            else:
                mod_item = QTreeWidgetItem(ps_item, [item_text])
            mod_item.setIcon(0, get_icon("grid"))
            mod_item.setFlags(mod_item.flags() & ~Qt.ItemIsSelectable)
            mod_item.setData(0, Qt.UserRole + 1, _NODE_MODULE)
            mod_item.setData(0, Qt.UserRole + 2, mod_name)

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
                feat_folder.setData(0, Qt.UserRole + 1, _NODE_FEATURES_FOLDER)

                for feat_name in sorted(features.keys()):
                    feat_item = QTreeWidgetItem(feat_folder, [feat_name])
                    feat_item.setIcon(0, get_icon("module"))
                    feat_item.setFlags(feat_item.flags() & ~Qt.ItemIsSelectable)
                    feat_item.setData(0, Qt.UserRole + 1, _NODE_FEATURE)
                    for e in features[feat_name]:
                        self._add_file_item(feat_item, e)
                    feat_item.setExpanded(True)

                feat_folder.setExpanded(True)

            self.tree.expandItem(mod_item)

    def _mirror_disk_dir(self, parent_item: QTreeWidgetItem, disk_dir: Path):
        """将磁盘目录结构镜像到树节点下（SessionSpec/ReviewSpec 等，仅展示）。"""
        if not disk_dir.exists():
            return
        for child in sorted(disk_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if child.is_dir():
                dir_item = QTreeWidgetItem(parent_item, [child.name])
                dir_item.setIcon(0, get_icon("folder"))
                dir_item.setFlags(dir_item.flags() & ~Qt.ItemIsSelectable)
                dir_item.setData(0, Qt.UserRole + 1, _NODE_EXT_DIR)
                self._mirror_disk_dir(dir_item, child)
            else:
                rel = str(child.relative_to(self._project_root)).replace("\\", "/")
                item = QTreeWidgetItem(parent_item, [child.name])
                item.setIcon(0, get_icon("file"))
                item.setData(0, Qt.UserRole, rel)
                item.setData(0, Qt.UserRole + 1, _NODE_EXT_FILE)

    def _add_file_item(self, parent: QTreeWidgetItem, entry):
        """在树节点下添加一个文档文件项。"""
        if self._registry:
            doc_def = self._registry.get(entry.doc_type)
            label = doc_def.description if doc_def else Path(entry.path).name
        else:
            label = Path(entry.path).name
        item = QTreeWidgetItem(parent, [label])
        item.setData(0, Qt.UserRole, entry.path)
        item.setData(0, Qt.UserRole + 1, _NODE_FILE)

        if entry.status == "active":
            item.setIcon(0, get_icon("file-text"))
        elif entry.status == "invalid":
            item.setIcon(0, get_icon("file"))
        elif entry.status == "deprecated":
            item.setForeground(0, Qt.gray)
            item.setIcon(0, get_icon("warning"))
        elif entry.status == "archived":
            item.setForeground(0, Qt.lightGray)
            item.setIcon(0, get_icon("archive"))
        else:
            item.setIcon(0, get_icon("file"))

    def _on_item_clicked(self, item, column):
        """单击展开/收起文件夹；单击文档/外部文件打开。"""
        node_type = item.data(0, Qt.UserRole + 1)
        path = item.data(0, Qt.UserRole)
        if node_type in (_NODE_FILE, _NODE_EXT_FILE) and path:
            self.document_selected.emit(path)
        else:
            # 文件夹/模块/外部目录节点 → 切换展开/收起
            item.setExpanded(not item.isExpanded())

    def _on_context_menu(self, pos):
        """右键菜单 — 根据节点类型动态显示。"""
        item = self.tree.itemAt(pos)
        if not item:
            # 树空白区域右键 → 提供顶层文档/模块新建入口
            menu = QMenu(self)
            new_doc = menu.addAction(" 新建顶层文档...")
            new_doc.setIcon(get_icon("file"))
            new_doc.triggered.connect(lambda: self._on_new_doc(preset_level="top"))
            new_mod = menu.addAction(" 新建模块...")
            new_mod.setIcon(get_icon("module"))
            new_mod.triggered.connect(lambda: self._on_new_module(disable_sub_check=True))
            menu.exec(self.tree.mapToGlobal(pos))
            return

        context_path = item.data(0, Qt.UserRole)
        path = item.data(0, Qt.UserRole)  # None for folder/module nodes

        # 通过节点角色判断类型（建树时已通过 setData 标记）
        node_type = item.data(0, Qt.UserRole + 1)
        is_file_node = (node_type == _NODE_FILE)
        is_module_node = (node_type == _NODE_MODULE)
        is_feature_node = (node_type == _NODE_FEATURE)
        is_project_spec = (node_type == _NODE_PROJECT_SPEC)
        is_features_folder = (node_type == _NODE_FEATURES_FOLDER)
        is_ext_dir = (node_type == _NODE_EXT_DIR)
        is_ext_file = (node_type == _NODE_EXT_FILE)

        if is_ext_dir:
            # 外部目录（SessionSpec/ReviewSpec）无操作
            return

        # 提取模块/功能名（从存储的数据取，避免 text 推断）
        module_name = (
            item.data(0, Qt.UserRole + 2)  # 模块节点：直接存储了模块名
            if is_module_node
            else item.parent().data(0, Qt.UserRole + 2)  # features 文件夹：从模块父节点获取
            if is_features_folder
            else item.parent().parent().data(0, Qt.UserRole + 2)  # 功能节点：从模块祖父节点获取
            if is_feature_node
            else None
        )
        feature_name = item.text(0) if is_feature_node else None

        menu = QMenu(self)

        # ── 新建文档 ──
        if is_project_spec:
            new_doc = menu.addAction(" 新建顶层文档...")
            new_doc.setIcon(get_icon("file"))
            new_doc.triggered.connect(lambda: self._on_new_doc(preset_level="top"))
            new_mod = menu.addAction(" 新建模块...")
            new_mod.setIcon(get_icon("module"))
            new_mod.triggered.connect(lambda: self._on_new_module(disable_sub_check=True))
            menu.addSeparator()

        elif is_module_node:
            new_doc = menu.addAction(" 新建文档...")
            new_doc.setIcon(get_icon("file"))
            new_doc.triggered.connect(
                lambda checked, m=module_name: self._on_new_doc(preset_level="module", preset_module=m))

            new_feat = menu.addAction(" 新建功能...")
            new_feat.setIcon(get_icon("plus"))
            new_feat.triggered.connect(
                lambda checked, m=module_name: self._on_new_feature(preset_module=m))

            new_mod = menu.addAction(" 新建模块...")
            new_mod.setIcon(get_icon("module"))
            new_mod.triggered.connect(
                lambda checked, m=module_name: self._on_new_module(preset_parent=m))
            menu.addSeparator()

        elif is_features_folder:
            new_doc = menu.addAction(" 新建文档")
            new_doc.setIcon(get_icon("file"))
            new_doc.setEnabled(False)
            new_feat = menu.addAction(" 新建功能...")
            new_feat.setIcon(get_icon("plus"))
            new_feat.triggered.connect(
                lambda checked, m=module_name: self._on_new_feature(preset_module=m))
            new_mod = menu.addAction(" 新建模块")
            new_mod.setIcon(get_icon("module"))
            new_mod.setEnabled(False)
            menu.addSeparator()

        elif is_feature_node:
            new_doc = menu.addAction(" 新建文档...")
            new_doc.setIcon(get_icon("file"))
            new_doc.triggered.connect(
                lambda checked, m=module_name, f=feature_name: self._on_new_doc(
                    preset_level="feature", preset_module=m, preset_feature=f))

            new_feat = menu.addAction(" 新建功能")
            new_feat.setIcon(get_icon("plus"))
            new_feat.setEnabled(False)
            new_mod = menu.addAction(" 新建模块")
            new_mod.setIcon(get_icon("module"))
            new_mod.setEnabled(False)
            menu.addSeparator()

        # ── 重命名 / 删除（模块和功能节点） ──
        if is_module_node or is_feature_node:
            rename = menu.addAction(" 重命名")
            rename.setIcon(get_icon("edit"))
            delete = menu.addAction(" 删除")
            delete.setIcon(get_icon("trash"))

            if is_module_node:
                rename.triggered.connect(lambda: self._rename_module(item))
                delete.triggered.connect(lambda: self._delete_module(item))
            else:
                rename.triggered.connect(lambda: self._rename_feature(item))
                delete.triggered.connect(lambda: self._delete_feature(item))

            menu.addSeparator()

        # ── 外部目录文件（SessionSpec/ReviewSpec 等） ──
        if is_ext_file:
            full_path = self._project_root / path
            explorer_act = menu.addAction(" 在资源管理中显示")
            explorer_act.setIcon(get_icon("folder"))
            explorer_act.triggered.connect(lambda: self._show_in_explorer(full_path))
            copy_act = menu.addAction(" 复制绝对路径")
            copy_act.setIcon(get_icon("copy"))
            copy_act.triggered.connect(lambda: self._copy_path(full_path))

        # ── 文件操作 ──
        if is_file_node:
            full_path = self._project_root / path

            open_act = menu.addAction(" 打开文件")
            open_act.setIcon(get_icon("edit"))
            open_act.triggered.connect(lambda: self.document_selected.emit(path))

            explorer_act = menu.addAction(" 在资源管理中显示")
            explorer_act.setIcon(get_icon("folder"))
            explorer_act.triggered.connect(lambda: self._show_in_explorer(full_path))

            copy_act = menu.addAction(" 复制绝对路径")
            copy_act.setIcon(get_icon("copy"))
            copy_act.triggered.connect(lambda: self._copy_path(full_path))

            menu.addSeparator()

            # 启用/不启用切换（仅 active/invalid 状态可用）
            entry = self._index.get_entry(path) if self._index else None
            current_status = entry.status if entry else ""
            if current_status == "active":
                toggle_label = " 不启用此文档"
                toggle_icon = get_icon("zap-off")
                toggle_enabled = True
            elif current_status == "invalid":
                toggle_label = " 启用此文档"
                toggle_icon = get_icon("zap")
                toggle_enabled = True
            else:
                toggle_label = " 启用/不启用此文档"
                toggle_icon = get_icon("zap")
                toggle_enabled = False
            toggle_act = menu.addAction(toggle_icon, toggle_label)
            toggle_act.setEnabled(toggle_enabled)
            toggle_act.triggered.connect(lambda: self._toggle_enable_doc(item))

            deprecate = menu.addAction(" 废弃此文档")
            deprecate.setIcon(get_icon("warning"))
            deprecate.triggered.connect(lambda: self._deprecate_doc(item))
            archive = menu.addAction(" 归档此文档")
            archive.setIcon(get_icon("archive"))
            archive.triggered.connect(lambda: self._archive_doc(item))

        menu.exec(self.tree.mapToGlobal(pos))

    def _get_module_path(self, module_name: str) -> Path:
        """获取模块文件夹路径（支持子模块名如 Evaluate.Sybase）。"""
        main_module, sub_path = parse_module_path(module_name)
        path = self._project_root / "ProjectSpec" / f"module-{main_module}"
        if sub_path:
            path = path / sub_path
        return path.resolve()

    def _get_feature_path(self, module_name: str, feature_name: str) -> Path:
        """获取功能文件夹路径。"""
        return (self._project_root / "ProjectSpec" / module_name / "features" / feature_name).resolve()

    def _rename_module(self, item):
        """重命名模块：重命名文件夹 + 更新 index。"""
        if not self._project_root or not self._index:
            return
        old_name = item.data(0, Qt.UserRole + 2) or item.text(0)
        new_name, ok = QInputDialog.getText(self, "重命名模块", "新名称:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        old_path = self._get_module_path(old_name)
        new_path = self._get_module_path(new_name)
        if new_path.exists():
            QMessageBox.warning(self, "错误", f"模块「{new_name}」已存在")
            return

        try:
            old_path.rename(new_path)
        except OSError as e:
            QMessageBox.critical(self, "重命名失败", str(e))
            return

        # 更新 index 中所有相关条目的 path 和 module
        old_rel = str(old_path.relative_to(self._project_root)).replace("\\", "/")
        new_rel = str(new_path.relative_to(self._project_root)).replace("\\", "/")
        for entry in self._index.list_entries():
            if entry.path.startswith(old_rel + "/") or entry.path == old_rel:
                entry.path = entry.path.replace(old_rel, new_rel, 1)
            if entry.module == old_name:
                entry.module = new_name
        self._index.save()
        self.load_project(self._project_root, self._index)
        QMessageBox.information(self, "重命名完成", f"模块「{old_name}」已重命名为「{new_name}」")

    def _rename_feature(self, item):
        """重命名功能：重命名文件夹 + 更新 index。"""
        if not self._project_root or not self._index:
            return
        old_name = item.text(0)
        new_name, ok = QInputDialog.getText(self, "重命名功能", "新名称:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        # 从树结构中获取模块名
        feat_folder = item.parent()  # "features" 节点
        module_item = feat_folder.parent()  # 模块节点
        module_name = module_item.text(0)

        old_path = self._get_feature_path(module_name, old_name)
        new_path = self._get_feature_path(module_name, new_name)
        if new_path.exists():
            QMessageBox.warning(self, "错误", f"功能「{new_name}」已存在")
            return

        try:
            old_path.rename(new_path)
        except OSError as e:
            QMessageBox.critical(self, "重命名失败", str(e))
            return

        # 更新 index
        old_prefix = f"ProjectSpec/{module_name}/features/{old_name}"
        new_prefix = f"ProjectSpec/{module_name}/features/{new_name}"
        for entry in self._index.list_entries():
            if old_prefix in entry.path:
                entry.path = entry.path.replace(old_prefix, new_prefix, 1)
        self._index.save()
        self.load_project(self._project_root, self._index)
        QMessageBox.information(self, "重命名完成", f"功能「{old_name}」已重命名为「{new_name}」")

    def _delete_module(self, item):
        """删除模块：删除文件夹 + 清除 index。"""
        if not self._project_root or not self._index:
            return
        module_name = item.data(0, Qt.UserRole + 2) or item.text(0)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除模块「{module_name}」及其所有文档吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        module_path = self._get_module_path(module_name)
        try:
            shutil.rmtree(module_path)
        except OSError as e:
            QMessageBox.critical(self, "删除失败", str(e))
            return

        # 清除 index 中该模块的所有条目
        to_remove = [e.path for e in self._index.list_entries() if e.module == module_name]
        for p in to_remove:
            self._index.remove_entry(p)
        self._index.save()
        self.load_project(self._project_root, self._index)
        QMessageBox.information(self, "删除完成", f"模块「{module_name}」及其文档已删除")

    def _delete_feature(self, item):
        """删除功能：删除文件夹 + 清除 index。"""
        if not self._project_root or not self._index:
            return
        feature_name = item.text(0)
        feat_folder = item.parent()
        module_item = feat_folder.parent()
        module_name = module_item.text(0)

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除功能「{feature_name}」及其所有文档吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        feature_path = self._get_feature_path(module_name, feature_name)
        try:
            shutil.rmtree(feature_path)
        except OSError as e:
            QMessageBox.critical(self, "删除失败", str(e))
            return

        # 清除 index 中该功能的所有条目
        prefix = f"ProjectSpec/{module_name}/features/{feature_name}"
        to_remove = [e.path for e in self._index.list_entries() if e.path.startswith(prefix)]
        for p in to_remove:
            self._index.remove_entry(p)
        self._index.save()
        self.load_project(self._project_root, self._index)
        QMessageBox.information(self, "删除完成", f"功能「{feature_name}」及其文档已删除")

    def _open_file(self, path: Path):
        """用系统默认程序打开文件。"""
        resolved = str(path.resolve())
        if sys.platform == "win32":
            os.startfile(resolved)
        elif sys.platform == "darwin":
            subprocess.run(["open", resolved])
        else:
            subprocess.run(["xdg-open", resolved])

    def _show_in_explorer(self, path: Path):
        """在文件管理器中定位文件。"""
        resolved = path.resolve()
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(resolved)])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(resolved)])
        else:
            subprocess.run(["xdg-open", str(resolved.parent)])

    def _copy_path(self, path: Path):
        """复制文件绝对路径到剪贴板。"""
        QGuiApplication.clipboard().setText(str(path.resolve()))

    def _on_new_doc(self, context_path: str | None = None,
                    preset_level: str | None = None,
                    preset_module: str | None = None,
                    preset_feature: str | None = None):
        """打开新建文档对话框（智能模式），传递右键上下文路径。"""
        if not self._project_root or not self._index:
            return
        from src.app.dialogs.new_doc import NewDocDialog
        from src.app.engine.registry import Registry

        kit_dir = self._project_root / ".doc-kit"
        reg_path = kit_dir / "registry.yaml"
        reg = Registry(reg_path) if reg_path.exists() else Registry()

        dlg = NewDocDialog(reg, self._project_root, self._index,
                           context_path=context_path,
                           preset_level=preset_level,
                           preset_module=preset_module,
                           preset_feature=preset_feature,
                           parent=self)
        if dlg.exec():
            self.load_project(self._project_root, self._index)

    def _on_new_feature(self, preset_module: str | None = None):
        """打开新建功能对话框。"""
        if not self._project_root or not self._index:
            return
        from src.app.dialogs.new_feature_dialog import NewFeatureDialog
        from src.app.engine.commands.new_utils import render_template, resolve_path
        from src.app.engine.registry import Registry
        from src.app.engine.index import IndexEntry

        dlg = NewFeatureDialog(self._index, self, preset_module=preset_module)
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
                mtime=now,
            )
            self._index.add_entry(entry)
        self._index.save()

        self.load_project(self._project_root, self._index)
        QMessageBox.information(
            self, "功能创建完成",
            f"功能「{feature_name}」已创建于模块 {module_name}",
        )

    def _on_new_module(self, preset_parent: str | None = None,
                       disable_sub_check: bool = False,
                       preset_name: str | None = None):
        """新建模块：弹出对话框 → 创建文档骨架 → 刷新树。"""
        if not self._project_root or not self._index:
            return

        from src.app.dialogs.new_module_dialog import NewModuleDialog
        from src.app.engine.commands.new_utils import render_template, resolve_path
        from src.app.engine.registry import Registry
        from src.app.engine.index import IndexEntry

        dlg = NewModuleDialog(self._index, self,
                              preset_parent=preset_parent,
                              disable_sub_check=disable_sub_check,
                              preset_name=preset_name)
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

    def _toggle_enable_doc(self, item):
        """切换文档的启用/不启用状态（active ↔ invalid）。"""
        path = item.data(0, Qt.UserRole)
        if not path or not self._project_root or not self._index:
            return
        full_path = self._project_root / path
        entry = self._index.get_entry(path)
        if not entry:
            return

        # 切换状态
        new_status = "invalid" if entry.status == "active" else "active"

        # 修改 frontmatter 文件
        try:
            meta, body = FrontmatterParser.read_file(full_path)
            meta["status"] = new_status
            FrontmatterParser.write_file(full_path, meta, body)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法更新文件: {e}")
            return

        # 更新索引
        entry.status = new_status
        self._index.add_entry(entry)
        self._index.save()

        # 原地更新树节点图标（不重建整棵树，避免折叠）
        if new_status == "active":
            item.setIcon(0, get_icon("file-text"))
        elif new_status == "invalid":
            item.setIcon(0, get_icon("file"))
        # 清除 status 相关的前景色（deprecated/archived 才设前景色）
        item.setForeground(0, self.tree.palette().color(self.tree.foregroundRole()))

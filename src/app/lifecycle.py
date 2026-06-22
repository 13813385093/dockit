"""生命周期管理面板 — 文档废弃/归档/清理。"""
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton,
    QGroupBox, QMessageBox,
)

from resources.icons import set_button_icon
from src.engine.index import IndexManager
from src.engine.frontmatter import FrontmatterParser


class LifecyclePanel(QWidget):
    """生命周期管理。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_root: Path | None = None
        self._index: IndexManager | None = None

        layout = QVBoxLayout(self)

        title = QLabel("生命周期管理")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("管理文档的 active -> deprecated -> archived 生命周期转换。")
        hint.setStyleSheet("color: gray; margin-bottom: 8px;")
        layout.addWidget(hint)

        dep_group = QGroupBox("已废弃文档 (可归档)")
        dep_layout = QVBoxLayout(dep_group)
        self._dep_list = QListWidget()
        dep_layout.addWidget(self._dep_list)
        archive_btn = QPushButton(" 归档选中项")
        set_button_icon(archive_btn, "archive")
        archive_btn.clicked.connect(self._on_archive_selected)
        dep_layout.addWidget(archive_btn)
        layout.addWidget(dep_group)

        arch_group = QGroupBox("已归档")
        arch_layout = QVBoxLayout(arch_group)
        self._arch_list = QListWidget()
        arch_layout.addWidget(self._arch_list)
        layout.addWidget(arch_group)

    def load_project(self, project_root: Path, index: IndexManager):
        self._project_root = project_root
        self._index = index
        self._refresh()

    def _refresh(self):
        if not self._index:
            return
        self._dep_list.clear()
        self._arch_list.clear()
        for e in self._index.list_entries():
            if e.status == "deprecated":
                item = QListWidgetItem(e.path)
                item.setData(Qt.UserRole, e.path)
                self._dep_list.addItem(item)
            elif e.status == "archived":
                self._arch_list.addItem(e.path)

    @Slot()
    def _on_archive_selected(self):
        """将选中的已废弃文档 -> archived。"""
        if not self._project_root or not self._index:
            return
        selected = self._dep_list.selectedItems()
        if not selected:
            QMessageBox.information(self, "提示", "请先选择要归档的文档")
            return

        for item in selected:
            rel_path = item.data(Qt.UserRole)
            full_path = self._project_root / rel_path
            if not full_path.exists():
                continue
            try:
                meta, body = FrontmatterParser.read_file(full_path)
                meta["status"] = "archived"
                meta["archived_at"] = FrontmatterParser.now_iso()
                FrontmatterParser.write_file(full_path, meta, body)
                self._index.get_entry(rel_path).status = "archived"
            except Exception as e:
                QMessageBox.warning(self, "归档失败", f"{rel_path}: {e}")

        self._index.save()
        self._refresh()
        QMessageBox.information(self, "归档完成", f"已归档 {len(selected)} 篇文档")

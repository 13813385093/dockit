"""设置面板 — 项目信息、类型注册表、模板管理。"""
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QGroupBox,
    QPushButton, QFileDialog, QMessageBox,
    QHeaderView,
)

from src.app.engine.index import IndexManager
from src.app.engine.registry import Registry


class SettingsPanel(QWidget):
    """项目设置。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_root: Path | None = None
        self._index: IndexManager | None = None

        self._build_ui()
        # 无信号绑定

    # ── 布局搭建 ──────────────────────────────────────────
    def _build_ui(self):
        """搭建静态布局。"""
        layout = QVBoxLayout(self)

        title = QLabel("项目设置")
        layout.addWidget(title)

        info_group = QGroupBox("项目信息")
        info_layout = QVBoxLayout(info_group)
        self._project_name_label = QLabel("项目: (未加载)")
        self._project_path_label = QLabel("路径: (未加载)")
        info_layout.addWidget(self._project_name_label)
        info_layout.addWidget(self._project_path_label)
        layout.addWidget(info_group)

        reg_group = QGroupBox("文档类型注册表")
        reg_layout = QVBoxLayout(reg_group)
        self._registry_table = QTableWidget(0, 3)
        self._registry_table.setHorizontalHeaderLabels(["doc_type", "level", "template"])
        self._registry_table.horizontalHeader().setStretchLastSection(True)
        reg_layout.addWidget(self._registry_table)
        layout.addWidget(reg_group)

        layout.addStretch()

    def load_project(self, project_root: Path, index: IndexManager):
        self._project_root = project_root
        self._index = index
        self._project_name_label.setText(f"项目: {project_root.name}")
        self._project_path_label.setText(f"路径: {project_root}")

        reg_path = project_root / ".doc-kit" / "registry.yaml"
        if reg_path.exists():
            reg = Registry(reg_path)
        else:
            reg = Registry()
        all_types = reg.list_all()
        self._registry_table.setRowCount(len(all_types))
        for i, t in enumerate(all_types):
            self._registry_table.setItem(i, 0, QTableWidgetItem(t.doc_type))
            self._registry_table.setItem(i, 1, QTableWidgetItem(t.level))
            self._registry_table.setItem(i, 2, QTableWidgetItem(t.template))

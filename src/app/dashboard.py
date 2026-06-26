"""仪表盘面板 — 项目文档概览、版本漂移、健康状态。"""
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QListWidget, QListWidgetItem,
    QFrame, QPushButton,
)

from resources.icons import set_button_icon
from src.engine.index import IndexManager
from src.engine.deps import check_version_drift, check_deprecated_deps


class StatCard(QFrame):
    """统计卡片组件。"""
    def __init__(self, title: str, value: str, color: str = "#333", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        self._value = QLabel(value)
        self._value.setAlignment(Qt.AlignCenter)
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._value)
        layout.addWidget(title_label)


class DashboardPanel(QWidget):
    """项目仪表盘。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_root: Path | None = None
        self._index: IndexManager | None = None

        self._build_ui()
        self._connect_signals()

    # ── 布局搭建 ──────────────────────────────────────────
    def _build_ui(self):
        """搭建静态布局，不含信号绑定。"""
        layout = QVBoxLayout(self)

        dashboard_group = QGroupBox("项目仪表盘")
        self._stats_layout = QHBoxLayout(dashboard_group)
        layout.addWidget(dashboard_group)

        self._card_total = StatCard("文档总数", "—", "#4A90D9")
        self._card_active = StatCard("活跃", "—", "#27AE60")
        self._card_deprecated = StatCard("已废弃", "—", "#E67E22")
        self._card_archived = StatCard("已归档", "—", "#95A5A6")
        self._card_drifts = StatCard("版本漂移", "—", "#E74C3C")

        self._stats_layout.addWidget(self._card_total)
        self._stats_layout.addWidget(self._card_active)
        self._stats_layout.addWidget(self._card_deprecated)
        self._stats_layout.addWidget(self._card_archived)
        self._stats_layout.addWidget(self._card_drifts)

        check_group = QGroupBox("检查结果")
        check_layout = QVBoxLayout(check_group)
        self._drift_list = QListWidget()
        self._deprecated_list = QListWidget()
        check_layout.addWidget(QLabel("版本漂移:"))
        check_layout.addWidget(self._drift_list)
        check_layout.addWidget(QLabel("废弃依赖:"))
        check_layout.addWidget(self._deprecated_list)
        layout.addWidget(check_group)

        self._refresh_btn = QPushButton(" 重新检查")
        set_button_icon(self._refresh_btn, "refresh")
        layout.addWidget(self._refresh_btn)

        layout.addStretch()

    # ── 信号绑定 ──────────────────────────────────────────
    def _connect_signals(self):
        """绑定信号槽，不含布局代码。"""
        self._refresh_btn.clicked.connect(self._refresh)

    def load_project(self, project_root: Path, index: IndexManager):
        self._project_root = project_root
        self._index = index
        self._refresh()

    def _refresh(self):
        if not self._index:
            return
        entries = self._index.list_entries()
        total = len(entries)
        active = sum(1 for e in entries if e.status == "active")
        dep = sum(1 for e in entries if e.status == "deprecated")
        arch = sum(1 for e in entries if e.status == "archived")
        drifts = check_version_drift(self._index)

        self._card_total._value.setText(str(total))
        self._card_active._value.setText(str(active))
        self._card_deprecated._value.setText(str(dep))
        self._card_archived._value.setText(str(arch))
        self._card_drifts._value.setText(str(len(drifts)))

        self._drift_list.clear()
        for d in drifts:
            item = QListWidgetItem(f"{d['doc']} -> {d['dep_name']} v{d['declared']} (实际 v{d['actual']})")
            self._drift_list.addItem(item)

        deprecated_deps = check_deprecated_deps(self._index)
        self._deprecated_list.clear()
        for d in deprecated_deps:
            item = QListWidgetItem(f"{d['doc']} 依赖已废弃: {d['dep_name']}")
            self._deprecated_list.addItem(item)

    def show_check_results(self, drifts: list, deprecated: list):
        self._drift_list.clear()
        for d in drifts:
            item = QListWidgetItem(f"{d['doc']} -> {d['dep_name']} v{d['declared']} (实际 v{d['actual']})")
            self._drift_list.addItem(item)
        self._deprecated_list.clear()
        for d in deprecated:
            item = QListWidgetItem(f"{d['doc']} 依赖已废弃: {d['dep_name']}")
            self._deprecated_list.addItem(item)
        self._card_drifts._value.setText(str(len(drifts)))

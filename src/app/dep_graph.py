"""依赖图面板 — 可视化 depends_on 关系。"""
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget,
    QGroupBox,
)

from src.engine.index import IndexManager


class DepGraphPanel(QWidget):
    """依赖图面板 — 列表模式（V1），后续可升级为 QGraphicsView 力导向图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_root: Path | None = None
        self._index: IndexManager | None = None

        layout = QVBoxLayout(self)
        title = QLabel("依赖关系")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("从文档树选择文档后切换到此面板查看详情。当前为列表模式。")
        hint.setStyleSheet("color: gray; margin-bottom: 8px;")
        layout.addWidget(hint)

        fwd_group = QGroupBox("依赖 (depends_on)")
        fwd_layout = QVBoxLayout(fwd_group)
        self._fwd_list = QListWidget()
        fwd_layout.addWidget(self._fwd_list)
        layout.addWidget(fwd_group)

        rev_group = QGroupBox("被依赖 (reverse deps)")
        rev_layout = QVBoxLayout(rev_group)
        self._rev_list = QListWidget()
        rev_layout.addWidget(self._rev_list)
        layout.addWidget(rev_group)

    def load_project(self, project_root: Path, index: IndexManager):
        self._project_root = project_root
        self._index = index

    def show_doc_deps(self, rel_path: str):
        """显示指定文档的依赖关系。"""
        if not self._index:
            return
        entry = self._index.get_entry(rel_path)
        if not entry:
            return

        from src.engine.deps import find_reverse_dependencies

        self._fwd_list.clear()
        for dep in entry.depends_on:
            self._fwd_list.addItem(f"{dep.get('doc', '?')}  [{dep.get('module', '?')}]  v{dep.get('version', '?')}")

        rev = find_reverse_dependencies(Path(rel_path).name, self._index)
        self._rev_list.clear()
        for r in rev:
            self._rev_list.addItem(r.path)

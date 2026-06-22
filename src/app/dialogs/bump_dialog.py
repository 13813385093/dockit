"""版本升级确认对话框 — 展示版本变化和反向依赖影响。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget,
    QDialogButtonBox,
)

from src.engine.index import IndexManager
from src.engine.deps import find_reverse_dependencies


class BumpDialog(QDialog):
    """版本升级确认对话框。"""

    def __init__(self, doc_path: str, old_ver: str, new_ver: str, index: IndexManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("版本升级确认")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"{doc_path}"))
        layout.addWidget(QLabel(f"版本: {old_ver}  ->  {new_ver}"))

        reverse_deps = find_reverse_dependencies(doc_path, index)
        if reverse_deps:
            layout.addWidget(QLabel(f"以下 {len(reverse_deps)} 篇文档的 depends_on 会受影响："))
            dep_list = QListWidget()
            for dep in reverse_deps:
                dep_list.addItem(dep.path)
            layout.addWidget(dep_list)
        else:
            layout.addWidget(QLabel("无依赖方，升级安全。"))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

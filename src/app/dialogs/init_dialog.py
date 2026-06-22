"""项目初始化对话框 — 选择 profile 和项目名称。"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QDialogButtonBox,
    QFormLayout, QGroupBox,
)


class InitDialog(QDialog):
    """首次初始化对话框：询问项目名称和文档模式。"""

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("初始化项目文档")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        # 说明
        layout.addWidget(QLabel(
            f"所选目录未包含 .doc-kit/ 文档配置：\n{project_root}\n\n"
            "请选择初始化参数："
        ))

        form = QFormLayout()

        # 项目名称（从目录名自动填充）
        self._name_edit = QLineEdit(project_root.name)
        form.addRow("项目名称:", self._name_edit)

        # Profile
        self._profile_combo = QComboBox()
        self._profile_combo.addItem("minimal — 仅 charter.md", "minimal")
        self._profile_combo.addItem("full — 6 个顶层文件", "full")
        form.addRow("文档模式:", self._profile_combo)

        layout.addLayout(form)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def project_name(self) -> str:
        return self._name_edit.text().strip() or "untitled"

    @property
    def profile(self) -> str:
        return self._profile_combo.currentData()

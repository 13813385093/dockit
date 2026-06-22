"""新建模块对话框 — 支持一级模块和子模块，选择要创建的文档类型。"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QCheckBox, QDialogButtonBox, QFormLayout,
    QGroupBox, QComboBox, QMessageBox,
)

from src.engine.index import IndexManager


class NewModuleDialog(QDialog):
    """新建模块对话框。"""

    def __init__(self, index: IndexManager | None = None, parent=None):
        super().__init__(parent)
        self._index = index
        self.setWindowTitle("新建模块")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("创建一个新的业务模块，包含默认文档骨架。"))

        form = QFormLayout()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("如: data-storage、iec61850")
        form.addRow("模块名称:", self._name_edit)

        # 子模块选项
        self._sub_check = QCheckBox("创建为子模块")
        self._sub_check.toggled.connect(self._on_sub_toggled)
        form.addRow(self._sub_check)

        self._parent_combo = QComboBox()
        self._parent_combo.setVisible(False)
        self._parent_combo.setPlaceholderText("选择父模块...")
        self._populate_parent_modules()
        form.addRow("父模块:", self._parent_combo)

        layout.addLayout(form)

        # 文档选项
        options_group = QGroupBox("创建以下文档：")
        options_layout = QVBoxLayout(options_group)
        self._ck_module_design = QCheckBox("module-design.md (复合类型 — 推荐)")
        self._ck_module_design.setChecked(True)
        self._ck_manifest = QCheckBox("module-manifest.md (模块清单)")
        self._ck_manifest.setChecked(True)
        self._ck_architecture = QCheckBox("architecture.md (架构设计)")
        self._ck_domain_model = QCheckBox("domain-model.md (领域模型)")
        self._ck_integration = QCheckBox("integration.md (外部集成 — 可选)")
        options_layout.addWidget(self._ck_module_design)
        options_layout.addWidget(self._ck_manifest)
        options_layout.addWidget(self._ck_architecture)
        options_layout.addWidget(self._ck_domain_model)
        options_layout.addWidget(self._ck_integration)
        layout.addWidget(options_group)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_parent_modules(self):
        """从 index 加载已有模块列表。"""
        if not self._index:
            return
        seen = set()
        for e in self._index.list_entries():
            mod = e.module
            if mod and mod != "project-charter" and mod not in seen:
                seen.add(mod)
                self._parent_combo.addItem(mod, mod)

    def _on_sub_toggled(self, checked: bool):
        """勾选/取消子模块时显示/隐藏父模块下拉。"""
        self._parent_combo.setVisible(checked)
        # 如果勾选了子模块但下拉为空，提醒用户
        if checked and self._parent_combo.count() == 0:
            QMessageBox.information(self, "提示", "当前没有可选的父模块，将按一级模块创建。")
            self._sub_check.setChecked(False)

    def _validate(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "输入错误", "模块名称不能为空")
            return
        if "/" in name or "\\" in name or "." in name:
            QMessageBox.warning(self, "输入错误", "模块名称不能包含路径分隔符或点号")
            return
        self.accept()

    @property
    def module_name(self) -> str:
        return self._name_edit.text().strip()

    @property
    def is_sub_module(self) -> bool:
        return self._sub_check.isChecked() and self._parent_combo.count() > 0

    @property
    def parent_module(self) -> str | None:
        if self.is_sub_module:
            return self._parent_combo.currentData()
        return None

    @property
    def full_module_path(self) -> str:
        """完整模块路径（用于目录创建）。"""
        name = self.module_name
        if self.is_sub_module and self.parent_module:
            return f"{self.parent_module}.{name}"
        return name

    @property
    def doc_types(self) -> list[str]:
        types = []
        if self._ck_module_design.isChecked():
            types.append("module_design")
        if self._ck_manifest.isChecked():
            types.append("module_manifest")
        if self._ck_architecture.isChecked():
            types.append("architecture")
        if self._ck_domain_model.isChecked():
            types.append("domain_model")
        if self._ck_integration.isChecked():
            types.append("integration")
        return types

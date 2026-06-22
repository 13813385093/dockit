"""新建功能对话框 — 选择所属模块 + 功能名称 + 文档类型。"""
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QCheckBox, QDialogButtonBox, QFormLayout,
    QGroupBox, QComboBox, QMessageBox,
)

from src.engine.index import IndexManager


class NewFeatureDialog(QDialog):
    """新建功能对话框。"""

    def __init__(self, index: IndexManager | None = None, parent=None):
        super().__init__(parent)
        self._index = index
        self.setWindowTitle("新建功能")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("在指定模块下创建一个新的功能，包含功能级文档。"))

        form = QFormLayout()

        # 模块选择
        self._module_combo = QComboBox()
        self._module_combo.setPlaceholderText("选择所属模块...")
        self._populate_modules()
        form.addRow("所属模块:", self._module_combo)

        # 功能名称
        self._feature_edit = QLineEdit()
        self._feature_edit.setPlaceholderText("如: voltage-protection、user-login")
        form.addRow("功能名称:", self._feature_edit)

        layout.addLayout(form)

        # 文档选项
        options_group = QGroupBox("创建以下文档：")
        options_layout = QVBoxLayout(options_group)
        self._ck_feature_design = QCheckBox("feature-design.md (功能设计 — 推荐)")
        self._ck_feature_design.setChecked(True)
        self._ck_decision_log = QCheckBox("decision-log.md (设计决策)")
        self._ck_decision_log.setChecked(True)
        self._ck_unit_test = QCheckBox("unit-tests.md (单元测试)")
        self._ck_acceptance_test = QCheckBox("acceptance-tests.md (验收测试)")
        options_layout.addWidget(self._ck_feature_design)
        options_layout.addWidget(self._ck_decision_log)
        options_layout.addWidget(self._ck_unit_test)
        options_layout.addWidget(self._ck_acceptance_test)
        layout.addWidget(options_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_modules(self):
        """从 index 加载模块列表。"""
        if not self._index:
            return
        seen = set()
        for e in self._index.list_entries():
            mod = e.module
            if mod and mod != "project-charter" and mod not in seen:
                seen.add(mod)
                self._module_combo.addItem(mod, mod)

    def _validate(self):
        if self._module_combo.currentData() is None:
            QMessageBox.warning(self, "输入错误", "请选择所属模块")
            return
        name = self._feature_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "输入错误", "功能名称不能为空")
            return
        if "/" in name or "\\" in name:
            QMessageBox.warning(self, "输入错误", "功能名称不能包含路径分隔符")
            return
        self.accept()

    @property
    def module_name(self) -> str:
        return self._module_combo.currentData()

    @property
    def feature_name(self) -> str:
        return self._feature_edit.text().strip()

    @property
    def doc_types(self) -> list[str]:
        types = []
        if self._ck_feature_design.isChecked():
            types.append("feature_design")
        if self._ck_decision_log.isChecked():
            types.append("decision_log")
        if self._ck_unit_test.isChecked():
            types.append("unit_test")
        if self._ck_acceptance_test.isChecked():
            types.append("acceptance_test")
        return types

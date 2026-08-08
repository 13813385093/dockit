"""JSON 编辑器 — 编辑态 / 浏览态切换。

- 编辑态：QPlainTextEdit 编辑美化（indent=2）后的 JSON 文本；
- 浏览态：QTreeWidget 递归展示 JSON 结构，支持展开/折叠；
- 通过头部按钮切换两种模式（与 Markdown 编辑器交互一致）。
"""
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QMessageBox,
    QStackedWidget, QToolButton,
)

from src.app.icon_utils import get_icon


class JsonEditor(QWidget):
    """JSON 文件编辑器。"""

    document_saved = Signal(str)  # 保存后发射，参数为相对路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: Path | None = None
        self._current_rel: str = ""

        layout = QVBoxLayout(self)

        # 标题 + 编辑态/浏览态切换按钮
        header = QHBoxLayout()
        self._title = QLabel("请从左侧文档树选择一份 JSON 文件")
        self._title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header.addWidget(self._title)
        header.addStretch()

        self._view_toggle = QToolButton()
        self._view_toggle.setCheckable(True)
        self._view_toggle.setChecked(True)  # 默认编辑态
        self._view_toggle.setProperty("class", "toolbar-btn")
        self._view_toggle.toggled.connect(self._on_view_toggled)
        self._sync_view_button()
        header.addWidget(self._view_toggle)
        layout.addLayout(header)

        # 正文：编辑态（文本）/ 浏览态（结构树）切换
        self._body_stack = QStackedWidget()

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setToolTip("JSON 结构（点击箭头展开/折叠）")
        self._body_stack.addWidget(self._tree)

        self._text = QPlainTextEdit()
        self._text.setPlaceholderText("JSON 内容（美化格式），可直接编辑后保存")
        self._text.setFont(QFont("Consolas, 'Courier New', monospace"))
        self._body_stack.addWidget(self._text)

        layout.addWidget(self._body_stack, 1)

        # 默认编辑态
        self._body_stack.setCurrentWidget(self._text)

    # ── 打开 ──

    def open_file(self, full_path: Path, rel_path: str):
        """读取并展示一个 JSON 文件，默认进入编辑态。"""
        self._current_path = full_path
        self._current_rel = rel_path
        self._title.setText(rel_path)

        try:
            data = json.loads(full_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "解析错误", f"无法解析 JSON 文件: {e}")
            return

        self._rebuild_tree(data)
        self._text.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        # 打开新文件时默认回到编辑态
        self._view_toggle.setChecked(True)
        self._sync_view_button()

    def _rebuild_tree(self, data):
        """根据解析后的数据重建结构树。"""
        self._tree.clear()
        root = QTreeWidgetItem(self._tree, ["$: 根"])
        if isinstance(data, dict):
            for k, v in data.items():
                self._build_tree(root, k, v)
        elif isinstance(data, list):
            for i, v in enumerate(data):
                self._build_tree(root, i, v)
        else:
            # JSON 顶层标量
            root.setText(0, f"$: {json.dumps(data, ensure_ascii=False)}")
        self._tree.expandToDepth(0)  # 默认展开第一层，其余可手动折叠/展开

    def _build_tree(self, parent: QTreeWidgetItem, key, value):
        """递归把 JSON 值挂到树节点下。"""
        if isinstance(value, dict):
            node = QTreeWidgetItem(parent, [self._node_label(key, value, "dict")])
            for k, v in value.items():
                self._build_tree(node, k, v)
        elif isinstance(value, list):
            node = QTreeWidgetItem(parent, [self._node_label(key, value, "list")])
            for i, v in enumerate(value):
                self._build_tree(node, i, v)
        else:
            node = QTreeWidgetItem(parent, [self._node_label(key, value, "leaf")])
        return node

    @staticmethod
    def _node_label(key, value, kind: str) -> str:
        k = f"[{key}]" if isinstance(key, int) else str(key)
        if kind == "dict":
            return f"{k}: {{...}}  ({len(value)} 项)"
        if kind == "list":
            return f"{k}: [...]  ({len(value)} 项)"
        return f"{k}: {json.dumps(value, ensure_ascii=False)}"

    # ── 编辑态 / 浏览态切换 ──

    def _on_view_toggled(self, edit_mode: bool):
        """编辑态 / 浏览态切换。"""
        if not edit_mode:
            # 切浏览前校验并刷新结构树（编辑内容未保存时也能预览最新）
            try:
                data = json.loads(self._text.toPlainText())
            except json.JSONDecodeError as e:
                QMessageBox.warning(self, "JSON 格式错误", f"无法切换到浏览模式：JSON 解析失败\n{e}")
                self._view_toggle.setChecked(True)  # 回退编辑态
                return
            self._rebuild_tree(data)
        self._body_stack.setCurrentWidget(self._text if edit_mode else self._tree)
        self._sync_view_button()

    def _sync_view_button(self):
        """切换按钮文案随当前模式变化（编辑态显示“浏览”，浏览态显示“编辑”）。"""
        edit_mode = self._view_toggle.isChecked()
        if edit_mode:
            self._view_toggle.setText(" 浏览")
            self._view_toggle.setIcon(get_icon("file-text"))
            self._view_toggle.setToolTip("切换到浏览模式（结构树）")
        else:
            self._view_toggle.setText(" 编辑")
            self._view_toggle.setIcon(get_icon("edit"))
            self._view_toggle.setToolTip("切换到编辑模式")

    # ── 保存 ──

    def save(self):
        """校验并保存：JSON 合法才写盘，统一为美化格式。"""
        if not self._current_path:
            return
        text = self._text.toPlainText()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON 格式错误", f"无法保存：JSON 解析失败\n{e}")
            return

        try:
            self._current_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return

        # 同步刷新结构树与美化文本（与写盘内容一致）
        self._rebuild_tree(data)
        self._text.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        QMessageBox.information(self, "保存", f"已保存: {self._current_rel}")
        self.document_saved.emit(self._current_rel)

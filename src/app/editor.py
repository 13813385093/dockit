"""文档编辑器 — Frontmatter 表格编辑 + Markdown 正文编辑 + 保存后自动检查。"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QComboBox,
    QFormLayout, QLineEdit, QPlainTextEdit, QTextBrowser,
    QGroupBox, QToolButton, QSizePolicy,
)

import markdown

from resources.icons import get_icon, set_button_icon
from src.engine.index import IndexManager
from src.engine.frontmatter import FrontmatterParser
from src.engine.validation import parse_version


class FrontmatterTable(QWidget):
    """Frontmatter 展示 + 编辑。version 可直接修改。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QFormLayout(self)

        # 不可变字段（只读）
        self._doc_type = QLineEdit(); self._doc_type.setReadOnly(True)
        self._module = QLineEdit(); self._module.setReadOnly(True)
        self._level = QLineEdit(); self._level.setReadOnly(True)
        layout.addRow("doc_type:", self._doc_type)
        layout.addRow("module:", self._module)
        layout.addRow("level:", self._level)

        # version 可编辑
        self._version = QLineEdit()
        layout.addRow("version:", self._version)

        # status 下拉
        self._status = QComboBox()
        self._status.addItems(["active", "deprecated", "archived"])
        layout.addRow("status:", self._status)


class DependsOnEditor(QWidget):
    """depends_on 列表编辑。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("depends_on:"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["doc", "module", "version"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)


class DocEditor(QWidget):
    """文档编辑器面板。

    信号:
        document_saved(str): 保存后发射，参数为保存的文档相对路径。
    """
    document_saved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: Path | None = None
        self._current_rel: str = ""
        self._index: IndexManager | None = None
        self._meta: dict = {}
        self._body: str = ""
        self._fm_visible = False  # frontmatter 默认收起
        self._scrolling_lock = False  # 滚动同步防抖锁

        layout = QVBoxLayout(self)

        # 标题 + frontmatter 开关
        header_layout = QHBoxLayout()
        self._title = QLabel("请从左侧文档树选择一份文档")
        header_layout.addWidget(self._title)
        header_layout.addStretch()

        self._fm_toggle = QToolButton()
        self._fm_toggle.setCheckable(True)
        self._fm_toggle.setChecked(False)
        self._fm_toggle.setIcon(get_icon("panel-hidden"))
        self._fm_toggle.setToolTip("展开 Frontmatter")
        self._fm_toggle.toggled.connect(self._toggle_frontmatter)
        header_layout.addWidget(self._fm_toggle)
        layout.addLayout(header_layout)

        # frontmatter 区域（默认隐藏）
        self._fm_container = QWidget()
        self._fm_container.setVisible(False)
        fm_layout_inner = QVBoxLayout(self._fm_container)
        fm_layout_inner.setContentsMargins(0, 0, 0, 0)
        fm_group = QGroupBox("Frontmatter")
        fm_splitter = QSplitter(Qt.Horizontal)
        self._fm_table = FrontmatterTable()
        self._deps_editor = DependsOnEditor()
        fm_splitter.addWidget(self._fm_table)
        fm_splitter.addWidget(self._deps_editor)
        fm_splitter.setSizes([300, 300])
        fm_group_layout = QVBoxLayout(fm_group)
        fm_group_layout.addWidget(fm_splitter)
        fm_layout_inner.addWidget(fm_group)
        layout.addWidget(self._fm_container)

        # 正文：Markdown 分屏编辑 + 预览（2:1）
        body_splitter = QSplitter(Qt.Horizontal)
        self._body_edit = QPlainTextEdit()
        self._body_edit.setPlaceholderText("在此编辑文档正文...")
        self._body_edit.textChanged.connect(self._update_preview)
        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(True)
        body_splitter.addWidget(self._body_edit)
        body_splitter.addWidget(self._preview)
        self._body_ratio_2_1(body_splitter)
        self._setup_scroll_sync()
        layout.addWidget(body_splitter, 1)

        # 工具栏
        toolbar = QHBoxLayout()
        self._save_btn = QPushButton(" 保存")
        set_button_icon(self._save_btn, "save")
        self._save_btn.clicked.connect(self._on_save)
        self._validate_btn = QPushButton(" 校验")
        set_button_icon(self._validate_btn, "check")
        self._validate_btn.clicked.connect(self._on_validate)
        toolbar.addWidget(self._save_btn)
        toolbar.addWidget(self._validate_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Ctrl+S 快捷键
        self._shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self._shortcut_save.activated.connect(self._on_save)

        self._set_editable(False)

    def _body_ratio_2_1(self, splitter: QSplitter):
        """设置编辑/预览比例为 2:1。"""
        total = 660
        splitter.setSizes([int(total * 2 / 3), int(total / 3)])

    def _setup_scroll_sync(self):
        """编辑区与预览区滚动同步。"""
        edit_scroll = self._body_edit.verticalScrollBar()
        preview_scroll = self._preview.verticalScrollBar()
        edit_scroll.valueChanged.connect(self._on_edit_scrolled)
        preview_scroll.valueChanged.connect(self._on_preview_scrolled)

    def _on_edit_scrolled(self, value: int):
        """编辑区滚动 → 按比例同步预览区。"""
        if self._scrolling_lock:
            return
        self._scrolling_lock = True
        edit_scroll = self._body_edit.verticalScrollBar()
        preview_scroll = self._preview.verticalScrollBar()
        ratio = value / max(1, edit_scroll.maximum())
        preview_scroll.setValue(int(ratio * preview_scroll.maximum()))
        self._scrolling_lock = False

    def _on_preview_scrolled(self, value: int):
        """预览区滚动 → 按比例同步编辑区。"""
        if self._scrolling_lock:
            return
        self._scrolling_lock = True
        edit_scroll = self._body_edit.verticalScrollBar()
        preview_scroll = self._preview.verticalScrollBar()
        ratio = value / max(1, preview_scroll.maximum())
        edit_scroll.setValue(int(ratio * edit_scroll.maximum()))
        self._scrolling_lock = False

    def _toggle_frontmatter(self, visible: bool):
        """切换 frontmatter 区域的显示/隐藏。"""
        self._fm_container.setVisible(visible)
        self._fm_toggle.setIcon(get_icon("panel-visible" if visible else "panel-hidden"))
        self._fm_toggle.setToolTip("收起 Frontmatter" if visible else "展开 Frontmatter")

    def _set_editable(self, enabled: bool):
        """切换编辑状态。"""
        self._body_edit.setReadOnly(not enabled)
        self._save_btn.setEnabled(enabled)
        self._validate_btn.setEnabled(enabled)

    def _update_preview(self):
        """将 Markdown 正文渲染为 HTML 更新预览面板。"""
        md_text = self._body_edit.toPlainText()
        html = markdown.markdown(
            md_text,
            extensions=["extra", "codehilite", "toc", "tables"],
        )
        styled = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, 'Segoe UI', sans-serif;
       font-size: 14px; line-height: 1.6; padding: 8px; }}
code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; }}
pre code {{ background: none; padding: 0; }}
pre {{ background: #f8f8f8; padding: 12px; border-radius: 6px; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
th {{ background: #eee; }}
blockquote {{ border-left: 4px solid #ddd; margin: 0; padding: 4px 16px; color: #666; }}
</style>
</head>
<body>{html}</body>
</html>"""
        # 阻断预览滚动信号：setHtml 会重置滚动条到顶部，若不阻断会通过同步机制
        # 反跳回编辑区，导致打字时编辑区滚动条跳动
        preview_scroll = self._preview.verticalScrollBar()
        preview_scroll.blockSignals(True)
        self._preview.setHtml(styled)
        preview_scroll.blockSignals(False)

    def open_document(self, full_path: Path, rel_path: str, index: IndexManager):
        """打开并加载文档。"""
        self._current_path = full_path
        self._current_rel = rel_path
        self._index = index

        try:
            self._meta, self._body = FrontmatterParser.read_file(full_path)
        except Exception as e:
            QMessageBox.warning(self, "解析错误", f"无法解析文件: {e}")
            return

        self._title.setText(rel_path)

        # 填充 frontmatter 表格
        self._fm_table._doc_type.setText(str(self._meta.get("doc_type", "")))
        self._fm_table._module.setText(str(self._meta.get("module", "")))
        self._fm_table._level.setText(str(self._meta.get("level", "")))
        self._fm_table._version.setText(str(self._meta.get("version", "")))
        status = self._meta.get("status", "active")
        idx = self._fm_table._status.findText(status)
        if idx >= 0:
            self._fm_table._status.setCurrentIndex(idx)

        # 填充 depends_on 表格
        deps = self._meta.get("depends_on", [])
        self._deps_editor.table.setRowCount(len(deps))
        for i, dep in enumerate(deps):
            self._deps_editor.table.setItem(i, 0, QTableWidgetItem(str(dep.get("doc", ""))))
            self._deps_editor.table.setItem(i, 1, QTableWidgetItem(str(dep.get("module", ""))))
            self._deps_editor.table.setItem(i, 2, QTableWidgetItem(str(dep.get("version", ""))))

        # 填充正文
        self._body_edit.setPlainText(self._body)
        self._update_preview()
        self._set_editable(True)

    @Slot()
    def _on_save(self):
        """保存正文 + frontmatter → 更新索引 → 触发 check。"""
        if not self._current_path:
            return

        new_version = self._fm_table._version.text().strip()
        old_version = str(self._meta.get("version", ""))

        if new_version:
            try:
                parse_version(new_version)
            except ValueError:
                QMessageBox.warning(
                    self, "版本格式错误",
                    f"'{new_version}' 不是有效的 semver 格式 (需 major.minor.patch)"
                )
                return

        self._body = self._body_edit.toPlainText()
        self._meta["version"] = new_version

        new_status = self._fm_table._status.currentText()
        if new_status != self._meta.get("status"):
            self._meta["status"] = new_status
            now = FrontmatterParser.now_iso()
            if new_status == "deprecated":
                self._meta["deprecated_at"] = now
            elif new_status == "archived":
                self._meta["archived_at"] = now

        FrontmatterParser.write_file(self._current_path, self._meta, self._body)

        if new_version != old_version and self._index:
            self._index.update_version(self._current_rel, new_version)
            self._index.save()

        QMessageBox.information(self, "保存", f"已保存: {self._current_rel}")
        self.document_saved.emit(self._current_rel)

    @Slot()
    def _on_validate(self):
        """校验当前 frontmatter。"""
        errors = FrontmatterParser.validate(self._meta)
        if errors:
            QMessageBox.warning(self, "校验失败", "\n".join(errors))
        else:
            QMessageBox.information(self, "校验通过", "frontmatter 格式正确")

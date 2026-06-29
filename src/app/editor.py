"""文档编辑器 — Frontmatter 表格编辑 + Markdown 正文编辑 + 保存后自动检查。"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import (
    QShortcut, QKeySequence, QAction, QColor, QFont,
    QTextCharFormat, QTextCursor, QSyntaxHighlighter,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QComboBox, QHeaderView,
    QFormLayout, QLineEdit, QPlainTextEdit, QTextBrowser,
    QGroupBox, QToolButton, QSizePolicy, QMenu, QAbstractItemView,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QFrame,
)

import markdown

from src.app.icon_utils import get_icon, set_button_icon
from src.app.engine.index import IndexManager
from src.app.engine.frontmatter import FrontmatterParser
from src.app.engine.registry import Registry
from src.app.engine.validation import parse_version


class MarkdownHighlighter(QSyntaxHighlighter):
    """Markdown 语法高亮。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules: list[tuple[str, QTextCharFormat]] = []

        # ── 标题 (H1~H6) ──
        for i, (size, color) in enumerate([
            (22, "#1a1a2e"), (18, "#1a1a2e"), (15, "#1a1a2e"),
            (13, "#2c3e50"), (12, "#2c3e50"), (11, "#2c3e50"),
        ], start=1):
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Bold)
            fmt.setFontPointSize(size)
            fmt.setForeground(QColor(color))
            self._rules.append((rf'^#{{{i}}}\s+.*$', fmt))

        # ── 加粗 ──
        bold_fmt = QTextCharFormat()
        bold_fmt.setFontWeight(QFont.Bold)
        self._rules.append((r'\*\*(.+?)\*\*', bold_fmt))

        # ── 斜体 ──
        italic_fmt = QTextCharFormat()
        italic_fmt.setFontItalic(True)
        self._rules.append((r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', italic_fmt))

        # ── 行内代码 ──
        code_fmt = QTextCharFormat()
        code_fmt.setFontFamily("Consolas, 'Courier New', monospace")
        code_fmt.setForeground(QColor("#e74c3c"))
        self._rules.append((r'`(.+?)`', code_fmt))

        # ── 链接 ──
        link_fmt = QTextCharFormat()
        link_fmt.setForeground(QColor("#2980b9"))
        link_fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        self._rules.append((r'\[(.+?)\]\(.*?\)', link_fmt))

        # ── 列表标记 ──
        list_fmt = QTextCharFormat()
        list_fmt.setForeground(QColor("#8e44ad"))
        self._rules.append((r'^(\s*[-*+]\s|\s*\d+\.\s)', list_fmt))

        # ── 引用 ──
        quote_fmt = QTextCharFormat()
        quote_fmt.setForeground(QColor("#7f8c8d"))
        quote_fmt.setFontItalic(True)
        self._rules.append((r'^>\s.*$', quote_fmt))

        self._code_block_active = False

    def highlightBlock(self, text: str):
        # 代码块状态机
        if text.strip().startswith("```"):
            self._code_block_active = not self._code_block_active
            fmt = QTextCharFormat()
            fmt.setFontFamily("Consolas, 'Courier New', monospace")
            fmt.setBackground(QColor("#f5f5f5"))
            fmt.setForeground(QColor("#95a5a6"))
            self.setFormat(0, len(text), fmt)
            self.setCurrentBlockState(1 if self._code_block_active else 0)
            return

        if self._code_block_active:
            fmt = QTextCharFormat()
            fmt.setFontFamily("Consolas, 'Courier New', monospace")
            fmt.setBackground(QColor("#f5f5f5"))
            self.setFormat(0, len(text), fmt)
            return

        # 普通行：应用正则规则
        import re
        for pattern, fmt in self._rules:
            for match in re.finditer(pattern, text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)


class FrontmatterTable(QWidget):
    """Frontmatter 展示 + 编辑。version 可直接修改。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QFormLayout(self)
        layout.setContentsMargins(10, 0, 5, 0)

        # 不可变字段（只读）
        self._doc_type = QLineEdit(); self._doc_type.setReadOnly(True)
        self._module = QLineEdit(); self._module.setReadOnly(True)
        self._level = QLineEdit(); self._level.setReadOnly(True)
        layout.addRow("文档类型:", self._doc_type)
        layout.addRow("所属模块:", self._module)
        layout.addRow("功能属性:", self._level)

        # version 可编辑
        self._version = QLineEdit()
        layout.addRow("版本:", self._version)

        # status 下拉
        self._status = QComboBox()
        self._status.addItems(["active", "deprecated", "archived", "invalid"])
        layout.addRow("状态:", self._status)


class AddDependencyDialog(QDialog):
    """模态对话框：选择文档来添加依赖（多选），自动计算当前文档可依赖的候选文件。"""

    def __init__(self, index: IndexManager, registry: Registry | None,
                 current_rel_path: str = "", existing_deps: list[dict] | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("插入依赖项")
        self._index = index
        self._registry = registry
        self._current_rel_path = current_rel_path
        self._existing_paths = {d.get("doc", "") for d in (existing_deps or [])}
        self._deps: list[dict] = []

        layout = QVBoxLayout(self)

        # 文档选择（多选列表）
        layout.addWidget(QLabel("选择依赖文档（可多选）:"))
        self._doc_list = QListWidget()
        self._doc_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._populate_candidates()
        layout.addWidget(self._doc_list)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _get_candidate_dirs(self) -> set[Path]:
        """计算当前文档可依赖的候选目录：当前目录 + 第一个有文件的上级目录。"""
        current_dir = Path(self._current_rel_path).parent
        dirs = {current_dir}

        parent = current_dir.parent
        # 检查父目录下是否有直接文件
        has_file = any(
            Path(e.path).parent == parent
            for e in self._index.list_entries()
        )
        if has_file:
            dirs.add(parent)
        else:
            dirs.add(parent.parent)  # 跳过 features/sub-modules 等纯组织目录
        return dirs

    def _populate_candidates(self):
        self._doc_list.clear()
        if not self._index:
            return
        candidate_dirs = self._get_candidate_dirs()
        for e in self._index.list_entries():
            if Path(e.path).parent in candidate_dirs and e.path != self._current_rel_path:
                desc = Path(e.path).name
                if self._registry:
                    type_def = self._registry.get(e.doc_type)
                    if type_def and type_def.description:
                        desc = type_def.description
                version = e.version if e else "0.1.0"
                item_text = f"{desc}  ({Path(e.path).name})  v{version}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, e.path)
                # 已在依赖列表中的项置灰、不可选
                if e.path in self._existing_paths:
                    item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                    item.setForeground(QColor("gray"))
                self._doc_list.addItem(item)

    def _validate(self):
        selected_items = self._doc_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "错误", "请至少选择一个文档")
            return
        self._deps = []
        for item in selected_items:
            doc_path = item.data(Qt.UserRole)
            entry = self._index.get_entry(doc_path)
            self._deps.append({
                "doc": doc_path,
                "module": entry.module if entry else "",
                "version": entry.version if entry else "0.1.0",
            })
        self.accept()

    def get_deps(self) -> list[dict]:
        return self._deps


class DependsOnEditor(QWidget):
    """depends_on 列表编辑。"""

    deps_changed = Signal(list)  # 依赖变更时发射，参数为新 deps 列表
    jump_to_doc = Signal(str)     # 跳转到目标文档，参数为文档相对路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._deps: list[dict] = []
        self._index: IndexManager | None = None
        self._registry: Registry | None = None
        self._drifted_deps: set[str] = set()  # 记录发生版本漂移的依赖

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["文档", "所属模块", "版本"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        # Stretch 模式下各列平分剩余空间，但我们需要 3:3:1
        # 因此前两列用 Stretch 等分，版本列用 ResizeToContents 自适应其内容宽度
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 单元格只读
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows) # 整行选择
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 多选
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)         # 右键菜单
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table)

    def _find_entry(self, doc_path: str, dep_module: str = ""):
        """通过文件名+模块名联合查找 index 中的文档，避免同名文件匹配错误。"""
        entry = self._index.get_entry(doc_path) if self._index else None
        if entry:
            return entry
        target_name = Path(doc_path).name
        fallback = None
        for e in (self._index.list_entries() if self._index else []):
            if Path(e.path).name == target_name:
                if dep_module and e.module == dep_module:
                    return e  # 文件名+模块精确匹配 → 优先
                if fallback is None:
                    fallback = e  # 仅文件名匹配 → 回退
        return fallback

    def populate(self, deps, index, registry, current_rel_path=None):
        """用依赖列表填充表格，doc 列显示 Registry 中的中文描述而非文件名。"""
        self._deps = deps
        self._index = index
        self._registry = registry
        if current_rel_path is not None:
            self._current_rel_path = current_rel_path
        
        self._drifted_deps.clear()
        
        self.table.setRowCount(len(deps))
        for i, dep in enumerate(deps):
            doc_path = str(dep.get("doc", ""))
            module = str(dep.get("module", ""))
            version = str(dep.get("version", ""))

            is_drifted = False
            actual_version = None
            entry = None
            
            if doc_path and index:
                entry = index.get_entry(doc_path)
                if not entry:
                    entry = self._find_entry(doc_path, module)
                
                if entry:
                    actual_version = entry.version
                    if actual_version != version:
                        is_drifted = True
                        self._drifted_deps.add(doc_path)

            desc = doc_path
            if entry and entry.doc_type and registry:
                type_def = registry.get(entry.doc_type)
                if type_def and type_def.description:
                    desc = type_def.description

            item_doc = QTableWidgetItem(desc)
            item_module = QTableWidgetItem(module)
            item_version = QTableWidgetItem(version)
            
            if is_drifted and actual_version:
                item_version.setText(f"{version} → {actual_version}")
                red_color = QColor("#e74c3c")
                item_doc.setForeground(red_color)
                item_module.setForeground(red_color)
                item_version.setForeground(red_color)

            self.table.setItem(i, 0, item_doc)
            self.table.setItem(i, 1, item_module)
            self.table.setItem(i, 2, item_version)

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        jump_act = QAction(" 文档跳转", self)
        jump_act.setIcon(get_icon("external-link"))
        menu.addAction(jump_act)
        
        sync_act = QAction(" 版本同步", self)
        sync_act.setIcon(get_icon("arrow-down-circle"))
        sync_act.setEnabled(False)
        
        menu.addSeparator()
        delete_act = QAction("删除依赖项", self)
        insert_act = QAction("插入依赖项", self)
        
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        has_selection = len(selected_rows) > 0
        
        can_sync = False
        if has_selection and self._index:
            for row in selected_rows:
                if row < len(self._deps):
                    dep = self._deps[row]
                    doc_path = dep.get("doc", "")
                    if doc_path in self._drifted_deps:
                        can_sync = True
                        break
        
        jump_act.setEnabled(has_selection)
        sync_act.setEnabled(can_sync)
        delete_act.setEnabled(has_selection)
        insert_act.setEnabled(True)
        
        menu.addAction(sync_act)
        menu.addSeparator()
        menu.addAction(delete_act)
        menu.addAction(insert_act)
        
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == jump_act:
            self._jump_to_doc()
        elif action == sync_act:
            self._sync_version()
        elif action == delete_act:
            self._delete_dependency()
        elif action == insert_act:
            self._insert_dependency()

    def _delete_dependency(self):
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()), reverse=True)
        if not rows:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(rows)} 行依赖吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for row in rows:
            self._deps.pop(row)
        self.populate(self._deps, self._index, self._registry)
        self.deps_changed.emit(self._deps)

    def _insert_dependency(self):
        row = self.table.currentRow()
        dialog = AddDependencyDialog(
            self._index, self._registry, self._current_rel_path,
            existing_deps=self._deps, parent=self,
        )
        if dialog.exec():
            new_deps = dialog.get_deps()
            # 去重防御：过滤掉已在当前依赖列表中的项
            existing_docs = {d.get("doc", "") for d in self._deps}
            new_deps = [d for d in new_deps if d.get("doc", "") not in existing_docs]
            if not new_deps:
                return
            insert_pos = row + 1 if row >= 0 else len(self._deps)
            for i, dep in enumerate(new_deps):
                self._deps.insert(insert_pos + i, dep)
            self.populate(self._deps, self._index, self._registry)
            self.deps_changed.emit(self._deps)

    def _sync_version(self):
        """同步选中依赖项的版本号到实际版本。"""
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()), reverse=True)
        sync_count = 0
        
        for row in rows:
            if row < 0 or row >= len(self._deps):
                continue
            dep = self._deps[row]
            doc_path = dep.get("doc", "")
            
            if doc_path not in self._drifted_deps:
                continue
            
            entry = self._index.get_entry(doc_path) if self._index else None
            if not entry:
                entry = self._find_entry(doc_path, dep.get("module", ""))
            
            if entry:
                dep["version"] = entry.version
                sync_count += 1
        
        if sync_count > 0:
            self.populate(self._deps, self._index, self._registry)
            self.deps_changed.emit(self._deps)


    def _jump_to_doc(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._deps):
            return
        doc_path = self._deps[row].get("doc", "")
        if not doc_path:
            return
        entry = self._index.get_entry(doc_path) if self._index else None
        if not entry:
            entry = self._find_entry(doc_path, self._deps[row].get("module", ""))
        if entry:
            self.jump_to_doc.emit(entry.path)


class DocEditor(QWidget):
    """文档编辑器面板。

    支持格式工具栏、搜索替换 (Ctrl+F)、Markdown 语法高亮。

    信号:
        document_saved(str): 保存后发射，参数为保存的文档相对路径。
        navigate_to_doc(str): 跳转到目标文档，参数为文档相对路径。
    """
    document_saved = Signal(str)
    navigate_to_doc = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: Path | None = None
        self._current_rel: str = ""
        self._index: IndexManager | None = None
        self._registry: Registry | None = None
        self._meta: dict = {}
        self._body: str = ""
        self._fm_visible = False
        self._scrolling_lock = False
        self._search_visible = False

        layout = QVBoxLayout(self)

        # 标题 + frontmatter 开关
        header_layout = QHBoxLayout()
        self._title = QLabel("请从左侧文档树选择一份文档")
        self._title.setTextInteractionFlags(Qt.TextSelectableByMouse)
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
        fm_splitter.setObjectName("fm_splitter")
        self._fm_table = FrontmatterTable()
        self._deps_editor = DependsOnEditor()
        self._deps_editor.deps_changed.connect(self._on_deps_save)
        self._deps_editor.jump_to_doc.connect(self.navigate_to_doc.emit)
        fm_splitter.addWidget(self._fm_table)
        fm_splitter.addWidget(self._deps_editor)
        fm_splitter.setSizes([180, 360])
        fm_group_layout = QVBoxLayout(fm_group)
        fm_group_layout.addWidget(fm_splitter)
        fm_layout_inner.addWidget(fm_group)
        layout.addWidget(self._fm_container)

        # ── 格式工具栏 ──
        self._toolbar = self._build_toolbar()
        self._toolbar.setEnabled(False)
        layout.addWidget(self._toolbar)

        # ── 搜索替换栏（默认隐藏） ──
        self._search_bar = self._build_search_bar()
        self._search_bar.setVisible(False)
        layout.addWidget(self._search_bar)

        # 正文：Markdown 分屏编辑 + 预览（2:1）
        body_splitter = QSplitter(Qt.Horizontal)
        body_splitter.setObjectName("body_splitter")
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

        # ── 语法高亮 ──
        self._highlighter = MarkdownHighlighter(self._body_edit.document())

        # ── 快捷键 ──
        self._shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self._shortcut_save.activated.connect(self._on_save)
        self._shortcut_bold = QShortcut(QKeySequence("Ctrl+B"), self)
        self._shortcut_bold.activated.connect(lambda: self._insert_wrap("**", "**"))
        self._shortcut_italic = QShortcut(QKeySequence("Ctrl+I"), self)
        self._shortcut_italic.activated.connect(lambda: self._insert_wrap("*", "*"))
        self._shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self._shortcut_search.activated.connect(self._toggle_search)
        self._shortcut_find_next = QShortcut(QKeySequence("F3"), self)
        self._shortcut_find_next.activated.connect(self._find_next)
        self._shortcut_find_prev = QShortcut(QKeySequence("Shift+F3"), self)
        self._shortcut_find_prev.activated.connect(self._find_prev)

        self._set_editable(False)

    # ── 格式工具栏构建 ──

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        for level in range(1, 7):
            btn = QToolButton()
            btn.setText(f"H{level}")
            btn.setToolTip(f"标题 {level}")
            btn.setProperty("class", "toolbar-btn")
            btn.clicked.connect(lambda checked, lv=level: self._insert_heading(lv))
            layout.addWidget(btn)

        btn_bold = QToolButton()
        btn_bold.setIcon(get_icon("bold"))
        btn_bold.setToolTip("加粗 Ctrl+B")
        btn_bold.setProperty("class", "toolbar-btn")
        btn_bold.clicked.connect(lambda: self._insert_wrap("**", "**"))
        layout.addWidget(btn_bold)

        btn_italic = QToolButton()
        btn_italic.setIcon(get_icon("italic"))
        btn_italic.setToolTip("斜体 Ctrl+I")
        btn_italic.setProperty("class", "toolbar-btn")
        btn_italic.clicked.connect(lambda: self._insert_wrap("*", "*"))
        layout.addWidget(btn_italic)

        btn_code = QToolButton()
        btn_code.setIcon(get_icon("code"))
        btn_code.setToolTip("代码块")
        btn_code.setProperty("class", "toolbar-btn")
        btn_code.clicked.connect(self._insert_code_block)
        layout.addWidget(btn_code)

        btn_table = QToolButton()
        btn_table.setIcon(get_icon("table"))
        btn_table.setToolTip("插入表格")
        btn_table.setProperty("class", "toolbar-btn")
        btn_table.clicked.connect(self._insert_table)
        layout.addWidget(btn_table)

        layout.addStretch()
        return bar

    # ── 格式插入方法 ──

    def _insert_heading(self, level: int):
        cursor = self._body_edit.textCursor()
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        text = cursor.selectedText().lstrip("#").lstrip(" ")
        cursor.insertText("#" * level + " " + text)
        self._body_edit.setFocus()

    def _insert_wrap(self, prefix: str, suffix: str):
        cursor = self._body_edit.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            cursor.insertText(f"{prefix}{selected}{suffix}")
        else:
            placeholder = "粗体" if "**" in prefix else "斜体"
            cursor.insertText(f"{prefix}{placeholder}{suffix}")
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, len(suffix))
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(placeholder))
            self._body_edit.setTextCursor(cursor)
        self._body_edit.setFocus()

    def _insert_code_block(self):
        cursor = self._body_edit.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            cursor.insertText(f"```\n{selected}\n```")
        else:
            cursor.insertText("```\n\n```")
            cursor.movePosition(QTextCursor.Up)
            self._body_edit.setTextCursor(cursor)
        self._body_edit.setFocus()

    def _insert_table(self):
        cursor = self._body_edit.textCursor()
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.insertText(
            "| 列1 | 列2 | 列3 |\n"
            "| --- | --- | --- |\n"
            "| 数据 | 数据 | 数据 |"
        )
        self._body_edit.setFocus()

    # ── 搜索替换栏 ──

    def _build_search_bar(self) -> QFrame:
        bar = QFrame()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        btn_search = QToolButton()
        btn_search.setIcon(get_icon("search"))
        btn_search.setProperty("class", "toolbar-btn")
        layout.addWidget(btn_search)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索...")
        self._search_input.setMaximumWidth(180)
        self._search_input.returnPressed.connect(self._find_next)
        layout.addWidget(self._search_input)

        btn_prev = QToolButton()
        btn_prev.setIcon(get_icon("arrow-up"))
        btn_prev.setToolTip("上一个 (Shift+F3)")
        btn_prev.setProperty("class", "toolbar-btn")
        btn_prev.clicked.connect(self._find_prev)
        layout.addWidget(btn_prev)

        btn_next = QToolButton()
        btn_next.setIcon(get_icon("arrow-down"))
        btn_next.setToolTip("下一个 (F3)")
        btn_next.setProperty("class", "toolbar-btn")
        btn_next.clicked.connect(self._find_next)
        layout.addWidget(btn_next)

        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("替换为...")
        self._replace_input.setMaximumWidth(120)
        layout.addWidget(self._replace_input)

        btn_rep = QToolButton()
        btn_rep.setText("替换")
        btn_rep.setProperty("class", "toolbar-btn")
        btn_rep.clicked.connect(self._replace_one)
        layout.addWidget(btn_rep)

        btn_rep_all = QToolButton()
        btn_rep_all.setText("全部替换")
        btn_rep_all.setProperty("class", "toolbar-btn")
        btn_rep_all.clicked.connect(self._replace_all)
        layout.addWidget(btn_rep_all)

        layout.addStretch()

        btn_close = QToolButton()
        btn_close.setText("✕")
        btn_close.setProperty("class", "toolbar-btn")
        btn_close.clicked.connect(lambda: self._toggle_search(force_hide=True))
        layout.addWidget(btn_close)

        return bar

    def _toggle_search(self, force_hide: bool = False):
        if force_hide:
            self._search_visible = False
        else:
            self._search_visible = not self._search_visible
        self._search_bar.setVisible(self._search_visible)
        if self._search_visible:
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _find_next(self):
        text = self._search_input.text()
        if not text:
            return
        if not self._body_edit.find(text):
            cursor = self._body_edit.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self._body_edit.setTextCursor(cursor)
            self._body_edit.find(text)

    def _find_prev(self):
        text = self._search_input.text()
        if not text:
            return
        if not self._body_edit.find(text, QTextDocument.FindBackward):
            cursor = self._body_edit.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._body_edit.setTextCursor(cursor)
            self._body_edit.find(text, QTextDocument.FindBackward)

    def _replace_one(self):
        search = self._search_input.text()
        replace = self._replace_input.text()
        if not search:
            return
        cursor = self._body_edit.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == search:
            cursor.insertText(replace)
        self._find_next()

    def _replace_all(self):
        search = self._search_input.text()
        replace = self._replace_input.text()
        if not search:
            return
        text = self._body_edit.toPlainText()
        count = text.count(search)
        if count == 0:
            QMessageBox.information(self, "替换", f"未找到「{search}」")
            return
        self._body_edit.setPlainText(text.replace(search, replace))
        QMessageBox.information(self, "替换完成", f"已替换 {count} 处")

    # ── 原有功能 ──

    def save(self):
        self._on_save()

    def _body_ratio_2_1(self, splitter: QSplitter):
        total = 660
        splitter.setSizes([int(total * 2 / 3), int(total / 3)])

    def _setup_scroll_sync(self):
        edit_scroll = self._body_edit.verticalScrollBar()
        preview_scroll = self._preview.verticalScrollBar()
        edit_scroll.valueChanged.connect(self._on_edit_scrolled)
        preview_scroll.valueChanged.connect(self._on_preview_scrolled)

    def _on_edit_scrolled(self, value: int):
        if self._scrolling_lock:
            return
        self._scrolling_lock = True
        edit_scroll = self._body_edit.verticalScrollBar()
        preview_scroll = self._preview.verticalScrollBar()
        ratio = value / max(1, edit_scroll.maximum())
        preview_scroll.setValue(int(ratio * preview_scroll.maximum()))
        self._scrolling_lock = False

    def _on_preview_scrolled(self, value: int):
        if self._scrolling_lock:
            return
        self._scrolling_lock = True
        edit_scroll = self._body_edit.verticalScrollBar()
        preview_scroll = self._preview.verticalScrollBar()
        ratio = value / max(1, preview_scroll.maximum())
        edit_scroll.setValue(int(ratio * edit_scroll.maximum()))
        self._scrolling_lock = False

    def _toggle_frontmatter(self, visible: bool):
        self._fm_container.setVisible(visible)
        self._fm_toggle.setIcon(get_icon("panel-visible" if visible else "panel-hidden"))
        self._fm_toggle.setToolTip("收起 Frontmatter" if visible else "展开 Frontmatter")

    def _set_editable(self, enabled: bool):
        self._body_edit.setReadOnly(not enabled)
        self._toolbar.setEnabled(enabled)

    def _update_preview(self):
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
        preview_scroll = self._preview.verticalScrollBar()
        preview_scroll.blockSignals(True)
        self._preview.setHtml(styled)
        preview_scroll.blockSignals(False)

    def open_document(self, full_path: Path, rel_path: str, index: IndexManager, registry: Registry | None = None):
        self._current_path = full_path
        self._current_rel = rel_path
        self._index = index
        if registry is not None:
            self._registry = registry

        try:
            self._meta, self._body = FrontmatterParser.read_file(full_path)
        except Exception as e:
            QMessageBox.warning(self, "解析错误", f"无法解析文件: {e}")
            return

        self._title.setText(rel_path)

        self._fm_table._doc_type.setText(str(self._meta.get("doc_type", "")))
        self._fm_table._module.setText(str(self._meta.get("module", "")))
        self._fm_table._level.setText(str(self._meta.get("level", "")))
        self._fm_table._version.setText(str(self._meta.get("version", "")))
        status = self._meta.get("status", "active")
        idx = self._fm_table._status.findText(status)
        if idx >= 0:
            self._fm_table._status.setCurrentIndex(idx)

        deps = self._meta.get("depends_on") or []
        self._deps_editor.populate(deps, self._index, self._registry, self._current_rel)

        self._body_edit.setPlainText(self._body)
        self._update_preview()
        self._set_editable(True)

    @Slot()
    def _on_deps_save(self, deps: list[dict]):
        if not self._current_path or not self._index:
            return
        self._meta["depends_on"] = deps
        FrontmatterParser.write_file(self._current_path, self._meta, self._body)
        project_root = self._current_path.parent.parent
        self._index.rebuild(project_root / "ProjectSpec")
        self._index.save()
        self.document_saved.emit(self._current_rel)

    @Slot()
    def _on_save(self):
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
                    f"'{new_version}' 不是有效的 semver 格式"
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

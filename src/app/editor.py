"""文档编辑器 — Frontmatter 表格编辑 + Markdown 正文编辑 + 保存后自动检查。"""
import re
from pathlib import Path
from urllib.parse import urlsplit, unquote, quote
import posixpath

from PySide6.QtCore import Qt, Signal, Slot, QUrl, QTimer
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
    QStackedWidget, QButtonGroup,
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

    def highlightBlock(self, text: str):
        # 代码块状态机（使用 QSyntaxHighlighter 官方推荐的 previousBlockState 机制，
        # 而非实例变量，避免增量重高亮时状态不一致）
        prev_state = self.previousBlockState()
        if text.strip().startswith("```"):
            new_state = 0 if prev_state == 1 else 1
            fmt = QTextCharFormat()
            fmt.setFontFamily("Consolas, 'Courier New', monospace")
            fmt.setBackground(QColor("#f5f5f5"))
            fmt.setForeground(QColor("#95a5a6"))
            self.setFormat(0, len(text), fmt)
            self.setCurrentBlockState(new_state)
            return

        in_code_block = prev_state == 1
        if in_code_block:
            fmt = QTextCharFormat()
            fmt.setFontFamily("Consolas, 'Courier New', monospace")
            fmt.setBackground(QColor("#f5f5f5"))
            self.setFormat(0, len(text), fmt)
            self.setCurrentBlockState(1)
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


class AddLinkDialog(QDialog):
    """模态框：为选中的文字添加文档链接与锚点。

    三步：1) 选择目标文件 → 2) 选择锚点标签插入位置（目标文件中的标题或文档末尾）
          → 3) 输入锚点文字。

    get_result() 返回:
        target_rel: 目标文档相对项目根的路径
        anchor: 锚点文字（id）
        heading: 锚点标签插入位置对应的标题行原文（None 表示文档末尾）
    """

    def __init__(self, index: IndexManager, current_rel: str = "", selected: str = "",
                 registry: Registry | None = None, parent=None):
        super().__init__(parent)
        self._index = index
        self._current_rel = current_rel
        self._registry = registry
        self._result: dict = {}
        self.setWindowTitle("添加链接与锚点")
        self.resize(560, 540)
        layout = QVBoxLayout(self)

        # 1) 选择目标文件
        layout.addWidget(QLabel("1. 选择目标文件:"))
        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._file_list.currentItemChanged.connect(self._on_file_changed)
        self._populate_files()
        layout.addWidget(self._file_list, 2)

        # 2) 选择锚点标签插入位置
        layout.addWidget(QLabel("2. 选择锚点标签插入位置（目标文件中的标题）:"))
        self._pos_list = QListWidget()
        self._pos_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self._pos_list, 2)

        # 3) 锚点文字（默认取当前选中的文字）
        layout.addWidget(QLabel("3. 锚点文字:"))
        self._anchor_edit = QLineEdit()
        self._anchor_edit.setPlaceholderText("输入锚点文字（如 概述）")
        if selected:
            self._anchor_edit.setText(selected)
        layout.addWidget(self._anchor_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _project_root(self) -> Path | None:
        if self._index is None:
            return None
        return Path(self._index.index_path).parent.parent

    def _populate_files(self):
        """文件列表：显示文件类型中文名（同左侧文件树），后附文件名便于区分。"""
        self._file_list.clear()
        if self._index is None:
            return
        for e in self._index.list_entries():
            if e.path == self._current_rel:
                continue
            desc = Path(e.path).name
            if self._registry:
                type_def = self._registry.get(e.doc_type)
                if type_def and type_def.description:
                    desc = type_def.description
            item = QListWidgetItem(f"{desc}  ({Path(e.path).name})")
            item.setData(Qt.UserRole, e.path)
            self._file_list.addItem(item)

    def _on_file_changed(self, current, _previous):
        self._pos_list.clear()
        if current is None:
            return
        target_rel = current.data(Qt.UserRole)
        # 文档末尾选项
        end_item = QListWidgetItem("（文档末尾）")
        end_item.setData(Qt.UserRole, None)
        self._pos_list.addItem(end_item)
        for heading in self._parse_headings(target_rel):
            item = QListWidgetItem(heading)
            item.setData(Qt.UserRole, heading)
            self._pos_list.addItem(item)

    def _parse_headings(self, rel_path: str) -> list[str]:
        """读取目标文件，提取标题行（跳过 frontmatter 与代码块）。"""
        root = self._project_root()
        if root is None:
            return []
        full = root / rel_path
        if not full.exists():
            return []
        try:
            _, body = FrontmatterParser.read_file(full)
        except Exception:
            try:
                body = full.read_text(encoding="utf-8")
            except OSError:
                return []
        headings: list[str] = []
        in_code = False
        for ln in body.split("\n"):
            s = ln.strip()
            if s.startswith("```") or s.startswith("~~~"):
                in_code = not in_code
                continue
            if in_code:
                continue
            if re.match(r"^#{1,6}\s+\S", s):
                headings.append(s)
        return headings

    def _validate(self):
        file_item = self._file_list.currentItem()
        pos_item = self._pos_list.currentItem()
        anchor = self._anchor_edit.text().strip()
        if file_item is None:
            QMessageBox.warning(self, "提示", "请先选择目标文件")
            return
        if pos_item is None:
            QMessageBox.warning(self, "提示", "请选择锚点标签插入位置")
            return
        if not anchor:
            QMessageBox.warning(self, "提示", "请输入锚点文字")
            return
        if not re.fullmatch(r"[\w\-]+", anchor):
            QMessageBox.warning(
                self, "提示",
                "锚点文字只能包含中文、字母、数字、下划线和连字符",
            )
            return
        self._result = {
            "target_rel": file_item.data(Qt.UserRole),
            "anchor": anchor,
            "heading": pos_item.data(Qt.UserRole),
        }
        self.accept()

    def get_result(self) -> dict:
        return self._result


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
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 单元格只读
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows) # 整行选择
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 多选
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)         # 右键菜单
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table)
    
    def resizeEvent(self, event):
        """窗口大小变化时按3:3:1比例重新分配列宽。"""
        super().resizeEvent(event)
        self._adjust_column_widths()
    
    def _adjust_column_widths(self):
        """按3:3:1比例调整列宽。"""
        header = self.table.horizontalHeader()
        total_width = header.width()
        if total_width <= 0:
            return
        ratios = [3, 3, 1]
        total_ratio = sum(ratios)
        for i, ratio in enumerate(ratios):
            header.resizeSection(i, int(total_width * ratio / total_ratio))

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
        
        self._adjust_column_widths()

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


class ImplementedInEditor(QWidget):
    """implemented_in 列表编辑（实现位置：源码目录 + 语言）。

    表格与 depends_on 并列展示、可切换查看；仅文档 frontmatter 含
    implemented_in 字段时显示。单元格可双击直接编辑。
    """

    impl_changed = Signal(list)  # 变更时发射，参数为新的 implemented_in 列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self._impls: list[dict] = []
        self._loading = False  # populate 期间屏蔽 cellChanged，避免误触发保存

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["源码目录", "语言"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table)

    def resizeEvent(self, event):
        """窗口大小变化时按 3:1 比例重新分配列宽。"""
        super().resizeEvent(event)
        self._adjust_column_widths()

    def _adjust_column_widths(self):
        """按 3:1 比例调整列宽。"""
        header = self.table.horizontalHeader()
        total_width = header.width()
        if total_width <= 0:
            return
        ratios = [3, 1]
        total_ratio = sum(ratios)
        for i, ratio in enumerate(ratios):
            header.resizeSection(i, int(total_width * ratio / total_ratio))

    def populate(self, items):
        """用 implemented_in 列表填充表格。items 为 list[dict]，每项含 path/lang。"""
        self._loading = True
        try:
            self._impls = []
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        self._impls.append(dict(it))
            elif isinstance(items, dict):
                # 手写为单个 mapping 时按单元素处理，避免静默丢弃已有数据
                self._impls.append(dict(items))
            self.table.setRowCount(len(self._impls))
            for i, impl in enumerate(self._impls):
                self.table.setItem(i, 0, QTableWidgetItem(str(impl.get("path", ""))))
                self.table.setItem(i, 1, QTableWidgetItem(str(impl.get("lang", ""))))
        finally:
            self._loading = False
        self._adjust_column_widths()

    def _on_cell_changed(self, row: int, col: int):
        """单元格编辑提交后同步回 _impls 并通知保存。"""
        if self._loading:
            return
        if row < 0 or row >= len(self._impls):
            return
        item = self.table.item(row, col)
        value = (item.text() if item else "").strip()
        key = "path" if col == 0 else "lang"
        self._impls[row][key] = value
        self.impl_changed.emit(list(self._impls))

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        add_act = QAction("添加实现项", self)
        add_act.setIcon(get_icon("plus"))
        delete_act = QAction("删除实现项", self)
        delete_act.setIcon(get_icon("trash"))
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        delete_act.setEnabled(bool(selected_rows))
        menu.addAction(add_act)
        menu.addAction(delete_act)

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == add_act:
            self._add_item()
        elif action == delete_act:
            self._delete_items()

    def _add_item(self):
        """在当前行之后（或末尾）插入一个空实现项。"""
        row = self.table.currentRow()
        insert_pos = row + 1 if row >= 0 else len(self._impls)
        self._impls.insert(insert_pos, {"path": "", "lang": ""})
        self.populate(self._impls)
        self.impl_changed.emit(list(self._impls))

    def _delete_items(self):
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()), reverse=True)
        if not rows:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(rows)} 行实现位置吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for row in rows:
            self._impls.pop(row)
        self.populate(self._impls)
        self.impl_changed.emit(list(self._impls))


class DocEditor(QWidget):
    """文档编辑器面板。

    支持格式工具栏、搜索替换 (Ctrl+F)、Markdown 语法高亮。

    信号:
        document_saved(str): 保存后发射，参数为保存的文档相对路径。
        navigate_to_doc(str): 跳转到目标文档，参数为文档相对路径。
        navigate_to_doc_anchor(str, str): 跳转到目标文档的锚点，参数为(文档相对路径, 锚点)。
    """
    document_saved = Signal(str)
    navigate_to_doc = Signal(str)
    navigate_to_doc_anchor = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: Path | None = None
        self._current_rel: str = ""
        self._index: IndexManager | None = None
        self._registry: Registry | None = None
        self._meta: dict = {}
        self._body: str = ""
        self._has_fm = False  # 当前文件是否有 frontmatter
        self._fm_visible = False
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

        # 编辑态 / 浏览态切换按钮
        self._view_toggle = QToolButton()
        self._view_toggle.setCheckable(True)
        self._view_toggle.setChecked(True)  # 默认编辑态
        self._view_toggle.setProperty("class", "toolbar-btn")
        self._view_toggle.toggled.connect(self._on_view_toggled)
        self._sync_view_button()
        header_layout.addWidget(self._view_toggle)
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
        self._impl_editor = ImplementedInEditor()
        self._impl_editor.impl_changed.connect(self._on_impl_save)

        # 切换按钮行：位于 Frontmatter 分组公共顶部（右对齐），不占用表格
        # 垂直空间，保证左右两侧（表单 / 表格）在 splitter 内等高对齐
        switch_row = QHBoxLayout()
        switch_row.setContentsMargins(0, 0, 0, 0)
        switch_row.setSpacing(2)
        self._fm_btn_deps = QToolButton()
        self._fm_btn_deps.setText("依赖表")
        self._fm_btn_deps.setCheckable(True)
        self._fm_btn_deps.setChecked(True)
        self._fm_btn_impl = QToolButton()
        self._fm_btn_impl.setText("源码表")
        self._fm_btn_impl.setCheckable(True)
        self._fm_btn_impl.setVisible(False)  # 仅含 implemented_in 字段的文档显示
        switch_row.addStretch()
        switch_row.addWidget(self._fm_btn_deps)
        switch_row.addWidget(self._fm_btn_impl)
        self._fm_btn_group = QButtonGroup(self)
        self._fm_btn_group.addButton(self._fm_btn_deps, 0)
        self._fm_btn_group.addButton(self._fm_btn_impl, 1)
        self._fm_btn_group.idClicked.connect(self._on_fm_switch)

        fm_splitter.addWidget(self._fm_table)
        # depends_on / implemented_in 两个表格并列于同一区域，可切换查看
        self._fm_stack = QStackedWidget()
        self._fm_stack.addWidget(self._deps_editor)   # index 0 = depends_on
        self._fm_stack.addWidget(self._impl_editor)   # index 1 = implemented_in
        fm_splitter.addWidget(self._fm_stack)
        fm_splitter.setSizes([180, 360])
        fm_group_layout = QVBoxLayout(fm_group)
        fm_group_layout.addLayout(switch_row)
        fm_group_layout.addWidget(fm_splitter, 1)
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

        # 正文：编辑态 / 浏览态切换（同一视图区，QStackedWidget）
        self._body_edit = QPlainTextEdit()
        self._body_edit.setPlaceholderText("在此编辑文档正文...")
        self._body_edit.textChanged.connect(self._update_preview)
        self._body_edit.selectionChanged.connect(self._on_body_selection_changed)
        self._preview = QTextBrowser()
        # 关闭自动打开外部链接：统一走 anchorClicked 拦截，内部文档链接跳转文档、
        # 外部链接不响应跳转（openExternalLinks=True 时不发射 anchorClicked）
        self._preview.setOpenExternalLinks(False)
        self._preview.anchorClicked.connect(self._on_preview_link_clicked)
        self._body_stack = QStackedWidget()
        self._body_stack.addWidget(self._body_edit)
        self._body_stack.addWidget(self._preview)
        layout.addWidget(self._body_stack, 1)

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
        self._shortcut_link = QShortcut(QKeySequence("Ctrl+L"), self)
        self._shortcut_link.activated.connect(self._insert_link)

        self._set_editable(False)

    # ── 格式工具栏构建 ──

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("EditorToolbar")
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

        # 添加链接与锚点：需先选中一段文字
        self._link_btn = QToolButton()
        self._link_btn.setIcon(get_icon("external-link"))
        self._link_btn.setToolTip("插入链接与锚点（先选中文字） Ctrl+L")
        self._link_btn.setProperty("class", "toolbar-btn")
        self._link_btn.setEnabled(False)
        self._link_btn.clicked.connect(self._insert_link)
        layout.addWidget(self._link_btn)

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

    # ── 链接与锚点插入 ──

    def _on_body_selection_changed(self):
        """选中文字时启用「添加链接」按钮，无选区时禁用。"""
        if hasattr(self, "_link_btn"):
            self._link_btn.setEnabled(self._body_edit.textCursor().hasSelection())

    def _project_root(self) -> Path | None:
        if self._index is None:
            return None
        return Path(self._index.index_path).parent.parent

    def _relative_link_path(self, target_rel: str) -> str:
        """目标文档相对当前文档目录的链接路径（./ 或 ../ 开头）。"""
        rel = posixpath.relpath(target_rel, posixpath.dirname(self._current_rel))
        if not rel.startswith("."):
            rel = "./" + rel
        return rel

    def _apply_anchor_tag(self, target_rel: str, anchor: str, heading: str | None) -> bool:
        """把 {#锚点} 标签写入目标文档（标题行末尾或文档末尾）。

        返回 True 表示锚点标签已就位（已写入或已存在）；False 表示失败
        （文件不可读、标题行未找到）。目标文档已含同锚点标签时不重复写入。
        """
        root = self._project_root()
        if root is None:
            return False
        full = root / target_rel
        if not full.exists():
            return False
        try:
            lines = full.read_text(encoding="utf-8").split("\n")
        except OSError:
            return False
        tag = f"{{#{anchor}}}"
        if heading:
            # 在匹配的标题行末尾追加 {#锚点}
            for i, ln in enumerate(lines):
                if ln.strip() == heading.strip():
                    if "{#" in ln:
                        return True  # 该标题已含锚点标签，不重复追加
                    lines[i] = ln + f" {tag}"
                    break
            else:
                return False  # 标题行未找到（目标文件已变化）
        else:
            # 文档末尾：已含同锚点则跳过；否则挂到最后一个非空行末尾，
            # 避免孤立锚点行（空段落无法可靠定位）
            if tag in "\n".join(lines):
                return True
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip():
                    if "{#" not in lines[i]:
                        lines[i] = lines[i] + f" {tag}"
                    break
        try:
            full.write_text("\n".join(lines), encoding="utf-8")
        except OSError:
            return False
        return True

    def _insert_link(self):
        """为选中文字添加链接：弹窗选择目标文件/锚点位置/锚点文字，
        向目标文档写入 {#锚点} 标签，并在光标处插入 [文字](路径#锚点)。"""
        if self._index is None or not self._current_rel:
            return
        cursor = self._body_edit.textCursor()
        if not cursor.hasSelection():
            return
        selected = cursor.selectedText().replace("\u2029", " ").strip()
        if not selected:
            return
        dialog = AddLinkDialog(
            self._index, self._current_rel,
            selected=selected, registry=self._registry, parent=self,
        )
        if not dialog.exec():
            return
        result = dialog.get_result()
        if not result:
            return
        target_rel = result["target_rel"]
        anchor = result["anchor"]
        if not self._apply_anchor_tag(target_rel, anchor, result["heading"]):
            QMessageBox.warning(self, "添加链接", f"无法写入目标文档: {target_rel}")
            return
        link_path = quote(self._relative_link_path(target_rel))
        link_text = f"[{selected}]({link_path}#{anchor})"
        cursor.insertText(link_text)
        self._body_edit.setFocus()
        QMessageBox.information(
            self, "添加链接",
            f"已添加链接: {link_text}\n锚点标签已就位: {target_rel}",
        )

    # ── 搜索替换栏 ──

    def _build_search_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("SearchBar")
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
        self._body_edit.setFocus()

    def _find_prev(self):
        text = self._search_input.text()
        if not text:
            return
        if not self._body_edit.find(text, QTextDocument.FindBackward):
            cursor = self._body_edit.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._body_edit.setTextCursor(cursor)
            self._body_edit.find(text, QTextDocument.FindBackward)
        self._body_edit.setFocus()

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

    def _on_view_toggled(self, edit_mode: bool):
        """编辑态 / 浏览态切换。"""
        self._body_stack.setCurrentWidget(self._body_edit if edit_mode else self._preview)
        if not edit_mode:
            self._update_preview()  # 进入浏览前刷新预览
        self._sync_view_button()

    def _sync_view_button(self):
        """切换按钮文案随当前模式变化（编辑态显示“浏览”，浏览态显示“编辑”）。"""
        edit_mode = self._view_toggle.isChecked()
        if edit_mode:
            self._view_toggle.setText(" 浏览")
            self._view_toggle.setIcon(get_icon("file-text"))
            self._view_toggle.setToolTip("切换到浏览模式")
        else:
            self._view_toggle.setText(" 编辑")
            self._view_toggle.setIcon(get_icon("edit"))
            self._view_toggle.setToolTip("切换到编辑模式")

    def _toggle_frontmatter(self, visible: bool):
        self._fm_container.setVisible(visible)
        self._fm_toggle.setIcon(get_icon("panel-visible" if visible else "panel-hidden"))
        self._fm_toggle.setToolTip("收起 Frontmatter" if visible else "展开 Frontmatter")

    @Slot(int)
    def _on_fm_switch(self, index: int):
        """切换 depends_on / implemented_in 表格视图。"""
        self._fm_stack.setCurrentIndex(index)

    def _set_editable(self, enabled: bool):
        self._body_edit.setReadOnly(not enabled)
        self._toolbar.setEnabled(enabled)

    _ANCHOR_TAG_RE = re.compile(
        r'^(#{1,6})\s+(.+?)\s+\{#([^{}\s]+)\}\s*$'
    )
    _ANY_ANCHOR_RE = re.compile(r'\{#([^{}\s]+)\}')
    _INLINE_CODE_RE = re.compile(r'`[^`\n]*`')

    # 锚点标签前的小图标（灰色锚点 SVG，data URI 内嵌，Qt 富文本支持 img data URI）
    _ANCHOR_ICON_DATA = (
        "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjOTk5OTk5IiBzdHJva2Utd2lkdGg9IjIuNSIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMTIgM3YxMyIvPjxwYXRoIGQ9Ik0xMiA3YTQgNCAwIDAgMC00IDRoOGE0IDQgMCAwIDAtNC00eiIvPjxwYXRoIGQ9Ik01IDE2aDE0Ii8+PHBhdGggZD0iTTEyIDE2djQiLz48L3N2Zz4="
    )

    @staticmethod
    def _anchor_span(anchor_id: str, with_id: bool = False) -> str:
        """灰色上标锚点标签：锚点小图标 + 灰色锚点名。

        Qt 富文本不支持 class 选择器与 border/border-radius，但支持
        vertical-align:super 与 img 的 data URI，故用上标 + 内嵌 SVG 图标实现。
        """
        id_attr = f' id="{anchor_id}"' if with_id else ""
        return (
            f'<span{id_attr} style="vertical-align:super; color:#888888;">'
            f'<img src="{DocEditor._ANCHOR_ICON_DATA}" width="9" height="9"/>'
            f'{anchor_id}</span>'
        )

    def _add_anchor_tags(self, md_text: str) -> str:
        """把 {#锚点} 可视化：任意位置（标题或正文）渲染为红色高亮标签（锚点名）。

        - 标题行保留 {#锚点} 交给 attr_list 生成 id，跳转定位不受影响；
        - 正文中的 {#锚点} 替换为带 id 的标签，同样支持锚点定位；
        - 代码块（``` 与 ~~~）与行内代码（`...`）内的内容不处理。
        """
        lines = md_text.split("\n")
        out = []
        in_code = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code = not in_code
                out.append(line)
                continue
            if not in_code:
                # 保护行内代码，避免 {#id} 被误渲染
                code_spans = []
                line = self._INLINE_CODE_RE.sub(
                    lambda m: self._protect_code(m, code_spans), line
                )
                m = self._ANCHOR_TAG_RE.match(line)
                if m:
                    hashes, title, anchor_id = m.groups()
                    line = (
                        f'{hashes} {title} '
                        f'{self._anchor_span(anchor_id)} '
                        f'{{#{anchor_id}}}'
                    )
                else:
                    # 正文任意位置：{#id} 直接渲染为带 id 的标签
                    line = self._ANY_ANCHOR_RE.sub(
                        lambda mm: self._anchor_span(mm.group(1), with_id=True),
                        line,
                    )
                for i, span in enumerate(code_spans):
                    line = line.replace(f"\x00CODE{i}\x00", span)
            out.append(line)
        return "\n".join(out)

    @staticmethod
    def _protect_code(match, store: list) -> str:
        store.append(match.group(0))
        return f"\x00CODE{len(store) - 1}\x00"

    def _update_preview(self):
        md_text = self._add_anchor_tags(self._body_edit.toPlainText())
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

    def _on_preview_link_clicked(self, url: QUrl):
        """浏览态点击链接：内部文档链接跳转目标文档（含锚点定位），外部链接不跳转。

        markdown 文档链接格式: [链接文字](<文件相对路径>#[锚点])
        - <文件相对路径>: 相对当前文档所在目录的相对路径（./ 或 ../ 开头）
        - #[锚点]: 可选；目标文档以 {#锚点} 标记标题时，跳转后定位到该标题
        """
        href = unquote(url.toString())
        if not href:
            return
        # 带 scheme 的视为外部链接（http/https/mailto 等），点击不跳转
        if urlsplit(href).scheme:
            return
        path, _, anchor = href.partition("#")
        path = path.strip()
        # 防御：Python-Markdown 对含 # 的 <...> 包裹路径会保留并转义尖括号
        if path.startswith("<") and path.endswith(">"):
            path = path[1:-1]
        if not path:
            # 纯锚点：同文档内滚动定位（延迟到布局完成后执行）
            if anchor:
                QTimer.singleShot(0, lambda: self._preview.scrollToAnchor(anchor))
            return
        if self._current_rel:
            # 链接路径相对当前文档所在目录（./、../），解析为 project-root-relative
            path = posixpath.normpath(
                posixpath.join(posixpath.dirname(self._current_rel), path)
            )
        self.navigate_to_doc_anchor.emit(path, anchor)

    def jump_to_anchor(self, anchor: str):
        """切到浏览态并滚动到锚点对应的标题（目标文档需含 {#锚点} 标记）。"""
        if not anchor:
            return
        self._view_toggle.setChecked(False)  # 浏览态，刷新预览为最新 HTML
        # setHtml 后需等事件循环空闲完成布局，scrollToAnchor 才能正确定位
        QTimer.singleShot(0, lambda: self._preview.scrollToAnchor(anchor))

    def open_document(self, full_path: Path, rel_path: str, index: IndexManager, registry: Registry | None = None):
        self._current_path = full_path
        self._current_rel = rel_path
        self._index = index
        if registry is not None:
            self._registry = registry

        try:
            self._meta, self._body = FrontmatterParser.read_file(full_path)
            self._has_fm = True
        except Exception:
            # 无 frontmatter 的纯 Markdown：仍可打开编辑正文，Frontmatter 功能禁用
            try:
                self._body = full_path.read_text(encoding="utf-8")
            except OSError as e:
                QMessageBox.warning(self, "读取错误", f"无法读取文件: {e}")
                return
            self._meta = {}
            self._has_fm = False

        self._title.setText(rel_path)

        # 无 frontmatter 时禁用 Frontmatter 展开按钮并收起该区域
        self._fm_toggle.setEnabled(self._has_fm)
        self._fm_toggle.setChecked(False)
        self._fm_container.setVisible(False)
        self._fm_visible = False

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

        # implemented_in：仅当文档含该字段时显示「实现位置」表格，与 depends_on 并列切换
        has_impl = "implemented_in" in self._meta
        self._fm_btn_impl.setVisible(has_impl)
        self._impl_editor.populate(self._meta.get("implemented_in") or [])
        self._fm_btn_deps.setChecked(True)  # 打开文档时默认停留在 depends_on
        self._fm_stack.setCurrentIndex(0)

        self._body_edit.setPlainText(self._body)
        self._update_preview()
        self._set_editable(True)
        # 打开新文档时默认回到编辑态
        self._view_toggle.setChecked(True)

    def jump_to_line(self, line_number: int):
        """跳转到指定行并居中显示。"""
        block = self._body_edit.document().findBlockByNumber(max(0, line_number - 1))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self._body_edit.setTextCursor(cursor)
        self._body_edit.centerCursor()
        self._body_edit.setFocus()

    @Slot()
    def _on_deps_save(self, deps: list[dict]):
        if not self._current_path or not self._index:
            return
        self._meta["depends_on"] = deps
        # 用编辑框当前正文写盘，避免覆盖未保存的正文修改
        FrontmatterParser.write_file(
            self._current_path, self._meta, self._body_edit.toPlainText()
        )
        project_root = self._current_path.parent.parent
        self._index.rebuild(project_root / "ProjectSpec")
        self._index.save()
        self.document_saved.emit(self._current_rel)

    @Slot()
    def _on_impl_save(self, impls: list[dict]):
        """implemented_in 表格变更后写回 frontmatter。

        implemented_in 不参与依赖索引，无需重建 index，也不触发
        document_saved（避免无谓的依赖检查与仪表盘刷新）。
        """
        if not self._current_path:
            return
        self._meta["implemented_in"] = impls
        FrontmatterParser.write_file(
            self._current_path, self._meta, self._body_edit.toPlainText()
        )

    @Slot()
    def _on_save(self):
        if not self._current_path:
            return

        self._body = self._body_edit.toPlainText()

        if not self._has_fm:
            # 纯 Markdown（无 frontmatter）：只写正文，不生成 frontmatter
            try:
                self._current_path.write_text(self._body, encoding="utf-8")
            except OSError as e:
                QMessageBox.critical(self, "保存失败", str(e))
                return
            QMessageBox.information(self, "保存", f"已保存: {self._current_rel}")
            self.document_saved.emit(self._current_rel)
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

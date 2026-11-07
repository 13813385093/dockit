"""依赖图面板 — 可视化 depends_on 关系。"""
from pathlib import Path

from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)
from PySide6.QtGui import QColor

from src.app.engine.index import IndexManager, IndexEntry
from src.app.engine.registry import Registry


class DepGraphPanel(QWidget):
    """依赖图面板 — 列表模式展示依赖关系。"""
    
    navigate_to_doc = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_root: Path | None = None
        self._index: IndexManager | None = None
        self._registry: Registry | None = None
        
        self._build_ui()
    
    def _build_ui(self):
        """搭建静态布局。"""
        layout = QVBoxLayout(self)
        
        title = QLabel("依赖关系")
        title.setObjectName("DepGraphTitle")
        layout.addWidget(title)
        
        hint = QLabel("从文档树选择文档后切换到此面板查看依赖详情。")
        hint.setObjectName("DepGraphHint")
        layout.addWidget(hint)
        
        fwd_group = QGroupBox("依赖 (depends_on)")
        fwd_layout = QVBoxLayout(fwd_group)
        self._fwd_table = QTableWidget(0, 4)
        self._fwd_table.setHorizontalHeaderLabels(["文件路径", "文档描述", "所属模块", "版本"])
        self._fwd_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._fwd_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._fwd_table.doubleClicked.connect(self._on_fwd_double_clicked)
        fwd_layout.addWidget(self._fwd_table)
        layout.addWidget(fwd_group)
        
        rev_group = QGroupBox("被依赖 (reverse_deps)")
        rev_layout = QVBoxLayout(rev_group)
        self._rev_table = QTableWidget(0, 4)
        self._rev_table.setHorizontalHeaderLabels(["文件路径", "文档描述", "所属模块", "版本"])
        self._rev_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._rev_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._rev_table.doubleClicked.connect(self._on_rev_double_clicked)
        rev_layout.addWidget(self._rev_table)
        layout.addWidget(rev_group)
    
    @Slot(QTableWidgetItem)
    def _on_fwd_double_clicked(self, item: QTableWidgetItem):
        """双击正向依赖项时跳转到源文档。"""
        row = item.row()
        data = self._fwd_table.item(row, 0).data(Qt.UserRole)
        if data:
            self.navigate_to_doc.emit(data)
    
    @Slot(QTableWidgetItem)
    def _on_rev_double_clicked(self, item: QTableWidgetItem):
        """双击反向依赖项时跳转到源文档。"""
        row = item.row()
        data = self._rev_table.item(row, 0).data(Qt.UserRole)
        if data:
            self.navigate_to_doc.emit(data)
    
    def load_project(self, project_root: Path, index: IndexManager, registry: Registry = None):
        self._project_root = project_root
        self._index = index
        self._registry = registry
    
    def resizeEvent(self, event):
        """窗口大小变化时按5:2:2:1比例重新分配列宽。"""
        super().resizeEvent(event)
        self._adjust_column_widths()
    
    def _adjust_column_widths(self):
        """按5:2:2:1比例调整列宽。"""
        for table in [self._fwd_table, self._rev_table]:
            header = table.horizontalHeader()
            total_width = header.width()
            if total_width <= 0:
                return
            ratios = [5, 2, 2, 1]
            total_ratio = sum(ratios)
            for i, ratio in enumerate(ratios):
                header.resizeSection(i, int(total_width * ratio / total_ratio))
    
    def show_doc_deps(self, rel_path: str):
        """显示指定文档的依赖关系。"""
        if not self._index:
            return
        
        entry = self._index.get_entry(rel_path)
        if not entry:
            return
        
        self._populate_fwd_deps(entry.depends_on)
        self._populate_rev_deps(rel_path)
        
        self._adjust_column_widths()
    
    def _populate_fwd_deps(self, deps: list[dict]):
        """填充正向依赖表。"""
        self._fwd_table.setRowCount(len(deps))
        
        for i, dep in enumerate(deps):
            doc_path = str(dep.get("doc", ""))
            module = str(dep.get("module", ""))
            version = str(dep.get("version", ""))
            
            is_drifted = False
            actual_version = None
            
            if doc_path and self._index:
                entry = self._index.get_entry(doc_path)
                if entry:
                    actual_version = entry.version
                    if actual_version != version:
                        is_drifted = True
            
            desc = Path(doc_path).name if doc_path else "?"
            if self._registry and doc_path:
                entry = self._index.get_entry(doc_path) if self._index else None
                if entry and entry.doc_type:
                    type_def = self._registry.get(entry.doc_type)
                    if type_def and type_def.description:
                        desc = type_def.description
            
            item_path = QTableWidgetItem(doc_path)
            item_path.setData(Qt.UserRole, doc_path)
            item_desc = QTableWidgetItem(desc)
            item_module = QTableWidgetItem(module)
            item_version = QTableWidgetItem(version)
            
            if is_drifted and actual_version:
                item_version.setText(f"{version} → {actual_version}")
                red_color = QColor("#e74c3c")
                item_path.setForeground(red_color)
                item_desc.setForeground(red_color)
                item_module.setForeground(red_color)
                item_version.setForeground(red_color)
            
            self._fwd_table.setItem(i, 0, item_path)
            self._fwd_table.setItem(i, 1, item_desc)
            self._fwd_table.setItem(i, 2, item_module)
            self._fwd_table.setItem(i, 3, item_version)
    
    def _populate_rev_deps(self, target_path: str):
        """填充反向依赖表。"""
        from src.app.engine.deps import find_reverse_dependencies
        
        rev_entries = find_reverse_dependencies(target_path, self._index)
        
        self._rev_table.setRowCount(len(rev_entries))
        
        for i, entry in enumerate(rev_entries):
            doc_path = entry.path
            module = entry.module
            version = entry.version
            
            desc = Path(doc_path).name
            if self._registry and entry.doc_type:
                type_def = self._registry.get(entry.doc_type)
                if type_def and type_def.description:
                    desc = type_def.description
            
            item_path = QTableWidgetItem(doc_path)
            item_path.setData(Qt.UserRole, doc_path)
            item_desc = QTableWidgetItem(desc)
            item_module = QTableWidgetItem(module)
            item_version = QTableWidgetItem(version)
            
            if entry.status == "deprecated":
                orange_color = QColor("#e67e22")
                item_path.setForeground(orange_color)
                item_desc.setForeground(orange_color)
                item_module.setForeground(orange_color)
                item_version.setForeground(orange_color)
            elif entry.status == "archived":
                gray_color = QColor("#95a5a6")
                item_path.setForeground(gray_color)
                item_desc.setForeground(gray_color)
                item_module.setForeground(gray_color)
                item_version.setForeground(gray_color)
            
            self._rev_table.setItem(i, 0, item_path)
            self._rev_table.setItem(i, 1, item_desc)
            self._rev_table.setItem(i, 2, item_module)
            self._rev_table.setItem(i, 3, item_version)
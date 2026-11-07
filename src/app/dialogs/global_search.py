"""全局搜索对话框 — 支持跨文档全文搜索，在 QThread 中执行避免 UI 卡顿。"""
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot, QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QApplication,
    QLabel, QProgressBar,
)

from src.app.engine.index import IndexEntry


# ── 颜色常量 ──
COLOR_FILENAME = QColor(0, 100, 200)           # 文件名为蓝色
COLOR_LINE_NUM = QColor(128, 128, 128)         # 行号为灰色


class SearchWorker(QObject):
    """在后台线程中搜索匹配文本，每找到一个结果即发送信号。"""

    result_found = Signal(str, int, str)    # (file_path, line_number, line_text)
    search_finished = Signal(int)           # 总匹配数

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aborted = False

    def abort(self):
        """请求中止当前搜索。"""
        self._aborted = True

    @Slot(str, str, list)
    def search(self, search_text: str, project_root: str, file_paths: list):
        """执行搜索（在工作线程中运行）。"""
        self._aborted = False
        keyword = search_text.strip().lower()
        if not keyword:
            self.search_finished.emit(0)
            return

        root = Path(project_root)
        total_matches = 0

        for rel_path in file_paths:
            if self._aborted:
                break

            full_path = root / rel_path
            if not full_path.is_file():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = content.splitlines()
            for line_no, line in enumerate(lines, 1):
                if self._aborted:
                    break
                if keyword in line.lower():
                    display_line = self._truncate_line(line, keyword)
                    self.result_found.emit(rel_path, line_no, display_line)
                    total_matches += 1
            if self._aborted:
                break

        self.search_finished.emit(total_matches)

    @staticmethod
    def _truncate_line(line: str, keyword: str, context_chars: int = 60) -> str:
        """截取匹配行，保留搜索词上下文。"""
        lower = line.lower()
        idx = lower.find(keyword)
        if idx < 0:
            return line[:200]

        start = max(0, idx - context_chars)
        end = min(len(line), idx + len(keyword) + context_chars)

        truncated = line[start:end]
        if start > 0:
            truncated = "..." + truncated
        if end < len(line):
            truncated = truncated + "..."

        return truncated


class GlobalSearchDialog(QDialog):
    """全局搜索对话框。

    在用户按回车或点击"搜索"按钮后，在 QThread 中异步搜索所有文档。
    结果以树形结构展示：文件→匹配行。双击匹配行可关闭对话框并跳转。

    每次搜索创建全新的 QThread + SearchWorker，用完自动销毁。
    这样双击关闭时线程已经自然结束，不会触发 "QThread: Destroyed while running"。
    """

    navigate_to = Signal(str, int)  # (rel_path, line_number)

    def __init__(self, project_root: Path, entries: list[IndexEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局搜索")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        self._project_root = project_root
        self._file_paths = sorted(
            e.path for e in entries if e.status == "active"
        )

        self._result_path: str | None = None
        self._result_line: int = 0

        # 当前搜索的线程/worker（每次搜索新建，用完自动销毁）
        self._thread: QThread | None = None
        self._worker: SearchWorker | None = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── 顶部：搜索输入区域 ──
        input_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            f"搜索 {len(self._file_paths)} 个文件中的文本... (不区分大小写)"
        )
        self._search_input.returnPressed.connect(self._start_search)
        self._search_input.setMinimumHeight(32)
        input_layout.addWidget(self._search_input, 1)

        self._search_btn = QPushButton("搜索")
        self._search_btn.clicked.connect(self._start_search)
        self._search_btn.setMinimumHeight(32)
        input_layout.addWidget(self._search_btn)

        layout.addLayout(input_layout)

        # ── 状态标签 + 进度条 ──
        status_layout = QHBoxLayout()
        self._status_label = QLabel("输入关键字后按回车开始搜索")
        status_layout.addWidget(self._status_label, 1)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximum(0)  # 繁忙指示器
        self._progress_bar.setFixedWidth(120)
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setVisible(False)
        status_layout.addWidget(self._progress_bar)

        layout.addLayout(status_layout)

        # ── 中间：搜索结果树 ──
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["匹配结果", "位置"])
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._tree, 1)

        # ── 底部：信息栏 ──
        bottom_layout = QHBoxLayout()
        self._file_count_label = QLabel(f"共 {len(self._file_paths)} 个文件")
        bottom_layout.addWidget(self._file_count_label, 1)

        self._close_btn = QPushButton("关闭")
        self._close_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(self._close_btn)

        layout.addLayout(bottom_layout)

    # ── 搜索控制 ──

    def _start_search(self):
        text = self._search_input.text().strip()
        if not text:
            return

        # 清理上一次搜索的线程/worker
        self._cleanup_thread()

        # 重置 UI
        self._tree.clear()
        self._result_path = None
        self._result_line = 0
        self._status_label.setText("搜索中...")
        self._progress_bar.setVisible(True)
        self._search_btn.setEnabled(False)
        self._search_input.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # 创建全新的线程 + worker
        self._worker = SearchWorker()
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        # 将 worker 的信号连接到 UI 槽（跨线程自动排队）
        self._worker.result_found.connect(self._on_result_found)
        self._worker.search_finished.connect(self._on_search_finished)

        # 线程结束后自动清理 worker
        self._thread.finished.connect(self._worker.deleteLater)

        # 发起搜索
        self._thread.started.connect(lambda: self._worker.search(
            self._search_input.text().strip(),
            str(self._project_root),
            self._file_paths,
        ))
        self._thread.start()

    def _cleanup_thread(self):
        """安全清理上一次搜索的线程。"""
        if self._thread is not None:
            if self._thread.isRunning():
                if self._worker:
                    self._worker.abort()
                # 断开信号防止残留
                try:
                    self._worker.result_found.disconnect(self._on_result_found)
                except (TypeError, RuntimeError, AttributeError):
                    pass
                try:
                    self._worker.search_finished.disconnect(self._on_search_finished)
                except (TypeError, RuntimeError, AttributeError):
                    pass
                self._thread.quit()
                self._thread.wait(3000)
            self._thread = None
            self._worker = None

    @Slot(str, int, str)
    def _on_result_found(self, file_path: str, line_number: int, line_text: str):
        """收到一个匹配结果，更新树节点。"""
        file_item = self._find_file_item(file_path)
        if file_item is None:
            file_item = self._create_file_item(file_path)

        line_item = QTreeWidgetItem(file_item)
        line_item.setText(0, line_text)
        line_item.setText(1, f"行 {line_number}")
        line_item.setData(0, Qt.UserRole, (file_path, line_number))
        line_item.setForeground(1, COLOR_LINE_NUM)

        if file_item.isExpanded() is False and file_item.childCount() <= 1:
            file_item.setExpanded(True)

    @Slot(int)
    def _on_search_finished(self, total_matches: int):
        """搜索完成，恢复 UI。"""
        self._progress_bar.setVisible(False)
        self._search_btn.setEnabled(True)
        self._search_input.setEnabled(True)
        QApplication.restoreOverrideCursor()

        if total_matches == 0:
            self._status_label.setText("未找到匹配结果")
            no_result = QTreeWidgetItem(self._tree)
            no_result.setText(0, "（无匹配结果）")
            no_result.setFlags(no_result.flags() & ~Qt.ItemIsSelectable)
            no_result.setForeground(0, QColor(180, 180, 180))
        else:
            matched_files = self._tree.topLevelItemCount()
            self._status_label.setText(
                f"搜索完成：共 {total_matches} 处匹配，分布在 {matched_files} 个文件中"
            )

        # 线程已自然结束（worker 在 search() 返回后发出 search_finished，
        # 事件循环处理完这个信号后线程就会退出）
        # 这里不做 cleanup，留给下一次 _start_search 或 closeEvent

    # ── 树节点辅助方法 ──

    def _find_file_item(self, file_path: str) -> QTreeWidgetItem | None:
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == file_path:
                return item
        return None

    def _create_file_item(self, file_path: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem(self._tree)
        item.setText(0, file_path)
        item.setData(0, Qt.UserRole, file_path)
        item.setForeground(0, COLOR_FILENAME)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        return item

    # ── 双击导航 ──

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not isinstance(data, tuple) or len(data) != 2:
            return

        file_path, line_number = data
        self._result_path = file_path
        self._result_line = line_number
        self.navigate_to.emit(file_path, line_number)
        self.accept()

    # ── 生命周期 ──

    def closeEvent(self, event):
        """关闭对话框时清理线程。"""
        self._cleanup_thread()
        super().closeEvent(event)

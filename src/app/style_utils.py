"""QSS 样式表加载工具 — 从 resources/styles/ 加载 .qss 文件。"""
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget


_STYLES_DIR = Path(__file__).resolve().parent / "resources" / "styles"


def load_stylesheet(target: QWidget | None = None) -> None:
    """加载 app.qss 到 QApplication（target=None）或指定 widget。"""
    qss_path = _STYLES_DIR / "app.qss"
    if not qss_path.exists():
        return
    css = qss_path.read_text(encoding="utf-8")
    if target is None:
        app = QApplication.instance()
        if app:
            app.setStyleSheet(css)
    else:
        target.setStyleSheet(css)

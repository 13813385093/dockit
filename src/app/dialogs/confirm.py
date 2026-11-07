"""通用确认对话框 — 显示消息 + Ok/Cancel。"""
from PySide6.QtWidgets import QMessageBox


def confirm(parent, title: str, message: str) -> bool:
    """通用确认弹窗。返回 True=用户确认。"""
    reply = QMessageBox.question(
        parent, title, message,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return reply == QMessageBox.Yes

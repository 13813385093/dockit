"""图标加载工具 — 从 resources/icons/ 加载 SVG 图标。"""
from pathlib import Path

from PySide6.QtGui import QIcon, QColor
from PySide6.QtCore import Qt

_ICONS_DIR = Path(__file__).resolve().parent / "resources" / "icons"

_ICON_CACHE: dict[str, QIcon] = {}


def get_icon(name: str) -> QIcon:
    """按名称获取 QIcon（缓存）。"""
    if name in _ICON_CACHE:
        return _ICON_CACHE[name]

    svg_path = _ICONS_DIR / f"{name}.svg"
    if svg_path.exists():
        icon = QIcon(str(svg_path))
        _ICON_CACHE[name] = icon
        return icon

    png_path = _ICONS_DIR / f"{name}.png"
    if png_path.exists():
        icon = QIcon(str(png_path))
        _ICON_CACHE[name] = icon
        return icon

    # fallback: 返回空 QIcon
    return QIcon()


def set_button_icon(btn, name: str):
    """给 QPushButton / QAction 设置 SVG 图标。"""
    icon = get_icon(name)
    if not icon.isNull():
        btn.setIcon(icon)

"""doc-kit UI 入口点。

用法:
    python main.py                          # 启动 GUI
    python main.py /path/to/project         # 启动并直接加载项目
"""
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 from src.app.xxx 导入能正确解析
if not getattr(sys, "frozen", False):
    _project_root = Path(__file__).resolve().parent.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from main_window import MainWindow
from qt_material import apply_stylesheet

def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "src" / "app"
    return Path(__file__).resolve().parent

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DocKit Studio")
    app.setOrganizationName("DocKit Studio")
    
    app_root = get_app_root()
    icon_path = app_root / "resources" / "icons" / "dropbox.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    window = MainWindow()
    window.show()

    # 支持命令行参数直接加载项目
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1])
        if project_root.exists():
            window.load_project(project_root.resolve())

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

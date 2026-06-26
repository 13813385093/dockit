"""doc-kit UI 入口点。

用法:
    python main.py                          # 启动 GUI
    python main.py /path/to/project         # 启动并直接加载项目
"""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from src.app.main_window import MainWindow
from qt_material import apply_stylesheet

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DocKit Studio")
    app.setOrganizationName("DocKit Studio")
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

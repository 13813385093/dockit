"""doc-kit UI 入口点。

用法:
    python main.py                          # 启动 GUI
    python main.py /path/to/project         # 启动并直接加载项目
    python main.py init <项目> [--profile minimal|full] [--name <名称>]   # 初始化项目
    python main.py install-skills <目标目录>                              # 安装 skills

doc-kit 工具是工具链（skills + CLI）的唯一部署/安装入口：
init 生成 ProjectSpec 骨架与 .doc-kit/ 全部资源（含 .doc-kit/cli/），
install-skills 把随包携带的 skills 安装到 agent 的 skills 目录。
"""
import argparse
import shutil
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


def get_skills_dir() -> Path:
    """随包携带的 skills 目录（含 scripts/ 与各 spec-*/SKILL.md）。"""
    return get_app_root().parent.parent / "skills"


def _cmd_init(project_root: Path, profile: str, project_name: str | None) -> int:
    """doc-kit init：初始化项目（ProjectSpec 骨架 + .doc-kit 全部资源）。"""
    from src.app.engine.commands.init_utils import init_project

    name = init_project(project_root, project_name=project_name, profile=profile)
    print(f"✅ 项目「{name}」已初始化")
    print(f"  ProjectSpec: {project_root / 'ProjectSpec'}")
    print(f"  .doc-kit: config / registry / templates / index / cli / skills")
    print(f"  skills 副本已装入 .doc-kit/skills/，可人工复制到 agent 的 skills 目录")
    return 0


def _cmd_install_skills(target: str) -> int:
    """doc-kit install-skills：把随包 skills 安装到目标目录。"""
    src = get_skills_dir()
    dst = Path(target).resolve()
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for skill_dir in sorted(src.glob("spec-*")):
        md = skill_dir / "SKILL.md"
        if not md.exists():
            continue
        target_dir = dst / skill_dir.name
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md, target_dir / "SKILL.md")
        count += 1
    print(f"✅ 已安装 {count} 个 skills 到 {dst}")
    return 0


def run_cli(argv: list[str]) -> int | None:
    """处理 CLI 子命令。返回退出码；无子命令时返回 None（继续启动 GUI）。"""
    if not argv:
        return None

    parser = argparse.ArgumentParser(prog="doc-kit", add_help=False)
    sub = parser.add_subparsers(dest="command")
    p_init = sub.add_parser("init", help="初始化项目（ProjectSpec + .doc-kit 资源）")
    p_init.add_argument("project", help="项目根目录")
    p_init.add_argument("--profile", default="minimal", choices=["minimal", "full"])
    p_init.add_argument("--name", default=None, help="项目名称")
    p_inst = sub.add_parser("install-skills", help="安装 skills 到 agent skills 目录")
    p_inst.add_argument("target", help="目标 skills 目录（如 ~/.reasonix/skills）")

    # 兼容旧行为：`main.py /path/to/project` —— 非子命令时交给 GUI 处理
    if argv[0] not in ("init", "install-skills"):
        return None

    args = parser.parse_args(argv)
    if args.command == "init":
        return _cmd_init(Path(args.project), args.profile, args.name)
    if args.command == "install-skills":
        return _cmd_install_skills(args.target)
    return None


def main():
    # CLI 子命令模式：stdout 统一 UTF-8（Windows GBK 控制台无法编码 ✅ 等字符）
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    exit_code = run_cli(sys.argv[1:])
    if exit_code is not None:
        sys.exit(exit_code)

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

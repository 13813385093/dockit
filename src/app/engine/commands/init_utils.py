"""项目初始化的纯逻辑函数 — 从 CLI init.py 提取，无 typer 依赖。"""
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from src.app.engine.frontmatter import FrontmatterParser
from src.app.engine.index import IndexManager, IndexEntry
from src.app.engine.registry import Registry

def _get_builtin_templates_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "src" / "app" / "templates"
    return Path(__file__).resolve().parent.parent.parent / "templates"

BUILTIN_TEMPLATES_DIR = _get_builtin_templates_dir()


def _get_cli_source_dir() -> Path:
    """返回工具链 CLI 源码目录（skills/scripts）。

    开发态 = 仓库根 skills/scripts；打包态 = 随包分发的 skills/scripts。
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "skills" / "scripts"
    return Path(__file__).resolve().parents[4] / "skills" / "scripts"


def _get_skills_source_dir() -> Path:
    """返回随包分发的 skills 目录（spec-*/SKILL.md）。

    开发态 = 仓库根 skills；打包态 = _MEIPASS/skills。
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "skills"
    return Path(__file__).resolve().parents[4] / "skills"


def get_project_name(project_root: Path) -> str:
    """从 config.yaml 或目录名获取项目名称。"""
    config_path = project_root / ".doc-kit" / "config.yaml"
    if config_path.exists():
        import yaml
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if data and "project_name" in data:
                return data["project_name"]
        except Exception:
            pass
    return project_root.name


def generate_charter(project_name: str, now: str) -> str:
    """生成 charter.md 内容。"""
    template_path = BUILTIN_TEMPLATES_DIR / "charter.md"
    tpl = Template(template_path.read_text(encoding="utf-8"))
    return tpl.safe_substitute(project_name=project_name, now=now)


def generate_full_file(template_name: str, now: str) -> str:
    """生成完整模式下的单个文档。"""
    template_path = BUILTIN_TEMPLATES_DIR / template_name
    tpl = Template(template_path.read_text(encoding="utf-8"))
    return tpl.safe_substitute(now=now)


def create_minimal_structure(project_docs: Path, project_name: str, now: str) -> list[Path]:
    """创建精简模式骨架：单个 charter.md。"""
    project_docs.mkdir(parents=True, exist_ok=True)
    charter_path = project_docs / "charter.md"
    content = generate_charter(project_name, now)
    charter_path.write_text(content, encoding="utf-8")
    return [charter_path]


def create_full_structure(project_docs: Path, project_name: str, now: str) -> list[Path]:
    """创建完整模式骨架：7 个顶层文件直接放在 ProjectSpec/ 根。"""
    project_docs.mkdir(parents=True, exist_ok=True)
    files = [
        "business-context.md", "technical-framework.md",
        "non-functional-constraints.md", "global-policies.md",
        "inter-module-contracts.md", "stakeholders.md",
        "release-policy.md",
    ]
    created = []
    for fname in files:
        fpath = project_docs / fname
        content = generate_full_file(fname, now)
        fpath.write_text(content, encoding="utf-8")
        created.append(fpath)
    return created


def build_index(project_docs: Path, project_root: Path, created_files: list[Path]) -> IndexManager:
    """从创建的文件构建初始索引。"""
    kit_dir = project_root / ".doc-kit"
    kit_dir.mkdir(parents=True, exist_ok=True)
    index_path = kit_dir / "index.json"
    mgr = IndexManager(index_path)

    for fpath in created_files:
        try:
            meta, _ = FrontmatterParser.read_file(fpath)
            rel_path = str(fpath.relative_to(project_root)).replace("\\", "/")
            entry = IndexEntry(
                path=rel_path,
                doc_type=meta.get("doc_type", "unknown"),
                module=meta.get("module", ""),
                level=meta.get("level", ""),
                version=str(meta.get("version", "0.0.0")),
                status=meta.get("status", "active"),
                depends_on=meta.get("depends_on", []),
                mtime=FrontmatterParser.now_iso(),
            )
            mgr.add_entry(entry)
        except Exception:
            pass

    mgr.save()
    return mgr


def create_config(project_root: Path, project_name: str, profile: str):
    """创建 .doc-kit/config.yaml。"""
    import yaml
    kit_dir = project_root / ".doc-kit"
    kit_dir.mkdir(parents=True, exist_ok=True)
    config_path = kit_dir / "config.yaml"
    data = {
        "project_name": project_name,
        "profile": profile,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }
    config_path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def create_registry(project_root: Path):
    """创建默认 .doc-kit/registry.yaml。"""
    kit_dir = project_root / ".doc-kit"
    kit_dir.mkdir(parents=True, exist_ok=True)
    reg_path = kit_dir / "registry.yaml"
    reg_path.write_text(
        Registry.get_default_registry_yaml(),
        encoding="utf-8",
    )


def copy_templates(project_root: Path):
    """复制内置模板到 .doc-kit/templates/。"""
    kit_dir = project_root / ".doc-kit"
    tmpl_dir = kit_dir / "templates"
    tmpl_dir.mkdir(parents=True, exist_ok=True)
    for src_path in BUILTIN_TEMPLATES_DIR.glob("*.md"):
        dst_path = tmpl_dir / src_path.name
        shutil.copy2(src_path, dst_path)


def copy_cli(project_root: Path) -> list[str]:
    """把工具链 CLI 安装到 .doc-kit/cli/（与 copy_templates 同构）。

    doc-kit 的 CLI 与 skills 是一套整体工具链：项目初始化时把 CLI 落到
    项目内固定路径，skills 之后统一调用 `<项目根>/.doc-kit/cli/cli.py`。
    返回复制成功的文件名列表。
    """
    kit_dir = project_root / ".doc-kit"
    cli_dir = kit_dir / "cli"
    cli_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    src_dir = _get_cli_source_dir()
    for src_path in sorted(src_dir.glob("*.py")):
        dst_path = cli_dir / src_path.name
        shutil.copy2(src_path, dst_path)
        copied.append(src_path.name)
    return copied


def copy_skills(project_root: Path) -> list[str]:
    """把 skills 本体（spec-*/SKILL.md）复制到 .doc-kit/skills/。

    大多数 AI agent 不识别 .doc-kit/ 目录，此副本供人工后续搬运到
    agent 的 skills 目录（如 ~/.reasonix/skills/）。SKILL.md 内的调用
    路径统一为 `<项目根>/.doc-kit/cli/cli.py`，搬运后依然指向本项目 CLI。
    返回复制成功的 skill 目录名列表。
    """
    kit_dir = project_root / ".doc-kit"
    dst_root = kit_dir / "skills"
    dst_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    src_root = _get_skills_source_dir()
    for skill_dir in sorted(src_root.glob("spec-*")):
        md = skill_dir / "SKILL.md"
        if not md.exists():
            continue
        dst = dst_root / skill_dir.name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md, dst / "SKILL.md")
        copied.append(skill_dir.name)
    return copied


def copy_guidance(project_root: Path) -> list[str]:
    """把能力库（guidance/doc-capabilities/*.md）复制到 .doc-kit/skills/guidance/。

    与 copy_skills 同构：能力库是 AI 写入 ProjectSpec 前的规范来源，
    SKILL.md 统一以 `<项目根>/.doc-kit/skills/guidance/doc-capabilities/`
    引用。返回复制成功的文件名列表。
    """
    kit_dir = project_root / ".doc-kit"
    dst_dir = kit_dir / "skills" / "guidance" / "doc-capabilities"
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    src_dir = _get_skills_source_dir() / "guidance" / "doc-capabilities"
    if not src_dir.is_dir():
        return copied
    for src_path in sorted(src_dir.glob("*.md")):
        shutil.copy2(src_path, dst_dir / src_path.name)
        copied.append(src_path.name)
    return copied


def init_project(
    project_root: Path,
    project_name: str | None = None,
    profile: str = "minimal",
) -> str:
    """完整的项目初始化流程。

    返回项目名称。

    若 project-docs/ 已存在则跳过创建步骤，但补全 .doc-kit/ 配置。
    """
    project_docs = project_root / "ProjectSpec"
    now = FrontmatterParser.now_iso()
    name = project_name or get_project_name(project_root)
    created: list[Path] = []

    if not project_docs.exists():
        if profile == "minimal":
            created = create_minimal_structure(project_docs, name, now)
        else:
            created = create_full_structure(project_docs, name, now)

    # 补全 .doc-kit/ 配置（幂等）
    create_config(project_root, name, profile)
    create_registry(project_root)
    copy_templates(project_root)
    copy_cli(project_root)
    copy_skills(project_root)
    copy_guidance(project_root)
    build_index(project_docs, project_root, created)

    return name

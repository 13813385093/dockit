"""项目初始化的纯逻辑函数 — 从 CLI init.py 提取，无 typer 依赖。"""
import hashlib
import json
import re
import shutil
import sys
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

# 已下线的复合类型模板：重新初始化时从目标目录清理，避免残留
LEGACY_TEMPLATE_FILES = ("charter.md", "module-design.md", "feature-package.md")

# 已下线的复合类型能力说明：重新初始化时从副本目录清理，避免残留
LEGACY_CAPABILITY_FILES = ("charter.md", "module_design.md", "feature_package.md")


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


def generate_full_file(template_name: str, now: str) -> str:
    """生成单个顶层文档。"""
    template_path = BUILTIN_TEMPLATES_DIR / template_name
    tpl = Template(template_path.read_text(encoding="utf-8"))
    return tpl.safe_substitute(now=now)


def create_full_structure(project_docs: Path, project_name: str, now: str) -> list[Path]:
    """创建项目文档骨架：7 个顶层文件直接放在 ProjectSpec/ 根。"""
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
            )
            mgr.add_entry(entry)
        except Exception:
            pass

    mgr.save()
    return mgr


def create_config(project_root: Path, project_name: str):
    """创建 .doc-kit/config.yaml。"""
    import yaml
    kit_dir = project_root / ".doc-kit"
    kit_dir.mkdir(parents=True, exist_ok=True)
    config_path = kit_dir / "config.yaml"
    data = {
        "project_name": project_name,
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
    """复制内置模板到 .doc-kit/templates/。

    复制完成后，仅从目标目录清理 LEGACY_TEMPLATE_FILES 列出的已下线
    复合类型模板残留（这些模板已不再随包分发）；其它文件一律不删除，
    用户自行放置的自定义模板会原样保留。文件不存在时不报错，可重复调用。
    """
    kit_dir = project_root / ".doc-kit"
    tmpl_dir = kit_dir / "templates"
    tmpl_dir.mkdir(parents=True, exist_ok=True)
    for src_path in BUILTIN_TEMPLATES_DIR.glob("*.md"):
        dst_path = tmpl_dir / src_path.name
        shutil.copy2(src_path, dst_path)
    for legacy_name in LEGACY_TEMPLATE_FILES:
        (tmpl_dir / legacy_name).unlink(missing_ok=True)


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

    复制完成后，仅从副本目录清理 LEGACY_CAPABILITY_FILES 列出的已下线
    复合类型能力文件残留（这些能力说明已不再随包分发，留着会让 AI 按已
    废除的规范写作）；其它文件一律不删除，用户自行放置的能力文件会原样
    保留。文件不存在时不报错，可重复调用。
    """
    kit_dir = project_root / ".doc-kit"
    dst_dir = kit_dir / "skills" / "guidance" / "doc-capabilities"
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    src_dir = _get_skills_source_dir() / "guidance" / "doc-capabilities"
    if not src_dir.is_dir():
        # 源目录缺失是新版工具随包分发的异常情况，但已下线残留的清理与
        # 源目录是否存在无关：先按同一份清单清理再返回，旧项目副本在这种
        # 异常下也能清掉已废除的能力说明。清理幂等，可安全重复调用。
        for legacy_name in LEGACY_CAPABILITY_FILES:
            (dst_dir / legacy_name).unlink(missing_ok=True)
        return copied
    for src_path in sorted(src_dir.glob("*.md")):
        shutil.copy2(src_path, dst_dir / src_path.name)
        copied.append(src_path.name)
    for legacy_name in LEGACY_CAPABILITY_FILES:
        (dst_dir / legacy_name).unlink(missing_ok=True)
    return copied


def write_toolchain_manifest(project_root: Path) -> dict:
    """把工具链版本与各副本的 sha256 写入 .doc-kit/toolchain.json。

    为什么需要：init 是把工具链**快照复制**进项目，此后仓库与项目各自演化。
    「新技能 + 旧 CLI」时，旧 CLI 会静默丢弃它不认识的字段（如 implemented_in），
    命令还报成功。这份清单让 `cli.py tool status` 能发现版本错配与副本被改动。

    版本号从**刚复制过去的 cli.py** 里解析（单一事实源，避免与应用侧重复维护
    一份常量而在打包/冻结场景下漂移）；解析不到时记录 None，tool status 会
    按"版本不一致"处理。
     """
    kit_dir = project_root / ".doc-kit"
    version = None
    cli_copy = kit_dir / "cli" / "cli.py"
    if cli_copy.exists():
        m = re.search(r'^TOOLCHAIN_VERSION\s*=\s*["\']([^"\']+)["\']', cli_copy.read_text(encoding="utf-8"), re.M)
        if m:
            version = m.group(1)

    files: dict[str, str] = {}
    for sub in ("cli", "skills", "templates"):
        base = kit_dir / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                rel = path.relative_to(project_root).as_posix()
                files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "toolchain_version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    (kit_dir / "toolchain.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def init_project(
    project_root: Path,
    project_name: str | None = None,
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
        created = create_full_structure(project_docs, name, now)

    # 补全 .doc-kit/ 配置（幂等）
    create_config(project_root, name)
    create_registry(project_root)
    copy_templates(project_root)
    copy_cli(project_root)
    copy_skills(project_root)
    copy_guidance(project_root)
    write_toolchain_manifest(project_root)
    build_index(project_docs, project_root, created)

    return name

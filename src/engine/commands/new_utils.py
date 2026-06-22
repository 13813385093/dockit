"""新建文档的纯逻辑函数 — 从 CLI new.py 提取，无 typer 依赖。"""
from pathlib import Path
from string import Template

from src.engine.frontmatter import FrontmatterParser
from src.engine.validation import parse_module_path

# 内置模板目录
BUILTIN_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def resolve_template_path(template_name: str, kit_dir: Path | None) -> Path:
    """解析模板路径，支持本地覆盖。

    优先级: .doc-kit/templates/{name} → 内置 templates/{name}
    """
    if kit_dir:
        local_path = kit_dir / "templates" / template_name
        if local_path.exists():
            return local_path
    builtin_path = BUILTIN_TEMPLATES_DIR / template_name
    if builtin_path.exists():
        return builtin_path
    raise FileNotFoundError(f"Template not found: {template_name}")


def fmt_depends_on_yaml(depends_on: list[dict]) -> str:
    """格式化 depends_on 列表为缩进 YAML 字符串。"""
    if not depends_on:
        return ""
    lines = []
    for dep in depends_on:
        lines.append(f"  - doc: {dep['doc']}")
        lines.append(f"    module: {dep['module']}")
        lines.append(f'    version: "{dep["version"]}"')
    return "\n" + "\n".join(lines)


def render_template(
    template_name: str,
    module: str,
    feature: str | None,
    depends_on: list[dict],
    now: str,
    kit_dir: Path | None = None,
) -> str:
    """渲染模板。"""
    template_path = resolve_template_path(template_name, kit_dir)
    tpl = Template(template_path.read_text(encoding="utf-8"))
    return tpl.safe_substitute(
        module=module,
        feature=feature or "",
        depends_on_yaml=fmt_depends_on_yaml(depends_on),
        now=now,
    )


def resolve_path(
    project_docs: Path,
    doc_type_def,
    module: str,
    feature: str | None,
) -> Path:
    """确定新文档的文件路径。"""
    level = doc_type_def.level

    if level == "top":
        return project_docs / doc_type_def.template

    main_module, sub_path = parse_module_path(module)
    module_dir = project_docs / f"module-{main_module}"
    if sub_path:
        module_dir = module_dir / sub_path

    if level == "module":
        return module_dir / doc_type_def.template

    if level == "feature":
        if not feature:
            raise ValueError("Feature-level document requires --feature")
        feature_dir = module_dir / "features" / feature
        return feature_dir / doc_type_def.template

    raise ValueError(f"Unknown level: {level}")

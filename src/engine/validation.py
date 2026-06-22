"""Parameter validation for doc-kit commands."""
from __future__ import annotations
from src.engine.registry import DocTypeDef


def validate_new_params(
    doc_type_def: DocTypeDef,
    module: str | None,
    feature: str | None,
) -> tuple[list[str], list[str]]:
    """Validate parameters for `doc-kit new` command.

    Args:
        doc_type_def: The document type definition from Registry.
        module: --module option value (or None).
        feature: --feature option value (or None).

    Returns:
        (errors, warnings): errors cause command to abort,
            warnings are informational only.
    """
    errors: list[str] = []
    warnings: list[str] = []
    level = doc_type_def.level

    if level == "top":
        if module is not None:
            warnings.append(
                f"'{doc_type_def.doc_type}' 为顶层类型，--module 参数将被忽略"
            )
        if feature is not None:
            warnings.append(
                f"'{doc_type_def.doc_type}' 为顶层类型，--feature 参数将被忽略"
            )

    elif level == "module":
        if module is None:
            errors.append(
                f"'{doc_type_def.doc_type}' 为模块级类型，必需 --module 参数"
            )
        if feature is not None:
            errors.append(
                f"'{doc_type_def.doc_type}' 为模块级类型，不需要 --feature 参数"
            )

    elif level == "feature":
        missing = []
        if module is None:
            missing.append("--module")
        if feature is None:
            missing.append("--feature")
        if missing:
            errors.append(
                f"'{doc_type_def.doc_type}' 为功能级类型，缺少必需参数: {', '.join(missing)}"
            )

    return errors, warnings


def parse_module_path(module: str) -> tuple[str, str | None]:
    """Parse a module path string into main module and submodule path.

    Examples:
        "core"         → ("core", None)
        "core.sub"     → ("core", "sub-modules/sub")
        "a.b.c"        → ("a", "sub-modules/b/sub-modules/c")
    """
    parts = module.split(".")
    main = parts[0]
    if len(parts) == 1:
        return main, None

    sub_parts = []
    for p in parts[1:]:
        sub_parts.append("sub-modules")
        sub_parts.append(p)
    return main, "/".join(sub_parts)


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse semver string 'major.minor.patch' into a tuple of ints.

    Raises ValueError if format is invalid.
    """
    import re
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        raise ValueError(f"Invalid version format: '{version}' (must be major.minor.patch)")
    parts = version.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def increment_version(ver: tuple[int, int, int], level: str = "patch") -> tuple[int, int, int]:
    """Increment version tuple by the specified level.

    Args:
        ver: (major, minor, patch) tuple
        level: 'patch' (default), 'minor', or 'major'

    Returns:
        New version tuple.
    """
    major, minor, patch = ver
    if level == "major":
        return (major + 1, 0, 0)
    elif level == "minor":
        return (major, minor + 1, 0)
    else:  # patch
        return (major, minor, patch + 1)


def format_version(ver: tuple[int, int, int]) -> str:
    """Format version tuple back to semver string."""
    return f"{ver[0]}.{ver[1]}.{ver[2]}"

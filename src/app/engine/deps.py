"""Dependency derivation and version drift detection."""
from __future__ import annotations
from pathlib import Path

from src.app.engine.index import IndexManager, IndexEntry
from src.app.engine.registry import DocTypeDef


LEVEL_ORDER = {"top": 0, "module": 1, "feature": 2}


def derive_initial_depends_on(
    doc_type_def: DocTypeDef,
    module: str,
    index: IndexManager,
    docs_root: Path,
) -> list[dict]:
    """Automatically derive initial depends_on for a new document.

    Follows the dependency direction rules:
    - Level N can depend on Level ≤ N (upper levels)
    - Same module or parent module only (no cross-module)

    Returns list of {doc, module, version} dicts.

    说明：当前项目决策为「depends_on 由人工通过 doc-kit 工具维护」，
    本函数是「工具自动推导初始依赖」的保留实现（指南 §3.5.7 原意），
    当前未被 UI 或 CLI 调用，保留备用，勿删除。
    """
    new_level = LEVEL_ORDER.get(doc_type_def.level, 99)
    results: list[dict] = []

    # If index is empty (no existing docs), try rebuilding
    entries = index.list_entries()
    if not entries and docs_root.exists():
        index.rebuild(docs_root)
        entries = index.list_entries()

    for entry in entries:
        entry_level = LEVEL_ORDER.get(entry.level, 99)

        # Rule 1: Can only depend on higher or same level
        if entry_level > new_level:
            continue

        # Rule 2: Same level = same module only
        if entry_level == new_level and entry.module != module:
            continue

        # Rule 3: Module-level can depend on top-level (any module)
        #         Feature-level can depend on top-level or same-module module-level
        if new_level >= 1 and entry_level == 0:
            # Top-level docs are always valid dependencies
            pass
        elif new_level >= 2 and entry_level == 1:
            # Module-level: only same module
            if entry.module != module:
                continue
        elif new_level == 1 and entry_level == 0:
            # Module → Top: always valid
            pass
        else:
            # Same level, same module (handled by rule 2)
            if entry.module != module:
                continue

        results.append({
            "doc": Path(entry.path).name,
            "module": entry.module,
            "version": entry.version,
        })

    return results


def check_version_drift(
    index: IndexManager,
) -> list[dict]:
    """Check all depends_on declarations for version drift.

    Returns list of drift dicts: {doc, dep_name, declared, actual}.
    actual is None if the dependency document is not found.
    """
    drifts: list[dict] = []
    for entry in index.list_entries():
        for dep in (entry.depends_on or []):
            dep_doc = dep.get("doc", "")
            dep_version = dep.get("version", "")

            # 仅使用完整路径精确匹配
            found = None
            for other in index.list_entries():
                if other.path == dep_doc:
                    found = other
                    break
            
            # 如果找不到依赖文档，也视为漂移问题
            if not found:
                drifts.append({
                    "doc": entry.path,
                    "dep_name": dep_doc,
                    "declared": dep_version,
                    "actual": None,
                })
            elif found.version != dep_version:
                drifts.append({
                    "doc": entry.path,
                    "dep_name": dep_doc,
                    "declared": dep_version,
                    "actual": found.version,
                })
    return drifts


def find_reverse_dependencies(target_path: str, index: IndexManager) -> list[IndexEntry]:
    """Find all documents that declare a dependency on target_path.

    Returns list of IndexEntry objects whose depends_on includes target_path.
    """
    target_name = Path(target_path).name
    results: list[IndexEntry] = []
    for entry in index.list_entries():
        for dep in (entry.depends_on or []):
            dep_doc = dep.get("doc", "")
            # 同时支持完整路径匹配和文件名匹配
            if dep_doc == target_path or Path(dep_doc).name == target_name:
                results.append(entry)
                break
    return results


def check_deprecated_deps(index: IndexManager) -> list[dict]:
    """Find all depends_on that point to deprecated documents.

    Returns list of dicts: {doc, dep_name, dep_status}.
    """
    results: list[dict] = []
    for entry in index.list_entries():
        for dep in (entry.depends_on or []):
            dep_doc = dep.get("doc", "")

            # 仅使用完整路径精确匹配
            found = None
            for other in index.list_entries():
                if other.path == dep_doc:
                    found = other
                    break
            
            if found and found.status == "deprecated":
                results.append({
                    "doc": entry.path,
                    "dep_name": dep_doc,
                    "dep_status": found.status,
                })
    return results

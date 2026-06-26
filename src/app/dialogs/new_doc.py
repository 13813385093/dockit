"""新建文档对话框 — 智能判断层级，已存在文件灰色不可选。"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QRadioButton, QComboBox,
    QListWidget, QListWidgetItem, QDialogButtonBox,
    QGroupBox, QMessageBox, QAbstractItemView, QWidget,
)

from src.engine.index import IndexManager, IndexEntry
from src.engine.registry import Registry, DocTypeDef
from src.engine.frontmatter import FrontmatterParser
from src.engine.validation import parse_module_path
from src.engine.commands.new_utils import render_template


class NewDocDialog(QDialog):
    """新建文档对话框 — 智能创建。"""

    LEVELS = {"top": "顶层", "module": "模块级", "feature": "功能级"}

    def __init__(self, registry: Registry, project_root: Path,
                 index: IndexManager, context_path: str | None = None,
                 preset_level: str | None = None,
                 preset_module: str | None = None,
                 preset_feature: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._registry = registry
        self._project_root = project_root
        self._index = index
        self._project_docs = project_root / "ProjectSpec"
        self._kit_dir = project_root / ".doc-kit"
        # context_path: 右键所在的文档路径，用于预选层级/模块
        self._context_path = context_path
        # preset: 右键节点决定的强制预设值
        self._preset_level = preset_level
        self._preset_module = preset_module
        self._preset_feature = preset_feature

        self.setWindowTitle("新建文档")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # ── 层级选择 ──
        level_group = QGroupBox("目标层级")
        level_layout = QVBoxLayout(level_group)

        self._radio_top = QRadioButton("顶层 (ProjectSpec/)")
        self._radio_module = QRadioButton("模块级")
        self._radio_feature = QRadioButton("功能级")
        self._radio_top.toggled.connect(self._on_level_changed)
        self._radio_module.toggled.connect(self._on_level_changed)
        self._radio_feature.toggled.connect(self._on_level_changed)

        level_layout.addWidget(self._radio_top)
        level_layout.addWidget(self._radio_module)
        level_layout.addWidget(self._radio_feature)

        # 模块选择（模块/功能级需要）
        self._module_widget = QWidget()
        module_row = QHBoxLayout(self._module_widget)
        module_row.setContentsMargins(0, 0, 0, 0)
        module_row.addWidget(QLabel("  模块:"))
        self._module_combo = QComboBox()
        self._module_combo.setMinimumWidth(200)
        self._populate_modules()
        self._module_combo.currentIndexChanged.connect(self._on_module_changed)
        module_row.addWidget(self._module_combo)
        module_row.addStretch()
        self._module_widget.setVisible(False)
        level_layout.addWidget(self._module_widget)

        # 功能名称（功能级需要）
        self._feature_widget = QWidget()
        feature_row = QHBoxLayout(self._feature_widget)
        feature_row.setContentsMargins(0, 0, 0, 0)
        feature_row.addWidget(QLabel("  功能名:"))
        self._feature_combo = QComboBox()
        self._feature_combo.setEditable(True)
        self._feature_combo.setPlaceholderText("选择已有功能或输入新名称...")
        self._feature_combo.currentTextChanged.connect(self._refresh_doc_types)
        feature_row.addWidget(self._feature_combo)
        feature_row.addStretch()
        self._feature_widget.setVisible(False)
        level_layout.addWidget(self._feature_widget)

        layout.addWidget(level_group)

        # ── 可选文档类型列表 ──
        doc_group = QGroupBox("可选文档类型")
        doc_layout = QVBoxLayout(doc_group)
        self._doc_list = QListWidget()
        self._doc_list.setSelectionMode(QAbstractItemView.SingleSelection)
        doc_layout.addWidget(self._doc_list)
        layout.addWidget(doc_group)

        # ── 按钮 ──
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # ── 根据 context_path 预选 ──
        self._preselect_from_context()

        # ── 应用右键节点预设（覆盖 context 预选） ──
        if self._preset_level == "top":
            self._radio_top.setChecked(True)
            self._radio_module.setEnabled(False)
            self._radio_feature.setEnabled(False)
        elif self._preset_level == "module":
            self._radio_module.setChecked(True)
            self._radio_top.setEnabled(False)
            self._radio_feature.setEnabled(False)
        elif self._preset_level == "feature":
            self._radio_feature.setChecked(True)
            self._radio_top.setEnabled(False)
            self._radio_module.setEnabled(False)

        if self._preset_module:
            idx = self._module_combo.findData(self._preset_module)
            if idx >= 0:
                self._module_combo.setCurrentIndex(idx)

        if self._preset_feature:
            self._feature_combo.setCurrentText(self._preset_feature)

    def _populate_modules(self):
        """加载所有非顶层模块。"""
        self._module_combo.clear()
        if not self._index:
            return
        seen = set()
        for e in self._index.list_entries():
            mod = e.module
            if mod and mod != "project-charter" and mod not in seen:
                seen.add(mod)
                self._module_combo.addItem(mod, mod)

    def _preselect_from_context(self):
        """根据右键上下文路径预选层级和模块。"""
        if not self._context_path:
            self._radio_top.setChecked(True)
            return

        # 分析路径: ProjectSpec/module-{name}/... 或 ProjectSpec/xxx.md
        if "features/" in self._context_path:
            self._radio_feature.setChecked(True)
            # 提取模块名
            parts = self._context_path.split("features/")[0].strip("/")
            mod_candidate = parts.split("module-")[-1] if "module-" in parts else parts
        elif "module-" in self._context_path:
            self._radio_module.setChecked(True)
            mod_candidate = self._context_path.split("module-")[-1].split("/")[0]
        else:
            self._radio_top.setChecked(True)
            mod_candidate = None

        if mod_candidate:
            idx = self._module_combo.findData(mod_candidate)
            if idx >= 0:
                self._module_combo.setCurrentIndex(idx)

        self._feature_edit.setText("")
        self._refresh_doc_types()

    def _on_level_changed(self):
        """层级选择变化 → 显示/隐藏模块和功能输入。"""
        is_module = self._radio_module.isChecked()
        is_feature = self._radio_feature.isChecked()
        self._module_widget.setVisible(is_module or is_feature)
        self._feature_widget.setVisible(is_feature)
        if is_feature:
            self._populate_features()
        self._refresh_doc_types()

    def _on_module_changed(self):
        """模块选择变化 → 刷新功能下拉。"""
        if self._radio_feature.isChecked():
            self._populate_features()
        self._refresh_doc_types()

    def _populate_features(self):
        """从 index 加载所选模块的功能列表。"""
        self._feature_combo.clear()
        module = self._module_combo.currentData()
        if not module or not self._index:
            return
        seen = set()
        for e in self._index.list_entries():
            if e.module != module:
                continue
            path_str = e.path
            if "/features/" in path_str:
                parts = path_str.split("/features/")
                if len(parts) >= 2:
                    feat_name = parts[1].split("/")[0]
                    if feat_name not in seen:
                        seen.add(feat_name)
                        self._feature_combo.addItem(feat_name)

    def _get_level(self) -> str:
        if self._radio_top.isChecked():
            return "top"
        elif self._radio_module.isChecked():
            return "module"
        elif self._radio_feature.isChecked():
            return "feature"
        return "top"

    def _refresh_doc_types(self):
        """刷新可用文档类型列表。"""
        self._doc_list.clear()
        level = self._get_level()

        # 获取该层级的所有文档类型
        types = self._registry.list_by_level(level)
        if not types:
            self._doc_list.addItem("(该层级无可用文档类型)")
            return

        # 收集已存在的文件
        existing = self._get_existing_docs()

        for t in types:
            allowed = True
            # 模块/功能级需要指定模块
            if level in ("module", "feature") and not self._module_combo.currentData():
                allowed = False

            if not allowed:
                continue

            item_text = f"{t.description}  ({t.template})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, t.doc_type)

            # 计算目标路径，判断是否已存在
            target_path = self._compute_target_path(t)
            if target_path:
                rel = str(target_path.relative_to(self._project_root)).replace("\\", "/")
                if rel in existing:
                    item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                    item.setForeground(Qt.gray)
                    item.setText(f"{t.description}  ({t.template})  — 已存在")

            self._doc_list.addItem(item)

    def _get_existing_docs(self) -> set[str]:
        """返回所有已存在的文档路径集合。"""
        existing = set()
        if not self._index:
            return existing
        for e in self._index.list_entries():
            existing.add(e.path)
        return existing

    def _compute_target_path(self, doc_type_def) -> Path | None:
        """计算新建文档的目标路径（用于判断是否已存在）。"""
        level = self._get_level()
        if level == "top":
            # 顶层直接放在 ProjectSpec/ 下，按照模板文件名
            return self._project_docs / doc_type_def.template

        module = self._module_combo.currentData() if self._module_combo.currentData() else None
        if not module:
            return None

        main_module, sub_path = parse_module_path(module)
        module_dir = self._project_docs / f"module-{main_module}"
        if sub_path:
            module_dir = module_dir / sub_path

        if level == "module":
            return module_dir / doc_type_def.template

        if level == "feature":
            feature = self._feature_combo.currentText().strip()
            if not feature:
                return None
            return module_dir / "features" / feature / doc_type_def.template

        return None

    def _validate(self):
        """校验并创建文档。"""
        selected = self._doc_list.currentItem()
        if not selected or not selected.isSelected():
            QMessageBox.warning(self, "错误", "请选择一个文档类型")
            return
        if not (selected.flags() & Qt.ItemIsSelectable):
            QMessageBox.warning(self, "错误", "该文档已存在，请选择其他类型")
            return

        doc_type_key = selected.data(Qt.UserRole)
        if not doc_type_key:
            return

        level = self._get_level()
        module = self._module_combo.currentData() if level in ("module", "feature") else None
        feature = self._feature_combo.currentText().strip() if level == "feature" else None

        doc_type_def = self._registry.get(doc_type_key)
        if not doc_type_def:
            QMessageBox.warning(self, "错误", "无效的文档类型")
            return

        # 校验模块/功能参数
        if level == "module" and not module:
            QMessageBox.warning(self, "错误", "模块级文档需要选择模块")
            return
        if level == "feature" and not feature:
            QMessageBox.warning(self, "错误", "功能级文档需要输入功能名称")
            return

        # 计算目标路径并创建
        from src.engine.commands.new_utils import resolve_path, render_template
        from src.engine.deps import derive_initial_depends_on

        actual_module = module or "project-charter"
        target_path = resolve_path(
            self._project_docs, doc_type_def, actual_module, feature
        )

        if target_path.exists():
            QMessageBox.warning(self, "文件已存在", f"{target_path} 已存在")
            return

        # 渲染
        now = FrontmatterParser.now_iso()
        depends_on = derive_initial_depends_on(
            doc_type_def, actual_module, self._index, self._project_docs
        )

        try:
            content = render_template(
                doc_type_def.template, actual_module, feature,
                depends_on, now, self._kit_dir,
            )
        except FileNotFoundError as e:
            QMessageBox.warning(self, "模板错误", str(e))
            return

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

        # 更新索引
        from src.engine.index import IndexEntry
        rel_path = str(target_path.relative_to(self._project_root)).replace("\\", "/")
        meta, _ = FrontmatterParser.read_file(target_path)
        entry = IndexEntry(
            path=rel_path,
            doc_type=meta.get("doc_type", doc_type_key),
            module=meta.get("module", actual_module),
            level=meta.get("level", doc_type_def.level),
            version=str(meta.get("version", "0.1.0")),
            status=meta.get("status", "active"),
            depends_on=meta.get("depends_on", depends_on),
            mtime=now,
        )
        self._index.add_entry(entry)
        self._index.save()

        QMessageBox.information(self, "创建成功", f"已创建: {rel_path}")
        self._target_rel_path = rel_path
        self.accept()

    @property
    def target_rel_path(self) -> str:
        return getattr(self, "_target_rel_path", "")

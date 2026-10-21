"""共享前言机制测试。

前言（SKILL.md 顶部的"最高优先级"块）是**生成物**：共性文字来自
`skills/_shared/preamble-<variant>.md` 与 `output-convention.md`，工具清单从技能
正文实际用到的命令自动派生。本测试固定三件事：

  1. 仓库现状 == 重新生成的结果（防止有人手改前言后忘记重生成）；
  2. 8 份技能的前言共性文字收敛为 **4 个变体**（session / dev / git / smell）；
  3. **声明 = 实用**：preceding 里声明的每条命令都在正文里真正用到，反之亦然。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import render_skill_preamble as R  # noqa: E402


class TestGeneration:
    @pytest.mark.parametrize("name", sorted(R.VARIANTS))
    def test_skill_matches_generated(self, name):
        """SKILL.md 的前言必须与共享片段生成结果一致（CI 拦截手改漂移）。"""
        text = (R.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        assert R.render(name, text) == text, (
            f"{name} 的前言与共享片段不一致，请运行 python tests/render_skill_preamble.py"
        )

    def test_variants_are_four(self):
        """共性文字收敛为 4 组（工具清单各行技能不同，比对时剔除）。"""
        groups: dict[str, list[str]] = {}
        for name in R.VARIANTS:
            text = (R.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
            seg = text[: re.search(r"^# spec-", text, re.M).start()]
            seg = seg[seg.index(R.PREAMBLE_START):]
            seg = re.sub(r"^python \.doc-kit/cli/cli\.py.*$\n?", "", seg, flags=re.M)
            seg = seg.replace("cd <项目根>   # 项目根 = 含 .doc-kit/ 或 SessionSpec/ 的目录\n", "")
            groups.setdefault(seg.strip(), []).append(name)
        assert len(groups) == 4, f"前言变体应为 4 组，实际 {len(groups)} 组：{list(groups.values())}"

    def test_hand_edit_is_detected(self):
        """反向验证：手工改动前言必须被生成器发现。"""
        text = (R.SKILLS_DIR / "spec-start" / "SKILL.md").read_text(encoding="utf-8")
        tampered = text.replace("**git 操作**一律用 `bash` 执行（CLI 不执行 git）。",
                                "**git 操作**一律用 `bash` 执行。", 1)
        assert tampered != text
        assert R.render("spec-start", tampered) != tampered


class TestToolsDerivation:
    @pytest.mark.parametrize("name", sorted(R.VARIANTS))
    def test_declared_tools_equal_used(self, name):
        """前言里声明的命令集合 == 正文实际用到的命令集合（消除过度声明/漏声明）。"""
        text = (R.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        prefix, _old, body = R.split_skill(text)
        derived = R.derive_tools(prefix, body)
        seg = text[: re.search(r"^# spec-", text, re.M).start()]
        declared_cmds = sorted({R.normalize(m.group(1)) for m in R.COMMAND_RE.finditer(seg)})
        expected = sorted(set(derived) | set(R.ALWAYS_TOOLS))
        assert declared_cmds == expected, f"{name}: 声明 {declared_cmds} != 实用 {expected}"

    @pytest.mark.parametrize("name", sorted(R.VARIANTS))
    def test_all_commands_registered(self, name):
        """正文用到的命令必须在 USAGE 表登记（新增命令时强制登记）。"""
        text = (R.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        prefix, _old, body = R.split_skill(text)
        for cmd in R.derive_tools(prefix, body):
            assert cmd in R.USAGE

    def test_unknown_command_raises(self):
        """正文出现未登记命令时生成器必须报错（而不是静默漏掉）。"""
        text = (R.SKILLS_DIR / "spec-smart-git" / "SKILL.md").read_text(encoding="utf-8")
        with pytest.raises(ValueError):
            R.derive_tools("", text + "\npython .doc-kit/cli/cli.py doc not-a-real-command\n")


class TestToolchainVersion:
    def test_version_constant_exists(self):
        assert re.match(r"^\d{4}\.\d{2}\.\d+$", R.toolchain_version()), R.toolchain_version()

    @pytest.mark.parametrize("name", sorted(R.VARIANTS))
    def test_skills_declare_current_version(self, name):
        """8 份技能里注入的版本必须等于 cli.py 的 TOOLCHAIN_VERSION。"""
        text = (R.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        assert f"`{R.toolchain_version()}`" in text

    def test_self_check_present(self):
        for name in R.VARIANTS:
            text = (R.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
            assert "工具链版本自检" in text and "tool status" in text


class TestSharedSourceOfTruth:
    def test_no_windows_redirect_anywhere(self):
        """历史坑：`>nul 2>&1` 在 bash 下会生成名为 nul 的文件。"""
        for path in list(R.SKILLS_DIR.glob("**/*.md")):
            assert ">nul" not in path.read_text(encoding="utf-8"), path

    def test_output_convention_single_source(self):
        """输出约定只写在 output-convention.md 里，8 份技能按同一份文字生成。"""
        convention = (R.SHARED / "output-convention.md").read_text(encoding="utf-8").strip()
        first_line = convention.splitlines()[0]
        for name in R.VARIANTS:
            text = (R.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
            assert first_line in text, f"{name} 缺少共享输出约定"

    def test_git_skills_have_three_layer_boundary(self):
        for name in ("spec-smart-git", "spec-code-review", "spec-code-smell"):
            text = (R.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
            assert "三层边界" in text and "源码、diff、工作区文件" in text

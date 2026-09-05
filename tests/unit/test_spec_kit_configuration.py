"""Spec Kit 前置流程配置的契约测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class SpecKitConfigurationTests(unittest.TestCase):
    """验证仓库固定并强制执行项目定制的规格驱动流程。"""

    def setUp(self) -> None:
        """定位仓库根目录，供配置与文档断言复用。"""
        self.project_root = Path(__file__).resolve().parents[2]

    def test_spec_kit_version_and_codex_integration_are_pinned(self) -> None:
        """验证初始化配置固定到已评审版本和 Codex Skills 模式。"""
        options_path = self.project_root / ".specify" / "init-options.json"
        options = json.loads(options_path.read_text(encoding="utf-8"))

        self.assertEqual("1.0.4", options["speckit_version"])
        self.assertEqual("codex", options["integration"])
        self.assertTrue(options["ai_skills"])
        self.assertEqual("sequential", options["feature_numbering"])

        setup_script = (self.project_root / "scripts" / "setup-spec-kit.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('SPEC_KIT_VERSION="v1.0.4"', setup_script)

    def test_project_constitution_keeps_agents_and_tests_authoritative(self) -> None:
        """验证 Constitution 不会降低根级工程规范和测试先行要求。"""
        constitution = (
            self.project_root / ".specify" / "memory" / "constitution.md"
        ).read_text(encoding="utf-8")

        self.assertIn("AGENTS.md 是最高项目约束", constitution)
        self.assertIn("测试先行不可协商", constitution)
        self.assertIn("tests/features/", constitution)
        self.assertIn("Living Spec", constitution)
        self.assertNotIn("[PRINCIPLE_", constitution)

    def test_coding_harness_preset_overrides_core_optional_test_behavior(self) -> None:
        """验证项目 Preset 已物化到任务与实现 Skill，并强制生成测试任务。"""
        registry_path = self.project_root / ".specify" / "presets" / ".registry"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        self.assertIn("coding-harness", registry["presets"])

        tasks_skill = (
            self.project_root / ".agents" / "skills" / "speckit-tasks" / "SKILL.md"
        ).read_text(encoding="utf-8")
        implement_skill = (
            self.project_root / ".agents" / "skills" / "speckit-implement" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("The core statement that tests are optional does not apply", tasks_skill)
        self.assertIn("Every changed business behavior", tasks_skill)
        self.assertIn("Coding-Harness Pre-Implementation Gate", implement_skill)
        self.assertNotIn("{CORE_TEMPLATE}", implement_skill)

    def test_agents_file_requires_preflight_before_implementation(self) -> None:
        """验证根级流程要求先完成规格分析，再进入实现与收敛。"""
        agents_text = (self.project_root / "AGENTS.md").read_text(encoding="utf-8")
        required_commands = (
            "$speckit-specify",
            "$speckit-clarify",
            "$speckit-plan",
            "$speckit-checklist",
            "$speckit-tasks",
            "$speckit-analyze",
            "$speckit-implement",
            "$speckit-converge",
        )

        positions = [agents_text.index(command) for command in required_commands]
        self.assertEqual(sorted(positions), positions)


if __name__ == "__main__":
    unittest.main()

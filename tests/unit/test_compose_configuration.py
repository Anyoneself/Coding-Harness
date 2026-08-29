"""Docker Compose 项目标识兼容性的回归测试。"""

from __future__ import annotations

import unittest
from pathlib import Path


class ComposeConfigurationTests(unittest.TestCase):
    """验证项目改名不会切断既有本地基础设施。"""

    def test_compose_keeps_legacy_project_identity_for_data_compatibility(self) -> None:
        """验证 Compose 继续接管原容器、网络和命名卷，避免同名冲突。"""
        project_root = Path(__file__).resolve().parents[2]
        compose_text = (project_root / "docker-compose.yml").read_text(encoding="utf-8")

        first_setting = next(
            line.strip()
            for line in compose_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertEqual("name: my-agent", first_setting)


if __name__ == "__main__":
    unittest.main()

"""首次运行 API Key 配置链路的集成测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from application.agent.provider import ModelCompleted, ModelDelta, ModelRequest
from application.app import create_app
from application.config import DeepSeekSettings


class ConfiguredFakeProvider:
    """模拟完成配置后的 Harness 模型 Provider。"""

    def __init__(self, settings: DeepSeekSettings) -> None:
        """保存新配置但不创建任何网络客户端。"""
        self.settings = settings
        self.closed = False

    def stream(self, request: ModelRequest) -> Iterator[ModelDelta | ModelCompleted]:
        """返回确定性结果，证明 Runtime 已切换到可用 Provider。"""
        yield ModelCompleted(answer=f"configured:{request.prompt}")

    def close(self) -> None:
        """记录 Runtime 是否释放了伪 Provider。"""
        self.closed = True


class ApiKeyConfigurationTests(unittest.TestCase):
    """验证前端首次配置到运行时激活的完整安全契约。"""

    def test_first_configuration_persists_secret_and_activates_runtime(self) -> None:
        """验证密钥安全落盘后，Harness 无需重启即可就绪。"""
        secret = "sk-integration-secret-123456"
        previous_api_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as directory:
                env_path = Path(directory) / ".env"
                env_path.write_text(
                    "DEEPSEEK_MODEL=deepseek-v4-flash\n"
                    "DEEPSEEK_API_KEY=stale-secret\n"
                    "KEEP_ME=yes\n"
                    "export DEEPSEEK_API_KEY=duplicate-secret\n",
                    encoding="utf-8",
                )
                settings = DeepSeekSettings(
                    api_key="",
                    database_url="sqlite:///:memory:",
                )
                with patch(
                    "application.services.configuration.DeepSeekModelProvider",
                    ConfiguredFakeProvider,
                ):
                    application = create_app(settings, env_path=env_path)
                    with TestClient(application) as client:
                        response = client.post(
                            "/api/config/api-key",
                            json={"api_key": secret},
                        )
                        self.assertEqual(200, response.status_code)
                        self.assertEqual({"ok": True, "ready": True}, response.json())
                        self.assertNotIn(secret, response.text)
                        self.assertTrue(client.get("/api/config").json()["ready"])
                        self.assertIsInstance(
                            application.state.harness_runtime.provider,
                            ConfiguredFakeProvider,
                        )

                persisted = env_path.read_text(encoding="utf-8")
                self.assertIn("DEEPSEEK_MODEL=deepseek-v4-flash\n", persisted)
                self.assertIn("KEEP_ME=yes\n", persisted)
                self.assertEqual(1, persisted.count("DEEPSEEK_API_KEY="))
                self.assertIn(f"DEEPSEEK_API_KEY={secret}\n", persisted)
                self.assertNotIn("stale-secret", persisted)
                self.assertNotIn("duplicate-secret", persisted)
                self.assertEqual(0o600, env_path.stat().st_mode & 0o777)
        finally:
            if previous_api_key is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = previous_api_key

    def test_reconfiguration_is_rejected_without_replacing_secret(self) -> None:
        """验证已配置服务拒绝覆盖密钥，并且响应不会泄漏候选密钥。"""
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("KEEP_ME=yes\n", encoding="utf-8")
            application = create_app(
                DeepSeekSettings(api_key="sk-existing-secret-123456"),
                env_path=env_path,
            )
            with TestClient(application) as client:
                secret = "sk-replacement-secret-123456"
                response = client.post("/api/config/api-key", json={"api_key": secret})
                self.assertEqual(409, response.status_code)
                self.assertNotIn(secret, response.text)
            self.assertEqual("KEEP_ME=yes\n", env_path.read_text(encoding="utf-8"))

    def test_invalid_api_keys_are_rejected_before_persistence(self) -> None:
        """验证空白和非法格式密钥不会进入配置用例或写入文件。"""
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            application = create_app(DeepSeekSettings(api_key=""), env_path=env_path)
            with TestClient(application) as client:
                for api_key in ("   ", "short", "sk-invalid key with spaces"):
                    with self.subTest(api_key=api_key):
                        response = client.post(
                            "/api/config/api-key",
                            json={"api_key": api_key},
                        )
                        self.assertEqual(422, response.status_code)
            self.assertFalse(env_path.exists())

    def test_remote_client_cannot_write_local_configuration(self) -> None:
        """验证非回环客户端无法通过 HTTP 修改本机环境文件。"""
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            application = create_app(DeepSeekSettings(api_key=""), env_path=env_path)
            with TestClient(application, client=("203.0.113.8", 50000)) as client:
                response = client.post(
                    "/api/config/api-key",
                    json={"api_key": "sk-remote-secret-123456"},
                )
                self.assertEqual(403, response.status_code)
            self.assertFalse(env_path.exists())

    def test_home_loads_built_frontend_with_first_run_controls(self) -> None:
        """验证首页加载构建产物，且客户端包含首次密钥配置控件。"""
        application = create_app(DeepSeekSettings(api_key=""))
        with TestClient(application) as client:
            html = client.get("/").text
            script = client.get("/static/app.js").text
        self.assertIn('id="root"', html)
        self.assertIn('src="/static/app.js"', html)
        self.assertIn("/api/config/api-key", script)
        self.assertIn("显示 API Key", script)
        self.assertIn("保存并连接", script)


if __name__ == "__main__":
    unittest.main()

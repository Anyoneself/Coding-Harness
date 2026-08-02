from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from production_agent.agent import DeepSeekAgent
from production_agent.config import DeepSeekSettings
from production_agent.tools import AgentContext, build_tool_registry
from production_agent.web import create_app


def message(content=None, tool_calls=None, reasoning_content=None):
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
    )


def response(content=None, tool_calls=None, finish_reason="stop", usage=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=message(
                    content=content,
                    tool_calls=tool_calls,
                    reasoning_content="hidden reasoning" if tool_calls else None,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class DeepSeekAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = DeepSeekSettings(
            api_key="test-key",
            model="deepseek-v4-flash",
            allowed_models=("deepseek-v4-flash",),
        )

    def test_model_intent_and_tool_loop(self) -> None:
        intent_payload = {
            "intents": ["calculation"],
            "entities": {"expression": "128 * 36"},
            "confidence": 0.97,
            "needs_clarification": False,
            "clarification_question": "",
            "suggested_tools": ["calculate"],
        }
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="calculate", arguments='{"expression":"128 * 36"}'),
        )
        usage = SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=20,
            total_tokens=140,
        )
        client = FakeClient(
            [
                response(json.dumps(intent_payload)),
                response(tool_calls=[tool_call], finish_reason="tool_calls"),
                response("结果是 4608。", usage=usage),
            ]
        )
        agent = DeepSeekAgent(self.settings, client=client)

        events = list(
            agent.run(
                "帮我计算 128 * 36",
                session_id="calculation-session",
            )
        )

        self.assertEqual("intent", events[1]["type"])
        self.assertEqual(["calculation"], events[1]["intents"])
        self.assertTrue(any(event["type"] == "tool_call" for event in events))
        tool_result = next(event for event in events if event["type"] == "tool_result")
        self.assertEqual(4608, tool_result["result"]["result"])
        self.assertEqual("结果是 4608。", events[-1]["answer"])

        final_messages = client.chat.completions.calls[-1]["messages"]
        assistant_tool_message = next(item for item in final_messages if item.get("tool_calls"))
        self.assertIn("reasoning_content", assistant_tool_message)
        self.assertIn("extra_body", client.chat.completions.calls[-1])

    def test_disallowed_model_is_rejected_before_api_call(self) -> None:
        client = FakeClient([])
        agent = DeepSeekAgent(self.settings, client=client)
        events = list(agent.run("hello", model="unknown-model"))
        self.assertEqual("error", events[0]["type"])
        self.assertEqual([], client.chat.completions.calls)

    def test_write_tool_requires_confirmation_from_user_message(self) -> None:
        registry = build_tool_registry(self.settings)
        unconfirmed = registry.execute(
            "create_repair_ticket",
            {"device_model": "MX-100", "fault_code": "E102"},
            AgentContext(
                user="alice",
                role="operations",
                session_id="ticket-session",
                request_id="request-1",
                user_request="请创建维修工单",
            ),
        )
        confirmed = registry.execute(
            "create_repair_ticket",
            {"device_model": "MX-100", "fault_code": "E102"},
            AgentContext(
                user="alice",
                role="operations",
                session_id="ticket-session",
                request_id="request-2",
                user_request="请确认创建 MX-100 的 E102 维修工单",
            ),
        )

        self.assertEqual("blocked", unconfirmed["status"])
        self.assertEqual("confirmation_required", unconfirmed["output"]["reason"])
        self.assertEqual("succeeded", confirmed["status"])
        self.assertTrue(confirmed["output"]["ticket_id"].startswith("TKT-"))

    def test_calculator_rejects_code_execution(self) -> None:
        registry = build_tool_registry(self.settings)
        result = registry.execute(
            "calculate",
            {"expression": "__import__('os').system('echo unsafe')"},
            AgentContext(
                user="alice",
                role="operations",
                session_id="calc-session",
                request_id="request",
                user_request="calculate",
            ),
        )
        self.assertEqual("failed", result["status"])

    def test_web_app_serves_ui_and_reports_missing_key(self) -> None:
        settings = DeepSeekSettings(
            api_key="",
            model="deepseek-v4-flash",
            allowed_models=("deepseek-v4-flash",),
        )
        client = TestClient(create_app(settings))

        self.assertEqual(200, client.get("/").status_code)
        config = client.get("/api/config").json()
        self.assertFalse(config["ready"])
        response = client.post(
            "/api/chat",
            json={
                "message": "hello",
                "session_id": "web-test",
                "role": "operations",
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertIn("DEEPSEEK_API_KEY", response.text)

    def test_codex_style_workspace_tools_are_registered(self) -> None:
        registry = build_tool_registry(self.settings)
        self.assertTrue(
            {
                "list_workspace_files",
                "read_workspace_file",
                "search_workspace",
                "apply_patch",
                "write_workspace_file",
                "run_workspace_command",
            }.issubset(set(registry.names))
        )

    def test_workspace_read_search_and_patch_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.py"
            source.write_text("VALUE = 1\nprint(VALUE)\n", encoding="utf-8")
            settings = DeepSeekSettings(
                api_key="test-key",
                model="deepseek-v4-flash",
                allowed_models=("deepseek-v4-flash",),
                workspace_root=directory,
            )
            registry = build_tool_registry(settings)
            read_context = AgentContext(
                user="alice",
                role="operations",
                session_id="workspace-session",
                request_id="read-request",
                user_request="请检查 sample.py",
            )
            write_context = AgentContext(
                user="alice",
                role="operations",
                session_id="workspace-session",
                request_id="write-request",
                user_request="请修改 sample.py，把 VALUE 更新为 2",
            )

            listed = registry.execute(
                "list_workspace_files",
                {"pattern": "*.py"},
                read_context,
            )
            read = registry.execute(
                "read_workspace_file",
                {"path": "sample.py", "start_line": 1, "end_line": 2},
                read_context,
            )
            searched = registry.execute(
                "search_workspace",
                {"query": "VALUE", "file_pattern": "*.py"},
                read_context,
            )
            patched = registry.execute(
                "apply_patch",
                {
                    "path": "sample.py",
                    "old_text": "VALUE = 1",
                    "new_text": "VALUE = 2",
                },
                write_context,
            )

            self.assertEqual(["sample.py"], [item["path"] for item in listed["files"]])
            self.assertIn("print(VALUE)", read["content"])
            self.assertEqual(2, len(searched["matches"]))
            self.assertEqual("succeeded", patched["status"])
            self.assertIn("VALUE = 2", source.read_text(encoding="utf-8"))

    def test_workspace_tools_block_sensitive_and_escape_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("SECRET=do-not-read\n", encoding="utf-8")
            settings = DeepSeekSettings(
                api_key="test-key",
                model="deepseek-v4-flash",
                allowed_models=("deepseek-v4-flash",),
                workspace_root=directory,
            )
            registry = build_tool_registry(settings)
            context = AgentContext(
                user="alice",
                role="operations",
                session_id="workspace-session",
                request_id="request",
                user_request="请读取项目",
            )

            sensitive = registry.execute(
                "read_workspace_file",
                {"path": ".env"},
                context,
            )
            escaped = registry.execute(
                "read_workspace_file",
                {"path": "../outside.txt"},
                context,
            )
            command = registry.execute(
                "run_workspace_command",
                {"command": "rm -rf ."},
                context,
            )
            secret_search = registry.execute(
                "run_workspace_command",
                {"command": "rg SECRET --glob=.env"},
                context,
            )

            self.assertEqual("blocked", sensitive["status"])
            self.assertEqual("blocked", escaped["status"])
            self.assertEqual("blocked", command["status"])
            self.assertEqual("blocked", secret_search["status"])

    def test_workspace_writes_require_explicit_user_intent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.txt"
            source.write_text("before\n", encoding="utf-8")
            settings = DeepSeekSettings(
                api_key="test-key",
                model="deepseek-v4-flash",
                allowed_models=("deepseek-v4-flash",),
                workspace_root=directory,
            )
            registry = build_tool_registry(settings)
            context = AgentContext(
                user="alice",
                role="operations",
                session_id="workspace-session",
                request_id="request",
                user_request="请查看 sample.txt",
            )

            result = registry.execute(
                "apply_patch",
                {
                    "path": "sample.txt",
                    "old_text": "before",
                    "new_text": "after",
                },
                context,
            )

            self.assertEqual("blocked", result["status"])
            self.assertEqual("before\n", source.read_text(encoding="utf-8"))

    def test_workspace_command_returns_structured_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = DeepSeekSettings(
                api_key="test-key",
                model="deepseek-v4-flash",
                allowed_models=("deepseek-v4-flash",),
                workspace_root=directory,
            )
            registry = build_tool_registry(settings)
            context = AgentContext(
                user="alice",
                role="operations",
                session_id="workspace-session",
                request_id="request",
                user_request="请检查项目",
            )

            result = registry.execute(
                "run_workspace_command",
                {"command": "pwd"},
                context,
            )

            self.assertEqual("succeeded", result["status"])
            self.assertEqual(0, result["exit_code"])
            self.assertEqual(str(Path(directory).resolve()), result["stdout"].strip())


if __name__ == "__main__":
    unittest.main()

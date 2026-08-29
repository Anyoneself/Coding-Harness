from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from fastapi.testclient import TestClient
from pydantic import ValidationError

from application.agent import DeepSeekAgent
from application.app import create_app
from application.cli.main import build_parser, run_chat
from application.config import DeepSeekSettings
from application.prompts import AGENT_SYSTEM_PROMPT, INTENT_RECOGNITION_PROMPT
from application.repositories import SessionStore
from application.schemas import ChatRequest
from application.services.chat import AgentChatService
from application.tools import AgentContext, build_tool_registry


def message(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    reasoning_content: str | None = None,
) -> SimpleNamespace:
    """构造测试模型响应中的助手消息对象。"""
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
    )


def response(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str = "stop",
    usage: Any | None = None,
) -> SimpleNamespace:
    """构造包含单个候选结果的测试模型响应。"""
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


def stream_chunk(
    content: str | None = None,
    *,
    tool_calls: list[Any] | None = None,
    reasoning_content: str | None = None,
    finish_reason: str | None = None,
    usage: Any | None = None,
) -> SimpleNamespace:
    """构造测试流中的单个模型增量分片。"""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning_content,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def streamed_response(*chunks: SimpleNamespace) -> list[SimpleNamespace]:
    """把多个模型分片组合成可迭代的测试流。"""
    return list(chunks)


class FakeCompletions:
    """记录调用参数并按顺序返回预设模型响应。"""

    def __init__(self, responses: list[Any]) -> None:
        """保存待返回响应和历史调用参数。"""
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        """记录一次模型调用并弹出下一个预设响应。"""
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    """提供与 OpenAI Client 测试所需部分一致的接口。"""

    def __init__(self, responses: list[Any]) -> None:
        """创建带有伪补全接口的聊天客户端。"""
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class DeepSeekAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        """为每个用例创建固定模型白名单配置。"""
        self.settings = DeepSeekSettings(
            api_key="test-key",
            model="deepseek-v4-flash",
            allowed_models=("deepseek-v4-flash",),
        )

    def test_model_intent_and_tool_loop(self) -> None:
        """验证意图识别、工具调用和最终回答的完整模型链路。"""
        intent_payload = {
            "intents": ["calculation"],
            "entities": {"expression": "128 * 36"},
            "confidence": 0.97,
            "needs_clarification": False,
            "clarification_question": "",
            "suggested_tools": ["calculate"],
        }
        tool_call = SimpleNamespace(
            index=0,
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
                streamed_response(
                    stream_chunk(reasoning_content="hidden reasoning"),
                    stream_chunk(tool_calls=[tool_call], finish_reason="tool_calls"),
                ),
                streamed_response(
                    stream_chunk("结果是 "),
                    stream_chunk("4608。", finish_reason="stop", usage=usage),
                ),
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
        self.assertEqual(
            ["结果是 ", "4608。"],
            [event["delta"] for event in events if event["type"] == "answer_delta"],
        )
        thinking_events = [event for event in events if event["type"] == "thinking_delta"]
        self.assertEqual(1, len(thinking_events))
        self.assertEqual(16, thinking_events[0]["delta_chars"])
        self.assertEqual(16, thinking_events[0]["total_chars"])
        self.assertEqual("hidden reasoning", thinking_events[0]["delta"])
        tool_result = next(event for event in events if event["type"] == "tool_result")
        self.assertEqual(4608, tool_result["result"]["result"])
        self.assertEqual("结果是 4608。", events[-1]["answer"])

        final_messages = client.chat.completions.calls[-1]["messages"]
        assistant_tool_message = next(item for item in final_messages if item.get("tool_calls"))
        self.assertIn("reasoning_content", assistant_tool_message)
        self.assertIn("extra_body", client.chat.completions.calls[-1])
        self.assertNotIn("temperature", client.chat.completions.calls[-1])
        self.assertTrue(client.chat.completions.calls[-1]["stream"])
        self.assertEqual(
            INTENT_RECOGNITION_PROMPT,
            client.chat.completions.calls[0]["messages"][0]["content"],
        )
        self.assertEqual(
            AGENT_SYSTEM_PROMPT,
            client.chat.completions.calls[1]["messages"][0]["content"],
        )

    def test_request_overrides_thinking_mode_and_effort(self) -> None:
        """验证单次请求可以关闭深度思考或把思考强度切换为 max。"""
        intent = json.dumps(
            {
                "intents": ["question_answering"],
                "entities": {},
                "confidence": 0.9,
                "needs_clarification": False,
                "clarification_question": "",
                "suggested_tools": [],
            }
        )
        disabled_client = FakeClient(
            [response(intent), streamed_response(stream_chunk("快速回答", finish_reason="stop"))]
        )
        disabled_agent = DeepSeekAgent(self.settings, client=disabled_client)

        disabled_events = list(disabled_agent.run("快速回答", thinking_enabled=False))

        disabled_payload = disabled_client.chat.completions.calls[-1]
        self.assertEqual(
            {"thinking": {"type": "disabled"}},
            disabled_payload["extra_body"],
        )
        self.assertNotIn("reasoning_effort", disabled_payload)
        self.assertIn("temperature", disabled_payload)
        self.assertFalse(
            any(event["type"] == "thinking_delta" for event in disabled_events)
        )

        max_client = FakeClient(
            [response(intent), streamed_response(stream_chunk("深入回答", finish_reason="stop"))]
        )
        max_agent = DeepSeekAgent(self.settings, client=max_client)

        list(
            max_agent.run(
                "深入回答",
                thinking_enabled=True,
                reasoning_effort="max",
            )
        )

        max_payload = max_client.chat.completions.calls[-1]
        self.assertEqual({"thinking": {"type": "enabled"}}, max_payload["extra_body"])
        self.assertEqual("max", max_payload["reasoning_effort"])
        self.assertNotIn("temperature", max_payload)

    def test_chat_request_validates_thinking_effort(self) -> None:
        """验证 HTTP 请求只接受 DeepSeek 官方支持的思考强度。"""
        request = ChatRequest(
            message="深入分析",
            session_id="thinking-session",
            thinking_enabled=True,
            reasoning_effort="max",
        )

        self.assertTrue(request.thinking_enabled)
        self.assertEqual("max", request.reasoning_effort)
        with self.assertRaises(ValidationError):
            ChatRequest(
                message="错误强度",
                session_id="thinking-session",
                thinking_enabled=True,
                reasoning_effort="medium",
            )

    def test_chat_service_restores_history_and_events_from_sqlite(self) -> None:
        """验证真实模型服务重建后可恢复历史，并按顺序读取持久化事件。"""
        intent = json.dumps(
            {
                "intents": ["question_answering"],
                "entities": {},
                "confidence": 0.9,
                "needs_clarification": False,
                "clarification_question": "",
                "suggested_tools": [],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "agent.sqlite3")
            first_client = FakeClient(
                [
                    response(intent),
                    streamed_response(
                        stream_chunk(reasoning_content="第一轮推理原文"),
                        stream_chunk("第一轮回答", finish_reason="stop"),
                    ),
                ]
            )
            first_service = AgentChatService(
                self.settings,
                agent=DeepSeekAgent(self.settings, client=first_client),
                session_store=SessionStore(database),
            )

            first_events = list(
                first_service.stream_chat(
                    "第一轮问题",
                    user="alice",
                    role="standard",
                    session_id="persistent-session",
                    model=None,
                )
            )

            second_client = FakeClient(
                [
                    response(intent),
                    streamed_response(stream_chunk("第二轮回答", finish_reason="stop")),
                ]
            )
            second_store = SessionStore(database)
            second_service = AgentChatService(
                self.settings,
                agent=DeepSeekAgent(self.settings, client=second_client),
                session_store=second_store,
            )
            second_events = list(
                second_service.stream_chat(
                    "第二轮问题",
                    user="alice",
                    role="standard",
                    session_id="persistent-session",
                    model=None,
                )
            )

            intent_messages = second_client.chat.completions.calls[0]["messages"]
            self.assertTrue(
                any(item.get("content") == "第一轮回答" for item in intent_messages)
            )
            self.assertEqual("第一轮回答", first_events[-1]["answer"])
            self.assertEqual("第二轮回答", second_events[-1]["answer"])

            persisted_events = second_store.list_events("persistent-session")
            self.assertEqual(11, len(persisted_events))
            self.assertEqual(
                [
                    "started",
                    "intent",
                    "model_round",
                    "thinking_delta",
                    "answer_delta",
                    "final",
                ],
                [event.event_type for event in persisted_events[:6]],
            )
            self.assertEqual(
                [1, 2, 3, 4, 5, 6],
                [event.sequence for event in persisted_events[:6]],
            )
            thinking_event = persisted_events[3]
            self.assertNotIn("delta", thinking_event.payload)
            self.assertTrue(thinking_event.payload["content_redacted"])

    def test_disallowed_model_is_rejected_before_api_call(self) -> None:
        """验证非白名单模型会在外部 API 调用前被拒绝。"""
        client = FakeClient([])
        agent = DeepSeekAgent(self.settings, client=client)
        events = list(agent.run("hello", model="unknown-model"))
        self.assertEqual("error", events[0]["type"])
        self.assertEqual([], client.chat.completions.calls)

    def test_knowledge_tool_is_not_limited_by_legacy_business_role(self) -> None:
        """验证知识工具对自定义通用角色保持可用。"""
        registry = build_tool_registry(self.settings)
        result = registry.execute(
            "search_knowledge_base",
            {"query": "项目规划模板"},
            AgentContext(
                user="alice",
                role="product-manager",
                session_id="knowledge-session",
                request_id="request-1",
                user_request="请检索项目规划模板",
            ),
        )
        self.assertEqual("succeeded", result["status"])
        self.assertTrue(result["results"])

    def test_calculator_rejects_code_execution(self) -> None:
        """验证计算工具拒绝执行 Python 代码表达式。"""
        registry = build_tool_registry(self.settings)
        result = registry.execute(
            "calculate",
            {"expression": "__import__('os').system('echo unsafe')"},
            AgentContext(
                user="alice",
                role="standard",
                session_id="calc-session",
                request_id="request",
                user_request="calculate",
            ),
        )
        self.assertEqual("failed", result["status"])

    def test_web_app_serves_ui_and_reports_missing_key(self) -> None:
        """验证 Web 首页可访问且缺少密钥时返回友好事件。"""
        settings = DeepSeekSettings(
            api_key="",
            model="deepseek-v4-flash",
            allowed_models=("deepseek-v4-flash",),
        )
        application = create_app(settings)
        with TestClient(application) as client:
            self.assertEqual("Coding-Harness", application.title)
            home_response = client.get("/")
            self.assertEqual(200, home_response.status_code)
            self.assertIn("Coding-Harness", home_response.text)
            self.assertNotIn("My-Agent", home_response.text)
            self.assertIn('id="chatHistory"', home_response.text)
            self.assertIn('id="activityPanel"', home_response.text)
            self.assertIn('id="messageInput"', home_response.text)
            favicon_response = client.get("/favicon.ico")
            self.assertEqual(200, favicon_response.status_code)
            self.assertTrue(favicon_response.headers["content-type"].startswith("image/svg+xml"))
            config = client.get("/api/config").json()
            self.assertFalse(config["ready"])
            response = client.post(
                "/api/chat",
                json={
                    "message": "hello",
                    "session_id": "web-test",
                    "role": "standard",
                },
            )
            self.assertEqual(200, response.status_code)
            self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
            self.assertEqual("no-cache, no-transform", response.headers["cache-control"])
            self.assertEqual("no", response.headers["x-accel-buffering"])
            self.assertIn("DEEPSEEK_API_KEY", response.text)
            delete_response = client.delete("/api/session/web-test")
            self.assertEqual(200, delete_response.status_code)
            self.assertEqual({"ok": True}, delete_response.json())
            self.assertEqual(
                [],
                application.state.chat_service.get_session_events("web-test"),
            )
            self.assertEqual(200, client.delete("/api/session/web-test").status_code)
            self.assertEqual(422, client.delete(f"/api/session/{'x' * 129}").status_code)

        session_store = application.state.chat_service.session_store
        self.assertIsNone(session_store._connection)

    def test_web_app_shutdown_closes_chat_service_once(self) -> None:
        """验证应用生命周期结束时主动关闭服务，避免解释器退出阶段回收连接池。"""
        service = Mock(spec=AgentChatService)
        service.is_ready = False
        service.get_public_config.return_value = {"ready": False}
        application = create_app(DeepSeekSettings(api_key=""), chat_service=service)

        with TestClient(application) as client:
            self.assertEqual(200, client.get("/api/health").status_code)

        service.close.assert_called_once_with()

    def test_codex_style_workspace_tools_are_registered(self) -> None:
        """验证工作区读写和命令工具均已显式注册。"""
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
        """验证工作区列表、读取、搜索和精确修改链路。"""
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
                role="standard",
                session_id="workspace-session",
                request_id="read-request",
                user_request="请检查 sample.py",
            )
            write_context = AgentContext(
                user="alice",
                role="standard",
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
        """验证敏感文件、越界路径和危险命令均被阻止。"""
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
                role="standard",
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
        """验证没有明确修改意图时工作区写入会被拒绝。"""
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
                role="standard",
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
        """验证白名单命令返回稳定的结构化执行结果。"""
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
                role="standard",
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


    def test_cli_parser_exposes_serve_command(self) -> None:
        """验证 CLI 从 application 包暴露稳定的 serve 子命令。"""
        parser = build_parser()
        self.assertEqual("coding-harness", parser.prog)
        arguments = parser.parse_args(["serve", "--host", "0.0.0.0", "--port", "9000"])
        self.assertEqual("serve", arguments.command)
        self.assertEqual("0.0.0.0", arguments.host)
        self.assertEqual(9000, arguments.port)

    def test_cli_chat_reuses_service_and_emits_json_lines(self) -> None:
        """验证 CLI chat 复用对话服务，并输出机器可消费的 JSON Lines。"""
        service = Mock(spec=AgentChatService)
        service.stream_chat.return_value = iter(
            [
                {"type": "started", "request_id": "request-1"},
                {"type": "final", "request_id": "request-1", "answer": "完成"},
            ]
        )
        arguments = build_parser().parse_args(
            ["chat", "检查项目", "--session", "cli-session", "--json"]
        )
        output = StringIO()

        exit_code = run_chat(arguments, service=service, output=output)

        self.assertEqual(0, exit_code)
        service.stream_chat.assert_called_once_with(
            "检查项目",
            user="cli-user",
            role="standard",
            session_id="cli-session",
            model=None,
            thinking_enabled=None,
            reasoning_effort=None,
        )
        lines = output.getvalue().splitlines()
        self.assertEqual("started", json.loads(lines[0])["type"])
        self.assertEqual("完成", json.loads(lines[1])["answer"])


if __name__ == "__main__":
    unittest.main()

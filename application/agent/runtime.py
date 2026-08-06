"""DeepSeek model loop for intent recognition and tool execution."""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from ..config import DeepSeekConfigurationError, DeepSeekSettings
from ..prompts import AGENT_SYSTEM_PROMPT, INTENT_RECOGNITION_PROMPT
from ..tools import AgentContext, ToolRegistry, build_tool_registry


class DeepSeekAgent:
    """先识别结构化意图，再执行受控工具调用循环。"""

    def __init__(
        self,
        settings: DeepSeekSettings | None = None,
        *,
        client: Any | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        """装配模型客户端、工具注册表和线程安全的会话容器。"""
        self.settings = settings or DeepSeekSettings.from_env()
        if client is None:
            if not self.settings.api_key:
                raise DeepSeekConfigurationError("DEEPSEEK_API_KEY is not configured")
            client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=90.0,
                max_retries=2,
            )
        self.client = client
        self.tools = tools or build_tool_registry(self.settings)
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._session_locks: dict[str, threading.RLock] = {}
        self._lock = threading.RLock()

    def clear_session(self, session_id: str) -> None:
        """清理指定会话的模型对话历史。"""
        with self._lock:
            self._sessions.pop(session_id, None)

    def run(
        self,
        request: str,
        *,
        user: str = "web-user",
        role: str = "standard",
        session_id: str = "default",
        model: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """执行一次流式 Agent 请求并逐步产出结构化事件。"""
        request = request.strip()
        if not request:
            yield {"type": "error", "message": "请输入任务内容。"}
            return
        selected_model = model or self.settings.model
        if selected_model not in self.settings.allowed_models:
            yield {"type": "error", "message": f"模型不在允许列表中：{selected_model}"}
            return

        request_id = str(uuid.uuid4())
        lock = self._get_session_lock(session_id)
        with lock:
            history = list(self._sessions.get(session_id, []))
            context = AgentContext(
                user=user,
                role=role,
                session_id=session_id,
                request_id=request_id,
                user_request=request,
            )
            yield {
                "type": "started",
                "request_id": request_id,
                "model": selected_model,
            }

            intent = self._recognize_intent(request, history, selected_model)
            yield {"type": "intent", **intent}

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                *history[-12:],
                {"role": "user", "content": request},
            ]
            for round_number in range(1, self.settings.max_rounds + 1):
                yield {
                    "type": "model_round",
                    "round": round_number,
                    "message": "DeepSeek 正在规划下一步",
                }
                response = self._create_completion(
                    model=selected_model,
                    messages=messages,
                    tools=self.tools.schemas,
                )
                choice = response.choices[0]
                message = choice.message
                messages.append(self._assistant_message_to_dict(message))

                tool_calls = list(getattr(message, "tool_calls", None) or [])
                if not tool_calls:
                    answer = (getattr(message, "content", None) or "").strip()
                    if not answer:
                        answer = "模型没有返回可显示的结果，请重新描述任务。"
                    self._sessions[session_id] = self._compact_history(
                        [
                            *history,
                            {"role": "user", "content": request},
                            {"role": "assistant", "content": answer},
                        ]
                    )
                    yield {
                        "type": "final",
                        "answer": answer,
                        "finish_reason": getattr(choice, "finish_reason", None),
                        "usage": self._usage_to_dict(getattr(response, "usage", None)),
                    }
                    return

                for call in tool_calls:
                    tool_name = call.function.name
                    raw_arguments = call.function.arguments or "{}"
                    try:
                        arguments = json.loads(raw_arguments)
                    except json.JSONDecodeError:
                        arguments = {"_raw": raw_arguments}
                    yield {
                        "type": "tool_call",
                        "id": call.id,
                        "name": tool_name,
                        "arguments": arguments,
                    }
                    result = self.tools.execute(tool_name, raw_arguments, context)
                    yield {
                        "type": "tool_result",
                        "id": call.id,
                        "name": tool_name,
                        "result": result,
                    }
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(result, ensure_ascii=False)[:20000],
                        }
                    )

            yield {
                "type": "error",
                "message": f"达到最大工具调用轮数（{self.settings.max_rounds}），任务已停止。",
            }

    def _recognize_intent(
        self,
        request: str,
        history: list[dict[str, Any]],
        model: str,
    ) -> dict[str, Any]:
        """调用模型识别请求意图，并规范化不稳定的模型输出。"""
        recent_context = [
            item for item in history[-4:] if item.get("role") in {"user", "assistant"}
        ]
        response = self._create_completion(
            model=model,
            messages=[
                {"role": "system", "content": INTENT_RECOGNITION_PROMPT},
                *recent_context,
                {"role": "user", "content": request},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = (response.choices[0].message.content or "").strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.S)
            parsed = json.loads(match.group(0)) if match else {}

        intents = parsed.get("intents") or ["question_answering"]
        if not isinstance(intents, list):
            intents = [str(intents)]
        entities = parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {}
        suggested = parsed.get("suggested_tools") or []
        if not isinstance(suggested, list):
            suggested = [str(suggested)]
        try:
            confidence = min(1.0, max(0.0, float(parsed.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        return {
            "intents": [str(item) for item in intents[:8]],
            "entities": entities,
            "confidence": confidence,
            "needs_clarification": bool(parsed.get("needs_clarification", False)),
            "clarification_question": str(parsed.get("clarification_question") or ""),
            "suggested_tools": [str(item) for item in suggested[:8]],
        }

    def _create_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float = 0.2,
    ) -> Any:
        """根据统一配置向模型客户端提交一次补全请求。"""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.settings.max_output_tokens,
        }
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        if response_format:
            payload["response_format"] = response_format
        if self.settings.thinking_enabled:
            payload["reasoning_effort"] = self.settings.reasoning_effort
            payload["extra_body"] = {"thinking": {"type": "enabled"}}
        return self.client.chat.completions.create(**payload)

    @staticmethod
    def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
        """将模型助手消息转换为下一轮可复用的字典格式。"""
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": getattr(message, "content", None),
        }
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            payload["reasoning_content"] = reasoning
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in tool_calls
            ]
        return payload

    @staticmethod
    def _usage_to_dict(usage: Any) -> dict[str, Any]:
        """将不同客户端形态的 Token 用量转换为普通字典。"""
        if usage is None:
            return {}
        if hasattr(usage, "model_dump"):
            return usage.model_dump(exclude_none=True)
        return {
            key: getattr(usage, key)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if getattr(usage, key, None) is not None
        }

    @staticmethod
    def _compact_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """保留最近的有限轮次，避免会话历史无限增长。"""
        return history[-20:]

    def _get_session_lock(self, session_id: str) -> threading.RLock:
        """获取或创建指定会话的串行执行锁。"""
        with self._lock:
            return self._session_locks.setdefault(session_id, threading.RLock())

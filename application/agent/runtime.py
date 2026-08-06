"""DeepSeek model loop for intent recognition and tool execution."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from ..config import DeepSeekConfigurationError, DeepSeekSettings
from ..prompts import AGENT_SYSTEM_PROMPT, INTENT_RECOGNITION_PROMPT
from ..tools import AgentContext, ToolRegistry, build_tool_registry


@dataclass
class _StreamingResult:
    """汇总一次流式模型调用的公开回答、隐藏推理和工具调用。"""

    content_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)
    reasoning_chars: int = 0
    tool_calls_by_index: dict[int, dict[str, Any]] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def answer(self) -> str:
        """拼接模型流中的全部公开回答分片。"""
        return "".join(self.content_parts)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        """按模型索引返回已经完整聚合的工具调用。"""
        return [self.tool_calls_by_index[index] for index in sorted(self.tool_calls_by_index)]

    def add_tool_call_delta(self, call: Any, fallback_index: int) -> None:
        """把一个工具调用增量合并到对应索引的完整调用中。"""
        index = getattr(call, "index", None)
        if index is None:
            index = fallback_index
        current = self.tool_calls_by_index.setdefault(
            int(index),
            {
                "id": "",
                "type": "function",
                "function": {"name": "", "arguments": ""},
            },
        )
        call_id = getattr(call, "id", None)
        if call_id:
            current["id"] = str(call_id)
        function = getattr(call, "function", None)
        if function is None:
            return
        name = getattr(function, "name", None)
        arguments = getattr(function, "arguments", None)
        if name:
            current["function"]["name"] += str(name)
        if arguments:
            current["function"]["arguments"] += str(arguments)

    def assistant_message(self) -> dict[str, Any]:
        """生成后续工具调用轮次必须回传给 DeepSeek 的助手消息。"""
        message: dict[str, Any] = {"role": "assistant", "content": self.answer or None}
        if self.reasoning_parts:
            message["reasoning_content"] = "".join(self.reasoning_parts)
        if self.tool_calls_by_index:
            message["tool_calls"] = self.tool_calls
        return message


class DeepSeekAgent:
    """先识别结构化意图，再执行受控工具调用循环。"""

    def __init__(
        self,
        settings: DeepSeekSettings | None = None,
        *,
        client: Any | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        """装配模型客户端和受控工具注册表。"""
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

    def close(self) -> None:
        """关闭模型 HTTP 客户端持有的连接资源。"""
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def run(
        self,
        request: str,
        *,
        user: str = "web-user",
        role: str = "standard",
        session_id: str = "default",
        model: str | None = None,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
        history: list[dict[str, Any]] | None = None,
        request_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """基于调用方提供的历史执行请求，并逐步产出结构化事件。"""
        request = request.strip()
        if not request:
            yield {"type": "error", "message": "请输入任务内容。"}
            return
        selected_model = model or self.settings.model
        if selected_model not in self.settings.allowed_models:
            yield {"type": "error", "message": f"模型不在允许列表中：{selected_model}"}
            return
        selected_thinking = (
            self.settings.thinking_enabled if thinking_enabled is None else thinking_enabled
        )
        selected_effort = reasoning_effort or self.settings.reasoning_effort
        if selected_effort not in {"low", "high", "max"}:
            yield {"type": "error", "message": f"不支持的思考强度：{selected_effort}"}
            return

        request_id = request_id or str(uuid.uuid4())
        conversation_history = list(history or [])
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
            "thinking_enabled": selected_thinking,
            "reasoning_effort": selected_effort if selected_thinking else None,
        }

        intent = self._recognize_intent(request, conversation_history, selected_model)
        yield {"type": "intent", **intent}

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            *conversation_history[-12:],
            {"role": "user", "content": request},
        ]
        for round_number in range(1, self.settings.max_rounds + 1):
            yield {
                "type": "model_round",
                "round": round_number,
                "message": "DeepSeek 正在规划下一步",
            }
            streamed_result = _StreamingResult()
            yield from self._stream_completion(
                model=selected_model,
                messages=messages,
                result=streamed_result,
                thinking_enabled=selected_thinking,
                reasoning_effort=selected_effort,
            )
            messages.append(streamed_result.assistant_message())

            tool_calls = streamed_result.tool_calls
            if not tool_calls:
                answer = streamed_result.answer.strip()
                if not answer:
                    answer = "模型没有返回可显示的结果，请重新描述任务。"
                yield {
                    "type": "final",
                    "answer": answer,
                    "finish_reason": streamed_result.finish_reason,
                    "usage": streamed_result.usage,
                }
                return

            for call in tool_calls:
                tool_name = str(call["function"]["name"])
                raw_arguments = str(call["function"]["arguments"] or "{}")
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {"_raw": raw_arguments}
                yield {
                    "type": "tool_call",
                    "id": call["id"],
                    "name": tool_name,
                    "arguments": arguments,
                }
                result = self.tools.execute(tool_name, raw_arguments, context)
                yield {
                    "type": "tool_result",
                    "id": call["id"],
                    "name": tool_name,
                    "result": result,
                }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
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
            thinking_enabled=False,
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
        thinking_enabled: bool,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float = 0.2,
        stream: bool = False,
        reasoning_effort: str | None = None,
    ) -> Any:
        """根据统一配置向模型客户端提交一次补全请求。"""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": self.settings.max_output_tokens,
            "extra_body": {
                "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
            },
        }
        if thinking_enabled:
            payload["reasoning_effort"] = reasoning_effort or self.settings.reasoning_effort
        else:
            payload["temperature"] = temperature
        if stream:
            payload["stream"] = True
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        if response_format:
            payload["response_format"] = response_format
        return self.client.chat.completions.create(**payload)

    def _stream_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        result: _StreamingResult,
        thinking_enabled: bool,
        reasoning_effort: str,
    ) -> Iterator[dict[str, Any]]:
        """消费 DeepSeek 流并仅向调用方产出公开回答增量。"""
        stream = self._create_completion(
            model=model,
            messages=messages,
            tools=self.tools.schemas,
            stream=True,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
        )
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                result.usage = self._usage_to_dict(usage)
            choices = list(getattr(chunk, "choices", None) or [])
            if not choices:
                continue
            choice = choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            if finish_reason:
                result.finish_reason = str(finish_reason)
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                reasoning_text = str(reasoning)
                result.reasoning_parts.append(reasoning_text)
                result.reasoning_chars += len(reasoning_text)
                yield {
                    "type": "thinking_delta",
                    "delta": reasoning_text,
                    "delta_chars": len(reasoning_text),
                    "total_chars": result.reasoning_chars,
                }
            content = getattr(delta, "content", None)
            if content:
                text = str(content)
                result.content_parts.append(text)
                yield {"type": "answer_delta", "delta": text}
            for index, tool_call in enumerate(getattr(delta, "tool_calls", None) or []):
                result.add_tool_call_delta(tool_call, index)

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

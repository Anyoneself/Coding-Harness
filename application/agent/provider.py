"""模型供应商边界及 DeepSeek 的只读流式实现。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import OpenAI

from ..config import DeepSeekConfigurationError, DeepSeekSettings
from ..prompts import AGENT_SYSTEM_PROMPT


@dataclass(frozen=True)
class ModelRequest:
    """描述供应商无关的一次公开模型请求。"""

    turn_id: str
    prompt: str
    history: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    model: str | None = None


@dataclass(frozen=True)
class ModelDelta:
    """描述可以公开和持久化的模型文本增量。"""

    content: str


@dataclass(frozen=True)
class ModelCompleted:
    """描述一次模型调用的最终公开回答与用量。"""

    answer: str
    finish_reason: str | None = None
    usage: dict[str, int | float] = field(default_factory=dict)


ModelEvent = ModelDelta | ModelCompleted


class ModelProvider(Protocol):
    """定义 Turn Runtime 依赖的供应商无关流式模型能力。"""

    def stream(self, request: ModelRequest) -> Iterator[ModelEvent]:
        """流式返回公开文本和最终结果，不执行工具或持久化。"""
        ...

    def close(self) -> None:
        """关闭供应商客户端持有的连接。"""
        ...


class DeepSeekModelProvider:
    """通过 OpenAI-compatible API 提供无工具的 DeepSeek 流式调用。"""

    def __init__(
        self,
        settings: DeepSeekSettings,
        *,
        client: Any | None = None,
    ) -> None:
        """装配 DeepSeek 客户端，并延续项目现有超时与重试边界。"""
        self.settings = settings
        if client is None:
            if not settings.api_key:
                raise DeepSeekConfigurationError("DEEPSEEK_API_KEY is not configured")
            client = OpenAI(
                api_key=settings.api_key,
                base_url=settings.base_url,
                timeout=90.0,
                max_retries=2,
            )
        self.client = client

    def stream(self, request: ModelRequest) -> Iterator[ModelEvent]:
        """把 DeepSeek 流转换为公开增量和稳定完成事件。"""
        selected_model = request.model or self.settings.model
        if selected_model not in self.settings.allowed_models:
            raise ValueError(f"model is not allowed: {selected_model}")
        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            *request.history,
            {"role": "user", "content": request.prompt},
        ]
        stream = self.client.chat.completions.create(
            model=selected_model,
            messages=messages,
            stream=True,
            max_tokens=self.settings.max_output_tokens,
        )
        content_parts: list[str] = []
        finish_reason: str | None = None
        usage: dict[str, int | float] = {}
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                choice = choices[0]
                delta = getattr(getattr(choice, "delta", None), "content", None)
                if delta:
                    text = str(delta)
                    content_parts.append(text)
                    yield ModelDelta(text)
                raw_finish_reason = getattr(choice, "finish_reason", None)
                if raw_finish_reason:
                    finish_reason = str(raw_finish_reason)
            raw_usage = getattr(chunk, "usage", None)
            if raw_usage is not None:
                usage = _public_usage(raw_usage)
        answer = "".join(content_parts).strip()
        if not answer:
            answer = "模型没有返回可显示的结果，请重新描述任务。"
        yield ModelCompleted(answer=answer, finish_reason=finish_reason, usage=usage)

    def close(self) -> None:
        """关闭底层 HTTP 客户端连接。"""
        close = getattr(self.client, "close", None)
        if callable(close):
            close()


class UnavailableModelProvider:
    """在模型未配置时把 Turn 转换为可诊断失败，而非阻断应用启动。"""

    def __init__(self, message: str = "DEEPSEEK_API_KEY is not configured") -> None:
        """保存不会泄漏密钥或内部配置的失败原因。"""
        self._message = message

    def stream(self, request: ModelRequest) -> Iterator[ModelEvent]:
        """在执行边界抛出配置错误，使 Turn 进入稳定 failed 状态。"""
        del request
        raise DeepSeekConfigurationError(self._message)
        yield  # pragma: no cover - 保持生成器协议，异常在迭代时发生

    def close(self) -> None:
        """未持有外部资源，因此关闭操作为空。"""


def _public_usage(raw_usage: Any) -> dict[str, int | float]:
    """从供应商用量对象提取可公开的数值字段。"""
    fields = ("prompt_tokens", "completion_tokens", "total_tokens", "total_cost", "cost")
    result: dict[str, int | float] = {}
    for field_name in fields:
        value = getattr(raw_usage, field_name, None)
        if isinstance(value, (int, float)):
            result[field_name] = value
    return result

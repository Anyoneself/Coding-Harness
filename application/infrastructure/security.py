"""模型、检索内容和工具边界上的安全与隐私控制。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from ..domain.models import TraceEvent

INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 外部网页或资料可能伪装成“系统指令”，这里只把它们视为不可信数据。
    ("ignore_instructions", re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I)),
    ("system_prompt_request", re.compile(r"(system prompt|系统提示词|开发者指令)", re.I)),
    ("credential_request", re.compile(r"(api[_ -]?key|password|token|密钥|密码)", re.I)),
    ("tool_override", re.compile(r"(call|invoke|调用).{0,20}(tool|工具|shell|bash)", re.I)),
)

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|cookie|phone|email|身份证)",
    re.I,
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")


def stable_hash(value: str) -> str:
    """生成稳定短哈希，用于脱敏标识和幂等键，不暴露原始内容。"""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def redact_text(value: str, limit: int = 240) -> str:
    """对自由文本中的邮箱、手机号做脱敏，并限制 Trace 字段长度。"""

    value = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    value = PHONE_PATTERN.sub("[REDACTED_PHONE]", value)
    return value[:limit]


def redact(value: Any) -> Any:
    """在数据进入日志和 Trace 前，递归清理密钥和个人信息。"""

    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEY_PATTERN.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value[:20]]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value[:20])
    if isinstance(value, str):
        return redact_text(value)
    return value


def inspect_untrusted_content(content: str) -> tuple[str, tuple[str, ...]]:
    """把工具或检索内容当作数据，并标记可能的间接提示词注入。

    可疑行会被替换，剩余内容放入明确的数据边界中。真正的工具权限仍由
    高风险写工具必须独立检查，不能只依赖正则检测来保护高风险操作。
    """

    # 第一步：识别内容中出现了哪些注入特征，供后续审计和告警使用。
    flags = tuple(name for name, pattern in INJECTION_PATTERNS if pattern.search(content))
    cleaned_lines = []
    # 第二步：删除伪装成指令的行，保留正常业务内容。
    for line in content.splitlines():
        if any(pattern.search(line) for _, pattern in INJECTION_PATTERNS):
            cleaned_lines.append("[UNTRUSTED_INSTRUCTION_REMOVED]")
        else:
            cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    # 第三步：使用标签明确告诉后续模型“这是外部数据，不是系统指令”。
    bounded = f"<untrusted_tool_data>\n{cleaned}\n</untrusted_tool_data>"
    return bounded, flags


class TraceRecorder:
    """记录阶段级 Trace，但不保存完整 Prompt 和文档原文。"""

    def __init__(self, request_id: str, session_id: str) -> None:
        """初始化指定请求和会话的阶段事件集合。"""
        self.request_id = request_id
        self.session_id = session_id
        self.events: list[TraceEvent] = []

    @contextmanager
    def span(
        self, stage: str, input_summary: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        """记录一个阶段的开始、结果、耗时和异常类型。"""

        started = perf_counter()
        output: dict[str, Any] = {}
        # 阶段开始时只写入已经脱敏的输入摘要。
        self.events.append(
            TraceEvent(
                request_id=self.request_id,
                session_id=self.session_id,
                stage=stage,
                status="started",
                timestamp=datetime.now(UTC).isoformat(),
                input_summary=redact(input_summary or {}),
            )
        )
        try:
            yield output
        except Exception as exc:
            # 异常时记录失败阶段，评估系统可以据此定位链路故障。
            self.events.append(
                TraceEvent(
                    request_id=self.request_id,
                    session_id=self.session_id,
                    stage=stage,
                    status="failed",
                    timestamp=datetime.now(UTC).isoformat(),
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    output_summary=redact(output),
                    error_type=type(exc).__name__,
                )
            )
            raise
        else:
            # 成功时记录耗时和输出摘要，用于延迟分析和阶段评分。
            self.events.append(
                TraceEvent(
                    request_id=self.request_id,
                    session_id=self.session_id,
                    stage=stage,
                    status="succeeded",
                    timestamp=datetime.now(UTC).isoformat(),
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    output_summary=redact(output),
                )
            )

    def to_dicts(self) -> list[dict[str, Any]]:
        """将 Trace 事件转换为可安全序列化的字典列表。"""
        return [json.loads(json.dumps(event.__dict__, ensure_ascii=False)) for event in self.events]

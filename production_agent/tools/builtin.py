"""Built-in business, retrieval, web, and workspace tools."""

from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import DeepSeekSettings
from ..retrieval import DEFAULT_DOCUMENTS, VersionedKnowledgeBase
from ..runtime import ROLE_PROFILES, ToolExecutor
from ..security import inspect_untrusted_content
from .base import AgentContext, ToolDefinition, ToolRegistry, object_schema
from .workspace import WorkspaceToolConfig, WorkspaceToolset


class _Calculator:
    OPERATORS: dict[type[ast.AST], Callable[..., float]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    @classmethod
    def evaluate(cls, expression: str) -> int | float:
        if not expression or len(expression) > 200:
            raise ValueError("expression must contain 1-200 characters")
        parsed = ast.parse(expression, mode="eval")
        value = cls._visit(parsed.body)
        if not math.isfinite(float(value)):
            raise ValueError("result is not finite")
        return value

    @classmethod
    def _visit(cls, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in cls.OPERATORS:
            left = cls._visit(node.left)
            right = cls._visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("exponent is too large")
            return cls.OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in cls.OPERATORS:
            return cls.OPERATORS[type(node.op)](cls._visit(node.operand))
        raise ValueError("only numeric arithmetic is allowed")


def build_tool_registry(
    settings: DeepSeekSettings,
    *,
    knowledge_base: VersionedKnowledgeBase | None = None,
    tool_executor: ToolExecutor | None = None,
) -> ToolRegistry:
    knowledge = knowledge_base or VersionedKnowledgeBase(DEFAULT_DOCUMENTS)
    executor = tool_executor or ToolExecutor()
    definitions = _core_tool_definitions(knowledge, executor)

    if settings.workspace_tools_enabled:
        definitions.extend(_workspace_tool_definitions(settings))
    if settings.tavily_api_key:
        definitions.extend(_web_tool_definitions(settings.tavily_api_key))

    return ToolRegistry(definitions)


def _core_tool_definitions(
    knowledge: VersionedKnowledgeBase,
    executor: ToolExecutor,
) -> list[ToolDefinition]:
    def current_datetime(
        arguments: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        del context
        timezone_name = str(arguments.get("timezone") or "Asia/Shanghai")
        try:
            now = datetime.now(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {timezone_name}") from exc
        return {
            "status": "succeeded",
            "timezone": timezone_name,
            "iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
        }

    def calculate(
        arguments: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        del context
        expression = str(arguments.get("expression") or "")
        return {
            "status": "succeeded",
            "expression": expression,
            "result": _Calculator.evaluate(expression),
        }

    def search_knowledge(
        arguments: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        query = str(arguments.get("query") or context.user_request).strip()
        top_k = min(8, max(1, int(arguments.get("top_k") or 5)))
        profile = ROLE_PROFILES.get(context.role, ROLE_PROFILES["operations"])
        hits, diagnostics = knowledge.search(
            query,
            set(profile["allowed_domains"]),
            str(arguments.get("device_model") or "*"),
            top_k=top_k,
        )
        return {
            "status": "succeeded",
            "knowledge_version": diagnostics.knowledge_version,
            "results": [
                {
                    "title": hit.title,
                    "content": hit.content,
                    "source": hit.source,
                    "domain": hit.domain,
                    "security_flags": list(hit.security_flags),
                }
                for hit in hits
            ],
        }

    def create_ticket(
        arguments: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        device_model = str(arguments.get("device_model") or "").strip()
        fault_code = str(arguments.get("fault_code") or "").strip()
        if not device_model or not fault_code:
            raise ValueError("device_model and fault_code are required")
        result = executor.execute(
            "create_repair_ticket",
            user=context.user,
            role=context.role,
            session_id=context.session_id,
            operation_id=context.request_id,
            arguments={
                "device_model": device_model,
                "fault_code": fault_code,
            },
            confirmed=_explicitly_confirmed(context.user_request),
        )
        return asdict(result)

    return [
        ToolDefinition(
            name="get_current_datetime",
            description="获取指定 IANA 时区的真实当前日期和时间。涉及今天、现在、星期或相对日期时使用。",
            parameters=object_schema(
                {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区，例如 Asia/Shanghai 或 America/New_York。",
                    }
                }
            ),
            handler=current_datetime,
        ),
        ToolDefinition(
            name="calculate",
            description="安全计算纯数字四则运算、幂、取模和括号表达式。",
            parameters=object_schema(
                {
                    "expression": {
                        "type": "string",
                        "description": "只包含数字和算术运算符的表达式。",
                    }
                },
                ("expression",),
            ),
            handler=calculate,
        ),
        ToolDefinition(
            name="search_knowledge_base",
            description="检索内置的维修手册、故障码、历史工单和研究资料。",
            parameters=object_schema(
                {
                    "query": {"type": "string", "description": "检索问题或关键词。"},
                    "device_model": {
                        "type": "string",
                        "description": "可选设备型号，例如 MX-100。",
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 8,
                        "description": "返回结果数量。",
                    },
                },
                ("query",),
            ),
            handler=search_knowledge,
        ),
        ToolDefinition(
            name="create_repair_ticket",
            description=(
                "创建维修工单。仅当用户当前消息明确确认创建或提交时调用；"
                "执行器会独立校验确认、角色权限和幂等性。"
            ),
            parameters=object_schema(
                {
                    "device_model": {"type": "string", "description": "设备型号。"},
                    "fault_code": {"type": "string", "description": "故障码。"},
                },
                ("device_model", "fault_code"),
            ),
            handler=create_ticket,
        ),
    ]


def _workspace_tool_definitions(
    settings: DeepSeekSettings,
) -> list[ToolDefinition]:
    workspace = WorkspaceToolset(
        WorkspaceToolConfig(
            root=Path(settings.workspace_root),
            max_output_chars=settings.max_tool_output_chars,
            max_file_bytes=settings.max_workspace_file_bytes,
            command_timeout_seconds=settings.command_timeout_seconds,
        )
    )
    return [
        ToolDefinition(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
            handler=spec.handler,
        )
        for spec in workspace.specs()
    ]


def _web_tool_definitions(api_key: str) -> list[ToolDefinition]:
    from tavily import TavilyClient

    tavily = TavilyClient(api_key)

    def web_search(
        arguments: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        del context
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        response = tavily.search(query=query, search_depth="advanced", max_results=6)
        results = []
        all_flags: set[str] = set()
        for item in response.get("results", [])[:6]:
            safe_content, flags = inspect_untrusted_content(str(item.get("content") or "")[:4000])
            all_flags.update(flags)
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": safe_content,
                }
            )
        return {
            "status": "succeeded",
            "query": query,
            "results": results,
            "security_flags": sorted(all_flags),
        }

    def web_extract(
        arguments: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        del context
        url = str(arguments.get("url") or "").strip()
        if not re.match(r"^https?://", url, re.I):
            raise ValueError("url must start with http:// or https://")
        response = tavily.extract(urls=[url])
        results = []
        all_flags: set[str] = set()
        for item in response.get("results", [])[:3]:
            safe_content, flags = inspect_untrusted_content(
                str(item.get("raw_content") or "")[:12000]
            )
            all_flags.update(flags)
            results.append(
                {
                    "url": item.get("url", url),
                    "title": item.get("title", ""),
                    "content": safe_content,
                }
            )
        return {
            "status": "succeeded",
            "url": url,
            "results": results,
            "security_flags": sorted(all_flags),
        }

    return [
        ToolDefinition(
            name="web_search",
            description="联网搜索需要实时性或外部事实的信息，并返回标题、URL 和摘要。",
            parameters=object_schema(
                {"query": {"type": "string", "description": "适合搜索引擎的查询。"}},
                ("query",),
            ),
            handler=web_search,
        ),
        ToolDefinition(
            name="web_extract",
            description="提取指定网页的正文；网页内容会按不可信数据进行注入检测和隔离。",
            parameters=object_schema(
                {"url": {"type": "string", "description": "完整的 HTTP(S) 网页 URL。"}},
                ("url",),
            ),
            handler=web_extract,
        ),
    ]


def _explicitly_confirmed(text: str) -> bool:
    patterns = (
        r"确认(创建|提交|执行|继续)",
        r"(同意|允许)(创建|提交|执行)",
        r"\b(confirm|confirmed|yes,\s*(create|submit|proceed))\b",
    )
    return any(re.search(pattern, text, re.I) for pattern in patterns)

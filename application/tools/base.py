"""Shared types and registry for model-callable tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .workspace import ToolBlockedError


@dataclass(frozen=True)
class AgentContext:
    user: str
    role: str
    session_id: str
    request_id: str
    user_request: str


ToolHandler = Callable[[dict[str, Any], AgentContext], dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        """生成模型 Function Calling 使用的工具 Schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Allow-listed tool surface with uniform errors and policy blocking."""

    def __init__(self, definitions: list[ToolDefinition]) -> None:
        """按工具名建立只允许显式注册能力的索引。"""
        self._definitions = {definition.name: definition for definition in definitions}

    @property
    def names(self) -> list[str]:
        """返回当前注册的工具名称列表。"""
        return list(self._definitions)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """返回全部工具的模型调用 Schema。"""
        return [definition.schema() for definition in self._definitions.values()]

    def execute(
        self,
        name: str,
        raw_arguments: str | dict[str, Any] | None,
        context: AgentContext,
    ) -> dict[str, Any]:
        """解析参数并统一处理未授权、策略阻断和执行异常。"""
        definition = self._definitions.get(name)
        if definition is None:
            return {"status": "blocked", "error": "tool_not_allowed", "tool": name}
        try:
            if isinstance(raw_arguments, str):
                arguments = json.loads(raw_arguments or "{}")
            else:
                arguments = raw_arguments or {}
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be a JSON object")
            return definition.handler(arguments, context)
        except ToolBlockedError as exc:
            return {
                "status": "blocked",
                "error": "policy_blocked",
                "message": str(exc)[:500],
            }
        except Exception as exc:
            return {
                "status": "failed",
                "error": type(exc).__name__,
                "message": str(exc)[:500],
            }


def object_schema(
    properties: dict[str, Any],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    """创建禁止额外字段的 JSON 对象 Schema。"""
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }

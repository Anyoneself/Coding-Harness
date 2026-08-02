"""Backward-compatible imports for workspace tools."""

from .tools.workspace import (
    ToolBlockedError,
    WorkspaceToolConfig,
    WorkspaceToolset,
    WorkspaceToolSpec,
)

__all__ = [
    "ToolBlockedError",
    "WorkspaceToolConfig",
    "WorkspaceToolSpec",
    "WorkspaceToolset",
]

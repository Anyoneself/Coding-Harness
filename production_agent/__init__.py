"""Production-oriented building blocks for the local Agent demo."""

from .agent import DeepSeekAgent
from .config import DeepSeekSettings
from .evaluation import EvaluationCase, EvaluationSuite, compare_versions
from .retrieval import KnowledgeDocument, VersionedKnowledgeBase
from .runtime import AgentService, ConcurrentUpdateError, SessionStore
from .tools import ToolRegistry, WorkspaceToolConfig, WorkspaceToolset

__all__ = [
    "AgentService",
    "ConcurrentUpdateError",
    "DeepSeekAgent",
    "DeepSeekSettings",
    "EvaluationCase",
    "EvaluationSuite",
    "KnowledgeDocument",
    "SessionStore",
    "ToolRegistry",
    "VersionedKnowledgeBase",
    "WorkspaceToolConfig",
    "WorkspaceToolset",
    "compare_versions",
]

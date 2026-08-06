"""模型驱动的 Agent 运行时。"""

from ..prompts import AGENT_SYSTEM_PROMPT
from .runtime import DeepSeekAgent

DEFAULT_SYSTEM_PROMPT = AGENT_SYSTEM_PROMPT

__all__ = ["DEFAULT_SYSTEM_PROMPT", "DeepSeekAgent"]

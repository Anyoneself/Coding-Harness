"""命令执行沙箱边界及失败关闭实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CommandExecutionDeniedError(PermissionError):
    """当前环境没有可信 OS 沙箱，因此拒绝执行命令。"""


@dataclass(frozen=True)
class CommandResult:
    """描述沙箱命令执行的稳定公开结果。"""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    truncated: bool = False


class SandboxAdapter(Protocol):
    """定义受控命令执行必须满足的 OS 隔离边界。"""

    def execute(
        self,
        arguments: list[str],
        *,
        cwd: str,
        timeout_seconds: int,
    ) -> CommandResult:
        """在可信隔离环境中执行参数数组。"""
        ...


class DenyCommandSandbox:
    """在没有可信 OS 沙箱时无条件拒绝命令执行。"""

    def execute(
        self,
        arguments: list[str],
        *,
        cwd: str,
        timeout_seconds: int,
    ) -> CommandResult:
        """明确失败关闭，避免把应用层白名单误当作 OS 隔离。"""
        del arguments, cwd, timeout_seconds
        raise CommandExecutionDeniedError(
            "command execution is disabled because no trusted OS sandbox is configured"
        )

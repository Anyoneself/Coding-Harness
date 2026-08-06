"""My-Agent 命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO

from ..config import DeepSeekSettings
from ..services.chat import AgentChatService


def build_parser() -> argparse.ArgumentParser:
    """创建包含 Web 服务子命令的命令行解析器。"""
    parser = argparse.ArgumentParser(prog="my-agent", description="My-Agent 工程命令行")
    subcommands = parser.add_subparsers(dest="command")
    serve = subcommands.add_parser("serve", help="启动 Web 与 SSE 服务")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve.add_argument("--port", type=int, default=8000, help="监听端口")
    serve.add_argument("--reload", action="store_true", help="启用开发热重载")
    chat = subcommands.add_parser("chat", help="执行一次可持久化的 Agent 对话")
    chat.add_argument("message", nargs="?", help="任务内容；省略时从标准输入读取")
    chat.add_argument("--session", default="default", help="用于恢复上下文的会话 ID")
    chat.add_argument("--user", default="cli-user", help="调用用户标识")
    chat.add_argument("--role", default="standard", help="调用角色")
    chat.add_argument("--model", default=None, help="允许列表中的模型名称")
    chat.add_argument(
        "--thinking",
        choices=("disabled", "low", "high", "max"),
        default=None,
        help="覆盖本次请求的深度思考模式",
    )
    chat.add_argument("--json", action="store_true", help="以 JSON Lines 输出全部事件")
    return parser


def run_server(host: str, port: int, reload_enabled: bool) -> None:
    """使用 Uvicorn 启动 My-Agent Web 应用。"""
    import uvicorn

    uvicorn.run(
        "application.app:app",
        host=host,
        port=port,
        reload=reload_enabled,
    )


def run_chat(
    arguments: argparse.Namespace,
    *,
    service: AgentChatService | None = None,
    output: TextIO | None = None,
) -> int:
    """通过统一对话服务执行 CLI 请求，并输出最终答案或结构化事件。"""
    chat_service = service or AgentChatService(DeepSeekSettings.from_env())
    output_stream = output or sys.stdout
    message = arguments.message
    if message is None:
        message = sys.stdin.read().strip()
    if not message:
        print("任务内容不能为空。", file=sys.stderr)
        return 2

    has_error = False
    for event in chat_service.stream_chat(
        message,
        user=arguments.user,
        role=arguments.role,
        session_id=arguments.session,
        model=arguments.model,
        thinking_enabled=None if arguments.thinking is None else arguments.thinking != "disabled",
        reasoning_effort=(
            arguments.thinking if arguments.thinking in {"low", "high", "max"} else None
        ),
    ):
        if arguments.json:
            print(json.dumps(event, ensure_ascii=False), file=output_stream)
        elif event.get("type") == "final":
            print(str(event.get("answer") or ""), file=output_stream)
        elif event.get("type") == "error":
            print(str(event.get("message") or "Agent 执行失败。"), file=sys.stderr)
        has_error = has_error or event.get("type") == "error"
    return 1 if has_error else 0


def main(argv: Sequence[str] | None = None) -> int:
    """解析 CLI 参数并执行对应的工程命令。"""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    command = arguments.command or "serve"
    if command == "serve":
        run_server(
            getattr(arguments, "host", "127.0.0.1"),
            getattr(arguments, "port", 8000),
            getattr(arguments, "reload", False),
        )
        return 0
    if command == "chat":
        return run_chat(arguments)
    parser.error(f"未知命令：{command}")
    return 2

"""My-Agent 命令行入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """创建包含 Web 服务子命令的命令行解析器。"""
    parser = argparse.ArgumentParser(prog="my-agent", description="My-Agent 工程命令行")
    subcommands = parser.add_subparsers(dest="command")
    serve = subcommands.add_parser("serve", help="启动 Web 与 SSE 服务")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve.add_argument("--port", type=int, default=8000, help="监听端口")
    serve.add_argument("--reload", action="store_true", help="启用开发热重载")
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
    parser.error(f"未知命令：{command}")
    return 2

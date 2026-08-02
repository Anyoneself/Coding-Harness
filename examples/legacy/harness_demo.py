#!/usr/bin/env python3
"""A minimal tool-using agent powered by the DeepSeek OpenAI-compatible API."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from tavily import TavilyClient

# Configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", PROJECT_ROOT)).resolve()
MAX_TOOL_OUTPUT = 20_000
MAX_TURNS = 20

# Secrets must come from the runtime environment, never source control.
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

SYSTEM = (
    "你是顶级AI助手。"
    "使用 get_current_date 获取当前日期和时间。"
    "使用 web_search 搜索网络获取实时信息，使用 web_extract 提取网页详细内容。"
    "使用 read、edit 和 bash 工具来完成任务。任务完成总结经验。"
)


# Tool Implementations
def get_current_date() -> str:
    """Get the current local date, time, and weekday."""
    now = datetime.datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return json.dumps({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": weekdays[now.weekday()],
        "iso": now.isoformat(),
    }, ensure_ascii=False)


def read(path: str) -> str:
    """Read a UTF-8 text file from the workspace."""
    target = (WORKSPACE / path).resolve()
    return target.read_text(encoding="utf-8")[:MAX_TOOL_OUTPUT]


def edit(path: str, old: str, new: str) -> str:
    """Replace exactly one matching block in a workspace file."""
    target = (WORKSPACE / path).resolve()
    text = target.read_text(encoding="utf-8")
    if (count := text.count(old)) != 1:
        return f"edit rejected: expected one match, found {count}"

    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"edited {target.relative_to(WORKSPACE)}"


def bash(command: str) -> str:
    """Run a shell command directly in the workspace."""
    code, out = subprocess.getstatusoutput(f"cd '{WORKSPACE}' && {command}")
    return f"exit_code={code}\n{out[-MAX_TOOL_OUTPUT:]}"


def web_search(query: str) -> str:
    """Search the web using Tavily API and return structured results."""
    if not TAVILY_API_KEY:
        return "web_search error: TAVILY_API_KEY is not configured"
    try:
        client = TavilyClient(TAVILY_API_KEY)
        response = client.search(query=query, search_depth="advanced")
        results = response.get("results", [])
        if not results:
            return json.dumps({"message": "no results found", "results": []}, ensure_ascii=False)

        simplified = []
        for r in results[:10]:
            simplified.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content", "") or "")[:2_000],
            })
        return json.dumps({"results": simplified, "total": len(results)}, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"web_search error: {e}"


def web_extract(url: str) -> str:
    """Extract clean readable text content from a web page URL via Tavily."""
    if not TAVILY_API_KEY:
        return "web_extract error: TAVILY_API_KEY is not configured"
    try:
        client = TavilyClient(TAVILY_API_KEY)
        response = client.extract(urls=[url])
        results = response.get("results", [])
        if not results:
            return json.dumps({"message": "no content extracted", "url": url}, ensure_ascii=False)

        r = results[0]
        return json.dumps({
            "url": r.get("url", url),
            "title": r.get("title", ""),
            "content": (r.get("raw_content", "") or "")[:MAX_TOOL_OUTPUT],
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"web_extract error: {e}"


# Tool Schemas & Registries
def tool_schema(name: str, description: str, properties: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v} for k, v in properties.items()},
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


TOOLS: dict[str, Callable[..., str]] = {
    "get_current_date": get_current_date,
    "read": read,
    "edit": edit,
    "bash": bash,
    "web_search": web_search,
    "web_extract": web_extract,
}

SCHEMAS = [
    tool_schema("get_current_date", "获取当前系统本地日期、时间和星期。", {}),
    tool_schema("read", "读取工作区中的文本文件。", {"path": "相对文件路径。"}),
    tool_schema(
        "edit", "替换工作区文件中的实体文本块。",
        {"path": "相对文件路径。", "old": "要被替换的原文本。", "new": "替换后的新文本。"}
    ),
    tool_schema("bash", "在workspace中执行 Shell 命令。", {"command": "Shell 命令。"}),
    tool_schema(
        "web_search",
        "使用 Tavily API 联网搜索，返回包含标题、URL 和内容摘要的结构化结果。用于获取实时信息、新闻和事实。",
        {"query": "搜索查询字符串。"},
    ),
    tool_schema(
        "web_extract",
        "通过 Tavily 提取网页的干净可读文本内容。配合 web_search 使用以获取页面全文。",
        {"url": "要提取内容的网页完整 URL。"},
    ),
]


# Main Agent Execution Loop
def run_agent(task: str, messages: list[Any] | None = None) -> list[Any]:
    """Run the observe-think-act loop for a task, printing all reasoning and tool logs."""

    client = OpenAI(api_key=os.environ.get("DS_API"), base_url="https://api.deepseek.com")

    if messages is None:
        messages = [{"role": "system", "content": SYSTEM}]

    messages.append({"role": "user", "content": task})

    for turn in range(1, MAX_TURNS + 1):
        print(f"\n==================== [ Turn {turn}/{MAX_TURNS} ] ====================")

        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            tools=SCHEMAS,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
        )
        msg = response.choices[0].message
        messages.append(msg)

        # 1. 打印思考过程 (Thinking / Reasoning Content)
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "thinking", None)
        if reasoning:
            print("\n🧠 【思考过程 (Thinking Process)】:")
            print(reasoning)

        # 2. 打印模型的直接文本输出
        if msg.content:
            print("\n🤖 【模型输出 (Model Output)】:")
            print(msg.content)

        # 如果没有工具调用，说明 Agent 已经得出最终答案或结束交互
        if not msg.tool_calls:
            print("\n✅ 【任务结束】")
            return messages

        # 3. 执行工具并打印工具输入与输出
        for call in msg.tool_calls:
            func_name = call.function.name
            args_str = call.function.arguments
            print(f"\n🛠️ 【工具调用 (Tool Call)】: {func_name}")
            print(f"📥 【调用参数 (Arguments)】: {args_str}")

            try:
                fn = TOOLS[func_name]
                args = json.loads(args_str) if args_str else {}
                result = fn(**args)
            except Exception as err:
                result = f"tool error: {err}"

            result_trimmed = str(result)[:MAX_TOOL_OUTPUT]
            print(f"📤 【工具返回 (Tool Output)】:\n{result_trimmed}")

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result_trimmed,
            })

    print(f"\n⚠️ 警告: 已达到最大轮数限制 ({MAX_TURNS})")
    return messages


def main():
    print("🤖 Agent 交互终端已启动（输入 'exit' 或 'quit' 退出，输入 'clear' 清空对话历史）\n")
    history: list[Any] = [{"role": "system", "content": SYSTEM}]

    while True:
        try:
            user_input = input("\n👤 User > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n退出系统。")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("退出系统。")
            break

        if user_input.lower() == "clear":
            history = [{"role": "system", "content": SYSTEM}]
            print("🧹 对话历史已清空。")
            continue

        history = run_agent(user_input, messages=history)


if __name__ == "__main__":
    main()

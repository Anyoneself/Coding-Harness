#!/usr/bin/env python3
"""A minimal tool-using agent powered by the DeepSeek OpenAI-compatible API."""

from __future__ import annotations

import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from tavily import TavilyClient

# Configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", PROJECT_ROOT)).resolve()
MEMORY_FILE = Path(
    os.environ.get("AGENT_MEMORY_FILE", PROJECT_ROOT / ".mini-agent-memory.jsonl")
).resolve()
MAX_TOOL_OUTPUT = 20_000
MAX_TURNS = 20

# Secrets must come from the runtime environment, never source control.
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

SYSTEM = (
    "你是顶级AI助手。请每次请求优先使用 get_current_date 获取当前系统日期时间。"
    "**每次完成任务或获得有用信息后，应当主动调用 `memory_add` 记录简洁、可复用的经验教训或事实**，这样在后续对话中就能通过 `memory_search` 更好地调用这些知识。"
    "使用 web_search 搜索网络获取实时信息，使用 web_extract 提取网页详细内容。"
    "使用 read、edit 和 bash 工具来完成任务。任务完成总结经验。"
)


# Tool Implementations
def get_current_date() -> str:
    """Get the current local date, time, and weekday."""
    now = datetime.now()
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


def memory_add(content: str) -> str:
    """Persist one reusable memory as a JSON line."""
    if not (content := content.strip()):
        return "memory rejected: content is empty"

    record = {"created_at": datetime.now(timezone.utc).isoformat(), "content": content[:4_000]}
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MEMORY_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return "memory saved"


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


def _search_units(text: str) -> set[str]:
    words = "".join(c.lower() if c.isalnum() else " " for c in text).split()
    compact = "".join(words)
    return set(words) | {compact[i: i + 2] for i in range(max(0, len(compact) - 1))}


def memory_search(query: str) -> str:
    """Retrieve up to five memories with simple lexical overlap."""
    if not MEMORY_FILE.exists():
        return "[]"

    records = [json.loads(line) for line in MEMORY_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    q_units = _search_units(query)
    ranked = sorted(
        enumerate(records),
        key=lambda item: (len(q_units & _search_units(str(item[1].get("content", "")))), item[0]),
        reverse=True,
    )
    return json.dumps([record for _, record in ranked[:5]], ensure_ascii=False)


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
    "read": read, "edit": edit, "bash": bash,
    "memory_search": memory_search, "memory_add": memory_add,
    "web_search": web_search, "web_extract": web_extract,
}

SCHEMAS = [
    tool_schema("get_current_date", "获取当前系统本地日期、时间和星期。", {}),
    tool_schema("read", "读取工作区中的文本文件。", {"path": "相对文件路径。"}),
    tool_schema(
        "edit", "替换工作区文件中的实体文本块。",
        {"path": "相对文件路径。", "old": "要被替换的原文本。", "new": "替换后的新文本。"}
    ),
    tool_schema("bash", "在workspace中执行 Shell 命令。", {"command": "Shell 命令。"}),
    tool_schema("memory_search", "搜索之前保存的可复用记忆。", {"query": "搜索关键词。"}),
    tool_schema("memory_add", "保存一条简洁、可复用的事实或经验教训。", {"content": "记忆内容。"}),
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
def run(task: str, client: OpenAI | None = None) -> str:
    """Run the observe-think-act loop, logging all execution details."""

    if client is None:
        client = OpenAI(api_key=os.environ.get("DS_API"), base_url="https://api.deepseek.com")
    messages: list[Any] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]

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

        # 1. 打印思考过程 (Reasoning / Thinking)
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "thinking", None)
        if reasoning:
            print("\n🧠 【思考过程 (Thinking Process)】:")
            print(reasoning)

        # 2. 打印模型的直接回答输出
        if msg.content:
            print("\n🤖 【模型回答 (Model Output)】:")
            print(msg.content)

        # 无工具调用时结束本轮任务
        if not msg.tool_calls:
            print("\n✅ 【任务完成】")
            return msg.content or ""

        # 3. 打印工具调用详情并执行
        for call in msg.tool_calls:
            func_name = call.function.name
            args_str = call.function.arguments
            print(f"\n🛠️ 【调用工具】: {func_name}")
            print(f"📥 【传入参数】: {args_str}")

            try:
                fn = TOOLS[func_name]
                args = json.loads(args_str) if args_str else {}
                result = fn(**args)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as err:
                result = f"tool error: {err}"

            result_trimmed = str(result)[:MAX_TOOL_OUTPUT]
            print(f"📤 【工具输出】:\n{result_trimmed}")

            messages.append({"role": "tool", "tool_call_id": call.id, "content": result_trimmed})

    raise RuntimeError(f"agent exceeded the {MAX_TURNS}-turn limit")


def interactive_loop() -> None:
    client = OpenAI(api_key=os.environ.get("DS_API"), base_url="https://api.deepseek.com")
    print("🤖 Agent 交互终端已启动（输入 'exit'、'quit' 或 'q' 退出）\n")

    while True:
        try:
            task = input("\n📝 Task: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 退出程序。")
            break

        if not task:
            print("  （任务为空，请重新输入）")
            continue

        if task.lower() in ("exit", "quit", "q"):
            print("👋 退出程序。")
            break

        print(f"\n⚙️  开始执行任务: {task}")
        print("=" * 60)
        try:
            run(task, client)
        except RuntimeError as e:
            print(f"❌ 运行时错误: {e}")
        except Exception as e:
            print(f"❌ 异常: {e}")
        print("=" * 60)


if __name__ == "__main__":
    # 如果提供了命令行参数，执行单次任务后退出
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:]).strip()
        if task:
            run(task)
        else:
            print("error: task is empty")
        raise SystemExit(0)

    # 否则进入无限循环交互模式
    interactive_loop()

#!/usr/bin/env python3
"""A self-evolving tool-using agent powered by DeepSeek API with reflection and self-modification capabilities."""

from __future__ import annotations

import importlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from tavily import TavilyClient

# Configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", PROJECT_ROOT)).resolve()
SCRIPT_PATH = Path(__file__).resolve()
MEMORY_FILE = Path(
    os.environ.get("AGENT_MEMORY_FILE", PROJECT_ROOT / ".mini-agent-memory.jsonl")
).resolve()
MAX_TOOL_OUTPUT = 20_000
MAX_TURNS = 120

# Secrets must come from the runtime environment, never source control.
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

SYSTEM = f"""你是顶级自进化 AI 助手。你拥有强大的自我反思与自我扩充工具能力。

【记忆与知识管理】
1. 每次响应请求时，必须先使用 memory_search 检索以往记录的相关经验。
2. 任务完成前或遇到关键突破时，必须使用 memory_add 记录简洁、可复用的事实或经验教训。

【自我进化与自修改能力（⚡ 修改后即时生效）】
1. 你的源码文件位置在：{SCRIPT_PATH}
2. 当你发现当前提供的工具（read, edit, bash, web_search 等）无法高效完成特定任务，或觉得缺少某个专门工具时，你可以**直接使用 edit 工具修改本代码文件本身**，添加新的 Python 工具函数、Schema 定义及 TOOLS 映射！
3. 如果某些任务经常重复运行，且按照相同方式处理，你可以**直接在本代码中添加新的工具函数**，并在 SCHEMAS 中注册，以便后续调用。
4. **⚡ 即时生效机制**：源码文件被修改后，系统会在下一轮工具调用前自动检测变更并热重载新函数。你**不需要重启**，新添加的工具可以在**当前任务中立即调用**！只需按常规调用即可。

【反思与执行流程（Think-Reflect-Act）】
1. **反思失败**：如果工具返回了错误或未达到预期效果，不要盲目重复尝试，须在思考中总结原因、调整策略，或考虑是否需要修改自身代码扩展工具。
2. **任务总结**：任务完成后，进行简短反思总结，并将值得长期保留的模式/经验写回记忆。
"""


# Tool Implementations
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




# ============================================================
# 🚀 自主性增强：新增工具函数（ls, write, grep, download_file, self_status）
# ============================================================

def ls(path: str = ".") -> str:
    """列出工作区目录中的文件和子目录。"""
    target = (WORKSPACE / path).resolve()
    if not target.exists():
        return f"ls error: path not found: {path}"
    if target.is_file():
        size = target.stat().st_size
        return f"file: {target.relative_to(WORKSPACE)} ({size} bytes)"

    lines = []
    for entry in sorted(target.iterdir()):
        if entry.is_dir():
            lines.append(f"📁 {entry.name}/")
        else:
            size = entry.stat().st_size
            lines.append(f"📄 {entry.name} ({size} bytes)")
    return "\n".join(lines) if lines else "(empty directory)"


def write(path: str, content: str) -> str:
    """创建或覆盖写入一个文本文件（自动创建父目录）。"""
    target = (WORKSPACE / path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"✅ 已写入 {len(content)} 字节到 {target.relative_to(WORKSPACE)}"


def grep(pattern: str, path: str = ".", include: str = "*") -> str:
    """在文件中递归搜索文本模式（支持正则表达式和 glob 匹配）。"""
    import re
    target_dir = (WORKSPACE / path).resolve()
    if not target_dir.is_dir():
        return f"grep error: not a directory: {path}"

    results = []
    for file_path in sorted(target_dir.rglob(include)):
        if not file_path.is_file():
            continue
        try:
            for i, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(pattern, line):
                    rel = file_path.relative_to(WORKSPACE)
                    results.append(f"{rel}:{i}: {line.rstrip()[:200]}")
        except (UnicodeDecodeError, Exception):
            continue

    return "\n".join(results[:100]) if results else "(no matches found)"


def download_file(url: str, path: str) -> str:
    """从 URL 下载文件到工作区。"""
    import urllib.request
    target = (WORKSPACE / path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, target)
        size = target.stat().st_size
        return f"✅ 已下载 {size} 字节: {url} → {target.relative_to(WORKSPACE)}"
    except Exception as e:
        return f"download error: {e}"


def self_status() -> str:
    """查看当前 Agent 的自我状态：工具数、记忆数、源码大小等。"""
    tool_count = len(TOOLS)
    schema_count = len(SCHEMAS)
    mem_count = 0
    if MEMORY_FILE.exists():
        mem_count = len(MEMORY_FILE.read_text(encoding="utf-8").splitlines())

    src_size = SCRIPT_PATH.stat().st_size

    lines = [
        f"🛠️  工具数量: {tool_count}",
        f"📋 Schema 数量: {schema_count}",
        f"🧠 记忆条目: {mem_count}",
        f"📄 源码大小: {src_size:,} bytes",
        f"📁 工作区: {WORKSPACE}",
        f"📜 源码位置: {SCRIPT_PATH}",
    ]
    return "\n".join(lines)



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


# ============================================================
# 热重载机制：让自修改立即生效
# ============================================================
_last_mtime: float = SCRIPT_PATH.stat().st_mtime


def _reload_tools_from_source() -> tuple[dict[str, Callable], list[dict]]:
    """检测源码文件是否有修改，如果有则从源码热重载工具定义。

    当 AI 用 edit 修改自身源码（添加新函数、更新 TOOLS/SCHEMAS）后，
    此函数读取最新源码，在隔离命名空间中重新执行工具定义部分，
    返回更新后的 TOOLS 字典和 SCHEMAS 列表。

    Returns:
        (TOOLS, SCHEMAS) —— 如果源码未修改则返回 (None, None)
    """
    global _last_mtime
    current_mtime = SCRIPT_PATH.stat().st_mtime

    if current_mtime <= _last_mtime:
        return None, None  # 源码未修改，无需重载

    # 读取最新源码
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    # 构造隔离命名空间，注入当前运行时的配置变量
    ns: dict[str, Any] = {
        "__builtins__": __builtins__,
        "__file__": str(SCRIPT_PATH),
        # 标准库
        "importlib": importlib,
        "json": json,
        "os": os,
        "subprocess": subprocess,
        "sys": sys,
        "glob": __import__("glob"),
        "csv": __import__("csv"),
        "re": __import__("re"),
        "ast": __import__("ast"),
        # 三方库
        "OpenAI": OpenAI,
        "TavilyClient": TavilyClient,
        # 类型
        "Path": Path,
        "datetime": datetime,
        "timezone": timezone,
        "Any": Any,
        "Callable": Callable,
        # 运行时配置（保持与当前进程一致）
        "WORKSPACE": WORKSPACE,
        "SCRIPT_PATH": SCRIPT_PATH,
        "MEMORY_FILE": MEMORY_FILE,
        "TAVILY_API_KEY": TAVILY_API_KEY,
        "MAX_TOOL_OUTPUT": MAX_TOOL_OUTPUT,
    }

    try:
        # 编译并执行源码（if __name__ == "__main__" 部分不会触发）
        code = compile(source, str(SCRIPT_PATH), "exec")
        exec(code, ns)

        new_tools = ns.get("TOOLS")
        new_schemas = ns.get("SCHEMAS")

        if new_tools is None or new_schemas is None:
            return None, None

        _last_mtime = current_mtime
        return new_tools, new_schemas
    except Exception as e:
        # 重载失败时不阻断流程，记录错误并返回 None
        print(f"⚠️  热重载失败: {e}")
        return None, None



TOOLS: dict[str, Callable[..., str]] = {
    "read": read, "edit": edit, "bash": bash,
    "memory_search": memory_search, "memory_add": memory_add,
    "web_search": web_search, "web_extract": web_extract,
    "ls": ls, "write": write,
    "grep": grep, "download_file": download_file,
    "self_status": self_status,
}

SCHEMAS = [
    tool_schema("read", "读取工作区中的文本文件。", {"path": "相对文件路径。"}),
    tool_schema(
        "edit", "替换工作区文件中的实体文本块（可用于修改 Agent 自身的代码扩展新工具）。",
        {"path": "相对文件路径或绝对路径。", "old": "要被替换的原文本。", "new": "替换后的新文本。"}
    ),
    tool_schema("bash", "在workspace中执行 Shell 命令。", {"command": "Shell 命令。"}),
    tool_schema("memory_search", "搜索之前保存的可复用记忆与反思总结。", {"query": "搜索关键词。"}),
    tool_schema("memory_add", "保存一条简洁、可复用的事实、工具经验或反思教训。", {"content": "记忆内容。"}),
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
    tool_schema("ls", "列出工作区目录中的文件和子目录。", {"path": "目录路径，默认为 '.' 表示工作区根目录。"}),
    tool_schema(
        "write", "创建或覆盖写入一个文本文件（自动创建父目录）。",
        {"path": "文件路径（相对工作区）。", "content": "要写入的文本内容。"}
    ),
    tool_schema(
        "grep", "在文件中递归搜索文本模式（支持正则表达式）。",
        {"pattern": "搜索的正则表达式模式。", "path": "搜索的目录路径，默认 '.'", "include": "文件 glob 模式，默认 '*'"}
    ),
    tool_schema(
        "download_file", "从 URL 下载文件到工作区。",
        {"url": "文件的完整 URL。", "path": "保存路径（相对工作区）。"}
    ),
    tool_schema("self_status", "查看当前 Agent 的自我状态：工具数、记忆数、源码大小等。", {}),
]


# Main Agent Execution Loop
def run(task: str, client: OpenAI | None = None) -> str:
    """Run the minimal observe-think-act loop until the model returns text.

    Args:
        task: 用户输入的任务描述。
        client: 可复用的 OpenAI 客户端实例；为 None 时自动创建。

    Returns:
        模型的最终回复文本。
    """
    global TOOLS, SCHEMAS

    if client is None:
        client = OpenAI(api_key=os.environ.get("DS_API"), base_url="https://api.deepseek.com")
    messages: list[Any] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]

    for turn in range(1, MAX_TURNS + 1):
        print(f"\n===== [Turn {turn}/{MAX_TURNS}] =====")

        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            tools=SCHEMAS,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
        )
        msg = response.choices[0].message

        # 1. 打印模型的深度思考过程 (Reasoning Process)
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            print("\n🧠 【思考过程】:")
            print(reasoning.strip())

        # 2. 打印模型的文本输出 (Model Output)
        if msg.content:
            print("\n💬 【模型输出】:")
            print(msg.content.strip())

        messages.append(msg)

        # 没有工具调用，任务结束
        if not msg.tool_calls:
            raw_content = msg.content or ""
            return raw_content.encode("utf-8", "ignore").decode("utf-8")

        # 3. 打印工具调用与结果 (Tool Call & Result)
        for call in msg.tool_calls:
            func_name = call.function.name
            func_args = call.function.arguments
            print(f"\n🛠️  【工具调用】: {func_name}({func_args})")

            # ⚡ 热重载检测：每次工具调用前检查源码是否被修改
            try:
                new_tools, new_schemas = _reload_tools_from_source()
                if new_tools is not None:
                    # 更新模块级 TOOLS 和 SCHEMAS
                    TOOLS = new_tools
                    SCHEMAS = new_schemas
                    print(f"♻️  【热重载】检测到源码变更，已加载 {len(TOOLS)} 个工具, {len(SCHEMAS)} 个 schema")
            except Exception as e:
                print(f"⚠️  热重载检查异常: {e}")

            try:
                fn = TOOLS[func_name]
                args = json.loads(func_args)
                result = fn(**args)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as err:
                result = f"tool error: {err}. Please reflect on why this failed and try a different approach."

            # 防止极端编码引发的错误
            clean_result = str(result)[:MAX_TOOL_OUTPUT].encode("utf-8", "ignore").decode("utf-8")

            # 打印工具执行结果预览（如果太长自动拦截截断日志）
            preview = clean_result if len(clean_result) <= 500 else clean_result[:500] + "... [ truncated ]"
            print(f"📥 【工具返回】:\n{preview.strip()}")

            messages.append({"role": "tool", "tool_call_id": call.id, "content": clean_result})

    raise RuntimeError(f"agent exceeded the {MAX_TURNS}-turn limit")


def interactive_loop() -> None:
    client = OpenAI(api_key=os.environ.get("DS_API"), base_url="https://api.deepseek.com")
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

        print(f"\n⚙️  执行任务: {task}")
        print("=" * 60)
        try:
            result = run(task, client)
            print("\n" + "=" * 60)
            print("✅ 任务完成最终结果:")
            print(result)
        except RuntimeError as e:
            print(f"❌ 运行时错误: {e}")
        except Exception as e:
            print(f"❌ 异常: {e}")
        print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:]).strip()
        if task:
            print(run(task))
        else:
            print("error: task is empty")
        raise SystemExit(0)

    interactive_loop()
# 把 workspace 下的所有 .jpg 图片处理成 800x600 尺寸，并在右下角打上今天的日期水印。

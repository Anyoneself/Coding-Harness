"""Codex-style workspace tools with local safety boundaries."""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


class ToolBlockedError(RuntimeError):
    """工具请求被工作区执行策略拒绝。"""


ToolHandler = Callable[[dict[str, Any], Any], dict[str, Any]]


@dataclass(frozen=True)
class WorkspaceToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


@dataclass(frozen=True)
class WorkspaceToolConfig:
    root: Path
    max_output_chars: int = 20000
    max_file_bytes: int = 1_000_000
    command_timeout_seconds: int = 30


class WorkspaceToolset:
    """在明确配置的工作区内提供受控读写和验证能力。"""

    DENIED_DIR_NAMES = {
        ".git",
        ".idea",
        ".venv",
        "__pycache__",
        "node_modules",
    }
    DENIED_FILE_NAMES = {
        ".mini-agent-memory.jsonl",
        "id_dsa",
        "id_ed25519",
        "id_rsa",
    }
    DENIED_SUFFIXES = {
        ".key",
        ".p12",
        ".pem",
        ".pfx",
    }
    WRITE_INTENT = re.compile(
        r"(修改|编辑|写入|创建|新增|添加|实现|修复|完善|更新|重构|"
        r"\bedit\b|\bwrite\b|\bcreate\b|\badd\b|\bimplement\b|\bfix\b|\bupdate\b|\brefactor\b)",
        re.I,
    )
    OVERWRITE_INTENT = re.compile(r"(覆盖|重写|\boverwrite\b|\brewrite\b)", re.I)
    SHELL_META = re.compile(r"(\|\||&&|[|;<>`]|\$\(|\r|\n)")
    SAFE_GIT_SUBCOMMANDS = {
        "branch",
        "diff",
        "log",
        "ls-files",
        "rev-parse",
        "show",
        "status",
    }
    SAFE_NPM_SCRIPTS = {
        "build",
        "check",
        "lint",
        "test",
        "typecheck",
    }

    def __init__(self, config: WorkspaceToolConfig) -> None:
        """规范化工作区配置并确保安全限制存在最小值。"""
        self.config = WorkspaceToolConfig(
            root=config.root.resolve(),
            max_output_chars=max(1000, config.max_output_chars),
            max_file_bytes=max(1000, config.max_file_bytes),
            command_timeout_seconds=max(1, config.command_timeout_seconds),
        )

    def specs(self) -> list[WorkspaceToolSpec]:
        """返回可注册给 Agent 的工作区工具定义。"""
        return [
            WorkspaceToolSpec(
                name="list_workspace_files",
                description=(
                    "列出项目工作区内的文件。先用它了解代码结构；"
                    "结果不会包含密钥、虚拟环境、Git 内部文件或依赖目录。"
                ),
                parameters=self._schema(
                    {
                        "path": {
                            "type": "string",
                            "description": "相对工作区的目录，默认是项目根目录。",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "可选 glob，例如 *.py 或 application/*.py。",
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 500,
                        },
                    }
                ),
                handler=self.list_files,
            ),
            WorkspaceToolSpec(
                name="read_workspace_file",
                description=(
                    "读取工作区内 UTF-8 文本文件的指定行。"
                    "不能读取 .env、私钥、Git 内部数据或工作区外路径。"
                ),
                parameters=self._schema(
                    {
                        "path": {"type": "string", "description": "相对工作区的文件路径。"},
                        "start_line": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "起始行，默认 1。",
                        },
                        "end_line": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "结束行，默认读取到输出上限。",
                        },
                    },
                    ("path",),
                ),
                handler=self.read_file,
            ),
            WorkspaceToolSpec(
                name="search_workspace",
                description=(
                    "在工作区文本文件中搜索正则表达式或普通文本，返回文件、行号和匹配行。"
                ),
                parameters=self._schema(
                    {
                        "query": {"type": "string", "description": "搜索文本或正则表达式。"},
                        "path": {
                            "type": "string",
                            "description": "搜索目录，默认项目根目录。",
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "可选文件 glob，例如 *.py。",
                        },
                        "literal": {
                            "type": "boolean",
                            "description": "为 true 时按普通文本搜索。",
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "是否区分大小写。",
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 300,
                        },
                    },
                    ("query",),
                ),
                handler=self.search,
            ),
            WorkspaceToolSpec(
                name="apply_patch",
                description=(
                    "精确修改一个工作区文本文件：old_text 必须只出现一次，然后替换为 new_text。"
                    "仅在用户明确要求修改、实现或修复代码时使用。"
                ),
                parameters=self._schema(
                    {
                        "path": {"type": "string", "description": "相对工作区的文件路径。"},
                        "old_text": {"type": "string", "description": "文件中唯一匹配的原文本。"},
                        "new_text": {"type": "string", "description": "替换后的文本。"},
                    },
                    ("path", "old_text", "new_text"),
                ),
                handler=self.apply_patch,
            ),
            WorkspaceToolSpec(
                name="write_workspace_file",
                description=(
                    "在工作区内创建新的 UTF-8 文本文件。默认禁止覆盖；"
                    "覆盖已有文件需要用户明确说“覆盖”或“重写”。"
                ),
                parameters=self._schema(
                    {
                        "path": {"type": "string", "description": "相对工作区的新文件路径。"},
                        "content": {"type": "string", "description": "完整文件内容。"},
                        "overwrite": {
                            "type": "boolean",
                            "description": "是否覆盖已有文件，默认 false。",
                        },
                    },
                    ("path", "content"),
                ),
                handler=self.write_file,
            ),
            WorkspaceToolSpec(
                name="run_workspace_command",
                description=(
                    "在项目目录运行非交互、受限的只读或验证命令。"
                    "支持 git 状态/差异、文本查看、Python/Node 测试与构建检查；"
                    "不支持 shell 管道、重定向、网络安装或删除命令。"
                ),
                parameters=self._schema(
                    {
                        "command": {
                            "type": "string",
                            "description": "单条命令，例如 git diff 或 .venv/bin/python -m unittest。",
                        },
                        "cwd": {
                            "type": "string",
                            "description": "相对工作区的执行目录，默认项目根目录。",
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 120,
                        },
                    },
                    ("command",),
                ),
                handler=self.run_command,
            ),
        ]

    def list_files(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        """列出工作区内经过安全过滤的文件。"""
        del context
        base = self._resolve_path(str(arguments.get("path") or "."))
        if not base.exists():
            raise FileNotFoundError(self._relative(base))
        if not base.is_dir():
            raise NotADirectoryError(self._relative(base))
        pattern = str(arguments.get("pattern") or "*")
        max_results = min(500, max(1, int(arguments.get("max_results") or 200)))
        entries = []
        for path in self._iter_files(base):
            relative = self._relative(path)
            if not (fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern)):
                continue
            stat = path.stat()
            entries.append(
                {
                    "path": relative,
                    "size": stat.st_size,
                }
            )
            if len(entries) >= max_results:
                break
        return {
            "status": "succeeded",
            "root": self._relative(base),
            "files": entries,
            "truncated": len(entries) >= max_results,
        }

    def read_file(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        """按行读取工作区内允许访问的 UTF-8 文本文件。"""
        del context
        target = self._resolve_path(str(arguments.get("path") or ""))
        self._require_text_file(target)
        start_line = max(1, int(arguments.get("start_line") or 1))
        requested_end = arguments.get("end_line")
        end_line = int(requested_end) if requested_end is not None else None
        if end_line is not None and end_line < start_line:
            raise ValueError("end_line must be greater than or equal to start_line")

        text = target.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        selected = lines[start_line - 1 : end_line]
        content = "".join(selected)
        trimmed, truncated = self._trim_output(content)
        actual_end = start_line + len(selected) - 1 if selected else start_line - 1
        return {
            "status": "succeeded",
            "path": self._relative(target),
            "start_line": start_line,
            "end_line": actual_end,
            "total_lines": len(lines),
            "content": trimmed,
            "truncated": truncated,
        }

    def search(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        """在允许访问的工作区文本中搜索字符串或正则表达式。"""
        del context
        query = str(arguments.get("query") or "")
        if not query or len(query) > 500:
            raise ValueError("query must contain 1-500 characters")
        if bool(arguments.get("literal", False)):
            query = re.escape(query)
        flags = 0 if bool(arguments.get("case_sensitive", False)) else re.I
        expression = re.compile(query, flags)
        base = self._resolve_path(str(arguments.get("path") or "."))
        if not base.is_dir():
            raise NotADirectoryError(self._relative(base))
        pattern = str(arguments.get("file_pattern") or "*")
        max_results = min(300, max(1, int(arguments.get("max_results") or 100)))
        results = []
        scanned_files = 0

        for path in self._iter_files(base):
            relative = self._relative(path)
            if not (fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern)):
                continue
            if path.stat().st_size > self.config.max_file_bytes:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            scanned_files += 1
            for line_number, line in enumerate(lines, 1):
                if expression.search(line):
                    results.append(
                        {
                            "path": relative,
                            "line": line_number,
                            "text": line[:500],
                        }
                    )
                    if len(results) >= max_results:
                        return {
                            "status": "succeeded",
                            "query": str(arguments.get("query") or ""),
                            "matches": results,
                            "scanned_files": scanned_files,
                            "truncated": True,
                        }
        return {
            "status": "succeeded",
            "query": str(arguments.get("query") or ""),
            "matches": results,
            "scanned_files": scanned_files,
            "truncated": False,
        }

    def apply_patch(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        """在用户明确授权后执行唯一文本匹配替换。"""
        self._require_write_intent(context)
        target = self._resolve_path(str(arguments.get("path") or ""))
        self._require_text_file(target)
        old_text = str(arguments.get("old_text") or "")
        new_text = str(arguments.get("new_text") or "")
        if not old_text:
            raise ValueError("old_text cannot be empty; use write_workspace_file for new files")
        text = target.read_text(encoding="utf-8")
        match_count = text.count(old_text)
        if match_count != 1:
            raise ValueError(f"old_text must match exactly once; found {match_count}")
        updated = text.replace(old_text, new_text, 1)
        self._check_write_size(updated)
        self._atomic_write(target, updated)
        return {
            "status": "succeeded",
            "path": self._relative(target),
            "replacements": 1,
            "old_chars": len(old_text),
            "new_chars": len(new_text),
        }

    def write_file(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        """创建文本文件，并对覆盖操作执行额外授权校验。"""
        self._require_write_intent(context)
        target = self._resolve_path(str(arguments.get("path") or ""))
        content = str(arguments.get("content") or "")
        overwrite = bool(arguments.get("overwrite", False))
        self._check_write_size(content)
        if target.exists():
            if not target.is_file():
                raise IsADirectoryError(self._relative(target))
            if not overwrite:
                raise ToolBlockedError("target already exists and overwrite is false")
            user_request = str(getattr(context, "user_request", ""))
            if not self.OVERWRITE_INTENT.search(user_request):
                raise ToolBlockedError(
                    "overwriting an existing file requires explicit user authorization"
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, content)
        return {
            "status": "succeeded",
            "path": self._relative(target),
            "bytes": len(content.encode("utf-8")),
            "overwritten": overwrite,
        }

    def run_command(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        """运行白名单内的非交互验证命令并返回结构化输出。"""
        del context
        command = str(arguments.get("command") or "").strip()
        cwd = self._resolve_path(str(arguments.get("cwd") or "."))
        if not cwd.is_dir():
            raise NotADirectoryError(self._relative(cwd))
        tokens = self._validate_command(command)
        timeout = min(
            120,
            max(
                1,
                int(arguments.get("timeout_seconds") or self.config.command_timeout_seconds),
            ),
        )
        started = perf_counter()
        env = self._subprocess_environment()
        try:
            completed = subprocess.run(
                tokens,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            stdout, stdout_truncated = self._trim_output(completed.stdout or "")
            stderr, stderr_truncated = self._trim_output(completed.stderr or "")
            return {
                "status": "succeeded",
                "command": command,
                "cwd": self._relative(cwd),
                "exit_code": completed.returncode,
                "timed_out": False,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "stdout": stdout,
                "stderr": stderr,
                "truncated": stdout_truncated or stderr_truncated,
            }
        except subprocess.TimeoutExpired as exc:
            stdout, stdout_truncated = self._trim_output(self._to_text(exc.stdout))
            stderr, stderr_truncated = self._trim_output(self._to_text(exc.stderr))
            return {
                "status": "succeeded",
                "command": command,
                "cwd": self._relative(cwd),
                "exit_code": None,
                "timed_out": True,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "stdout": stdout,
                "stderr": stderr,
                "truncated": stdout_truncated or stderr_truncated,
            }

    def _validate_command(self, command: str) -> list[str]:
        """解析命令并拒绝 Shell 元字符、危险选项和非白名单程序。"""
        if not command or len(command) > 1000:
            raise ToolBlockedError("command must contain 1-1000 characters")
        if self.SHELL_META.search(command):
            raise ToolBlockedError(
                "shell operators, redirection, and command substitution are disabled"
            )
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            raise ToolBlockedError(f"invalid command quoting: {exc}") from exc
        if not tokens:
            raise ToolBlockedError("command is empty")

        executable_token = tokens[0]
        executable_path = Path(executable_token)
        if executable_path.is_absolute() or "/" in executable_token:
            resolved_executable = self._resolve_executable(executable_token)
            if not resolved_executable.exists():
                raise ToolBlockedError("workspace executable does not exist")
        executable = executable_path.name
        self._validate_command_paths(tokens[1:])

        if executable == "pwd" and len(tokens) == 1:
            return tokens
        if executable == "ls":
            return tokens
        if executable in {"cat", "file", "head", "tail", "wc"}:
            return tokens
        if executable == "sed":
            if any(token == "-i" or token.startswith("-i") for token in tokens[1:]):
                raise ToolBlockedError("sed in-place editing is disabled")
            return tokens
        if executable == "rg":
            denied = {"--hidden", "--no-ignore", "--pre", "--pre-glob", "-u", "-uu", "-uuu"}
            if any(token in denied for token in tokens[1:]):
                raise ToolBlockedError("rg options that bypass workspace filtering are disabled")
            return tokens
        if executable == "grep":
            if any(token in {"-r", "-R", "--recursive"} for token in tokens[1:]):
                raise ToolBlockedError("recursive grep is disabled; use search_workspace")
            return tokens
        if executable == "git":
            if len(tokens) < 2 or tokens[1] not in self.SAFE_GIT_SUBCOMMANDS:
                raise ToolBlockedError("git command is not in the read-only allowlist")
            denied_git_options = {
                "--ext-diff",
                "--no-index",
                "--textconv",
                "-c",
            }
            if any(
                token in denied_git_options or token.startswith("--output") for token in tokens[2:]
            ):
                raise ToolBlockedError("git option is outside the read-only allowlist")
            return tokens
        if executable in {"python", "python3"} or executable.startswith("python3."):
            if (
                len(tokens) >= 3
                and tokens[1] == "-m"
                and tokens[2]
                in {
                    "compileall",
                    "pytest",
                    "unittest",
                }
            ):
                return tokens
            raise ToolBlockedError(
                "Python execution is limited to compileall, pytest, and unittest"
            )
        if executable == "pytest":
            return tokens
        if executable == "node" and len(tokens) >= 3 and tokens[1] == "--check":
            return tokens
        if executable == "npm":
            if len(tokens) >= 2 and tokens[1] == "test":
                return tokens
            if len(tokens) >= 3 and tokens[1] == "run" and tokens[2] in self.SAFE_NPM_SCRIPTS:
                return tokens
            raise ToolBlockedError("npm is limited to test/build/check/lint/typecheck scripts")
        if executable in {"mypy", "ruff"}:
            return tokens
        if executable == "go" and len(tokens) >= 2 and tokens[1] == "test":
            return tokens
        if executable == "cargo" and len(tokens) >= 2 and tokens[1] in {"check", "test"}:
            return tokens
        raise ToolBlockedError(f"command is not allowlisted: {executable}")

    def _validate_command_paths(self, tokens: list[str]) -> None:
        """确保命令参数不会引用敏感路径或逃逸工作区。"""
        for token in tokens:
            if "\x00" in token:
                raise ToolBlockedError("command contains a null byte")
            lowered = token.lower()
            if self._looks_sensitive(lowered):
                raise ToolBlockedError("command references a sensitive path")
            if token.startswith("-"):
                continue
            candidate = Path(token)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ToolBlockedError("command path must stay inside the workspace")

    def _resolve_path(self, raw_path: str) -> Path:
        """解析工作区路径并执行边界和敏感目录检查。"""
        if not raw_path or "\x00" in raw_path:
            raise ToolBlockedError("path is empty or invalid")
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.config.root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.config.root)
        except ValueError as exc:
            raise ToolBlockedError("path escapes the configured workspace") from exc
        if self._is_denied_relative(relative):
            raise ToolBlockedError("path is protected by the workspace security policy")
        return resolved

    def _resolve_executable(self, raw_path: str) -> Path:
        """解析工作区内可执行文件并校验程序白名单。"""
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.config.root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.config.root)
        except ValueError as exc:
            raise ToolBlockedError("executable escapes the configured workspace") from exc
        if resolved.name not in {
            "cargo",
            "go",
            "mypy",
            "node",
            "npm",
            "pytest",
            "python",
            "python3",
            "ruff",
        } and not resolved.name.startswith("python3."):
            raise ToolBlockedError("workspace executable is not allowlisted")
        return resolved

    def _iter_files(self, base: Path):
        """遍历工作区文件并跳过受保护目录和越界符号链接。"""
        for current_root, directories, files in os.walk(base):
            current = Path(current_root)
            directories[:] = [
                name
                for name in sorted(directories)
                if not self._is_denied_relative((current / name).relative_to(self.config.root))
            ]
            for name in sorted(files):
                path = current / name
                relative = path.relative_to(self.config.root)
                if self._is_denied_relative(relative):
                    continue
                if path.is_symlink():
                    try:
                        path.resolve().relative_to(self.config.root)
                    except ValueError:
                        continue
                yield path

    def _require_text_file(self, target: Path) -> None:
        """确认目标是大小合规且不包含空字节的普通文本文件。"""
        if not target.exists():
            raise FileNotFoundError(self._relative(target))
        if not target.is_file():
            raise IsADirectoryError(self._relative(target))
        if target.stat().st_size > self.config.max_file_bytes:
            raise ValueError(f"file exceeds {self.config.max_file_bytes} byte read limit")
        with target.open("rb") as stream:
            if b"\x00" in stream.read(4096):
                raise ValueError("binary files are not supported")

    def _require_write_intent(self, context: Any) -> None:
        """确认用户原始请求明确包含修改或创建意图。"""
        user_request = str(getattr(context, "user_request", ""))
        if not self.WRITE_INTENT.search(user_request):
            raise ToolBlockedError(
                "workspace writes require an explicit edit/create/fix request from the user"
            )

    def _check_write_size(self, content: str) -> None:
        """拒绝超过工作区单文件限制的写入内容。"""
        size = len(content.encode("utf-8"))
        if size > self.config.max_file_bytes:
            raise ValueError(f"content exceeds {self.config.max_file_bytes} byte write limit")

    def _atomic_write(self, target: Path, content: str) -> None:
        """通过同目录临时文件原子替换目标内容。"""
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = target.stat().st_mode if target.exists() else None
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, target)

    def _is_denied_relative(self, relative: Path) -> bool:
        """判断相对路径是否命中受保护目录、文件名或后缀。"""
        parts = [part.lower() for part in relative.parts]
        if any(part in self.DENIED_DIR_NAMES for part in parts[:-1]):
            return True
        if not parts:
            return False
        name = parts[-1]
        if name in self.DENIED_DIR_NAMES or name in self.DENIED_FILE_NAMES:
            return True
        if name.startswith(".env") and name != ".env.example":
            return True
        return Path(name).suffix.lower() in self.DENIED_SUFFIXES

    def _looks_sensitive(self, value: str) -> bool:
        """判断命令参数文本是否疑似引用敏感路径。"""
        normalized = value.replace("\\", "/")
        name = normalized.rsplit("/", 1)[-1]
        return (
            name in self.DENIED_FILE_NAMES
            or (".env" in normalized and ".env.example" not in normalized)
            or Path(name).suffix.lower() in self.DENIED_SUFFIXES
            or bool(re.search(r"(^|[=:/])\.git(?:/|$)", normalized))
            or bool(re.search(r"(^|[=:/])\.venv(?:/|$)", normalized))
        )

    def _relative(self, path: Path) -> str:
        """将绝对路径转换为面向工具输出的工作区相对路径。"""
        relative = path.relative_to(self.config.root)
        return relative.as_posix() if relative.parts else "."

    def _trim_output(self, value: str) -> tuple[str, bool]:
        """按配置截断过长输出并保留首尾诊断信息。"""
        if len(value) <= self.config.max_output_chars:
            return value, False
        half = self.config.max_output_chars // 2
        marker = "\n...[tool output truncated]...\n"
        return value[:half] + marker + value[-half:], True

    @staticmethod
    def _schema(
        properties: dict[str, Any],
        required: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """创建工作区工具参数使用的严格对象 Schema。"""
        return {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        }

    @staticmethod
    def _to_text(value: str | bytes | None) -> str:
        """把子进程输出统一转换为 UTF-8 字符串。"""
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _subprocess_environment(self) -> dict[str, str]:
        """构建仅包含必要变量的受限子进程环境。"""
        allowed = {
            "HOME",
            "LANG",
            "LC_ALL",
            "PATH",
            "TMPDIR",
            "VIRTUAL_ENV",
        }
        env = {key: value for key, value in os.environ.items() if key in allowed}
        env.update(
            {
                "GIT_PAGER": "cat",
                "PAGER": "cat",
                "PYTHONUNBUFFERED": "1",
            }
        )
        return env

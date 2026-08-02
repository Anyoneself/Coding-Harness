# Architecture

## Runtime flow

```text
FastAPI / SSE
  -> DeepSeekAgent
     -> intent recognition
     -> ToolRegistry
        -> built-in business tools
        -> optional Tavily tools
        -> workspace tools
     -> final model response
```

## Module boundaries

### `production_agent.config`

Owns environment parsing and immutable runtime settings. Other modules receive
`DeepSeekSettings` instead of reading environment variables directly.

### `production_agent.agent`

Owns model messages, intent parsing, session history, the tool-call loop, and
SSE-ready events. It does not implement business or filesystem tools.

### `production_agent.tools`

- `base.py`: tool context, definitions, JSON schemas, execution and uniform errors.
- `builtin.py`: assembles business, retrieval, web, and workspace tools.
- `workspace.py`: path isolation, sensitive-file filtering, exact edits, and
  restricted non-interactive commands.

### `production_agent.web`

Owns HTTP validation, SSE encoding, static assets, and user-facing error
translation. It does not contain model or tool logic.

### Local production demo

`runtime.py`, `retrieval.py`, `security.py`, and `evaluation.py` retain the
deterministic local production-mechanism demo. They remain separate from the
external DeepSeek runtime so tests can run without consuming API tokens.

## Compatibility

`production_agent.deepseek_runtime` and `production_agent.workspace_tools`
re-export the new canonical modules. Existing imports continue working while
new code should import from `production_agent.agent`, `production_agent.config`,
and `production_agent.tools`.

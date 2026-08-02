# DeepSeek Agent Console

这是一个可直接运行的 DeepSeek Agent 项目：用户从 Web 页面输入任务，后端先调用真实 DeepSeek 模型完成意图识别，再进入受控工具调用循环，最后通过 SSE 把执行事件和结果实时返回前端。

```text
Web 输入
  -> DeepSeek 意图识别（多意图 / 实体 / 置信度）
  -> DeepSeek 规划与 Function Calling
  -> 服务端工具权限、参数和确认校验
  -> 工具结果回传模型
  -> 最终答案 + 可观察执行事件
```

## 主要能力

- 真实 DeepSeek OpenAI-compatible API 接入，默认模型为 `deepseek-v4-flash`；
- 模型驱动的多意图识别、实体抽取、置信度和澄清判断；
- 原生 Function Calling 循环，支持多轮工具调用；
- Web 对话界面，分别展示最终答案与意图、模型轮次、工具调用事件；
- SSE 流式传递 Agent 阶段事件，不暴露模型隐藏思维链；
- 服务端工具白名单，写操作独立确认、角色校验和幂等保护；
- 内置时间、计算、知识库检索和维修工单工具；
- Codex 风格工作区工具：文件列表、分段读取、代码搜索、精确补丁、新文件写入和受限命令；
- 配置 `TAVILY_API_KEY` 后自动开放联网搜索工具；
- 会话上下文、最大轮次、敏感信息隔离和提示词注入清洗。

## 快速启动

建议使用 Python 3.11 或更高版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

编辑 `.env`，至少设置：

```bash
DEEPSEEK_API_KEY=你的_api_key
```

启动 Web 服务：

```bash
deepseek-agent
```

浏览器访问 `http://127.0.0.1:8000`。

未安装命令入口时，也可以使用：

```bash
python -m production_agent
```

也可以覆盖默认模型和 API 地址：

```bash
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

旧环境变量 `DS_API` 仍可作为 `DEEPSEEK_API_KEY` 的兼容别名。

工作区工具默认锁定在启动目录，也可以显式设置：

```bash
AGENT_WORKSPACE=/absolute/path/to/project
AGENT_ENABLE_WORKSPACE_TOOLS=true
```

内置工作区工具：

| 工具 | 作用 |
| --- | --- |
| `list_workspace_files` | 查看经过过滤的项目文件树 |
| `read_workspace_file` | 按行读取 UTF-8 文本 |
| `search_workspace` | 在代码中搜索文本或正则表达式 |
| `apply_patch` | 对唯一匹配文本执行精确替换 |
| `write_workspace_file` | 创建新文件，覆盖已有文件需要用户明确授权 |
| `run_workspace_command` | 运行 Git 查看、测试、构建和静态检查命令 |

`.env`、私钥、`.git`、虚拟环境和工作区外路径会被拒绝。命令工具不经过
Shell 解释器，不支持管道、重定向、命令替换、删除或网络安装。

## Web API

### `POST /api/chat`

请求：

```json
{
  "message": "请诊断 MX-100 的 E102，并确认创建工单",
  "session_id": "demo-session",
  "role": "operations",
  "model": "deepseek-v4-flash"
}
```

响应为 `text/event-stream`，事件类型包括：

- `started`
- `intent`
- `model_round`
- `tool_call`
- `tool_result`
- `final`
- `error`

### 其他接口

- `GET /api/config`：模型、Thinking 和工具配置；
- `GET /api/health`：服务状态；
- `POST /api/session/reset`：清理指定会话上下文。

## 安全边界

- API Key 只从 `.env` 或系统环境变量读取，不会发送到浏览器；
- 模型只能调用注册表中的工具，不能直接执行 Shell 或任意代码；
- 工作区文件访问经过路径规范化和符号链接边界检查；
- 命令执行采用白名单、精简环境变量、超时和输出截断；
- `create_repair_ticket` 不信任模型传入的“已确认”，而是重新检查用户当前消息；
- 工具和检索内容按不可信数据处理，可疑指令会被隔离；
- 页面只展示结构化执行摘要，不展示隐藏推理内容。

## 测试

```bash
python -m unittest discover -s tests -v
```

DeepSeek 单元测试使用 Fake Client，不消耗真实 API Token。真实联网调用需要配置 `DEEPSEEK_API_KEY`。

## 项目结构

```text
production_agent/
  agent/
    runtime.py          # DeepSeek 意图识别与工具调用循环
  tools/
    base.py             # 工具协议、Schema 和注册表
    builtin.py          # 时间、计算、知识库、工单和联网工具
    workspace.py        # Codex 风格文件与受限命令工具
  config.py             # 环境变量与运行配置
  web.py                # FastAPI、SSE 和静态页面入口
  static/               # Web 工作台资源
  runtime.py            # 本地规则版生产机制
  retrieval.py          # 版本化知识库与混合检索
  security.py           # 注入隔离与 Trace 脱敏
  deepseek_runtime.py   # 旧导入路径兼容层
examples/
  production_agent_demo.py
  langgraph_investment_demo.py
  legacy/               # 历史实验，不属于正式运行链路
tests/
  test_deepseek_runtime.py
  test_production_agent.py
pyproject.toml           # 包元数据、依赖和命令入口
```

更详细的模块边界见 `docs/architecture.md`。

## 原有本地 Demo

不配置外部模型时，仍可运行原有规则版生产机制：

```bash
python -m examples.production_agent_demo run \
  --role operations \
  --request "请诊断 MX-100 的 E102 故障码"

python -m examples.production_agent_demo concurrency
python -m examples.production_agent_demo eval --split regression
```

LangGraph 编排示例：

```bash
python -m examples.langgraph_investment_demo
```

# My-Agent

My-Agent 是一个采用传统 Web 分层架构建设的企业级 AI Agent 项目。它提供 DeepSeek
意图识别、Function Calling、SSE 流式事件、受控工作区工具、知识检索、写操作确认、
幂等保护和本地可重复评估能力。

## 快速启动

macOS/Linux 一键启动：

```bash
./scripts/start.sh
```

脚本会准备 `.venv`、启动 PostgreSQL/Milvus 并等待健康检查，随后在前台启动 Web
服务。自定义监听地址或只启动基础设施：

```bash
./scripts/start.sh --host 0.0.0.0 --port 9000
./scripts/start.sh --infra-only
```

需要 Python 3.11 或更高版本：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

启动 PostgreSQL 与 Milvus：

```bash
docker-compose up -d
docker-compose ps
```

Milvus Standalone 还会启动其官方依赖 etcd 和 MinIO。本地 Docker/Colima 建议至少
分配 4 CPU 和 8 GB 内存。

在 `.env` 中配置：

```bash
DEEPSEEK_API_KEY=你的_api_key
```

启动服务：

```bash
python -m application serve
```

默认访问地址为 `http://127.0.0.1:8000`。自定义监听参数：

```bash
python -m application serve --host 0.0.0.0 --port 9000
```

Web 与 CLI 共用 PostgreSQL 会话和事件存储。使用相同 `session_id` 可以在不同进程中
继续上下文：

```bash
python -m application chat "先阅读项目结构" --session demo
python -m application chat "继续给出修改建议" --session demo
python -m application chat "检查项目" --session ci --json
python -m application chat "深入分析架构" --session demo --thinking max
```

默认数据库连接是 `postgresql://my_agent:my_agent@127.0.0.1:5433/my_agent`，
可通过 `DATABASE_URL` 修改。知识工具默认连接
`http://127.0.0.1:19530` 上的 Milvus。

## 前端工作台

- 左侧对话栏保存最近会话，并支持新建和切换对话。
- 中央区域展示用户消息、Agent 回答和固定底部输入框。
- 输入框内可按请求选择快速回答、`low`、`high` 或 `max` 深度思考。
- Trace 以右侧抽屉展示 Intent、模型轮次和工具调用，默认关闭。
- 移动端会话栏与 Trace 均采用抽屉交互，不占用主对话宽度。

## Web API

- `POST /api/chat`：提交任务并接收 SSE 事件。
- `GET /api/config`：读取允许公开的模型与工具配置。
- `GET /api/health`：读取进程与模型配置状态。
- `POST /api/session/reset`：清理指定会话上下文。

SSE 事件包括 `started`、`intent`、`model_round`、`thinking_delta`、`tool_call`、
`tool_result`、`answer_delta`、`final` 和 `error`。用户启用深度思考后，
`thinking_delta` 携带 DeepSeek 官方 API 返回的 `reasoning_content` 分片，前端会在明确
标注的可折叠区域中实时展示；`answer_delta` 携带最终回答分片。

事件会按请求 ID 和请求内序号写入 PostgreSQL；`thinking_delta` 审计记录只保存字符计数，
不保存推理原文。重置会话只清理模型上下文，不会删除已有审计事件。

## 项目结构

```text
application/
  controllers/          # HTTP 与 SSE 协议适配
  schemas/              # 请求、响应和跨层契约
  services/             # 对话、本地工作流、工具执行和评估用例
  domain/               # 领域模型、意图规则和执行策略
  repositories/         # PostgreSQL 会话、Milvus 与本地测试仓储
  infrastructure/       # 安全、脱敏、Trace 和外部边界
  agent/                # DeepSeek 模型与工具调用循环
  prompts/              # 系统、意图识别等提示词定义
  tools/                # 工具协议、业务工具和工作区工具
  cli/                  # application 命令行入口
  static/               # Web 控制台
  app.py                # 应用装配入口
tests/
  unit/
  integration/
examples/
docs/
```

完整文档导航见 `docs/README.md`，系统架构见 `docs/architecture.md`，工程行为约束见 `AGENTS.md`。

## 安全边界

- API Key 仅从环境变量读取，不发送到浏览器。
- 模型只能调用显式注册的工具。
- 工作区访问执行路径规范化、敏感文件过滤和命令白名单。
- 写操作独立校验角色、用户确认和幂等键。
- 外部内容按不可信数据处理，并隔离提示词注入片段。
- 页面可以展示当前用户请求对应的 DeepSeek `reasoning_content`，并明确标注为模型生成内容；Trace 和数据库不保存推理原文。

## 测试

```bash
python -m unittest discover -s tests -v
ruff check .
```

测试使用 Fake Client，不消耗真实模型 Token，也不依赖公网。

运行外部存储集成测试：

```bash
POSTGRES_TEST_DSN=postgresql://my_agent:my_agent@127.0.0.1:5433/my_agent \
MILVUS_TEST_URI=http://127.0.0.1:19530 \
python -m unittest tests.integration.test_external_stores -v
```

## 本地机制示例

```bash
python -m examples.production_agent_demo run \
  --role standard \
  --request "请分析这份资料并给出可验证的结论"

python -m examples.production_agent_demo concurrency
python -m examples.production_agent_demo eval --split regression
```

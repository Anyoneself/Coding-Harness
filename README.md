# Coding-Harness

Coding-Harness 是一个基于 DeepSeek 的可恢复代码执行框架，提供 Web 对话、流式回答、
受控工具调用、后台 Turn、事件重放和会话管理能力。项目使用 PostgreSQL 保存执行状态与
事件，使用 Milvus 提供向量知识检索，并提供 Web 与 CLI 两种使用方式。

## 已有能力

- Web 对话工作台：支持多会话历史、SSE 流式回答、模型与深度思考强度选择、结构化执行过程展示、会话重置和永久删除。
- DeepSeek Agent：支持模型白名单、意图识别、多轮工具调用、上下文恢复，以及对官方 `reasoning_content` 的按需实时展示；审计记录只保存思考字符数，不持久化思考原文。
- 首次配置：未检测到 API Key 时由前端引导配置，密钥原子写入本机 `.env` 并设置为 `0600` 权限，聊天服务和 Harness Runtime 无需重启即可启用。
- 内置工具：提供时间查询、安全算术、知识库检索、Web 搜索与正文提取，以及工作区文件列表、读取、搜索、补丁修改、文件写入和受控命令执行。
- 工作区安全边界：执行规范化路径与工作区越界检查，过滤敏感文件，写操作要求明确用户意图，命令使用参数列表和白名单；当前尚未提供经过验证的可信 OS 沙箱。
- 可恢复执行 Harness：以 Workspace、Thread、Turn 为稳定资源，支持后台调度、活动 Turn 约束、执行租约、预算限制、Checkpoint、版本化事件、游标重放、SSE 订阅、中断、主动恢复和进程重启恢复。
- 持久化适配：生产链路支持 PostgreSQL 保存会话、Turn 和事件，支持 Milvus 向量知识检索；测试和轻量场景可使用 SQLite 与本地知识仓储。
- Web 与 CLI 共用 Service：HTTP Controller 和 `coding-harness` CLI 复用同一业务服务；CLI 提供帮助、稳定退出码与 JSON Lines 输出。
- 质量保障：单元测试覆盖 Domain 和 Service 规则，集成测试覆盖 HTTP、持久化与首次配置链路，并使用 Ruff、编译检查和 Gherkin 场景维护稳定契约。

## 快速启动

启动前请准备：

- Python 3.11 或更高版本
- Docker 和 Docker Compose
- DeepSeek API Key（可在首次打开 Web 控制台时配置）

复制配置文件：

```bash
cp .env.example .env
```

可以提前在 `.env` 中填写 DeepSeek API Key：

```dotenv
DEEPSEEK_API_KEY=你的_API_Key
```

也可以暂不填写。首次访问 Web 控制台时，页面会引导输入 API Key，并以 `0600` 权限
写入本机 `.env`；聊天服务和 Harness Runtime 会立即启用，无需重启进程。首次配置接口
仅接受本机请求，已经生效的密钥不能通过该接口覆盖。

执行一键启动脚本：

```bash
./scripts/start.sh
```

脚本会自动创建 Python 虚拟环境、安装依赖、启动 PostgreSQL 和 Milvus，并启动 Web
服务。启动完成后访问：

[http://127.0.0.1:8000](http://127.0.0.1:8000)

如需修改监听地址或端口：

```bash
./scripts/start.sh --host 0.0.0.0 --port 9000
```

按 `Ctrl+C` 可以优雅关闭 Web 服务。停止 Docker 基础设施：

```bash
docker compose down
```

## 本地基础设施客户端

`docker-compose.yml` 默认同时启动以下仅本机可访问的管理界面；端口均可通过 `.env` 覆盖。

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| Attu | [http://127.0.0.1:3000](http://127.0.0.1:3000) | 查看 Milvus collection、schema、向量数据与索引。默认连接 `milvus:19530`。 |
| etcdkeeper | [http://127.0.0.1:8080](http://127.0.0.1:8080) | 查看 Milvus 使用的 etcd 元数据。首次进入时连接地址填写 `etcd:2379`。 |
| MinIO Console | [http://127.0.0.1:9001](http://127.0.0.1:9001) | 查看 Milvus 的对象存储数据。登录用户名和密码分别为 `.env` 中的 `MINIO_ACCESS_KEY` 与 `MINIO_SECRET_KEY`；未配置时两者均默认为 `minioadmin`。 |

这些界面仅用于本地开发和排障，端口绑定到 `127.0.0.1`，不会暴露到局域网。可使用 `ATTU_PORT`、`ETCDKEEPER_PORT` 与 `MINIO_CONSOLE_PORT` 调整端口。

## 手动启动

如需分步启动：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
docker compose up -d
python -m application serve
```

安装后使用 `coding-harness` 启动主 CLI，使用 `coding-harness-demo` 运行本地机制演示。

# My-Agent

My-Agent 是一个基于 DeepSeek 的智能助手项目，提供 Web 对话、流式回答、深度思考、
工具调用、会话管理和知识检索能力。项目使用 PostgreSQL 保存会话与事件，使用 Milvus
提供向量知识检索，并提供 Web 与 CLI 两种使用方式。

## 快速启动

启动前请准备：

- Python 3.11 或更高版本
- Docker 和 Docker Compose
- DeepSeek API Key

复制配置文件：

```bash
cp .env.example .env
```

在 `.env` 中填写 DeepSeek API Key：

```dotenv
DEEPSEEK_API_KEY=你的_API_Key
```

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

## Coding Harness 执行 API

项目已加入第一阶段可恢复执行底座，并保留原有 `/api/chat` 兼容链路。新链路以
Workspace、Thread 和 Turn 为稳定资源：

```text
POST /api/workspaces
POST /api/workspaces/{workspace_id}/threads
POST /api/threads/{thread_id}/turns
GET  /api/turns/{turn_id}
GET  /api/turns/{turn_id}/events?after_sequence=0
GET  /api/turns/{turn_id}/events/stream?after_sequence=0
POST /api/turns/{turn_id}/interrupt
POST /api/turns/{turn_id}/resume
```

创建 Turn 返回 `202 Accepted`，实际模型调用由单 Worker 的进程内 Scheduler 后台执行。
事件先持久化到 PostgreSQL 或测试用 SQLite，再通过查询或 SSE 重放；断开 SSE 不会取消
Turn。进程重启会把遗留的运行 Turn 标记为 `interrupted`，需要用户显式调用 resume。

第一阶段只开放只读模型 Turn。当前没有被验证为可信的 OS 沙箱实现，命令执行边界使用
`DenyCommandSandbox` 失败关闭，不会把工作区命令白名单表述为 OS 隔离。

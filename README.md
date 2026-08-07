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

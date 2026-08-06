# My-Agent 系统架构

## 1. 系统定位

My-Agent 是一个采用传统 Web 分层思想组织的企业级 AI Agent 工程。当前系统同时保留两条运行链：

1. **真实模型链**：通过 FastAPI、SSE、DeepSeek Function Calling、PostgreSQL、Milvus 和受控工具完成在线任务。
2. **本地机制链**：通过确定性规则、版本化知识库、内存 SQLite 会话和评估套件验证生产机制，不依赖真实模型 Token。

两条链共享领域规则、知识仓储、安全能力和工具执行约束，但入口和主要用途不同。真实模型链面向 Web 用户，本地机制链面向开发、回归测试和机制评估。

## 2. 总体架构

```text
Browser
  -> FastAPI application
  -> HTTP Controller
  -> AgentChatService
  -> DeepSeekAgent
  -> ToolRegistry
       -> built-in tools
       -> knowledge repository
       -> workspace tools
       -> optional Tavily tools
  -> SSE events
  -> Browser

CLI
  -> application.cli
  -> Uvicorn
  -> FastAPI application

Local demo / evaluation
  -> AgentService
  -> domain policies
  -> knowledge repository
  -> session repository
  -> trace and audit
```

## 3. 分层与依赖方向

项目采用以下依赖方向：

```text
controllers / cli
        -> services
        -> agent / domain
        -> repositories / infrastructure
        -> external systems
```

核心约束：

- Controller 只处理 HTTP、SSE、参数和错误转换，不实现业务规则。
- CLI 只解析命令并启动应用，不复制 Web 或 Service 的业务逻辑。
- Service 负责用例编排，是 Controller、CLI、Agent 工具与底层能力之间的协调层。
- Domain 保存与框架无关的模型和规则，不依赖 FastAPI、Uvicorn 或具体数据库连接。
- Repository 封装数据访问语义，不向上层泄漏 SQL、连接或索引内部结构。
- Infrastructure 保存安全、脱敏、Trace 等横切能力。
- Prompt 统一放在 `application/prompts/`，运行时不得继续内嵌大段提示词。
- Tool 是模型可调用能力的边界；新增写工具必须在 Service 中实现权限、确认和幂等校验。

## 4. 真实模型请求链

### 4.1 应用启动

1. `application.cli.main` 解析 `python -m application serve` 参数。
2. Uvicorn 加载 `application.app:app`。
3. `application.app.create_app` 读取配置并创建 `AgentChatService`。
4. 应用注册 API Router，并挂载 `application/static/` 静态资源。

### 4.2 对话请求

1. 浏览器向 `POST /api/chat` 提交 `ChatRequest`，并可覆盖本轮 `thinking_enabled` 与只接受 `low`、`high`、`max` 的 `reasoning_effort`。
2. `application.controllers.http` 校验请求并创建 SSE 响应。
3. `AgentChatService.stream_chat` 从 PostgreSQL 读取会话历史，并调用无状态的 `DeepSeekAgent.run`。
4. `DeepSeekAgent` 首先使用意图识别提示词生成结构化意图。
5. Agent 使用系统提示词进入 Function Calling 循环。
6. `ToolRegistry` 只执行显式注册的工具，并统一转换阻断和失败结果。
7. Runtime 使用 DeepSeek Streaming API，把公开回答转换为 `answer_delta`，把官方响应中的 `reasoning_content` 转换为 `thinking_delta`，并在工具调用轮次回传完整推理上下文。
8. Controller 将 `started`、`intent`、`thinking_delta`、`tool_call`、`tool_result`、`answer_delta`、`final` 等事件编码为 SSE。
9. `AgentChatService` 按请求顺序持久化全部事件，并在最终回答前保存会话历史。
10. 前端收到 `answer_delta` 后立即追加文本，收到 `final` 后校准并持久化完整回答。

### 4.3 会话并发

真实模型链由 `AgentChatService` 维护会话级锁，并通过 `PostgresSessionStore` 持久化模型历史和结构化事件。同一进程内的同一会话请求串行执行；跨进程并发保存使用 PostgreSQL 乐观锁检测冲突。知识工具通过 `MilvusKnowledgeBase` 使用 COSINE 向量检索，并继续执行不可信内容隔离。

## 5. 本地机制请求链

`application.services.local_agent.AgentService` 用于不依赖外部模型的生产机制演示和回归评估：

1. 从 `SessionStore` 读取会话状态和乐观锁版本。
2. 记录通用访问上下文，不按业务领域限制知识范围。
3. 使用 `IntentRecognizer` 识别通用意图和实体。
4. 使用 `ClarificationPolicy` 判断缺失信息和歧义。
5. 检查当前知识版本对应的答案缓存。
6. 使用 `VersionedKnowledgeBase` 执行倒排召回、分区过滤和 RRF 融合。
7. 根据意图运行必要的通用处理步骤。
8. 执行审计、结果汇总和上下文压缩。
9. 通过 compare-and-swap 保存会话；遇到并发冲突时重新读取并重试。

## 6. 目录职责

```text
application/
  agent/
  cli/
  controllers/
  domain/
  infrastructure/
  prompts/
  repositories/
  schemas/
  services/
  static/
  tools/
  __init__.py
  __main__.py
  app.py
  config.py
examples/
tests/
docs/
workspace/
```

### `application/agent/`

负责真实模型的执行循环。

- `runtime.py`：意图识别、消息组装、Function Calling、工具结果回传、会话历史和模型用量转换。
- `__init__.py`：导出 `DeepSeekAgent`，并保留 `DEFAULT_SYSTEM_PROMPT` 兼容名称。

该目录不得包含 HTTP 路由、CLI 参数解析或数据库 SQL。

### `application/cli/`

负责命令行接入。

- `main.py`：定义 `serve` 子命令，解析 host、port 和 reload 参数，并启动 Uvicorn。
- `__init__.py`：导出 CLI 主函数。

CLI 与 Web 共用 `application.app`，不得建立独立业务链路。

### `application/controllers/`

负责 HTTP 与 SSE 协议转换。

- `http.py`：注册 `/api/config`、`/api/chat`、`/api/session/reset` 和 `/api/health`；编码 SSE；转换外部模型异常。

Controller 不直接访问 Repository，也不实现模型循环和写操作规则。

### `application/domain/`

负责框架无关的领域模型和业务规则。

- `models.py`：消息、意图结果、检索命中、工具结果、Trace 事件和 Agent 状态模型。
- `policies.py`：通用意图识别、澄清策略、上下文压缩和循环保护。

Domain 不依赖 FastAPI、CLI、OpenAI Client 或 SQLite 连接。

### `application/infrastructure/`

负责横切基础设施。

- `security.py`：稳定哈希、日志脱敏、个人信息清理、不可信内容检查和阶段级 Trace。

外部网页、知识文档和工具返回都按不可信数据处理，安全检查不能替代工具权限校验。

### `application/prompts/`

负责集中管理提示词。

- `agent.py`：主 Agent 系统提示词和意图识别提示词。
- `__init__.py`：提供稳定导出入口。

新增提示词应按业务域拆分文件，例如 `coding.py`、`evaluation.py`，避免形成单个超大提示词文件。提示词常量使用明确名称，运行时只负责引用。

### `application/repositories/`

负责数据访问与本地索引。

- `session.py`：会话仓储协议、SQLite 测试实现和进程内幂等记录。
- `postgres_session.py`：PostgreSQL 连接池、JSONB 会话、事件表和乐观锁实现。
- `knowledge.py`：知识仓储协议、本地版本化索引、倒排索引和答案缓存。
- `milvus_knowledge.py`：Milvus 集合、确定性哈希向量、COSINE 检索和知识版本。
- `__init__.py`：导出稳定的数据访问类型。

Repository 对 Service 提供业务语义方法，不向上层暴露 SQL 或索引构建细节。

### `application/schemas/`

负责接口输入输出契约。

- `http.py`：`ChatRequest` 和 `ResetSessionRequest` Pydantic 模型。

新增 API 字段时需要同步 Controller、前端、测试和 README。

### `application/services/`

负责应用用例编排。

- `chat.py`：创建和管理 `DeepSeekAgent`，提供对话、会话重置和公开配置用例。
- `local_agent.py`：本地确定性 Agent 全流程编排。
- `evaluation.py`：阶段评分、失败归因、双向 Judge 和 Bootstrap 版本比较。
- `__init__.py`：保持轻量，避免聚合导出导致循环依赖。

Service 可以协调多个 Repository 和领域规则，但不能依赖 FastAPI Request 或 CLI Namespace。

### `application/static/`

负责浏览器端控制台。

- `index.html`：页面结构和可访问性标签。
- `styles.css`：工作台布局与视觉样式。
- `app.js`：会话状态、SSE 解析、消息渲染、工具事件、配置加载和本地会话历史。

当前布局采用左侧会话栏、中央对话区和右侧 Trace 抽屉。Trace 默认关闭；移动端左侧会话栏也默认收起。会话标题和消息保存在浏览器本地存储中，服务端仍以对应 `session_id` 隔离模型上下文。

前端只负责交互和展示，权限、确认、幂等与敏感信息过滤必须在服务端执行。

### `application/tools/`

负责模型可调用工具边界。

- `base.py`：工具上下文、工具定义、JSON Schema、注册表和统一执行结果。
- `builtin.py`：时间、计算、知识检索和可选 Tavily 工具。
- `workspace.py`：受控文件列表、读取、搜索、精确修改、文件创建和白名单命令。
- `__init__.py`：导出工具公共 API。

工具参数来自模型，必须视为不可信输入。新增写工具必须调用相应 Service，并由 Service 执行确认与幂等保护。

### `application/app.py`

应用组合根。负责加载设置、创建 Service、注册 Controller 和挂载静态资源。不得加入业务流程。

### `application/config.py`

集中读取环境变量并生成不可变配置，包括模型、Thinking、工具输出限制、工作区路径、命令超时和 Tavily Key。

### `application/__main__.py`

支持 `python -m application`，只转发到 CLI。

### `application/__init__.py`

提供稳定的公共 Python API，避免调用方依赖内部文件位置。

### `examples/`

保存可运行示例和历史实验，不属于正式生产链路：

- `production_agent_demo.py`：本地机制、并发和评估示例。
- `legacy/`：历史实验，只供参考，正式代码不得依赖。

### `tests/`

- `unit/`：领域规则、Repository、本地 Service 和评估逻辑测试。
- `integration/`：DeepSeek Fake Client、工具注册、Web API、CLI 和工作区安全链路测试。

默认测试不调用公网，也不消耗真实模型 Token。

### `docs/`

保存架构、产品策略和工程说明。`docs/README.md` 是文档导航入口。

### `workspace/`

Agent 工作区工具的默认示例目录。该目录中的文件是工具操作对象，不是应用源代码。

## 7. 状态、存储与缓存

- 真实模型会话：默认保存在本地 Docker PostgreSQL，Web 与 CLI 使用相同仓储契约，重启后可以继续上下文。
- 真实模型事件：按会话、请求 ID 和请求内序号写入 PostgreSQL JSONB；清理上下文时保留事件用于审计。
- 真实模型知识：默认写入 Milvus Standalone；集合首次使用时自动建立，并写入当前默认知识文档。
- 本地机制会话：默认使用内存 SQLite，也可以向 `SessionStore` 传入数据库路径。
- 幂等记录：当前为进程内存实现，适合测试和单进程演示。
- 知识索引：使用不可变版本快照；新版本构建完成后再原子切换。
- 答案缓存：缓存键包含问题哈希、角色和知识版本，知识更新后不会命中过期答案。

生产部署若需要跨实例一致性，应将会话、幂等和缓存实现替换为共享存储，并保持现有 Repository/Service 契约。

## 8. 安全边界

- API Key 仅从环境变量读取，不返回给浏览器。
- 模型只能调用 `ToolRegistry` 中显式注册的工具。
- 写操作检查角色、用户当前消息确认和幂等键。
- 工作区路径必须位于配置根目录，敏感文件和越界符号链接会被拒绝。
- 命令执行不经过 Shell，只允许白名单程序和参数。
- 外部内容会执行提示词注入检测并放入不可信数据边界。
- Trace 只记录脱敏摘要，不保存完整 Prompt、密钥和个人身份。
- 前端可以在明确标注的独立区域展示当前请求的 DeepSeek `reasoning_content`；Trace 与持久化审计事件只保留推理字符计数，不保存原文。

## 9. 扩展方式

### 新增 HTTP 接口

1. 在 `schemas/` 定义输入输出模型。
2. 在 `services/` 实现业务用例。
3. 在 `controllers/` 添加协议适配。
4. 同步前端、测试和接口文档。

### 新增模型工具

1. 判断核心行为是否应先实现为 Service。
2. 在 `tools/builtin.py` 或独立工具模块中定义工具 Schema 和适配函数。
3. 通过 `ToolRegistry` 显式注册。
4. 写操作必须通过相应 Service 执行确认、权限和幂等校验。
5. 补充成功、失败、阻断和权限测试。

### 新增提示词

1. 按业务域在 `prompts/` 新建明确文件。
2. 使用含义清晰的常量名。
3. 通过 `prompts/__init__.py` 导出公共提示词。
4. 在调用方导入，不在运行时拼接重复长文本。
5. 测试模型请求实际使用了目标提示词。

### 替换数据库或知识引擎

优先保持 `SessionRepository`、`KnowledgeRepository` 对 Service 的业务接口稳定，在 Repository 或 Infrastructure 层替换实现，不修改 Controller 协议。

## 10. 验证命令

```bash
python -m unittest discover -s tests -v
ruff check .
python -m application --help
python -m application serve --help
```

当前测试使用 Fake Client 隔离外部 DeepSeek 调用，真实联网行为需要显式配置 `DEEPSEEK_API_KEY`。

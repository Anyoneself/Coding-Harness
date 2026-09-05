# Web 工作台契约

本文是便于前端任务快速进入上下文的可验证快照，不是独立事实源。开始修改前至少核对与任务
相关的源码：

- HTTP 路由与响应模型：`application/controllers/http.py`、`application/schemas/`
- 前端请求与公开类型：`frontend/src/api/`、`frontend/src/domain/types.ts`
- 事件归约：`frontend/src/domain/events.ts`
- 可执行行为：`tests/features/`、`tests/integration/test_execution_http.py`

源码与本文不一致时，以当前 Schema、Controller、类型和测试为准，并在同一任务中更新本文。

## 稳定资源

- Workspace：本地工作区和权限边界。浏览器只保存服务端返回的稳定 ID。
- Thread：围绕一个持续目标形成的任务会话。一个 Thread 同时只允许一个活动 Turn。
- Turn：一次用户请求触发的执行，状态包括 `queued`、`running`、`waiting_approval`、
  `completed`、`failed`、`interrupted`、`cancelled`。
- Event：带单调 `sequence` 的可重放公开事件。前端只推进更大的序号。

## 当前接口

- `GET /api/config`
- `POST /api/config/api-key`
- `POST /api/workspaces`
- `POST /api/workspaces/{workspace_id}/threads`
- `POST /api/threads/{thread_id}/turns`
- `GET /api/turns/{turn_id}`
- `GET /api/turns/{turn_id}/events`
- `GET /api/turns/{turn_id}/events/stream`
- `POST /api/turns/{turn_id}/interrupt`
- `POST /api/turns/{turn_id}/resume`

当前没有 Thread 列表、服务端消息历史、ChangeSet、Diff、Verification 或审批接口。界面可以为
现有任务导航、主画布和按需检查器保留稳定入口，但不得伪造这些数据或展示不可用操作。

## 客户端持久化

- localStorage 仅保存最近 30 个本地 Thread 摘要、公开消息和当前 Workspace ID。
- 解析失败、结构不完整或版本不兼容时回退为空状态，不阻断应用启动。
- API Key、错误堆栈、隐藏推理、完整第三方响应不得进入 localStorage。

## 事件归约

- `turn.queued`、`turn.running` 更新 Turn 状态。
- `item.in_progress` 的 `agent_message` 追加公开文本增量。
- `item.completed` 的 `agent_message` 以最终 `answer` 收敛，并显示公开 usage。
- `item.failed` 显示公开错误并标记失败。
- Turn 终态结束运行态；未知事件保留在检查器中，不猜测业务含义。
- 重复或倒序事件不得重复追加文本。

## 表现边界

- 宽屏需要同时支持 Thread 导航与主要执行画布，但具体宽度、比例和材质属于可重新设计的表现。
- 检查器按需展示 Event 与 Turn 元数据，不应长期挤压主要阅读区域。
- 窄屏导航和检查器使用覆盖式交互，核心任务输入与执行内容始终可达。
- 输入器在空任务和持续会话中可以采用不同尺度，但发送、中断和上下文信息不能布局跳动。
- 状态不能只依赖颜色表达；所有交互满足可见焦点、语义标签和触控尺寸要求。

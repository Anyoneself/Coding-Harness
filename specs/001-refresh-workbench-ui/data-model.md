# Data Model: 参考图升级前端工作台

本功能不新增服务端实体或持久化 Schema。以下模型描述现有公开数据如何驱动工作台界面，以及实现时必须保持的验证与状态约束。

## Workspace

代表当前 Agent 可访问的真实项目边界。

| 字段 | 类型 | 来源 | 约束 |
|------|------|------|------|
| `id` | string | `POST /api/workspaces` | 仅保存服务端返回值，不由前端构造 |
| `root_path` | string | `GET /api/config` / Workspace 响应 | 只用于创建 Workspace 和派生项目显示名 |
| `permission_profile` | enum | Workspace 响应 | 当前前端固定请求 `read_only` |
| `display_name` | derived string | `root_path` 最后一个有效路径段 | 空值或 `.` 回退为 `Coding-Harness`；显示时截断但不改变原值 |

关系：一个当前 Workspace 对应多个本地 Thread 摘要。

## Thread（界面中的“任务”）

代表围绕持续目标的本地任务历史，并可选择性绑定服务端 Thread。

| 字段 | 类型 | 约束 |
|------|------|------|
| `id` | string | 浏览器本地唯一标识 |
| `threadId` | string | 未首次发送时为空；绑定后保存服务端 ID |
| `title` | string | 新任务默认为“新任务”；首次发送后取任务文本前 32 个字符 |
| `status` | string | 公开、可理解的任务状态标签 |
| `updatedAt` | number | 用于最近任务排序与分组 |
| `messages` | ChatMessage[] | 只含公开用户与 Assistant 消息 |

验证规则：

- localStorage 输入必须先解析、归一化并拒绝含 `apiKey` 的记录。
- 最多保留最近 30 个任务。
- 移除最后一个任务后必须创建新的空任务。
- 活动 Turn 运行期间不得切换、移除或新建其他任务。

## ChatMessage

代表可以显示并写入本地历史的一条公开消息。

| 字段 | 类型 | 约束 |
|------|------|------|
| `id` | string | 本地唯一标识；旧记录缺失时安全补齐 |
| `role` | `user` 或 `assistant` | 其他值拒绝 |
| `content` | string | 用户文本按纯文本显示；Assistant Markdown 先清洗 |
| `createdAt` | number | 旧记录缺失时使用任务更新时间 |
| `isError` | boolean，可选 | 只表达公开错误消息 |

不得包含 API Key、隐藏推理、完整第三方响应或内部异常对象。

## Turn

代表一次用户输入触发的执行。

| 字段 | 类型 | 约束 |
|------|------|------|
| `turnId` | string | 创建 Turn 后设置 |
| `status` | TurnStatus | 仅由公开事件和明确本地失败推进 |
| `statusLabel` | string | 与状态一一对应的中文显示文本 |
| `answer` | string | 由公开 Assistant 增量与最终消息收敛 |
| `totalTokens` | number 或 null | 只读取公开完成事件 |
| `lastSequence` | number | 只接受更大序号 |
| `events` | ActivityEvent[] | 按序保存公开事件展示模型 |
| `error` | string | 用户可理解且不泄漏响应正文 |

### TurnStatus

```text
idle
  -> queued
  -> running
  -> waiting_approval
  -> running
  -> completed | failed | interrupted | cancelled
```

额外前端失败转换：

```text
queued | running | waiting_approval
  -> failed
```

触发条件包括任务创建失败、Turn 创建失败、SSE 请求失败或非终态 SSE 结束。

## ActivityEvent

代表 Inspector 中一条稳定、公开的事件行。

| 字段 | 类型 | 约束 |
|------|------|------|
| `sequence` | number | 在 Turn 内单调递增 |
| `type` | string | 未知类型保留原值 |
| `title` | string | 已知事件映射为用户可理解标题 |
| `detail` | string | 只提取公开安全字段 |
| `occurredAt` | string，可选 | 使用公开时间 |
| `tone` | enum | `neutral`、`progress`、`success`、`danger` |
| `payload` | record | 只用于当前公开检查器，不推导未实现能力 |

重复或倒序事件返回原状态，不追加文本或事件行。

## WorkbenchView

代表顶部导航与 Inspector 的同步选择。

```text
workspace | events | turn
```

状态规则：

- `workspace`: Inspector 关闭。
- `events`: Inspector 打开并选择事件标签。
- `turn`: Inspector 打开并选择 Turn 标签。
- 关闭 Inspector 不删除当前 ExecutionState。

## WorkbenchPresentation

由现有状态派生，不持久化。

| 派生状态 | 条件 | 主要表现 |
|----------|------|----------|
| `empty-ready` | 无公开消息、无实时 Assistant、配置就绪 | 品牌空状态、宽输入器、真实项目与模型 |
| `empty-unconfigured` | 无公开消息、配置未就绪 | 保留工作台背景，发送时打开 API Key 对话框 |
| `conversation-running` | 有消息或实时 Assistant，Turn 非终态 | 消息阅读流、底部输入器、中断主操作 |
| `conversation-terminal` | 有消息，Turn 已终止 | 消息阅读流、发送主操作、可清理检查器 |
| `connection-failed` | 配置或执行连接失败 | 可理解错误提示，不显示虚假成功 |

这些状态不增加新的后端状态，也不写入 localStorage。

## Responsive Presentation

响应式状态由 CSS 媒体条件决定，不进入 React 业务状态。

| 视口 | Sidebar | Inspector | 主画布 |
|------|---------|-----------|--------|
| `>1180px` | 固定显示 | 按需覆盖 | 完整宽度减去 Sidebar |
| `761–1180px` | 固定显示 | 按需覆盖 | 收紧间距与输入器宽度 |
| `≤760px` | 按需抽屉 | 按需抽屉 | 单列完整宽度 |
| `≤560px` | 按需抽屉 | 按需抽屉 | 收敛顶部次要信息 |

React 只保存抽屉开关，不持续读取或持久化视口宽度。

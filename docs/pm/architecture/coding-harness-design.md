# Coding-Harness 产品与架构设计

## 一、项目理解

- **项目目标：** 建设一个模型无关、工具受控、过程可观察、结果可审查的 Coding Harness，产品形态接近 Codex 或 Claude Code，而不是某个固定业务场景的聊天机器人。
- **目标用户：** 第一阶段面向愿意让 Agent 在本地代码仓库内完成开发任务的个人开发者和技术团队成员；企业管理员和平台团队属于后续用户。
- **核心场景：** 代码库问答与定位、功能实现、缺陷修复、测试与静态检查、代码审查、文档维护，以及围绕同一代码任务的连续协作。
- **当前阶段：** 第一阶段“可持续执行”底座已落地，处于第二阶段“安全交付闭环”开始前。新执行链已经是唯一正式运行链，但目前主要完成只读模型 Turn，尚不能安全修改、验证和交付代码变化。
- **已有能力：** Workspace、Thread、Turn、Item、Checkpoint 和版本化事件；后台单 Worker 调度；SSE 事件重放；主动中断与稳定点恢复；模型调用、Token、时间和成本预算；Provider 与执行 Service 分离；PostgreSQL 生产仓储和 SQLite 契约测试仓储；启动迁移与遗留运行恢复；API Key 首次配置；默认拒绝命令执行的失败关闭沙箱。
- **关键约束：** 当前为 Python/FastAPI 单体和进程内 Scheduler；同一 Thread 只允许一个活动 Turn；Item 类型目前仅覆盖消息、错误和 Checkpoint；工具调用、审批、ChangeSet、Artifact 和 Verification 尚未实现；可信 OS 沙箱尚未接入；当前只有 DeepSeek ModelProvider；测试评估以执行机制和 Fake Provider 为主，尚未形成真实 Coding Task 发布门禁。

### 1.1 假设与待确认

- **假设：** MVP 采用 local-first，代码和命令在用户机器执行。
- **假设：** MVP 先支持单用户、单个 Turn 串行执行，不做组织级 RBAC。
- **假设：** Git 仓库是主要工作区，但允许只读打开非 Git 目录。
- **待确认：** 是否需要优先支持 DeepSeek 之外的 OpenAI、Anthropic 或本地模型。
- **待确认：** 产品首发入口以 Web 工作台为主，还是以交互式 CLI 为主。

## 二、主要判断

- **当前最重要的问题：** 新执行控制面已经能够可靠运行和恢复只读 Turn，但还缺少从工具提议到策略、审批、沙箱执行、变更归因和验证交付的完整控制链，用户尚不能获得可审查的代码结果。
- **最大机会：** 旧链已删除，Workspace、Thread、Turn 和 Item 成为唯一事实模型。后续能力可以直接建立在现有事件、Checkpoint、预算、仓储和 HTTP 资源协议上，不再承担双链兼容和数据迁移成本。
- **最大风险：** 在可信 OS 沙箱、工具策略、审批票据、幂等和基线冲突检测完成前开放写工具或通用命令，会破坏当前执行控制面的安全可信度。
- **暂不建议投入的事项：** 多 Agent 编排、通用工作流 DSL、云端容器平台、IDE 插件、MCP 市场、长期记忆、向量知识库扩容、复杂 Plan 编辑器和自主提交/推送。

### 2.1 五维现状分析

| 维度 | 当前判断 | 下一步验证 |
| --- | --- | --- |
| 用户价值 | 可创建、观察、中断和恢复只读代码任务，但尚不能交付可审查修改 | 用真实仓库任务验证从工具执行到 Diff、测试结果的闭环 |
| 业务价值 | 已具备区别于普通聊天的持续任务形态，仍缺少用户可接受的代码交付物 | 观察任务完成率、Diff 接受率、同一 Thread 二次交互率 |
| 技术可行性 | 新领域模型、后台调度、事件重放和恢复机制已落地 | 在现有单进程控制面上补齐安全写入闭环，不引入分布式队列 |
| 风险 | 命令越权、路径逃逸、Prompt Injection、误覆盖用户改动 | OS 沙箱、审批票据、基线哈希、敏感路径 deny-read、审计日志 |
| 成本 | 已有执行预算，但真实工具循环和 Coding Task 成本尚无基线 | 增加工具输出截断、ContextSnapshot 和每成功 Turn 成本统计 |

---

## 三、产品设计

### 3.1 产品定义

Coding Harness 是位于用户界面、模型和真实开发环境之间的执行控制层，负责把一个自然语言代码任务变成**可约束、可暂停、可恢复、可审计、可验证**的执行过程。

模型负责判断“下一步做什么”；Harness 负责决定“这一步是否允许、怎样执行、怎样记录、失败后怎样恢复”。

### 3.2 产品边界

**Harness 必须负责：**

- 工作区生命周期和项目指令加载。
- Thread、Turn、Item 的状态与事件持久化。
- 上下文构建、预算控制和压缩。
- 工具注册、参数校验、权限决策、审批和幂等。
- 命令沙箱、文件边界、网络边界和敏感数据过滤。
- 中断、恢复、超时、重试和降级。
- Diff、ChangeSet、测试证据和最终交付。
- Trace、指标、成本、评估和版本归因。

**Agent 必须负责：**

- 理解用户目标和仓库上下文。
- 选择工具和安排当前任务步骤。
- 根据工具结果调整策略。
- 主动验证修改，解释失败和剩余风险。
- 生成面向用户的进度和最终总结。

**P0 不负责：**

- 替代 Git 托管平台、CI/CD 或 IDE。
- 自动部署生产环境。
- 在未确认的情况下执行不可逆外部操作。
- 保证模型生成代码必然正确。

### 3.3 核心领域对象

```text
Workspace 1 --- * Thread 1 --- * Turn 1 --- * Item
                         |          |--- * ToolInvocation
                         |          |--- * ApprovalRequest
                         |          |--- 1 ChangeSet
                         |          |--- * Checkpoint
                         |          `--- * Artifact
                         `--- * ContextSnapshot
```

| 对象 | 含义 | 关键字段 |
| --- | --- | --- |
| `Workspace` | Agent 可访问的本地目录及其执行边界 | `id`、`root_path`、`git_root`、`trust_level`、`permission_profile` |
| `Thread` | 围绕一个持续目标的对话与工作历史 | `id`、`workspace_id`、`title`、`status`、`created_at` |
| `Turn` | 一次用户输入触发的完整 Agent 执行 | `id`、`thread_id`、`status`、`model_config`、`version_set`、`started_at`、`finished_at` |
| `Item` | 流中可独立显示和持久化的执行单元 | `id`、`turn_id`、`type`、`status`、`sequence`、`public_payload` |
| `ToolInvocation` | 一次工具调用及其执行结果 | `call_id`、`tool_name`、`arguments_hash`、`status`、`risk`、`result_ref` |
| `ApprovalRequest` | 对受限动作的结构化授权请求 | `id`、`action_digest`、`scope`、`decision`、`expires_at` |
| `ChangeSet` | Turn 相对启动基线产生的文件变更 | `base_revision`、`files`、`diff_ref`、`conflicts` |
| `Checkpoint` | 可恢复执行所需的稳定状态快照 | `turn_id`、`next_action`、`context_snapshot_id`、`sequence` |
| `Artifact` | 测试报告、日志片段、补丁等交付物 | `kind`、`path_or_ref`、`mime_type`、`sha256` |
| `ContextSnapshot` | 送入一次模型调用的上下文清单和版本 | `sources`、`token_counts`、`compaction_summary`、`builder_version` |

为避免概念膨胀，产品不额外创建 `Session`、`Task` 和通用 `Run`：

- 用户看到的“任务”由 Thread 表达。
- Turn 是一次执行单元。
- 离线评估中的 `EvaluationRun` 仅属于评估域，不进入在线执行模型。

### 3.4 状态机

`Turn.status`：

```text
queued -> running -> waiting_approval -> running -> completed
                  |                    |        -> failed
                  |                    `--------> interrupted
                  `-----------------------------> cancelled
```

约束：

- 状态迁移只能由 `TurnExecutionService` 完成，Controller、Agent 和 Tool 不直接写状态。
- 每次迁移先写事件，再更新聚合状态，事件序号在 Turn 内单调递增。
- `waiting_approval` 和 `interrupted` 必须落 Checkpoint；服务重启后可恢复。
- `completed` 要求最终消息、ChangeSet 和 Verification Summary 均已生成。

`ToolInvocation.status`：

```text
proposed -> validating -> waiting_approval -> executing -> succeeded
                         |             |     -> failed
                         |             `----> timed_out
                         `-------------------> denied
```

### 3.5 一次 Turn 的完整生命周期

1. Controller 校验请求，`TurnExecutionService` 创建 Turn 并记录 `turn.started`。
2. `ContextBuilder` 解析 Workspace、Git 状态、项目指令和 Thread 最近历史，生成首个 `ContextSnapshot`。
3. `AgentRuntime` 调用模型并把输出转换成消息或工具提议，不直接执行工具。
4. `ToolExecutionService` 校验工具 Schema、解析规范化路径、计算风险和审批策略。
5. 低风险动作在沙箱中执行；需审批动作创建 `ApprovalRequest`，Turn 进入 `waiting_approval`。
6. 每个动作产生 Item 和 Trace Span，公开事件通过 SSE 推送，敏感字段只保存摘要。
7. 每轮后更新上下文预算；超限时压缩旧历史和大工具输出，保留引用而非全文。
8. 文件修改后，Harness 比较基线哈希；发现用户同时修改则阻止覆盖并请求 Agent 重新读取。
9. Agent 运行与改动相关的测试、静态检查或构建；Harness 记录命令、退出码、耗时和摘要。
10. Agent 结束时，`ChangeSetService` 生成 Diff 与验证摘要，Turn 进入 `completed`。

### 3.6 Item 与事件协议

P0 对外保持 SSE，但事件协议必须独立于 SSE，以便 CLI、WebSocket 或 SDK 复用。

核心 Item 类型：

- `user_message`
- `agent_message`
- `plan_update`
- `command_execution`
- `file_change`
- `tool_call`
- `approval_request`
- `verification_result`
- `error`

统一事件信封：

```json
{
  "event_id": "evt_...",
  "thread_id": "thr_...",
  "turn_id": "turn_...",
  "sequence": 17,
  "type": "item.completed",
  "occurred_at": "2026-08-29T10:00:00Z",
  "item": {
    "id": "item_...",
    "type": "command_execution",
    "status": "succeeded",
    "public_payload": {
      "command": "python -m unittest discover -s tests -v",
      "exit_code": 0,
      "duration_ms": 8120
    }
  }
}
```

客户端通过 `Last-Event-ID` 或 `after_sequence` 重连，不能依赖内存中的生成器继续存在。

### 3.7 上下文构建与状态管理

`ContextBuilder` 按以下优先级构建模型输入：

1. Harness 安全规则和工具契约。
2. 用户级指令。
3. Workspace 根目录到当前工作目录沿途的 `AGENTS.md`，越近优先级越高。
4. 当前 Turn 用户目标和用户补充指令。
5. 当前 Plan、未解决审批和最近 Checkpoint。
6. 与任务相关的文件片段、Git Diff、诊断和测试结果。
7. Thread 历史摘要及最近消息。
8. 可选 Skill 的按需说明和外部资源。

预算建议：系统与权限 15%，用户目标和状态 15%，代码与工具证据 50%，历史 15%，输出预留 5%。这是初始假设，需用真实 Trace 调整。

上下文规则：

- 文件必须按需读取，禁止启动时全仓库灌入。
- 工具结果进入事件存储；模型上下文只放截断摘要和可重新读取的引用。
- 压缩摘要必须保存生成来源、模型和版本，不能覆盖原始事件。
- 不把模型隐藏推理持久化；只记录公开 reasoning summary 或字符数。
- 每次模型调用记录 ContextSnapshot，确保失败可归因、版本可复现。

### 3.8 工具系统

工具定义必须包含：

```text
name + version + description + input_schema + output_schema
+ side_effect(read/write/external/destructive)
+ risk_level + idempotency_mode + timeout_policy
+ permission_requirements + result_size_limit
```

职责边界：

- `ToolRegistry` 负责发现和版本选择。
- `ToolPolicyService` 负责判定 allow、ask 或 deny。
- `ToolExecutionService` 负责幂等、超时、沙箱执行和结果规范化。
- Tool Adapter 只封装一个外部能力，不包含 Agent 流程和业务权限判断。
- 写工具通过 Service 完成，禁止 Tool 直接写数据库或绕过 ChangeSet 记录。

P0 内置工具组：

- 文件：`list_files`、`read_file`、`search_text`、`apply_patch`、`write_file`。
- Git：`git_status`、`git_diff`、`git_log`。P0 不开放 commit、push、reset。
- 命令：`exec_command`，由沙箱与策略决定能力，不继续维护不断膨胀的硬编码完整命令白名单。
- 计划：`update_plan`，仅维护小型可见清单，不实现 DAG 工作流引擎。
- 交互：`request_approval` 由 Harness 触发，不暴露为模型可自由伪造的授权工具。

### 3.9 权限、确认与幂等

权限由两层组成：

- **执行边界：** OS 级沙箱实际限制可读、可写路径和网络。
- **审批策略：** 在执行边界内或越界前决定是否暂停询问用户。

P0 权限模式：

| 模式 | 文件读取 | 工作区写入 | 命令 | 网络 |
| --- | --- | --- | --- | --- |
| `read_only` | 工作区允许 | 每次询问或拒绝 | 只读命令 | 默认关闭 |
| `workspace` | 工作区允许 | 工作区允许 | 沙箱内允许，危险前缀询问 | 默认关闭 |
| `full_access` | 按宿主权限 | 按宿主权限 | 允许但保留危险动作确认 | 显式开启 |

审批请求必须绑定 `action_digest = hash(tool + normalized_args + workspace + policy_version)`。批准内容发生变化后旧票据立即失效。

审批范围只支持：

- `once`：仅本次完全相同动作。
- `turn`：本 Turn 内匹配规范化前缀规则的动作。

P0 不提供永久批准。删除、覆盖工作区外文件、提权、读取密钥、`git push` 等能力默认 deny，而不是通过一句自然语言确认放行。

幂等规则：

- 每次 ToolInvocation 使用稳定 `call_id`；重复执行返回已保存结果。
- 文件写入携带读取时的 `base_sha256`，不匹配时返回 `conflict`。
- 外部写操作必须提供目标系统支持的 idempotency key，否则不可自动重试。
- 纯读取调用可在瞬时错误时自动重试；写入超时后状态标记为 `unknown`，先核验结果再决定是否重试。

### 3.10 错误恢复、重试与降级

| 失败类型 | 策略 |
| --- | --- |
| 模型限流或瞬时网络错误 | 指数退避加抖动，最多 2 次；保持同一 Turn 和调用版本 |
| 模型上下文超限 | 重新压缩工具输出和旧历史，最多重建一次上下文 |
| SSE 断开 | Agent 继续执行；客户端按序号补拉事件 |
| 进程重启 | 从最后 Checkpoint 恢复为 `interrupted`，由用户点击继续 |
| 命令超时 | 终止进程组，保存尾部输出，交给 Agent 决定缩小验证或报告 |
| 工具参数错误 | 返回结构化可修复错误给 Agent，不重试相同参数 |
| 文件基线冲突 | 阻止写入，要求重新读取并生成新补丁 |
| 主模型不可用 | P0 明确失败；P1 才允许经过能力校验的模型降级 |

自动恢复必须有预算：`max_model_calls`、`max_tool_calls`、`max_wall_time`、`max_tokens` 和 `max_cost` 任一达到上限即停止并说明原因。

### 3.11 变更与验证交付

Turn 完成页必须展示：

- 修改文件列表、增删行数和完整 Diff。
- Agent 的变更摘要及关键设计决定。
- 已运行验证命令、退出码和结果摘要。
- 未运行的建议验证及原因。
- 冲突、失败、跳过项和剩余风险。
- Token、耗时和估算成本。

P0 不自动提交 Git。用户审查后可继续在同一 Thread 要求修正，形成新 Turn 和新 ChangeSet。

### 3.12 Web 与 CLI 形态

Web 工作台采用三栏而非纯聊天页：

```text
左：Workspace / Thread 列表
中：对话、计划、工具执行、审批和进度流
右：Files Changed / Diff / Verification / Trace 标签页
```

CLI 与 Web 共用 Service 和事件协议：

```bash
coding-harness                      # 在当前目录打开交互式 Harness
coding-harness exec "修复登录超时"  # 单次非交互运行
coding-harness resume <thread-id>   # 恢复 Thread
coding-harness inspect <turn-id>    # 输出状态、Diff 和验证结果
```

P0 可以先交付 Web 工作台和最小 `exec` CLI；完整 TUI 延后。

---

## 四、目标架构与演进

### 4.1 逻辑架构

```text
Web Controller / CLI
        |
        v
ThreadService ---- WorkspaceService
        |
        v
TurnExecutionService <---- ApprovalService
        |                         |
        v                         v
ModelProvider ---> ContextBuilder / Checkpoint
        |
        v
ToolExecutionService ---> ToolPolicyService
        |                       |
        v                       v
Tool Adapters            SandboxAdapter
        |
        v
Filesystem / Git / Process / MCP (P1)

All components ---> TurnExecutionStore / Event stream / Trace / Metrics
Turn completed ---> ChangeSetService / VerificationService
```

### 4.2 当前代码基线

| 当前模块 | 已承担职责 | 下一步演进 |
| --- | --- | --- |
| `application.domain.execution` | Workspace、Thread、Turn、Item、Checkpoint、状态机和执行预算 | 增加 ToolInvocation、ApprovalRequest、ChangeSet、Artifact 与 Verification 领域对象 |
| `application.services.execution` | Thread/Turn 用例、进程内调度、后台执行、事件通知、增量合并、中断和恢复 | 将模型单轮执行扩展为受控工具循环，并接入审批和交付服务 |
| `application.agent.provider` | ModelProvider 协议与 DeepSeek 流式适配 | 增加能力声明、工具提议事件和供应商契约测试 |
| `application.repositories.execution` | SQLite 执行仓储及共用语义 | 扩展工具、审批、变更和验证的事务写入 |
| `application.repositories.postgres_turn_execution` | PostgreSQL 执行控制面、租约、事件与 Checkpoint | 增加第二阶段实体表和 Artifact 引用 |
| `application.controllers.http` | Workspace、Thread、Turn、事件查询/SSE、中断、恢复和配置 API | 增加审批、ChangeSet、Artifact 和 Verification API |
| `application.infrastructure.sandbox` | 未配置可信隔离时拒绝全部命令 | 接入目标平台可信 OS 沙箱；不达标时继续失败关闭 |
| `application.static` | 通过新资源 API 创建任务并观察 Turn 事件 | 演进为执行流、审批、Diff 和验证三栏工作台 |
| `application.db.migrations` | 编号迁移、执行域建表和启动恢复 | 增加第二阶段可回滚迁移 |
| 现有测试 | 新执行链唯一性、HTTP 资源闭环、状态机、预算、中断恢复和沙箱拒绝 | 增加工具安全、冲突、审批、ChangeSet 和真实 Coding Task 评估 |

### 4.3 下一步新增的稳定职责

只在实现对应能力时新增模块，继续避免空接口和无消费者抽象：

```text
application/domain/tools.py
application/services/tool_execution.py
application/services/approvals.py
application/services/change_sets.py
application/services/verification.py
application/agent/context.py
application/tools/policy.py
application/tools/adapters.py
application/repositories/artifacts.py
```

### 4.4 数据与事务原则

- PostgreSQL 是执行控制面的事实来源；Workspace 文件系统和 Git 是代码状态的事实来源。
- 当前 Workspace、Thread、Turn、Item、Checkpoint 和事件 Schema 直接向前演进，不再设计旧 Session 导入、双写或兼容读路径。
- 一个 Item 完成、ToolInvocation 更新和事件追加应在同一事务中提交。
- 事件表使用 `(turn_id, sequence)` 唯一约束，支持断线重放。
- 大命令输出和 Diff 放入 Artifact Store，数据库只保存摘要、哈希和引用。
- Turn 使用现有租约和单活动 Turn 约束防止双执行。
- P0 继续使用进程内 Scheduler，不提前引入消息队列。
- 可信沙箱不可用时，命令执行保持拒绝，不能退回应用层白名单冒充隔离。

---

## 五、下一步执行路线

### P0：必须完成

#### 已完成：可持续执行底座

- **已具备：** Workspace、Thread、Turn、Item、Checkpoint、版本化事件、后台单 Worker、SSE 重放、中断恢复、预算、Provider 边界、SQLite/PostgreSQL Store 和旧接口移除。
- **产品价值：** 任务已经脱离单次页面连接，执行状态可持续、可查询、可中断、可恢复。
- **保持门禁：** 后续改动不得恢复 chat/session 双链，不得让 SSE 连接承担执行生命周期，不得绕过 TurnExecutionStore 写执行状态。

#### P0-1 工具提议与执行控制链

- **任务：** 扩展 ModelProvider 事件和 Item 类型，建立 ToolDefinition、ToolInvocation、ToolRegistry、ToolPolicyService 与 ToolExecutionService。
- **目标与用户价值：** Agent 可以探索仓库并提出动作，同时每个动作都有统一、可解释的控制入口。
- **前置依赖：** 现有 TurnExecutionService、事件协议和事务仓储。
- **预期产出：** 文件读取、搜索、Git 查询和受控命令适配器；类型化输入输出；结构化错误。
- **验收标准：** Agent 无法直接持有或调用底层 handler；所有动作都有 ToolInvocation、Item 和可重放事件。
- **风险及应对：** 工具循环破坏恢复语义；只在完整工具结果后保存稳定 Checkpoint。

#### P0-2 权限、审批、幂等与可信沙箱

- **任务：** 实现 allow、ask、deny 策略，结构化审批、action digest、一次/本 Turn 授权、call_id 幂等和可信 SandboxAdapter。
- **目标与用户价值：** 低风险动作连续执行，高风险动作在执行前由用户掌控。
- **前置依赖：** P0-1；确定首发平台的 OS 隔离实现。
- **预期产出：** 审批 API/UI、权限矩阵、命令沙箱、安全回归集。
- **验收标准：** 路径逃逸、敏感读取和未授权网络被阻断；参数变化后旧审批失效；重复调用不重复产生副作用。
- **风险及应对：** 跨平台隔离不一致；未通过验证的平台保持命令禁用。

#### P0-3 ChangeSet、冲突检测与 Artifact

- **任务：** 在 Turn 起止记录 Git/文件基线，使用 base hash 阻止覆盖，聚合实际触碰文件并保存大型结果。
- **目标与用户价值：** 用户能准确审查 Agent 产生的变化，不会丢失自己同时进行的编辑。
- **前置依赖：** P0-1、P0-2。
- **预期产出：** ChangeSet、文件变化列表、完整 Diff Artifact 和冲突提示。
- **验收标准：** 所有写入可归因；既有脏改动与 Turn 新改动可区分；基线变化时拒绝覆盖。
- **风险及应对：** 大 Diff 影响事件和数据库；事件只存摘要，正文存不可变 Artifact。

#### P0-4 Verification 与完成语义

- **任务：** 记录测试、静态检查和构建命令，生成 Verification Summary，并收紧 completed 条件。
- **目标与用户价值：** 用户依据可执行证据判断任务是否完成。
- **前置依赖：** P0-2、P0-3。
- **预期产出：** 验证结果、失败摘要、未运行说明和剩余风险。
- **验收标准：** 非零退出码不能显示通过；completed Turn 同时具有最终消息、ChangeSet 和 Verification Summary；只读 Turn 可拥有空 ChangeSet。
- **风险及应对：** 验证命令耗时或不稳定；沿用 Turn 预算、超时和明确降级结果。

#### P0-5 可审查工作台

- **任务：** 在现有新链前端上增加执行 Item、审批、Files Changed、Diff、Verification 和错误定位视图。
- **目标与用户价值：** 用户可以理解执行过程、审批风险、代码变化和验证结果，并继续要求修正。
- **前置依赖：** P0-1 至 P0-4 的稳定 API。
- **预期产出：** Workspace/Thread、执行流、Diff/Verification 三栏工作台。
- **验收标准：** 刷新和重连不丢状态；审批决定与服务端一致；长输出按需查看；所有交付物定位到对应 Turn。
- **风险及应对：** UI 绑定临时字段；先冻结事件和资源 Schema，再实现展示。

#### P0-6 真实 Coding Task 评估与发布门禁

- **任务：** 直接运行 TurnExecutionService，建立 dev、regression、holdout、security 和 recovery 数据集。
- **目标与用户价值：** 模型、Prompt、工具、策略或工作流变化都有可量化证据。
- **前置依赖：** P0-1 至 P0-4。
- **预期产出：** 版本化任务集、可复现 Workspace、逐例 Trace/ChangeSet 和发布报告。
- **验收标准：** 安全用例零放行；恢复无事件缺口和重复写入；候选版本不显著降低任务成功率。
- **风险及应对：** 模型波动影响结论；优先使用测试、Diff、权限和文件断言等确定性指标。

### P1：应该完成

#### P1-1 项目指令、Skill 与渐进式上下文

- **任务：** 支持分层 `AGENTS.md`、Repo Skill 发现、按需加载和 ContextSnapshot 归因。
- **目标与用户价值：** Agent 能稳定遵循项目规则，重复任务不用反复输入流程。
- **负责人角色：** Agent 工程师、后端工程师。
- **前置依赖：** P0 执行与上下文接口稳定。
- **预期产出：** 指令优先级、Skill 元数据索引、上下文预算面板。
- **验收标准：** 嵌套指令优先级正确；未触发 Skill 不加载全文；每次模型调用可解释上下文来源。
- **风险及应对：** 指令注入和上下文膨胀；仓库指令标记为受信配置，外部内容标记为不可信数据并设置字节上限。

#### P1-2 模型适配与版本集

- **任务：** 抽象 ModelProvider，记录 Prompt、模型、工具、策略和工作流版本集合。
- **目标与用户价值：** 可按任务选择模型，并定位质量变化来自哪一部分。
- **负责人角色：** Agent 平台工程师。
- **前置依赖：** P0-6 评估门禁。
- **预期产出：** 至少两个 Provider、能力矩阵、版本清单和回放工具。
- **验收标准：** 不支持工具或上下文能力的模型启动前失败；每个 Turn 可精确追溯版本；模型切换通过回归集。
- **风险及应对：** 追求统一接口损失厂商能力；公共最小协议加 Provider capability，不强行抹平差异。

#### P1-3 非交互 CLI 与 CI 模式

- **任务：** 提供 `exec`、`resume`、`inspect` 和 JSON 输出，支持结构化退出码。
- **目标与用户价值：** Harness 可进入脚本、Git Hook 和 CI，而不依赖浏览器。
- **负责人角色：** CLI 工程师、后端工程师。
- **前置依赖：** 稳定 Service 和事件 Schema。
- **预期产出：** CLI、README、契约测试。
- **验收标准：** CLI 与 Web 对同一 Turn 展示一致状态；JSON 无进度杂音；中断信号可安全终止并保存 Checkpoint。
- **风险及应对：** 形成第二套业务逻辑；CLI 只调用 Service/API，不复制执行循环。

#### P1-4 OpenTelemetry 与成本治理

- **任务：** 建立 Turn 到模型调用、工具调用、命令和持久化的 Trace，增加预算告警和仪表盘。
- **目标与用户价值：** 定位慢、贵、失败的任务，并阻止异常循环消耗。
- **负责人角色：** 可观测性工程师、后端工程师。
- **前置依赖：** P0 事件和版本字段。
- **预期产出：** Trace、指标、脱敏策略、成本面板。
- **验收标准：** 可从 turn_id 查询完整调用树；Prompt、密钥和隐藏推理不进入日志；成本与供应商账单抽样误差在约定范围内。
- **风险及应对：** 高基数和敏感数据；字段白名单、采样和 Artifact 保留周期分级。

### P2：可以延后

- MCP 外部工具、插件安装和组织级分发。
- 子 Agent 委派和并行工作树。
- 云沙箱、远程 Worker 和任务排队。
- IDE 插件、行级上下文和编辑器内 Diff。
- Git commit、push、PR 和代码托管平台审批。
- 后台任务、定时任务和移动端远程控制。
- 企业 RBAC、审计导出、集中策略和私有模型路由。

P2 的启动条件不是“架构已经留好位置”，而是 P0/P1 指标证明用户在稳定完成任务，并出现明确的并行、远程或组织治理需求。

---

## 六、阶段里程碑

详细产品里程碑独立维护，本文只保留迭代关系：

1. [可持续执行](../milestone/01-phase-one-execution-foundation.md)：已完成核心底座。产品从一次性代码聊天演进为可后台运行、重放、中断和恢复的只读任务。
2. [安全交付闭环](../milestone/02-phase-two-safe-delivery-loop.md)：当前主迭代。产品增加受控工具、审批、可信沙箱、ChangeSet、冲突保护和 Verification。
3. [可配置内测产品](../milestone/03-phase-three-release-and-hardening.md)：在安全交付稳定后，增加项目指令、Skill、第二 Provider、CLI、可观测性、成本和反馈闭环。

进入下一迭代以当前阶段完成标准为条件，不绑定固定日期、开发周期或人员配置。

---

## 七、评估指标

| 类别 | 核心指标 | P0 建议目标 |
| --- | --- | --- |
| 用户价值 | 端到端任务完成率、Diff 接受率、首次结果后无需修正率、同 Thread 继续使用率 | 完成率 >= 70%；Diff 接受率 >= 60% |
| 任务成功率 | 测试通过率、要求满足率、仓库无意外改动率、失败阶段分布 | 关键断言通过且无范围外改动 |
| 质量 | Code review 缺陷数、回归数、引用证据完整率、Judge 成对胜率 | 候选版本无显著回退 |
| 性能 | 首事件延迟、首模型输出延迟、Turn 总耗时、工具 P50/P95 | 首事件 < 1 秒；工具延迟按类型设基线 |
| 稳定性 | Turn 完成率、崩溃恢复率、事件缺口率、工具超时率、重复执行率 | 事件缺口和重复写入为 0；稳定点恢复成功率 >= 99% |
| 安全性 | 越界读写阻断率、敏感文件阻断率、未授权网络阻断率、审批绕过数 | 红队用例阻断率 100%；审批绕过为 0 |
| 成本 | 每成功 Turn Token、模型成本、无效工具调用占比、上下文复用率 | 建立分位数基线；预算超限可自动停止 |

评估集至少分为：

- `dev`：开发期快速定位问题。
- `regression`：每次模型、Prompt、工具和工作流变更必跑。
- `holdout`：只在版本候选阶段运行，防止过拟合。
- `security`：路径逃逸、命令注入、Prompt Injection、敏感读取、审批重放和幂等失败。
- `recovery`：断网、进程重启、SSE 断开、命令超时和文件并发修改。

每个评估结果必须绑定 `model_version`、`prompt_version`、`toolset_version`、`policy_version`、`workflow_version` 和 `dataset_version`。

---

## 八、待确认问题

1. 首发运行平台只支持 macOS，还是必须同时覆盖 Linux/Windows？这直接影响可信 OS 沙箱路线。
2. 安全交付闭环默认采用 `workspace` 自动写入，还是所有写操作均需审批？这决定默认权限策略和操作效率。
3. 第二 Provider 优先接入 OpenAI、Anthropic 还是本地模型？当前 DeepSeek Provider 足以继续验证 P0。
4. P0 的命令网络策略是完全关闭，还是允许用户为特定域配置显式 allowlist？

---

## 九、参考实现与依据

- OpenAI Codex App Server 将 Thread、Turn、Item 作为核心原语，并提供 start、resume、fork、steer、interrupt 和流式事件，适合作为客户端无关执行协议的参考：[Codex App Server](https://learn.chatgpt.com/docs/app-server)。
- OpenAI 将 Sandbox 与 Approval 明确拆成两层：前者是技术执行边界，后者决定何时暂停询问；本方案据此避免把自然语言确认当作安全边界：[Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)、[Sandbox](https://learn.chatgpt.com/docs/sandboxing)。
- OpenAI Codex 使用 `AGENTS.md` 承载持久项目指令，使用 Skill 的渐进式披露减少无关上下文，并用 MCP 连接外部工具；本方案将这些能力放在 P1，而不是阻塞 P0 执行闭环：[Customization](https://learn.chatgpt.com/docs/customization/overview)。
- Codex 的官方术语区分 Approval policy、Checkpoint、Compaction、Diff、Permission profile、Plan、Skill 和 Worktree，可用于校准 Harness 的产品对象边界：[Codex Glossary](https://learn.chatgpt.com/docs/glossary)。

本文引用 Codex 作为成熟产品参考，不表示 Coding-Harness 必须复刻其内部实现。最终技术方案应以 Coding-Harness 的用户验证、风险边界和现有 Python 工程为准。

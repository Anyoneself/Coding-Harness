# 第一阶段：可恢复执行底座

## 元信息

- 状态：首个纵向执行切片及真实 PostgreSQL 验证已完成，OS 沙箱选型待安全评审
- 日期：2026-08-31 至 2026-10-02，共 5 周
- 团队：2 名后端，前端参与契约评审，安全与 QA 兼职
- 前置依赖：无
- 产品输入：[Coding Harness 产品与架构设计](../../pm/architecture/coding-harness-design.md)
- 工程基线：[Coding-Harness 系统架构](../../architecture.md)
- 阶段置信度：`0.79`；完成沙箱探针后预计提升至 `0.86`

## 阶段目标

把当前依附于 SSE 请求生命周期的聊天执行，演进为以 Workspace、Thread、Turn、Item 为中心的持久化执行内核。阶段结束时，即使浏览器断开，Fake Provider 仍能在后台完成一个只读 Turn；事件可重放，进程故障可被识别并由用户从稳定 Checkpoint 主动恢复。

本阶段采用“依赖优先的纵向切片”：先冻结契约和验证高风险技术假设，再建设领域与存储，最后接入后台执行。不会先并行铺开 PM 功能列表，也不会建立没有真实消费者的抽象。

## 当前项目依据

| 当前事实 | 影响 | 本地依据 |
| --- | --- | --- |
| `AgentChatService` 在一次流式请求中编排模型、事件和会话保存 | 执行必须从连接生命周期拆出 | [chat.py](../../../application/services/chat.py) |
| `DeepSeekAgent` 同时解析供应商流并直接执行工具 | Provider、Runtime 和工具控制边界必须拆分 | [runtime.py](../../../application/agent/runtime.py) |
| PostgreSQL 以 Session JSONB 和 request 事件为核心 | 新执行域应使用新表，不能原地硬改旧语义 | [postgres_session.py](../../../application/repositories/postgres_session.py) |
| 已有 SQLite 测试仓储和 Fake Client | 可建立跨 PostgreSQL/SQLite 的契约测试 | [tests](../../../tests) |
| 当前基线 38 项测试通过、2 项外部存储测试因环境缺失跳过，Ruff 通过 | 可渐进重构，但 PostgreSQL 执行域测试必须进入 CI | [pyproject.toml](../../../pyproject.toml) |

基线命令于 2026-08-29 验证：

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check .
```

## 范围与非范围

本阶段包括：状态与事件契约、沙箱/解耦/大事件探针、执行领域模型、迁移机制、事务事件存储、后台调度、Provider 边界、Checkpoint、预算、中断和主动恢复。

本阶段不包括：写工具、审批 UI、ChangeSet、完整 Web 工作台、第二 Provider、自动恢复运行、分布式队列、自动 commit/push/deploy。P0 坚持 Web-first、单 Provider、进程内 Scheduler、同一 Thread 单活动 Turn。

## 不变量与事实来源

1. PostgreSQL 是执行控制面的事实来源；Git 和文件系统是代码状态的事实来源。
2. SSE 断开只影响观察，不取消 Turn；中断必须通过显式命令。
3. 同一 Thread 只允许一个 `queued/running/waiting_approval` Turn。
4. 聚合状态、Item 和事件变化必须在同一数据库事务内提交。
5. 隐藏推理不写事件、Checkpoint、Trace 或审计；只允许公开内容与字符计数。
6. 进程崩溃后的运行中 Turn 标记为 `interrupted`，由用户主动恢复。

## 目标架构与接口优先实现

```text
Web Controller
  -> TurnCommandService / TurnQueryService
  -> TurnScheduler(InProcessTurnScheduler)
  -> TurnExecutionService
       -> ContextBuilder
       -> ModelProvider(DeepSeekModelProvider)
  -> TurnExecutionStore(PostgreSQL / SQLite test)
  -> EventNotifier(LocalConditionNotifier)
```

接口只按现有用例所需的业务语义设计：

```python
class TurnExecutionStore(Protocol):
    def create_turn(self, command: CreateTurn) -> Turn: ...
    def claim_turn(self, turn_id: str, lease: Lease) -> Turn: ...
    def append_item_event(self, command: AppendItemEvent) -> TurnEvent: ...
    def transition_turn(self, command: TransitionTurn) -> Turn: ...
    def save_checkpoint(self, checkpoint: Checkpoint) -> None: ...
    def list_events(self, turn_id: str, after_sequence: int) -> list[TurnEvent]: ...

class TurnScheduler(Protocol):
    def schedule(self, turn_id: str) -> None: ...

class ModelProvider(Protocol):
    def stream(self, request: ModelRequest) -> Iterator[ModelEvent]: ...

class EventNotifier(Protocol):
    def notify(self, turn_id: str, sequence: int) -> None: ...
```

首批具体实现是 `PostgresTurnExecutionStore`、契约测试使用的 `SqliteTurnExecutionStore`、`InProcessTurnScheduler(max_workers=1)`、`DeepSeekModelProvider` 和 `LocalConditionNotifier`。每个接口在引入时必须同时具有 Service 消费者和可运行实现；禁止通用 `BaseRepository`、空 Worker 或预留式工厂。

## 数据设计与所有权

本阶段新增：`schema_migrations`、`workspaces`、`threads`、`turns`、`items`、`turn_events`、`checkpoints`、`context_snapshots`、`model_calls`。

- `TurnExecutionStore` 独占执行域写入，Controller、Provider 和 Scheduler 不直接执行 SQL。
- `(turn_id, sequence)` 唯一；`next_sequence` 在事务中用 `UPDATE ... RETURNING` 分配。
- `turns.version` 承担乐观锁；租约由 `lease_owner`、`lease_expires_at` 表达。
- PostgreSQL 部分唯一索引保证同一 Thread 只有一个活动 Turn。
- 时间统一为 UTC `TIMESTAMPTZ`，ID 由应用生成 UUID，事件带 `schema_version=1`。
- 大消息只保存摘要、SHA-256 和 Artifact 占位引用；Artifact 实体在第二阶段落地。
- 旧 `agent_sessions/agent_events` 保持只读；新链路只写新 Schema，不双写。

迁移使用编号 SQL 和 `schema_migrations`，由 `SchemaMigrationService` 持 PostgreSQL advisory lock 串行执行。当前项目没有 SQLAlchemy，不为迁移单独引入完整 ORM。

## 内部演进排期

### 1A：契约冻结与技术探针，08-31 至 09-04

- 冻结 `TurnStatus`、`ItemStatus`、版本化事件信封、API 草案和 ERD。
- 验证 30 秒 Fake Turn 在 SSE 断开后继续，重连可从 `after_sequence` 补齐事件。
- 验证 10 MB 命令输出、5 MB Diff 只以摘要和引用进入数据库。
- 对目标平台验证 OS 沙箱的路径、网络、资源、进程树终止和工具链兼容性。
- 形成 Web-first、单 Provider、用户主动恢复、沙箱失败关闭 ADR。

沙箱是整个 16 周计划唯一硬 Go/No-Go：若不存在可信 OS 隔离，命令执行必须使用 `DenyCommandSandbox` 禁用。应用层命令白名单只能作为开发防护，不能宣称等价于 OS 隔离。

### 1B：领域、存储与事件重放，09-07 至 09-18

- 先写状态机 Gherkin、领域单元测试和 Store 契约测试。
- 实现 Workspace、Thread、Turn、Item、TurnEvent 及语义异常。
- 先实现 SQLite Store 跑通契约，再实现 PostgreSQL Store 和真实事务测试。
- 实现 `ThreadService`、`TurnCommandService`、`TurnQueryService`。
- 通过故障注入证明状态、Item 和事件原子提交。

### 1C：Runtime、Checkpoint 与后台执行，09-21 至 10-02

- 先用 Fake Provider 写完成、失败、预算耗尽、断流和恢复测试。
- 从 `DeepSeekAgent` 抽取 `ModelProvider`，Provider 不执行工具、不写 Repository、不决定审批。
- HTTP 创建 Turn 返回资源 ID；Scheduler 领取租约后调用 `TurnExecutionService`。
- 稳定恢复点仅为 `before_model`、完整工具结果之后、`waiting_approval` 之前和 final 之后。
- 实现 `ExecutionBudget`：模型调用、工具调用、墙钟时间、Token 和成本上限。
- 使用 EventCoalescer 合并文本增量，默认最多 100 ms 或 2 KB，final 前强制 flush。

## Gherkin 验收

```gherkin
Feature: Turn 脱离客户端连接后仍可可靠执行

  Scenario: SSE 断开后事件可完整重放
    Given 一个 Fake Provider 会在三轮后完成的 Turn
    When 客户端在 sequence 3 后断开 SSE
    Then Turn 最终状态为 completed
    And 使用 after_sequence 3 能按序读取全部后续事件

  Scenario: 非法状态迁移不产生部分写入
    Given 一个状态为 completed 的 Turn
    When 服务尝试将它迁移为 running
    Then 返回 InvalidTurnTransitionError
    And 聚合状态、Item 和事件序号均不变化

  Scenario: 进程重启后由用户从稳定点恢复
    Given Turn 已在完整模型结果后写入 Checkpoint
    When Worker 在下一轮执行时崩溃
    Then 启动恢复把 Turn 标记为 interrupted
    And 用户 resume 后从最后稳定 Checkpoint 继续

  Scenario: 可信沙箱不可用时命令失败关闭
    Given 主平台没有通过沙箱探针
    When Turn 请求执行工作区命令
    Then Harness 拒绝命令执行
    And 只读文件能力仍可使用
```

## 测试与自动化门禁

- 领域状态机、非法迁移、不变量和预算边界单元测试。
- SQLite/PostgreSQL 共用 Store 契约测试；覆盖 sequence 并发、重复 claim、租约过期。
- Migration 空库、重复执行、并发启动、失败回滚测试。
- Fake Provider 覆盖 stop、tool proposal、限流、畸形流、空回答和上下文超限。
- Checkpoint 兼容、隐藏推理不落库、EventCoalescer 时间/大小/final 边界测试。
- SSE 断开重连、Worker 崩溃、重复调度和 interrupt 竞态集成测试。
- CI 执行单元测试、Ruff、Schema 快照和 PostgreSQL 集成测试；默认测试不访问公网或消耗 Token。

## 退出条件

- 无模型调用即可通过 Service 创建 Workspace/Thread/Turn、合法迁移状态并重放事件。
- Fake Provider 可独立于 SSE 完成持久化只读 Turn，租约保证无双执行。
- 进程故障、用户中断、Provider 失败和预算耗尽都有稳定终态与可诊断原因。
- 状态、Item 和事件事务一致，故障注入无部分提交。
- 沙箱探针形成明确 Go/No-Go 和失败关闭实现，不能以“后续再看”进入第二阶段。
- 旧 `/api/chat` 与 Session 链路保持可用且未被双写污染。

## 风险、回滚与可行性自评

| 风险 | 处理与回滚 | 置信度 |
| --- | --- | ---: |
| OS 沙箱无法满足边界 | 命令能力强制切换 `DenyCommandSandbox`，不阻塞只读 Turn | 0.45 |
| 半截模型流无法恢复 | 丢弃未完成 Item，从前一稳定 Checkpoint 重建上下文 | 0.75 |
| PostgreSQL 高频增量写入 | EventCoalescer 限频限量，大正文只存引用 | 0.84 |
| 新旧模型语义混淆 | 旧 Session 只读，新 Turn 只写新表，禁止双写 | 0.90 |

阶段综合可行性为 `0.79`。现有 Service、Repository、Fake Client 和 SSE 机制足以支持渐进拆分；主要不确定性集中在 OS 沙箱，而该风险已有明确的失败关闭路径。本阶段通过功能开关接入新链，回滚只停止新 API/Scheduler，保留新表审计数据，旧 `/api/chat` 不受影响。

## 参考资料

- [Coding Harness 产品与架构设计](../../pm/architecture/coding-harness-design.md)，访问日期：2026-08-29。
- [Coding-Harness 系统架构](../../architecture.md)，访问日期：2026-08-29。
- [WHATWG Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)，SSE 重连语义参考，访问日期：2026-08-29。
- [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)，租约和迁移并发控制参考，访问日期：2026-08-29。

# 第二阶段：安全交付闭环

## 元信息

- 状态：依赖第一阶段退出评审
- 日期：2026-10-05 至 2026-11-20，共 7 周
- 团队：2 名后端、1 名前端，安全与 QA 兼职
- 前置依赖：[第一阶段：可恢复执行底座](01-phase-one-execution-foundation.md)
- 产品输入：[Coding Harness 产品与架构设计](../../pm/architecture/coding-harness-design.md)
- 阶段置信度：`0.77`；可信沙箱已选定时为 `0.84`

## 阶段目标

在可恢复执行内核之上完成 P0 的安全交付闭环：模型只能提出动作，Harness 负责校验、策略、审批、沙箱、幂等和持久化；所有写入都有基线哈希与 ChangeSet；用户可通过 Web 创建任务、重连、审批、中断、恢复并审查 Diff 和验证证据。

第一、第二阶段合计 12 周，于 2026-11-20 达到 P0 发布条件。阶段结束的判断依据是可执行证据，不是 Agent 最终回答中的自述。

## 当前项目依据

| 当前事实 | 影响 | 本地依据 |
| --- | --- | --- |
| `ToolRegistry` 解析参数后直接调用 handler | 必须加入不可绕过的 Policy/Approval/Executor 控制链 | [base.py](../../../application/tools/base.py) |
| Workspace 工具已有路径过滤、敏感文件阻断、原子写和非 Shell 参数列表 | 可保留为 Adapter 基础，但不能当作 OS 沙箱 | [workspace.py](../../../application/tools/workspace.py) |
| 前端已有会话、消息和 Trace 雏形，但 `app.js` 约 1,110 行且 localStorage 保存权威聊天 | 应渐进拆为 API client、state、renderer，并改由服务端持有执行状态 | [app.js](../../../application/static/app.js) |
| 现有 Controller 已支持 FastAPI/SSE | 可复用协议接入层，但不能让 SSE 生成器承担执行 | [http.py](../../../application/controllers/http.py) |
| 现有确定性评估具备阶段评分和版本比较 | P0 发布门禁可迁移到真实 Turn | [evaluation.py](../../../application/services/evaluation.py) |

## 范围与非范围

本阶段包括：类型化工具、策略决策、一次/本 Turn 审批、动作摘要、幂等、OS 沙箱、ChangeSet、冲突检测、Artifact、Verification、稳定 API、SSE 重放、三栏工作台、真实 Turn 评估、旧 Session 迁移和 P0 发布。

本阶段不包括：永久审批、自动 commit/push/deploy、`full_access` 默认启用、第二 Provider、完整 AGENTS/Skill、CLI/CI 执行模式、分布式 Worker、多 Agent 和云执行。

## 目标架构与具体实现

```text
Web Controller
  -> Thread/Turn/Approval Services
  -> TurnExecutionService
       -> ModelProvider
       -> ToolExecutionService
            -> ToolPolicyService -> ApprovalService
            -> SandboxAdapter -> ToolAdapter
       -> ChangeSetService -> VerificationService
  -> TurnExecutionStore
  -> ArtifactStore(LocalArtifactStore)
  -> EventStreamService(Store replay + LocalConditionNotifier)
```

接口与首个实现：

- `ToolAdapter` -> 从现有 Workspace 工具拆出的文件、Git、进程适配器。
- `SandboxAdapter` -> 第一阶段选定的可信实现；不可用时使用 `DenyCommandSandbox`。
- `ArtifactStore` -> `LocalArtifactStore`，数据目录位于用户 Workspace 外。
- `TurnExecutionStore`、`ModelProvider`、`TurnScheduler` 和 `EventNotifier` 继续复用第一阶段契约。

`ToolDefinition` 必须包含版本、Pydantic 输入/输出模型、side effect、风险、幂等模式、超时、权限和结果大小上限。Pydantic 同时负责生成 Schema 和参数校验，不引入第二套 JSON 校验体系。

```text
validate -> policy -> approval -> sandbox execute -> reconcile -> persist
```

Agent 不持有 handler，不能创建 Approval，也不能绕过 Executor。`ToolPolicyService.decide()` 返回结构化 `allow/ask/deny` 与原因。

## 安全、审批与幂等

审批绑定规范化动作：

```text
action_digest = sha256(
  tool_name + tool_version + canonical_json(normalized_args)
  + workspace_id + permission_profile + policy_version
)
```

- P0 只支持 `once` 和 `turn`，不支持永久授权。
- 参数、工作区、权限档或策略版本变化会使审批立即失效。
- `call_id` 在 Turn 内唯一；重复提交返回第一次持久化结果。
- 读操作只对可判定的瞬时错误有限重试。
- 写操作超时进入 `unknown`，必须由 Adapter reconcile 后再决定成功、失败或人工处理。
- ToolInvocation、Item、Checkpoint、Turn 状态和事件在同一事务中更新。

Sandbox 输入必须是参数数组、规范化 cwd、环境变量白名单、网络策略、超时和输出上限。超时终止整个进程组。没有可信 OS 沙箱时通用命令保持 deny；禁止用应用 allowlist 对外宣称已隔离。

## ChangeSet、Artifact 与验证

Turn 启动时记录 Git root、HEAD、初始 dirty 状态和 workspace fingerprint。文件第一次读取或写入前保存 `base_sha256`；不存在文件使用显式 `absent`。每次写入前重新校验基线，不匹配则返回 conflict，绝不覆盖用户并发修改。

ChangeSet 只归因于 Harness 触碰路径，并区分 `preexisting` 和 `turn_delta`。Git 仓库用 Git Diff 展示；非 Git 目录保存触碰文件前镜像并生成统一 Diff。

`LocalArtifactStore` 保存大命令输出、文件前镜像、完整 Diff 和测试报告。Artifact 使用不可变 ID、SHA-256、MIME、字节数和 retention class；数据库只存摘要与引用，浏览器不接触内部路径。敏感输出先脱敏再持久化。

`VerificationService` 记录命令、cwd、退出码、耗时、摘要、Artifact 引用和 `passed/failed/timed_out`。退出码非零不能显示通过，未执行验证必须明确为未运行。`completed` 要求 final message、ChangeSet 和 VerificationSummary 同时存在；只读 Turn 可拥有空 ChangeSet。

## API 与 Web 工作台

P0 资源 API：

```text
POST /api/workspaces
POST /api/workspaces/{id}/threads
POST /api/threads/{id}/turns
GET  /api/threads/{id}
GET  /api/turns/{id}
GET  /api/turns/{id}/events?after_sequence=N
GET  /api/turns/{id}/events/stream
POST /api/turns/{id}/interrupt
POST /api/turns/{id}/resume
POST /api/approvals/{id}/decision
GET  /api/turns/{id}/changeset
GET  /api/artifacts/{id}
```

创建 Turn 返回 `202` 和资源 ID。SSE 先重放数据库事件，再订阅 `LocalConditionNotifier`；支持 `Last-Event-ID` 和 `after_sequence`，慢客户端或通知丢失时仍以数据库补拉。关闭浏览器不取消 Turn。

工作台采用 Workspace/Thread、执行流、Diff/Verification 三栏。服务端是 Workspace、Thread、Turn、Item、Approval 和 ChangeSet 的事实来源；localStorage 只保存折叠和标签偏好。Approval 显示动作、规范化参数、风险原因和范围。现有原生前端按 API client、state、renderers 渐进拆分，不在 P0 同时迁移框架。

旧 `/api/chat` 保留一个版本，内部转为创建默认 Workspace/Thread/Turn 并转换旧事件名，不再调用同步 `stream_chat`；P0 发布后进入弃用期。

## 数据设计与所有权

本阶段新增：`tool_invocations`、`approval_requests`、`changesets`、`change_files`、`artifacts`、`verification_results`。

- `ToolExecutionService` 是 ToolInvocation 状态唯一写入口。
- `ApprovalService` 按 action digest、scope、过期时间和乐观锁决定授权。
- `WorkspaceFileService` 是文件写入唯一入口，并同步登记 ChangeSet。
- `ArtifactStore` 先原子落盘，数据库再提交引用；孤儿由基于创建时间和引用关系的清理任务回收。
- PostgreSQL 仍是控制状态和事件事实来源，文件系统/Git 仍是代码事实来源。

旧 Session 迁移遵循：旧数据只读、新链只写新表、禁止双写。`session import` 先 dry-run，再备份、分批导入、数量/哈希/抽样校验和切换读路径。无法可靠映射的事件保存为 `legacy_event` Item，不伪造 ToolInvocation 或 Approval；旧表至少保留一个版本。

## 内部演进排期

### 2A：工具策略、审批、幂等与沙箱，10-05 至 10-16

- 先写 Policy 决策表、审批防重放和工具状态机测试。
- 迁移只读工具到新 Executor，再迁移写工具。
- 接入可信 SandboxAdapter 并跑路径、网络、命令注入和进程树红队集。
- 移除 Agent 对工具 handler 的直接引用。

### 2B：ChangeSet、Artifact 与 Verification，10-19 至 10-23

- 先写并发编辑、并发创建、脏工作区和失败测试 Gherkin。
- 实现基线哈希、触碰路径归因、完整 Diff Artifact 和验证摘要。
- 通过故障注入验证写入、数据库引用和孤儿清理边界。

### 2C：API、SSE 与 Web 工作台，10-26 至 11-06

- 冻结 OpenAPI 与事件 Schema，补 Controller/Service 边界测试。
- 实现数据库重放加本地通知，验证刷新、重连和慢客户端。
- 切换前端权威状态，完成审批、中断、恢复、Diff 和 Verification 流程。

### 2D：真实评估、迁移与 P0 发布，11-09 至 11-20

- 让评估套件直接运行 `TurnExecutionService`。
- 建立 dev、regression、holdout、security、recovery 数据集及版本归因。
- 演练旧 Session 幂等导入、读路径切换和回滚。
- 运行发布门禁并新增 `docs/releases/<version>.md`。

## Gherkin 验收

```gherkin
Feature: Coding Harness 安全交付可审查变更

  Scenario: 修改参数后旧审批失效
    Given 用户批准了删除 path A 的 once 请求
    When 模型用同一 call_id 请求删除 path B
    Then ToolPolicy 返回 ask 或 deny
    And path B 未发生变化

  Scenario: 用户并发修改阻止覆盖
    Given Harness 读取 sample.py 时记录了 base hash
    And 用户随后在编辑器修改了 sample.py
    When Harness 提交基于旧内容的补丁
    Then 写入返回 conflict
    And 用户的文件内容保持不变

  Scenario: 刷新后恢复完整执行流
    Given Turn 已产生 sequence 1 到 8 并仍在运行
    When 用户从 sequence 5 重新连接
    Then 页面先显示 sequence 6 到 8
    And 后续事件连续显示且不重复

  Scenario: 安全回归阻断 P0 发布
    Given 候选版本在 security 数据集中成功读取工作区外文件
    When 发布门禁计算结果
    Then 候选版本被拒绝
```

## 测试与自动化门禁

- Policy 权限档、风险、side effect 决策表单元测试。
- action digest 规范化、过期、scope、防重放和并发审批测试。
- 路径逃逸、符号链接、敏感文件、网络、命令注入、进程树与资源限制安全测试，要求零放行。
- 写入前/中/后崩溃、`unknown` reconcile、重复 call_id 和事务故障注入测试。
- Git 干净/脏工作区、未跟踪、重命名、删除、非 Git、并发编辑和大文件测试。
- Artifact 哈希、越权读取、崩溃孤儿回收；Verification 退出码和超时测试。
- OpenAPI 快照，SSE 重放/重复连接/慢客户端/重启，桌面与移动端 E2E。
- 真实 Turn 的 security/recovery 硬门禁，以及 20 个真实 coding task 的可审查结果评估。
- 全量单元、集成、Gherkin/E2E、Ruff 和 PostgreSQL/沙箱/Artifact 真实适配器 CI。

P0 发布指标：security 越权放行为 0，审批绕过为 0，范围外文件修改为 0；recovery 事件缺口和重复写入为 0；20 个真实任务至少 70% 形成可审查结果，失败必须明确归因阶段。可信沙箱不达标时，发布配置必须自动禁用命令工具。

## 退出条件

- 本地代码任务可安全读取、修改、验证并生成可归因 Diff 和验证证据。
- 所有工具调用都有 ToolInvocation、Item 和可重放事件，Agent 无绕过路径。
- 审批不可重放，重复写调用不产生二次副作用，未知结果可 reconcile。
- 所有写入都有 base hash 冲突保护，用户并发改动不会被覆盖。
- 页面刷新、SSE 断开和服务重启不丢事件；关闭浏览器不终止 Turn。
- 新前端不把消息正文写入 localStorage。
- P0 默认入口使用新 Turn 链；旧数据可幂等迁移且旧表未删除。
- 发布版本说明包含兼容性、迁移、已知限制和回滚方式。

## 风险、回滚与可行性自评

| 风险 | 处理与回滚 | 置信度 |
| --- | --- | ---: |
| OS 沙箱不可信 | 禁用命令，保留文件与只读闭环；这是唯一硬 Go/No-Go | 0.45/0.85 已选定后 |
| 写操作超时导致结果未知 | 状态置 `unknown`，reconcile 后再推进，不盲目重试 | 0.76 |
| 脏工作区错误归因 | 只记录触碰路径并区分 preexisting/turn_delta | 0.82 |
| 前端切换状态源引发回归 | 新工作台功能开关，旧 `/api/chat` 兼容一个版本 | 0.78 |
| 迁移产生双事实源 | 只读旧表、单向幂等导入、不双写 | 0.86 |

阶段综合可行性为 `0.77`。工具安全和写入一致性工作量较大，但现有路径限制、原子写、SSE 和前端雏形可复用。若沙箱未通过，命令能力降级不影响安全发布；回滚时按功能开关关闭写工具或新工作台，已有 Turn、ChangeSet 和 Artifact 保持只读审计，绝不回退到 Agent 直连高风险 handler。

## 参考资料

- [Coding Harness 产品与架构设计](../../pm/architecture/coding-harness-design.md)，访问日期：2026-08-29。
- [Coding-Harness 系统架构](../../architecture.md)，访问日期：2026-08-29。
- [OpenAI Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)，审批与执行边界参考，访问日期：2026-08-29。
- [WHATWG Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)，重连与事件流参考，访问日期：2026-08-29。

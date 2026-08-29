# 第三阶段：内测强化与成熟演进

## 元信息

- 状态：依赖 P0 发布
- 日期：2026-11-23 至 2026-12-18，共 4 周
- 团队：2 名后端、1 名前端，QA/DevOps 兼职
- 前置依赖：[第二阶段：安全交付闭环](02-phase-two-safe-delivery-loop.md)
- 产品输入：[Coding Harness 产品与架构设计](../../pm/architecture/coding-harness-design.md)
- 阶段置信度：`0.73`
- 16 周总计划结束日期：2026-12-18

## 阶段目标

在不改变 P0 执行控制面事实来源和安全边界的前提下，补齐渐进式项目上下文、第二 ModelProvider、CLI/CI 模式、OpenTelemetry 和成本治理，并通过 5 至 10 名目标用户连续两周内测证明系统可以稳定承担真实开发任务。

本阶段不是扩大自治权限。新增入口和供应商必须复用第二阶段已经验证的 Turn、Policy、Approval、Sandbox、ChangeSet 和 Verification 链路。

## 当前项目与 P0 输入依据

| 输入事实 | 本阶段影响 | 本地依据 |
| --- | --- | --- |
| 当前项目已有根级 AGENTS 规范，但运行时未实现目录优先级和 Skill 按需加载 | ContextBuilder 需提供可追溯来源与预算 | [AGENTS.md](../../../AGENTS.md) |
| 当前只有 DeepSeek 真实模型执行链 | 第二 Provider 必须通过同一契约和回归集 | [runtime.py](../../../application/agent/runtime.py) |
| CLI 当前主要负责启动 Web | 新命令只能调用现有 Service/API，不复制业务逻辑 | [main.py](../../../application/cli/main.py) |
| 现有评估具备确定性评分，P0 已转为真实 Turn 数据集 | 内测发布继续使用版本化证据和硬门禁 | [evaluation.py](../../../application/services/evaluation.py) |
| 基线存在 Starlette TestClient 弃用警告和未关闭 SQLite ResourceWarning | 候选版本需清零这些已知工程债务 | [tests](../../../tests) |

## 范围与非范围

本阶段包括：AGENTS.md 层级、Repo Skill 元数据和按需加载、第二 Provider、能力矩阵、`exec/resume/inspect` CLI、稳定 JSON Lines、OTel Trace、结构化日志脱敏、成本预算和内测指标。

本阶段不包括：MCP 市场、多 Agent、云 Worker、IDE 插件、自动 commit/push/deploy、后台定时任务、企业 RBAC 和永久审批。这些能力必须由内测数据证明需求后另行设计。

## 保持不变的架构约束

1. PostgreSQL 继续是执行控制面的事实来源，Git/文件系统继续是代码状态事实来源。
2. CLI 和 Web 是并列输入适配层，共用 Service、Turn 和事件协议。
3. Provider 只处理供应商协议，不执行工具、不决定权限、不直接持久化。
4. 所有写操作继续使用 base hash、ToolExecutionService 和 ChangeSet。
5. 隐藏推理不持久化；Trace、日志和审计只保留公开摘要或字符计数。
6. P1 仍不开放自动 commit、push、deploy 或永久审批。

## 演进架构

```text
Web / CLI / CI
  -> shared Thread and Turn Services
  -> TurnScheduler -> TurnExecutionService
       -> ContextBuilder(AGENTS + Skills + budget)
       -> ModelProvider
            -> DeepSeekModelProvider
            -> SecondModelProvider
       -> existing Tool/Policy/Sandbox/ChangeSet/Verification chain
  -> TurnExecutionStore / ArtifactStore / EventNotifier
  -> OpenTelemetry + structured metrics + cost ledger
```

不新增通用 Provider 基类或 CLI 专用执行器。第二 Provider 是 `ModelProvider` 的第二个真实实现；CLI 是现有 Service/API 的消费者；OTel 通过现有 turn_id、model_call_id 和 tool_invocation_id 关联，不成为业务事务事实来源。

## 工作流 A：渐进式上下文

`ContextBuilder` 按以下优先级组合输入：Harness 安全规则与工具契约、用户指令、从仓库根到工作目录的 AGENTS.md、当前 Turn 目标、计划与 Checkpoint、相关代码和验证证据、Thread 历史摘要、按需 Skill。

- 距离工作目录更近的 AGENTS.md 只能细化项目规范，不能覆盖 Harness 安全边界。
- Skill 默认只加载名称、描述和路径；匹配当前任务后才读取正文与资源。
- 外部检索内容始终标记为不可信，不能提升权限或修改系统规则。
- 每次模型调用保存 ContextSnapshot 的来源、优先级、字节/Token 数和 builder version。
- 上下文超限优先裁剪可重读输出和旧历史，不删除当前目标、安全规则和未解决审批。

## 工作流 B：第二 ModelProvider

在 Turn 启动前通过 capability matrix 校验 streaming、tools、context length、reasoning、usage 和 cancellation。能力不足时在任何文件修改前失败，不能运行中静默换模型。

两个 Provider 使用相同的 Fake/contract tests、security/recovery 集和版本归因。供应商专有字段留在 Adapter 内；公开事件仍使用版本化 Harness 信封。新增依赖必须同步评估许可证、维护状态和安全风险。

## 工作流 C：CLI 与 CI 模式

新增：

```text
coding-harness exec <goal> [--workspace PATH] [--json]
coding-harness resume <turn-id> [--json]
coding-harness inspect <turn-id> [--json]
```

- CLI 只调用现有 Service 或 API，不建立平行业务链。
- `--json` 输出稳定 JSON Lines，进度与日志不混入 stdout。
- 退出码区分成功、验证失败、权限拒绝、用户中断和系统错误。
- SIGINT 请求 Turn interrupt，等待稳定 Checkpoint 后退出。
- CI 默认使用非交互权限配置；遇到 `ask` 必须失败关闭，不能自动批准。

## 工作流 D：可观测性与成本治理

- 以 turn_id 串联模型、工具、命令、数据库和 Artifact Span。
- 日志使用字段白名单，不记录完整 Prompt、密钥、隐藏推理或敏感工具输出。
- 记录模型/工具调用次数、Token、估算成本、墙钟耗时、Checkpoint 恢复和验证状态。
- 仪表指标展示 p50/p95 耗时、任务完成率、Diff 接受率、审批率、恢复成功率和每成功 Turn 成本。
- 预算超限沿用执行域结构化终止，不由观测组件直接修改业务状态。

## 数据与版本所有权

本阶段在既有 `context_snapshots`、`model_calls` 和 Turn version set 上扩展来源清单、capability snapshot、usage 和 cost 字段；必要时增加 OTel export 配置与聚合视图，不复制事件正文。

每个评估结果绑定：model、prompt、toolset、policy、workflow、context builder 和 dataset 版本。旧 Session 在 P0 验证后仍保持只读至少一个版本；删除旧表必须作为独立、可回滚迁移，不在启动流程自动执行。

## 内部演进排期

### 3A：上下文规则与工程债务清理，11-23 至 12-04

- 先写 AGENTS 层级、Skill 未触发不加载、Prompt Injection 和预算测试。
- 实现 ContextSnapshot 来源解释和上下文裁剪。
- 清理 Starlette TestClient 弃用与 SQLite 未关闭资源警告。

### 3B：第二 Provider 与 CLI/CI，12-07 至 12-11

- 先冻结 capability matrix 和 Provider 契约测试。
- 接入第二 Provider，运行与 DeepSeek 相同的回归集。
- 实现 `exec/resume/inspect`，验证 Web/CLI 状态、事件、Diff 和退出码一致。

若人力不足，第二 Provider 可延后一轮；上下文可追溯、CLI 复用控制面和质量债务清理优先。

### 3C：OTel、成本治理与内测门禁，12-14 至 12-18

- 接入 Span、指标、字段白名单和敏感信息扫描。
- 抽样对账供应商 usage 与成本估算。
- 组织 5 至 10 名目标用户连续两周使用；评审成功率、Diff 接受率、恢复和安全指标。
- 只有达到门禁后才立项 P2，不以功能数量替代成熟度证据。

## Gherkin 验收

```gherkin
Feature: P1 能力复用可追溯的执行控制面

  Scenario: 嵌套 AGENTS 指令按来源覆盖
    Given 根目录和工作目录都有 AGENTS.md
    When Turn 在工作目录构建上下文
    Then 工作目录规则具有更高项目优先级
    And ContextSnapshot 可解释每条规则的来源
    And Harness 安全规则仍具有最高优先级

  Scenario: 不兼容 Provider 在写入前失败
    Given 任务需要工具调用
    And 选择的 Provider 不支持工具
    When 用户启动 Turn
    Then Turn 在任何文件修改前失败
    And 错误包含缺失 capability

  Scenario: CI 遇到审批请求时失败关闭
    Given CI 使用非交互权限配置
    When 工具策略返回 ask
    Then Turn 停止且退出码表示需要审批
    And Harness 不自动创建批准决定

  Scenario: Trace 不泄漏隐藏推理
    Given Provider 返回隐藏 reasoning 内容
    When Turn 完成并导出 Trace
    Then Trace 只包含允许公开的摘要或字符计数
    And 敏感字段扫描结果为零泄漏
```

## 测试与自动化门禁

- AGENTS 根/子目录优先级、冲突、缺失、编码和工作区逃逸单元测试。
- Skill 匹配、按需加载、上下文预算、裁剪和 Prompt Injection 测试。
- 两个 Provider 共用契约测试；覆盖工具、流式中断、usage、限流和畸形响应。
- CLI 参数、JSON Lines Schema、退出码、SIGINT、stdout/stderr 分离测试。
- Web/CLI 对同一 Turn 的状态、事件、Diff 和 Verification 一致性 E2E。
- OTel Span 关联、Exporter 失败降级、日志字段白名单和敏感信息扫描。
- 成本预算边界、usage 对账和超限停止测试。
- 全量单元、集成、Gherkin/E2E、Ruff、PostgreSQL、真实沙箱和两个 Provider 的离线契约 CI。
- 候选版本不得新增运行时警告；已知 TestClient 与 SQLite ResourceWarning 必须清零。

## 内测质量指标与退出条件

- 5 至 10 名目标用户连续两周完成真实任务，无安全硬门禁事故。
- security 集越权放行、审批绕过和敏感日志泄漏均为 0。
- recovery 集事件缺口、重复写入均为 0，恢复成功率达到 PM 目标。
- 真实任务成功率、Diff 接受率、二次交互率和每成功 Turn 成本均可从版本化数据复现。
- 两个 Provider 在同一回归集上有能力差异报告，不兼容能力均提前失败。
- CLI 与 Web 对同一 Turn 的状态、事件、ChangeSet 和 Verification 一致。
- 可从 turn_id 查询完整公开 Trace，隐藏推理和敏感工具正文不落日志。
- 所有发布说明位于 `docs/releases/`，记录兼容性、迁移、限制和回滚方式。

若 PM 文档尚未冻结恢复率、Diff 接受率和成本阈值，3A 结束前由产品、研发和 QA 依据 P0 基线共同设定；门禁冻结后候选版本不得临时降低阈值。

## 风险、回滚与可行性自评

| 风险 | 处理与回滚 | 置信度 |
| --- | --- | ---: |
| AGENTS/Skill 导致上下文膨胀或注入 | 元数据先行、按需加载、来源可追溯、安全规则不可覆盖 | 0.78 |
| 第二 Provider 能力语义不同 | 启动前 capability 校验；独立功能开关可关闭 | 0.72 |
| CLI 形成第二套逻辑 | CLI 仅调用共享 Service/API，以一致性 E2E 约束 | 0.86 |
| OTel 或 Exporter 影响执行 | 异步/有界导出，失败只降级观测，不改变 Turn 状态 | 0.82 |
| 内测样本量小 | 结论限定为内部 beta，不外推企业规模 | 0.68 |

阶段综合可行性为 `0.73`。A、C、D 都建立在 P0 已稳定的接口之上，可独立开关和回滚；第二 Provider 的供应商差异是主要交付波动来源，因此在人力不足时允许延后，而不牺牲执行安全和可观测性。完成本阶段后系统达到成熟内部 beta，而非完整 Codex 等价物。

## 参考资料

- [Coding Harness 产品与架构设计](../../pm/architecture/coding-harness-design.md)，访问日期：2026-08-29。
- [Coding-Harness 系统架构](../../architecture.md)，访问日期：2026-08-29。
- [OpenAI Codex App Server](https://learn.chatgpt.com/docs/app-server)，Thread/Turn/Item 和流式协议参考，访问日期：2026-08-29。
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)，Trace、指标与日志关联参考，访问日期：2026-08-29。

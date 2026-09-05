# Coding-Harness Constitution

## Core Principles

### I. AGENTS.md 是最高项目约束

所有规格、计划、任务、实现和评审必须读取并遵守仓库根级及适用子目录的
`AGENTS.md`。本 Constitution、Spec Kit 模板、Preset、Extension 或 Agent 输出与
`AGENTS.md` 冲突时，以 `AGENTS.md` 为准，并修正冲突的 Spec Kit 工件。不得通过
自动生成内容降低分层、类型、文档字符串、测试、安全或完成标准。

### II. 先定义行为，再设计和实现

新功能、用户可观察行为变化、接口契约变化、跨模块重构和非平凡缺陷修复必须先生成
功能规格。规格使用业务语言说明用户价值、范围、验收场景、边界条件、失败行为、兼容
要求和可测量结果，不得提前把实现方案伪装成业务需求。存在高影响歧义时必须先澄清，
不得让 Agent 自行决定安全、权限、数据一致性或兼容性语义。

### III. 测试先行不可协商

每个新增或变化的业务行为必须先写入 `tests/features/` 的 Gherkin 场景，并映射到可执行
单元、集成或端到端测试。新增测试必须先因目标行为缺失而失败，再完成最小实现使其通过。
缺陷修复必须先有可复现问题的回归测试。Spec Kit 任务中的测试不是可选项；每个用户故事
都必须包含适当的测试任务和明确的独立验收方式。

### IV. 保持分层和契约一致

Controller、CLI、Service、Domain、Repository、DB、Agent、Tool 和 Infrastructure
必须遵守 `AGENTS.md` 定义的职责与依赖方向。计划必须基于仓库真实目录、现有接口和测试
约定，不得套用通用示例目录。前端、HTTP API、Service DTO、持久化模型和 CLI JSON
对同一业务概念使用一致术语；契约变化必须同步所有受影响入口和测试。

### V. 安全、可审查和可验证优先

所有外部输入、模型输出、工具参数、路径和下载内容均不可信。写操作必须经过工作区边界、
权限和幂等检查；高风险或不可逆动作需要明确确认。完成声明必须附带可审查 Diff 和真实
测试、静态检查或构建证据。不得把密钥、Cookie、隐藏推理、完整敏感响应或内部路径写入
规格、日志、测试快照和错误消息。

## Artifact Ownership

- `specs/<feature>/` 保存单个功能的 `spec.md`、`plan.md`、`tasks.md` 和设计工件。
- `docs/pm/` 保存产品级路线、长期架构和跨功能任务，不由单个 Feature Spec 复制替代。
- `tests/features/` 保存可执行行为场景，并通过用户故事、需求编号或任务 ID 关联规格。
- `AGENTS.md` 保存项目工程规则；Constitution 只摘要 Spec Kit 执行所需的不可变原则。
- 需求变化采用 Living Spec 模式：先更新 `spec.md`，再同步计划、任务、测试和实现。

## Development Workflow

1. 阅读 `AGENTS.md`、相关产品文档、架构、代码和测试。
2. 执行 `specify → clarify → plan → checklist → tasks → analyze`。
3. `analyze` 存在严重冲突、遗漏、反向依赖或测试缺口时停止实现并修正上游工件。
4. 按 Gherkin、失败测试、最小实现、通过测试和局部整理的顺序执行任务。
5. 运行受影响测试、全量测试和 `ruff check .`，前端变化还需执行对应前端检查。
6. 执行 `converge`；有追加任务时继续实现和验证，直至收敛或记录明确阻塞。
7. 接口和用户行为变化同步更新相关 Schema、前端、CLI、示例和架构文档；未经用户明确
   要求不得修改 README。

## Governance

- Constitution 修订必须说明原因、兼容影响和迁移要求，并同步检查项目 Preset。
- 每次规格和计划评审必须验证本 Constitution；违反 MUST 原则的计划不得进入实现。
- 自动化只能增强门禁，不能代替人工业务判断、代码评审和发布责任。
- Spec Kit 固定版本升级必须先在隔离工作区检查生成 Diff、Preset 兼容性和测试结果。

**Version**: 1.0.0 | **Ratified**: 2026-09-04 | **Last Amended**: 2026-09-04

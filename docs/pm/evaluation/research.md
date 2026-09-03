# Agent 运行评估市场调研

| 项目 | 内容 |
| --- | --- |
| 文档状态 | Research / Recommendation |
| 调研日期 | 2026年08月25日 |
| 调研范围 | Agent 离线评估、运行轨迹评估、在线监控、Coding Agent 基准与发布门禁 |
| 项目关联 | Coding-Harness Python 工程 |

## 1. 执行摘要

成熟的 Agent 评估不是给最终回答打一个总分，而是同时评估五类对象：

1. **任务结果**：目标是否真正完成，环境终态是否正确。
2. **运行轨迹**：工具选择、参数、顺序和停止条件是否合理。
3. **安全合规**：是否越权、泄密、绕过审批或产生重复副作用。
4. **效率成本**：模型轮次、工具调用、Token、延迟和费用是否可接受。
5. **重复稳定性**：同一案例多次执行是否持续成功，而不是偶然命中。

主流平台的共同抽象可以归纳为：

```text
Dataset
  -> Evaluation Case
      -> Agent Task / Run
          -> Trace / Tool Trajectory
          -> Final State / Artifacts
      -> Scorers
  -> Experiment
  -> Baseline Comparison / Release Gate
```

对 Coding-Harness，近期最重要的不是接入一个评分平台，而是先让正式 `DeepSeekAgent` 链路产生可评估的 Run、工具轨迹、Diff、验证结果和成本数据。当前确定性本地 `AgentService` 评估不能代表真实模型链路的成功率。

## 2. 调研范围与方法

本调研覆盖离线数据集、最终结果与轨迹评分、确定性评分器、LLM-as-a-Judge、线上失败回流、Coding Agent 仓库任务、Trace 标准和发布门禁。

资料优先采用官方产品文档、标准规范和官方基准仓库。产品能力变化较快，本文重点提炼稳定方法，不比较短期 UI 或套餐差异。

## 3. 市场通用做法

### 3.1 数据集与实验

主流平台通常把一次评估建模为“数据集 + 待测任务 + 多个评分器”。Braintrust 将 Eval 组织为 Dataset、Task 和 Scorers，并把每次运行保存为可与基线比较的 Experiment；LangSmith 同样支持在数据集上运行实验，再使用确定性、人工或模型评分器评价结果。参考：[Braintrust Evals](https://www.braintrust.dev/docs/guides/evals)、[LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation)。

一个可维护的案例通常包含：

```text
case_id
input / user goal
initial environment
expected final state
required evidence
allowed and forbidden actions
time / token / cost budget
deterministic grader configuration
optional judge rubric
dataset split
```

建议把数据集分为 `dev`、`regression`、`holdout`、`security` 和 `production_failures`。开发集用于调试，回归集用于持续门禁，盲测集减少过拟合，安全集覆盖越权与注入，生产失败集持续吸收真实问题。

### 3.2 分层评分

LangSmith 对复杂 Agent 明确区分最终响应、单步骤和完整轨迹评估，并支持精确轨迹匹配、顺序匹配、自定义规则和 LLM Judge。参考：[Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent)。

市场实践可以归纳为以下评分优先级：

```text
环境终态和测试
  > 确定性规则
  > LLM Judge
  > 人工复核
```

确定性评分适合测试结果、文件哈希、Diff 范围、Schema、权限和成本预算；LLM Judge 适合需求符合度、代码可读性、计划合理性和解释质量；人工复核用于校准 Judge、处理分歧及高风险案例。

### 3.3 Trace 与轨迹评估

Agent 的答案正确不等于过程可信。轨迹通常按以下维度评价：

| 维度 | 典型判断 |
| --- | --- |
| Tool selection | 是否选择正确工具 |
| Arguments | 参数是否有效、最小且符合策略 |
| Ordering | 是否先理解再修改、修改后验证 |
| Progress | 每一步是否推进任务 |
| Redundancy | 是否重复读取、搜索或调用失败工具 |
| Grounding | 最终结论是否有工具证据支持 |
| Policy | 是否遵守权限、审批和工作区边界 |
| Termination | 是否在完成、阻断或预算耗尽时正确停止 |

OpenAI 的 Agent Evals 文档将 Trace Grading 用于评估工作流级行为；Phoenix 支持对 Trace、Span 和数据集执行代码或 LLM 评估，并把评分关联回可观察轨迹。参考：[OpenAI Agent evals](https://platform.openai.com/docs/guides/agent-evals)、[Phoenix Evaluation](https://arize.com/docs/phoenix/evaluation/overview)。

### 3.4 在线生产评估

生产环境通常采用分层采样：所有 Run 执行低成本规则评分；失败、高成本、权限阻断和用户差评 Run 强制进入评估；其余 Run 按比例执行 LLM Judge；典型失败经过脱敏后加入回归数据集。

Langfuse 支持将 Score 关联到 Trace、Observation、Session 和 Dataset Run，也支持人工 Annotation Queue 和基于采样条件的自动评估。参考：[Langfuse Evaluation](https://langfuse.com/docs/evaluation/overview)、[Evaluation methods](https://langfuse.com/docs/evaluation/evaluation-methods)。

### 3.5 Trace 标准化

OpenTelemetry 已维护生成式 AI 的语义约定；OpenInference 在此基础上定义 Agent、Tool、Retriever、LLM 等 Span 类型，使运行数据可在不同观测和评估工具间迁移。参考：[OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)、[OpenInference conventions](https://arize-ai.github.io/openinference/spec/semantic_conventions.html)。

## 4. 代表性平台对比

| 平台 | 核心模型 | 强项 | 主要取舍 |
| --- | --- | --- | --- |
| LangSmith | Dataset、Experiment、Trace、Evaluator | Agent 轨迹与 LangChain/LangGraph 集成 | 与 LangChain 生态结合较深 |
| Braintrust | Dataset、Task、Scorer、Experiment | 实验比较、CI 回归、评分器组合 | 托管产品导向较强 |
| Phoenix | OpenInference Trace、Dataset、Evaluator | 开源、自托管、Trace 与评估一体 | 业务评分体系仍需自行定义 |
| Langfuse | Trace、Observation、Score、Dataset Run | 自托管、线上评分、人工标注 | Coding 终态评分需项目实现 |
| W&B Weave | Calls、Objects、Dataset、Evaluation | 实验追踪、版本对象和评分器 | 更偏通用 AI 应用实验平台 |

来源：[LangSmith](https://docs.langchain.com/langsmith/evaluation)、[Braintrust](https://www.braintrust.dev/docs/guides/evals)、[Phoenix](https://arize.com/docs/phoenix/evaluation/overview)、[Langfuse](https://langfuse.com/docs/evaluation/overview)、[W&B Weave](https://weave-docs.wandb.ai/guides/core-types/evaluations/)。

这些平台解决数据记录、实验运行、评分器编排和结果分析，但不能替代 Harness 自己定义任务成功、权限合规、Diff 正确性和副作用幂等语义。

## 5. Coding Agent 基准的关键模式

### 5.1 SWE-bench：以真实仓库终态为准

SWE-bench 给 Agent 一个真实 GitHub Issue 和对应仓库快照，最终通过测试判定补丁是否解决问题。SWE-bench Verified 进一步对案例可判定性进行人工筛选。参考：[SWE-bench](https://www.swebench.com/SWE-bench/)、[SWE-bench GitHub](https://github.com/SWE-bench/SWE-bench)。

其可复用原则是固定仓库 Commit 和依赖环境，使用隐藏测试判断结果，区分目标测试和回归测试，并避免把最终回答作为主要成功判定。

### 5.2 Terminal-Bench：隔离任务环境

Terminal-Bench 使用隔离任务环境、Agent 执行轨迹和验证脚本评价终端型 Agent。参考：[Terminal-Bench](https://www.tbench.ai/)、[Terminal-Bench GitHub](https://github.com/laude-institute/terminal-bench)。

其可复用原则是每个案例使用独立临时工作区，保护测试脚本不被篡改，捕获命令、退出码、时长、Token 和输出 Artifact，并在结束后销毁环境。

### 5.3 重复运行与稳定性

Agent 输出具有随机性，单次满分不能证明可靠。建议同时报告：

- `pass@1`：单次运行成功概率；
- `pass@k`：多次运行中至少一次成功；
- `pass^k`：连续 k 次全部成功；
- 平均分、最差分和方差；
- 同一案例不同模型、Prompt、工具版本的配对差异。

对生产 Harness，`pass^k`、最差运行和安全失败次数通常比“多跑几次总能成功”更重要。

## 6. 建议评分器

### 6.1 结果评分

| 指标 | 实现方式 |
| --- | --- |
| Task success | 隐藏测试或验收脚本 |
| Build health | Build、Lint、Typecheck、Test 退出码 |
| Diff scope | 修改文件允许列表和行数预算 |
| Regression | 原有测试和行为是否保持 |
| Artifact integrity | 目标文件、报告或数据是否存在且有效 |
| Honest completion | 未验证时是否明确说明 |

### 6.2 轨迹评分

| 指标 | 实现方式 |
| --- | --- |
| Valid tool call rate | 成功解析且通过 Schema 的调用比例 |
| Tool failure rate | failed / total tool invocations |
| Redundant call rate | 相同工具和参数的无进展重复比例 |
| Evidence coverage | 最终声明是否关联文件、测试或工具事件 |
| Verification rate | 发生修改后是否运行适用验证 |
| Loop detection | 是否触发最大轮次或重复动作保护 |

### 6.3 安全评分

安全指标应作为发布硬门禁，而不是与质量分数平均：

- 未经确认的写入和命令执行；
- 工作区路径逃逸和符号链接逃逸；
- 敏感文件、环境变量或密钥泄漏；
- Approval 参数被替换或跨 Run 复用；
- 重试导致副作用重复执行；
- 测试、评分器或基准文件被 Agent 篡改；
- Prompt Injection 导致策略改变。

### 6.4 LLM Judge

Judge 适合评价需求符合度、代码清晰度、计划合理性、无关修改和最终总结。使用时应保存 Rubric 与 Judge 版本，交换 A/B 顺序检测位置偏差，并用人工标注集校准。Judge 不应覆盖确定性失败或安全阻断。

## 7. Coding-Harness 当前差距

当前仓库已经具备会话 Event、工具调用事件、Token Usage、本地 Trace 和基础评估模型，但存在四个关键断点：

1. `EvaluationSuite` 评估确定性 `AgentService`，不是正式 `DeepSeekAgent` 链路。
2. 正式链路没有独立 Run、Step、ToolInvocation、Artifact 和 EvaluationResult 模型。
3. 文件修改没有统一 Diff、基线哈希和验证证据，难以评价真实终态。
4. Prompt、模型、工具和工作流没有统一版本快照，实验结果难以重现。

因此不建议先接入完整第三方平台。应先建立项目自己的评估契约，再选择 Phoenix、Langfuse 等平台作为展示和分析层。

## 8. 最小评估架构

```text
EvaluationDataset
  -> EvaluationCase
      -> isolated Workspace fixture
      -> AgentChatService / DeepSeekAgent
          -> Run Events
          -> Tool Invocations
          -> Diff and Validation Artifacts
          -> Usage and Timing
      -> Deterministic Scorers
      -> Optional Judge
  -> Experiment Summary
  -> Baseline Comparison
```

每次实验应保存：应用版本、模型、Prompt 版本、工具注册表版本、工作流版本、案例版本、评分器版本、工作区 Fixture Commit 和运行预算。

单条评分结果建议采用：

```json
{
  "run_id": "run-123",
  "case_id": "fix-login-regression",
  "metric": "tool_policy_compliance",
  "score": 1.0,
  "label": "passed",
  "evaluator_version": "policy-v1",
  "evidence_event_ids": [12, 15, 18],
  "explanation": "所有写操作均经过授权",
  "created_at": "2026-08-25T10:00:00Z"
}
```

## 9. 实施优先级

### P0：真实链路评估闭环

1. 定义 `EvaluationDataset`、`EvaluationCase`、`Experiment` 和 `EvaluationResult`。
2. 为正式 Agent 链路增加 Run、ToolInvocation、耗时和 Artifact 记录。
3. 建立 20 个通用 Coding Harness 案例，覆盖探索、修改、验证和失败路径。
4. 实现测试、Diff 范围、禁止文件、工具失败、权限和验证证据评分器。
5. 支持基线与候选版本配对比较。
6. 将任何安全回归设置为 CI 硬门禁。

验收标准：同一案例可重复运行，能够重现版本配置，输出逐案例分数、失败阶段、证据和成本。

### P1：稳定性和在线反馈

1. 每个关键案例重复运行 3 至 5 次，报告成功率、方差和最差结果。
2. 增加经人工校准的 LLM Judge。
3. 增加线上规则评分、异常采样和用户反馈关联。
4. 将典型线上失败脱敏后转为回归案例。
5. 使用 OpenTelemetry/OpenInference 输出 Trace，按需要接入 Phoenix 或 Langfuse。

### P2：高级评估

1. Prompt Injection、权限绕过和数据外传对抗集。
2. 模型超时、限流、工具失败、数据库断开等故障注入。
3. 长任务、中断和恢复评估。
4. 多模型、多 Prompt、多工具版本实验矩阵。

## 10. 发布门禁建议

候选版本应同时满足：

- 安全回归为 0，未授权副作用为 0；
- 核心任务成功率不显著下降；
- 至少 80% 的成功修改 Run 包含有效验证证据；
- 工具失败率和循环终止率不增加；
- P95 Token、成本和耗时增长不超过预算；
- 低置信度 Judge 分数不覆盖确定性结果；
- 回归报告包含版本快照和逐案例证据。

统计门禁应优先使用配对实验并报告置信区间。安全指标采用零容忍，不与其他指标加权抵消。

## 11. 风险与限制

- 固定测试可能被 Agent 针对性优化，需要隐藏测试和 Holdout 数据。
- LLM Judge 可能存在位置、长度、风格和模型家族偏差。
- 只看平均成功率会掩盖高风险失败和不稳定案例。
- 生产 Trace 可能包含源码、个人信息和密钥，必须采集前脱敏并设置保留期限。
- 第三方平台的默认模型不能代替 Coding-Harness 的权限和副作用语义。
- 市场产品变化较快，接入前应重新确认部署、数据处理和版本状态。

## 12. 待确认问题

1. 首版评估环境使用临时目录、Docker 容器还是固定测试仓库？
2. CI 是否允许调用真实 DeepSeek API，还是默认只运行录制响应与 Mock？
3. 线上 Trace 的保存期限、访问角色和脱敏要求是什么？
4. 是否需要从第一版开始支持多模型实验？

## 13. 资料来源

以下资料均于 2026年08月25日访问：

- [OpenAI Agent evals](https://platform.openai.com/docs/guides/agent-evals)
- [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation)
- [LangSmith: Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent)
- [Braintrust Evals](https://www.braintrust.dev/docs/guides/evals)
- [Arize Phoenix Evaluation](https://arize.com/docs/phoenix/evaluation/overview)
- [Langfuse Evaluation](https://langfuse.com/docs/evaluation/overview)
- [Langfuse Evaluation Methods](https://langfuse.com/docs/evaluation/evaluation-methods)
- [W&B Weave Evaluations](https://weave-docs.wandb.ai/guides/core-types/evaluations/)
- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OpenInference Semantic Conventions](https://arize-ai.github.io/openinference/spec/semantic_conventions.html)
- [SWE-bench](https://www.swebench.com/SWE-bench/)
- [SWE-bench GitHub](https://github.com/SWE-bench/SWE-bench)
- [Terminal-Bench](https://www.tbench.ai/)
- [Terminal-Bench GitHub](https://github.com/laude-institute/terminal-bench)

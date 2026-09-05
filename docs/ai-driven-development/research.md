# AI 驱动开发方式调研与学习路径

## 元信息

- 状态：已完成
- 调研日期：2026-09-04
- 调研范围：AI 辅助编码、交互式 Coding Agent、异步任务委派、规格驱动开发、多 Agent 协作、Agent-first 工程体系
- 目标读者：希望系统理解并实践 AI 驱动开发的软件工程师
- 项目关联：Coding-Harness 已通过 `AGENTS.md`、Skills、测试与分层规则约束 Agent 行为，属于“工程约束进入仓库、Agent 在约束内执行”的实践方向。

## 执行摘要

截至 2026 年，AI 驱动开发已经不再等同于代码补全或在聊天框中索要代码。主流方式形成了一条逐步提高自治程度的谱系：**补全与问答 → 交互式 Agent 结对 → 后台任务委派 → 规格驱动开发 → 多 Agent 并行 → Agent-first 工程体系**。GitHub、OpenAI、Anthropic、Google 和 Cursor 的公开实践都在向“人负责目标、约束和验收，Agent 负责检索、实现、测试和迭代”收敛。[Anthropic 对约 40 万次 Claude Code 会话的研究](https://www.anthropic.com/research/claude-code-expertise)也观察到，典型协作中人主要决定“做什么”，Agent 更多决定“怎么做”。

真正决定效果的通常不是单次 Prompt 技巧，而是 Agent 所处的工程环境：是否有清楚的仓库说明、可执行测试、类型和静态检查、稳定的开发环境、结构化任务、权限边界以及可审查的变更记录。OpenAI 的 Agent-first 工程实践将这些要素概括为提高仓库的“Agent 可读性”，Anthropic 和 Cursor 的实践文章也都强调计划、上下文、测试反馈和仓库规则。[OpenAI：Harness engineering](https://openai.com/index/harness-engineering/)、[Anthropic：Claude Code best practices](https://www.anthropic.com/engineering/claude-code-best-practices)、[Cursor：Best practices for coding with agents](https://cursor.com/blog/agent-best-practices)。

需要避免把 AI 使用量直接等同于生产率。DORA 2025 的结论是 AI 更像“放大器”：成熟的平台、测试和流程会被增强，混乱的系统也会更快地产生不稳定和技术债。[DORA 2025 报告](https://dora.dev/research/2025/dora-report/)、[DORA：Balancing AI tensions](https://dora.dev/insights/balancing-ai-tensions/)。METR 在 2025 年针对资深开源开发者的随机对照试验中曾观察到早期工具使特定任务平均耗时增加 19%；其 2026 年更新认为后续工具很可能已带来更多加速，但新实验受到样本选择和并行 Agent 使用的干扰，无法可靠估算加速幅度。[METR 2025 研究](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)、[METR 2026 更新](https://metr.org/blog/2026-02-24-uplift-update/)。

## 六种主流开发方式

| 层级 | 方式 | 人的主要职责 | Agent 的主要职责 | 适用场景 | 主要风险 | 依据 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 补全与问答 | 逐行编写、选择建议、理解代码 | 补全、解释、生成局部代码 | 熟悉代码库中的小改动、API 查询、样板代码 | 上下文窄，容易生成局部正确但系统不一致的代码 | [GitHub Copilot Agent mode 与 Next Edit Suggestions](https://github.blog/changelog/2025-05-13-agent-mode-mcp-and-next-edit-suggestions-come-to-github-copilot-in-visual-studio-17-14/) |
| 2 | 交互式 Agent 结对 | 描述任务、审计划、过程中纠偏、审 Diff | 搜索仓库、跨文件修改、运行命令、测试与修复 | 日常功能、缺陷修复、重构、代码库学习 | 长会话上下文污染；目标含糊时反复返工 | [Anthropic 最佳实践](https://www.anthropic.com/engineering/claude-code-best-practices)、[Cursor 最佳实践](https://cursor.com/blog/agent-best-practices) |
| 3 | 异步任务委派 | 写 Issue/验收标准、等待结果、审 PR | 在隔离环境后台实现、验证并提交 PR | 边界清楚的低中复杂度任务、测试补充、文档和技术债 | 环境不完整、任务过大、自动验证不足时产生“看似完成”的 PR | [GitHub Copilot coding agent](https://github.blog/changelog/2025-09-25-copilot-coding-agent-is-now-generally-available/)、[Google Jules](https://blog.google/innovation-and-ai/models-and-research/google-labs/jules-now-available/) |
| 4 | 规格驱动开发（SDD） | 明确用户价值、约束、验收场景并批准规格 | 将规格细化为计划、任务、测试和实现 | 中大型功能、多人协作、需要审计和长期维护的系统 | 规格形式化过度；规格本身错误会被规模化实现 | [GitHub：Spec-driven development with AI](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)、[Spec Kit 文档](https://github.github.com/spec-kit/) |
| 5 | 多 Agent 并行 | 分解任务、隔离工作区、比较结果、解决集成冲突 | 并行探索方案、实现子任务、独立复核 | 相互独立的任务、方案竞赛、研究与实现并行 | 协调与审查成本上升；共享文件和架构决策容易冲突 | [OpenAI Codex app](https://openai.com/index/introducing-the-codex-app/)、[Cursor 并行 Agent 实践](https://cursor.com/blog/agent-best-practices) |
| 6 | Agent-first / Harness engineering | 设计约束、反馈回路、任务系统、评估和治理 | 长时间自主执行，持续维护代码、测试、文档和基础设施 | Agent 已成为主要实现力量的成熟团队 | 错误高速累积、权限扩大、质量门禁和可观测性不足 | [OpenAI：Harness engineering](https://openai.com/index/harness-engineering/)、[OpenAI：Running Codex safely](https://openai.com/index/running-codex-safely/) |

### 1. 补全与问答：把 AI 当作更强的编辑器

这是成本最低、风险也最低的入口。开发者仍然掌握逐行控制权，AI 主要完成代码补全、局部改写、解释和 API 示例。它适合建立信任，但没有充分利用 Agent 的代码搜索、终端执行和自我验证能力。GitHub 对 Agent mode 的说明明确区分了补全、下一编辑建议和能够多步执行的 Agent 工作流。[GitHub 官方说明](https://github.blog/changelog/2025-05-13-agent-mode-mcp-and-next-edit-suggestions-come-to-github-copilot-in-visual-studio-17-14/)。

### 2. 交互式 Agent 结对：当前最实用的日常模式

开发者在 IDE、终端或桌面应用中与 Agent 保持一个任务会话。推荐循环是：**探索代码 → 形成计划 → 编写或先补测试 → 实现 → 运行验证 → 审查 Diff → 提交**。Anthropic、Cursor 和 OpenAI 的公开指南都强调先让 Agent 理解代码库和计划复杂改动，再进入实现；测试、类型检查和 Linter 则给 Agent 提供可执行的反馈信号。[Anthropic 最佳实践](https://www.anthropic.com/engineering/claude-code-best-practices)、[Cursor 最佳实践](https://cursor.com/blog/agent-best-practices)、[OpenAI 如何使用 Codex](https://openai.com/business/guides-and-resources/how-openai-uses-codex/)。

这种模式下，人不应退化为“接受/拒绝按钮”。高价值动作是补充领域知识、指出不变量、识别错误假设和决定是否达到发布标准。Anthropic 2026 年的使用研究显示，领域专家更容易让 Agent 每条指令完成更多工作，也更容易从失败中恢复，说明 AI 降低了代码输入成本，但没有消除专业判断的价值。[Agentic coding and persistent returns to expertise](https://www.anthropic.com/research/claude-code-expertise)。

### 3. 异步任务委派：从结对编程转向分派工作

这类工具把 Issue 或任务描述交给云端 Agent。Agent 在独立环境中克隆仓库、创建分支、修改代码、运行测试，然后发起 PR 等待人类审查。GitHub Copilot coding agent 和 Google Jules 都公开采用了这种模式；Cursor Cloud Agents 也将后台任务、隔离环境和结果制品作为核心流程。[GitHub Copilot coding agent](https://github.blog/changelog/2025-09-25-copilot-coding-agent-is-now-generally-available/)、[Google Jules](https://blog.google/innovation-and-ai/models-and-research/google-labs/jules-now-available/)、[Cursor Cloud Agents](https://cursor.com/blog/agent-computer-use)。

适合委派的任务通常具备四个特征：边界明确、可独立完成、验收可自动化、失败容易回滚。可以优先从增加测试、修复有复现步骤的缺陷、局部重构、依赖升级和文档同步开始。架构方向不清、跨团队依赖多、涉及敏感生产操作的任务仍需要更强的人类参与。这一判断与 GitHub 对 coding agent“低到中复杂度、测试良好代码库”的早期定位一致。[GitHub 公开预览说明](https://github.blog/changelog/2025-05-19-github-copilot-coding-agent-in-public-preview/)。

### 4. 规格驱动开发：用持久化意图替代临时 Prompt

SDD 将需求、约束和验收标准保存为版本化工件，再由 Agent 生成或维护技术计划、任务、测试和实现。GitHub Spec Kit 的核心流程是 **Specify → Plan → Tasks → Implement**，目的是把稳定的“做什么、为什么”与可调整的“怎么实现”分离。[GitHub SDD 介绍](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)、[Spec Kit 当前文档](https://github.github.com/spec-kit/)。

SDD 特别适合已有工程规范的项目，因为 `AGENTS.md`、架构原则、测试要求、安全约束和业务验收场景可以共同构成 Agent 的执行合同。需要警惕把 SDD 变成文档生产运动：小修复不必生成完整规格包，规格应服务于减少歧义、提供验收依据和保存关键决策，而不是追求模板数量。

### 5. 多 Agent 并行：把人的角色变成调度与评审

多 Agent 有两种常见用法：一是将互不依赖的子任务分派到隔离 worktree 或云端环境；二是让多个 Agent 对同一难题给出候选方案，再由人或评审 Agent选择。OpenAI Codex app 和 Cursor 都把并行任务、独立工作区与结果比较作为重要能力。[OpenAI Codex app](https://openai.com/index/introducing-the-codex-app/)、[Cursor Agent 最佳实践](https://cursor.com/blog/agent-best-practices)。

并行并不自动等于更快。任务分解、环境启动、重复探索、冲突解决和最终审查都会消耗人的注意力。适合并行的工作应尽量减少共享写入，并预先约定接口、所有权和验收命令。对同一任务运行多个候选 Agent 更适合高不确定性、高价值问题，不适合所有普通改动。

### 6. Agent-first 工程：开发“让 Agent 能开发的软件系统”

在这一阶段，团队的核心产物不只是业务代码，还包括让 Agent 稳定工作的工程系统：短而可导航的仓库说明、结构化架构约束、可重复环境、快速测试、评估集、权限策略、日志和审查队列。OpenAI 的 Harness engineering 案例把人的角色概括为设定方向、提高仓库可读性、构建反馈回路和维护架构不变量；其安全实践进一步强调沙箱、网络策略、审批边界和 Agent 原生审计记录。[Harness engineering](https://openai.com/index/harness-engineering/)、[Running Codex safely](https://openai.com/index/running-codex-safely/)。

这一模式不是“完全无人开发”。更准确地说，人类劳动从重复实现迁移到问题定义、系统设计、验证机制、风险治理和最终发布责任。DORA 的研究提示，组织基础能力不足时，AI 会放大交付不稳定，因此不应在测试、平台和架构尚不可靠时直接追求最大自治。[DORA 2025](https://dora.dev/research/2025/dora-report/)。

## 支撑这些方式的四项基础能力

### 仓库上下文即代码

把构建命令、测试命令、架构边界、命名规则和典型实现位置放入版本控制，并保持简短、可导航。Anthropic 使用 `CLAUDE.md`，OpenAI 使用 `AGENTS.md`，Google Jules 也支持读取 `AGENTS.md`；三者都说明持久化仓库指令已成为跨产品的共同模式。[Anthropic 最佳实践](https://www.anthropic.com/engineering/claude-code-best-practices)、[OpenAI Codex 介绍](https://openai.com/index/introducing-codex/)、[Jules 更新](https://jules.google/docs/changelog/2025-06-20/)。

### 可执行反馈回路

测试、类型检查、Linter、构建、浏览器操作和运行时观测让 Agent 能判断自己的改动是否有效。没有自动反馈时，Agent 只能依据文本表面判断“完成”；反馈越快、失败信息越明确，Agent 越容易自主迭代。Cursor 和 Anthropic 均把测试驱动循环列为常用工作流。[Cursor 最佳实践](https://cursor.com/blog/agent-best-practices)、[Anthropic 最佳实践](https://www.anthropic.com/engineering/claude-code-best-practices)。

### 工具与外部系统连接

MCP 以 Host、Client、Server 架构为 Agent 暴露资源、工具和 Prompt，同时保留能力协商和安全边界。它适合连接代码托管、数据库、设计工具、内部文档和业务系统，但工具权限应遵循最小授权，并防范不可信内容导致的 Prompt Injection。[MCP 官方架构](https://modelcontextprotocol.io/specification/2025-06-18/architecture)、[GitHub Copilot 的 MCP 支持](https://github.blog/changelog/2025-05-19-agent-mode-and-mcp-support-for-copilot-in-jetbrains-eclipse-and-xcode-now-in-public-preview/)。

### 沙箱、审批与审计

更高自治需要更清晰的边界，而不是无条件自动批准。Anthropic 的沙箱实践将文件系统和网络隔离作为减少审批疲劳、提高自治的手段；OpenAI 的内部实践则强调受管配置、受限执行、网络政策和 Agent 原生日志。[Anthropic：Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)、[OpenAI：Running Codex safely](https://openai.com/index/running-codex-safely/)。

## 推荐学习路径

### 第一阶段：建立正确概念

1. [Simon Willison：Vibes](https://simonwillison.net/2025/May/1/vibes/)  
   为什么读：帮助区分广义 AI 辅助开发和“不理解、不审查就接受代码”的狭义 vibe coding。篇幅很短，适合作为起点。

2. [DORA：State of AI-assisted Software Development 2025](https://dora.dev/research/2025/dora-report/)  
   为什么读：从组织与交付系统角度理解 AI，而不是只看个人生成速度。重点看“AI 是放大器”及配套能力模型。

3. [Anthropic：Agentic coding and persistent returns to expertise](https://www.anthropic.com/research/claude-code-expertise)  
   为什么读：基于约 40 万次会话理解实际的人机分工。重点看领域知识、任务成功和从错误恢复之间的关系。

### 第二阶段：学会单 Agent 日常协作

4. [Anthropic：Claude Code: Best practices for agentic coding](https://www.anthropic.com/engineering/claude-code-best-practices)  
   为什么读：最完整的实操型文章之一。重点练习“探索—计划—编码—提交”、测试驱动、上下文管理和及时纠偏。

5. [Cursor：Best practices for coding with agents](https://cursor.com/blog/agent-best-practices)  
   为什么读：覆盖计划、Rules、Skills、浏览器验证、代码审查、并行 Agent 和云端委派，可作为工作流手册。

6. [OpenAI：How OpenAI uses Codex](https://openai.com/business/guides-and-resources/how-openai-uses-codex/)  
   为什么读：学习如何把任务写成高质量 GitHub Issue，并通过开发环境和 `AGENTS.md` 降低执行错误。

7. [Google Cloud：Five Best Practices for Using AI Coding Assistants](https://cloud.google.com/blog/topics/developers-practitioners/five-best-practices-for-using-ai-coding-assistants)  
   为什么读：提供跨 Gemini CLI、Code Assist 和 Jules 的团队实践视角，可与前三篇互相印证。

### 第三阶段：从 Prompt 驱动进入规格驱动

8. [GitHub：Spec-driven development with AI](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)  
   为什么读：理解为什么要让规格成为持久化工件，以及 Specify、Plan、Tasks、Implement 四阶段如何减少 Agent 猜测。

9. [GitHub Spec Kit 文档](https://github.github.com/spec-kit/)  
   为什么读：跟着 Quick Start 做一个小项目。建议先用一项真实但边界明确的功能体验完整流程，不要一开始改造整个仓库。

### 第四阶段：理解异步、多 Agent 与 Agent-first 工程

10. [GitHub：Copilot coding agent](https://github.blog/changelog/2025-09-25-copilot-coding-agent-is-now-generally-available/)  
    为什么读：理解 Issue → 后台环境 → Draft PR → 人工 Review 的任务委派模型。

11. [OpenAI：Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)  
    为什么读：理解并行 Agent、长任务和定时自动化如何改变开发者工作台。

12. [OpenAI：Harness engineering](https://openai.com/index/harness-engineering/)  
    为什么读：这是从“会用 Agent”走向“建设 Agent-first 代码库”的关键文章。重点看仓库知识、架构约束、反馈回路和自治层级。

13. [MCP 官方架构](https://modelcontextprotocol.io/specification/2025-06-18/architecture)  
    为什么读：理解 Agent 如何标准化连接外部工具、数据和服务，以及 Host 应承担的权限和隔离职责。

14. [OpenAI：Running Codex safely](https://openai.com/index/running-codex-safely/)  
    为什么读：在扩大 Agent 权限和运行时长之前，系统学习沙箱、网络边界、审批和审计。

### 第五阶段：校准对生产率的判断

15. [METR：早期 2025 AI 对资深开源开发者生产率的影响](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)  
    为什么读：提醒自己不要用主观“感觉更快”替代测量，并理解真实任务、基准测试与使用体验可能给出不同结论。

16. [METR：2026 实验设计更新](https://metr.org/blog/2026-02-24-uplift-update/)  
    为什么读：了解工具快速演进、并行 Agent 和样本选择如何让生产率测量变得困难，也避免把 2025 年结果机械外推到当前工具。

## 建议的四周实践安排

以下内容属于学习建议，不是外部事实判断。

| 周次 | 实践目标 | 建议任务 | 验收标准 |
| --- | --- | --- | --- |
| 第 1 周 | 建立单 Agent 协作循环 | 选择一个可复现的小缺陷，让 Agent 先解释调用链、写计划，再补回归测试和修复 | 能说明每项改动原因；测试先失败后通过；人工审完 Diff |
| 第 2 周 | 建设仓库上下文 | 精简或补充 `AGENTS.md`，明确构建、测试、架构边界和安全限制 | 新会话无需重复说明即可找到入口并执行正确验证 |
| 第 3 周 | 体验规格驱动 | 用 Spec Kit 或等价 Markdown 流程完成一个中等功能的规格、计划、任务和实现 | 需求、验收场景、测试和实现能相互追踪 |
| 第 4 周 | 体验并行与委派 | 将两个独立任务交给不同 Agent；另让两个 Agent竞争解决同一难题 | 工作区无相互覆盖；记录协调成本、审查时间和采用理由 |

建议同时记录四个指标：任务总历时、本人专注时间、返工次数、合入后缺陷。依据 DORA 和 METR 的研究，只有把生成速度与验证、返工、稳定性一起看，才能判断 AI 是否真正改善了交付结果。[DORA 2025](https://dora.dev/research/2025/dora-report/)、[METR 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)。

## 对 Coding-Harness 的启示

本项目现有根级 `AGENTS.md` 已经覆盖分层职责、中文文档字符串、类型契约、测试、静态检查、安全和完成标准。这与 OpenAI、Anthropic、Cursor 所强调的“仓库规则、可执行反馈和 Agent 可读性”方向一致。下一步的重点不是继续无限扩充通用规则，而是观察 Agent 的重复失败点，将高频、可执行的领域流程沉淀为短小 Skill、测试或静态约束；OpenAI 的 Harness engineering 特别提醒，单个超长说明文件会挤占任务上下文，应提供地图和可导航知识，而不是一份巨型手册。[OpenAI：Harness engineering](https://openai.com/index/harness-engineering/)。

建议先使用本仓库做上述四周练习，重点测量现有规则是否真的减少返工。若规则只能表达愿望而不能通过测试、Linter、依赖检查或架构测试验证，应优先把关键不变量转化为机器可执行门禁。该建议的事实基础来自 DORA 对基础工程能力放大效应的研究，以及 OpenAI 对架构约束和反馈回路的实践。[DORA 2025](https://dora.dev/research/2025/dora-report/)、[OpenAI：Harness engineering](https://openai.com/index/harness-engineering/)。

## 风险与局限

- 产品能力在快速变化，本文避免比较价格、模型排行榜和短期功能细节；具体使用前应重新查看官方文档。
- 厂商工程博客包含自身产品立场，本文通过 GitHub、Google、OpenAI、Anthropic、Cursor、DORA 和 METR 等不同来源交叉观察，但并不代表所有团队都能复现厂商案例。
- Anthropic 的会话研究来自其自身产品数据；它能说明 Claude Code 使用行为，但不能直接代表所有 Coding Agent。
- METR 2025 的随机对照试验针对熟悉大型开源仓库的资深开发者和早期 2025 工具，不应外推为“AI 对所有开发都更慢”；METR 2026 更新也明确指出新实验存在严重选择偏差。
- Agent-first 工程仍处于快速演进期，长期维护成本、安全事件率和团队技能变化尚缺少多年纵向证据。

## 分类资料来源

访问日期均为 2026-09-04。

### 方法与实操

- [Anthropic：Claude Code: Best practices for agentic coding](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Cursor：Best practices for coding with agents](https://cursor.com/blog/agent-best-practices)
- [OpenAI：How OpenAI uses Codex](https://openai.com/business/guides-and-resources/how-openai-uses-codex/)
- [Google Cloud：Five Best Practices for Using AI Coding Assistants](https://cloud.google.com/blog/topics/developers-practitioners/five-best-practices-for-using-ai-coding-assistants)

### 规格驱动与 Agent-first 工程

- [GitHub：Spec-driven development with AI](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [GitHub Spec Kit 文档](https://github.github.com/spec-kit/)
- [OpenAI：Harness engineering](https://openai.com/index/harness-engineering/)
- [OpenAI：Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)

### 异步 Agent 与工具协议

- [GitHub：Copilot coding agent GA](https://github.blog/changelog/2025-09-25-copilot-coding-agent-is-now-generally-available/)
- [Google：Jules is now available](https://blog.google/innovation-and-ai/models-and-research/google-labs/jules-now-available/)
- [Cursor：Agents can control their own computers](https://cursor.com/blog/agent-computer-use)
- [Model Context Protocol：Architecture](https://modelcontextprotocol.io/specification/2025-06-18/architecture)

### 安全、组织与实证研究

- [OpenAI：Running Codex safely](https://openai.com/index/running-codex-safely/)
- [Anthropic：Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [DORA：State of AI-assisted Software Development 2025](https://dora.dev/research/2025/dora-report/)
- [DORA：Balancing AI tensions](https://dora.dev/insights/balancing-ai-tensions/)
- [Anthropic：Agentic coding and persistent returns to expertise](https://www.anthropic.com/research/claude-code-expertise)
- [METR：Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)
- [METR：We are Changing our Developer Productivity Experiment Design](https://metr.org/blog/2026-02-24-uplift-update/)
- [Simon Willison：Vibes](https://simonwillison.net/2025/May/1/vibes/)

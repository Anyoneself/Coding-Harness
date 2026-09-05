# GitHub Spec Kit 项目调研

## 元信息

- 调研对象：[github/spec-kit](https://github.com/github/spec-kit)
- 调研版本：[`v1.0.4`](https://github.com/github/spec-kit/releases/tag/v1.0.4)
- 调研日期：2026-09-04
- 调研方式：阅读官方 README、文档、模板、CLI 源码、工作流定义、测试目录和版本记录
- 项目关联：评估 Spec Kit 是否适合 Coding-Harness 当前的 AI 驱动开发流程

## 一句话结论

**Spec Kit 是一个面向 AI Coding Agent 的“规格驱动开发脚手架与工作流编排器”：它先把自然语言需求逐步变成规格、设计和任务，再让现有 Agent 按这些工件实现和检查代码。**

它不是新的大模型，不是 IDE，也不是独立的代码生成器。真正检索和修改代码的仍然是 GitHub Copilot、Claude Code、Codex、Cursor、Gemini CLI 等外部 Agent；Spec Kit 提供的是一套统一流程、Markdown 模板、Agent Skill/命令、辅助脚本以及可选的工作流运行时。[项目 README](https://github.com/github/spec-kit/blob/v1.0.4/README.md)、[Codex 集成实现](https://github.com/github/spec-kit/blob/v1.0.4/src/specify_cli/integrations/codex/__init__.py)。

## 它要解决什么问题

普通 AI 编程经常从一句模糊 Prompt 直接跳到代码，容易出现以下问题：

- Agent 自行补全未说明的业务规则；
- 需求、设计和实现混在同一次对话里，难以审查；
- 长任务中逐渐遗忘最初目标；
- 任务完成后无法回答某段代码对应哪条需求；
- 不同开发者或 Agent 使用不同提示方式，结果不可重复；
- “代码写完了”不等于需求、计划和任务全部落实。

Spec Kit 的处理方式是把开发拆成连续、可保存的工件：

```text
项目原则
   ↓
功能规格
   ↓
需求澄清
   ↓
技术计划与设计工件
   ↓
可执行任务列表
   ↓
实现
   ↓
规格、计划、任务与代码的收敛检查
```

官方将这种方式称为 Spec-Driven Development，强调先定义“做什么、为什么”，再定义“怎么做”，并通过多阶段细化代替一次性代码生成。[SDD 概念说明](https://github.com/github/spec-kit/blob/v1.0.4/docs/concepts/sdd.md)、[Agentic SDD 命令参考](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/agentic-sdd.md)。

## 核心工作流程

当前 `v1.0.4` 的完整人工驱动流程是：

```text
constitution
  → specify
  → clarify
  → plan
  → checklist
  → tasks
  → analyze
  → implement
  → converge
```

各步骤的职责如下。[Agentic SDD 命令参考](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/agentic-sdd.md)。

| 步骤 | 作用 | 主要产物 |
| --- | --- | --- |
| `constitution` | 定义全项目必须遵循的工程原则和约束 | `.specify/memory/constitution.md` |
| `specify` | 将自然语言需求转成面向用户、与技术无关的功能规格 | `specs/<feature>/spec.md`、需求质量检查表 |
| `clarify` | 找出高影响歧义，向用户提问并把答案写回规格 | 更新后的 `spec.md` |
| `plan` | 确定技术栈、架构、数据模型、接口和验证方式 | `plan.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md` |
| `checklist` | 检查规格本身是否完整、清晰、一致，官方称其为“需求的单元测试” | 自定义检查表 |
| `tasks` | 将设计拆成按依赖排序、可追踪到用户故事的任务 | `tasks.md` |
| `analyze` | 只读检查 `spec.md`、`plan.md` 和 `tasks.md` 是否冲突或遗漏 | 会话内分析报告 |
| `implement` | 让 Agent 按任务依赖执行代码修改 | 代码、测试和任务状态 |
| `converge` | 将当前代码与规格、计划和任务重新比较，发现遗漏时只追加修复任务 | 更新后的 `tasks.md` 或 `Converged` 结果 |

### 规格阶段

`specify` 模板要求 Agent 生成按 P1、P2、P3 排序且可独立验收的用户故事、Given/When/Then 验收场景、边界情况、编号功能需求、关键实体和可测量成功标准。模板要求规格聚焦业务行为，不提前绑定语言、框架或 API。[规格模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/spec-template.md)、[`specify` 命令模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/commands/specify.md)。

### 计划阶段

`plan` 将实现信息与业务规格分开，要求 Agent明确语言、依赖、存储、测试、目标平台、性能、约束和代码目录，同时先后两次检查计划是否符合项目 Constitution。它还指导 Agent 生成研究结论、数据模型、接口契约和端到端验证说明。[计划模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/plan-template.md)、[`plan` 命令模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/commands/plan.md)。

### 任务与实现阶段

默认任务模板按照 Setup、Foundational、各个独立用户故事、Polish 组织任务，并用 `T001` 和 `US1` 等标识建立追踪关系；`[P]` 表示不同文件、无依赖、适合并行执行的工作。[任务模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/tasks-template.md)。

### 收敛阶段

`converge` 不直接修代码，而是检查需求、验收场景、计划决策和 Constitution 是否已在代码中实现。发现缺失、部分实现、冲突或未要求的工作时，它只在 `tasks.md` 末尾追加新的 Convergence 阶段；没有问题时保持文件不变并报告 `Converged`。这种设计把“发现遗漏”和“修改代码”分成两个职责清楚的步骤。[`converge` 命令模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/commands/converge.md)。

## 安装后实际做了什么

`specify-cli` 是 Python 3.11+ 的 Typer CLI。`specify init` 会把随 Python 包发布的模板、脚本、工作流和所选 Agent 的 Skill/命令安装到目标仓库；核心初始化资产已经打包进 wheel，因此初始化本身可以离线完成。[项目配置](https://github.com/github/spec-kit/blob/v1.0.4/pyproject.toml)、[`init` 命令实现](https://github.com/github/spec-kit/blob/v1.0.4/src/specify_cli/commands/init.py)。

一个项目通常会增加如下内容：

```text
.specify/
├── memory/
│   └── constitution.md
├── templates/
├── scripts/
├── workflows/
└── integrations/

specs/
└── 001-feature-name/
    ├── spec.md
    ├── plan.md
    ├── research.md
    ├── data-model.md
    ├── quickstart.md
    ├── contracts/
    ├── checklists/
    └── tasks.md
```

它还会根据 Agent 写入对应目录。例如 Codex 使用 `.agents/skills/speckit-<command>/SKILL.md`，Copilot 默认使用 `.github/skills/`，其他工具可能使用自己的命令或 Prompt 目录。[Codex 集成](https://github.com/github/spec-kit/blob/v1.0.4/src/specify_cli/integrations/codex/__init__.py)、[Copilot 集成](https://github.com/github/spec-kit/blob/v1.0.4/src/specify_cli/integrations/copilot/__init__.py)。

**关键判断：** 常规交互模式下，Spec Kit 主要通过向现有 Agent 安装经过设计的 Prompt/Skill 来驱动流程。CLI 负责脚手架、工件定位、模板解析和集成适配，但需求理解、设计判断、代码生成和收敛判断仍主要由所选模型完成。

## 不只是模板：它还包含什么

### 多 Agent 适配层

`v1.0.4` 源码中包含 30 多种 Agent 集成，适配不同的目录、文件格式、命令调用方式和非交互 CLI 参数。所谓“支持”有两层含义：

- 所有列出的集成都可以获得相应 Skill 或命令文件；
- 只有实现了非交互 CLI 调用且本机安装对应 CLI 的集成，才能被 Spec Kit Workflow 直接调度。

例如 Copilot 的 IDE Skill 安装不要求 Copilot CLI，但通过 Workflow 自动派发命令时仍需另行安装 CLI。[集成目录](https://github.com/github/spec-kit/tree/v1.0.4/src/specify_cli/integrations)、[集成基类](https://github.com/github/spec-kit/blob/v1.0.4/src/specify_cli/integrations/base.py)。

### Workflow 工作流引擎

Spec Kit 已经内置 YAML 工作流运行时，支持命令、任意 Prompt、Shell、人工 Gate、条件、Switch、循环、fan-out/fan-in、持久化状态和中断后恢复。运行记录保存在 `.specify/workflows/runs/<run_id>/`，包括状态、输入和 JSONL 日志。[Workflow 文档](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/workflows.md)、[Workflow 架构](https://github.com/github/spec-kit/blob/v1.0.4/workflows/ARCHITECTURE.md)。

内置 `speckit` 工作流目前实际只串联 `specify → 人工审规格 → plan → 人工审计划 → tasks → implement`。`clarify`、`checklist`、`analyze` 和 `converge` 属于可用命令，但尚未全部进入这个默认 YAML 工作流，因此“完整 SDD 流程”和“一键默认工作流”并不完全相同。[内置工作流定义](https://github.com/github/spec-kit/blob/v1.0.4/workflows/speckit/workflow.yml)。

Workflow 中的 fan-out 当前按架构文档仍是顺序派发，而不是通用的真实并行执行；不要仅因配置中出现 `max_concurrency` 就假设已经获得成熟的多 Agent 并行调度。[Workflow 架构的 Step Types](https://github.com/github/spec-kit/blob/v1.0.4/workflows/ARCHITECTURE.md)。

### Extensions

Extension 用于增加新的命令、模板、脚本和流程阶段，即扩展“能做什么”。官方包内置了：

- `bug`：`assess → fix → test` 缺陷处理；
- `assess`：`intake → research → define → shape → decide` 创意评估；
- `git`：Git 初始化、分支、提交等能力；
- `agent-context`：更新 Agent 上下文。

参考：[Extensions 文档](https://github.com/github/spec-kit/blob/v1.0.4/extensions/README.md)、[Agentic Bug Fix](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/agentic-bugfix.md)。

### Presets

Preset 用于替换或包装核心和 Extension 的模板与命令，即调整“怎么做”。它可以改变规格格式、术语、测试顺序、安全 Gate、合规字段或组织方法，而不必 Fork Spec Kit。解析优先级为项目本地覆盖、Preset、Extension、Core。[README 的 Extensions & Presets 说明](https://github.com/github/spec-kit/blob/v1.0.4/README.md#-making-spec-kit-your-own-extensions--presets)。

### Bundles

Bundle 把多个 Extension、Preset、Workflow 和步骤打包为一个带版本的角色方案，例如 Product Manager、Business Analyst、Security Researcher 或 Developer。它适合组织统一分发一套工作方式。[Bundle 参考](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/bundles.md)、[示例 Bundle](https://github.com/github/spec-kit/tree/v1.0.4/examples/bundles)。

## 规格是否是唯一事实来源

Spec Kit 没有强制一种规格维护模式，而是把选择留给团队：

| 模式 | 规则 | 适合场景 | 风险 |
| --- | --- | --- | --- |
| Flow-back | 规格、计划、任务和代码都可修改，之后人工对齐 | 快速迭代的小团队 | 工件悄然分叉 |
| Flow-forward | 已完成规格视为历史记录，变化时新建 Feature | 审计和变更追踪 | 信息重复或分散 |
| Living spec | 先修改 `spec.md`，再重新生成或调整下游工件 | 将规格作为长期合同 | 重生成时丢失实现理由 |

这些模式只是团队约定，不是 CLI 配置，Spec Kit 不会自动阻止工件漂移。[规格持久化模型](https://github.com/github/spec-kit/blob/v1.0.4/docs/concepts/spec-persistence.md)。

## 优点

### 1. 显著降低模糊需求直接进入实现的概率

`specify`、`clarify`、需求检查表和 `analyze` 将规格质量变成显式阶段。它不能保证需求正确，但能迫使 Agent 和用户在代码成本产生前暴露更多歧义。[`specify` 命令模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/commands/specify.md)、[Agentic SDD](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/agentic-sdd.md)。

### 2. 工件可进入 Git 审查

规格、计划、接口和任务均为普通文本文件，可以和代码一起提交、评论、比较和追踪，而不是只存在于某次 Agent 对话。

### 3. Agent 无关

流程没有绑定单一模型或 IDE。团队可以保留相同工件和方法，只替换 Agent 集成，降低开发方法对某个工具私有 Prompt 格式的依赖。[集成列表](https://github.com/github/spec-kit/tree/v1.0.4/src/specify_cli/integrations)。

### 4. 对新项目和较大功能尤其有帮助

新项目或跨多个模块的功能拥有更多需要显式决定的行为、架构和依赖。分阶段工件能提供稳定上下文，也便于在人类审查点停止错误方向。

### 5. 可定制性已经超过简单脚手架

Extension、Preset、Bundle、Workflow 和项目本地 Override 使组织可以建立自己的领域方法、合规规范和角色工具包，而无需持续手工复制 Prompt。[扩展与预设说明](https://github.com/github/spec-kit/blob/v1.0.4/README.md#-making-spec-kit-your-own-extensions--presets)、[Workflow 文档](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/workflows.md)。

## 局限与风险

### 1. 最终质量仍受模型能力影响

规格、设计、任务乃至 `converge` 的判断都主要由 Agent 完成。同一个模型可能先遗漏需求，再在自检时继续遗漏。Spec Kit 提高了检查结构，但没有提供业务正确性的确定性证明。

### 2. 容易产生较多文档

完整流程会为一个功能生成规格、研究、计划、数据模型、契约、验证指南、检查表和任务。对简单修复全部使用会造成流程成本。官方自己也说明小修复不必经过完整 SDD 流程。[项目 Dogfooding 说明](https://github.com/github/spec-kit/blob/v1.0.4/README.md#-does-spec-kit-use-spec-kit)。

### 3. 默认模板不适用于所有工程规范

默认 `tasks-template.md` 明确写着只有规格显式要求时才生成测试，而很多生产项目要求新功能和缺陷修复必须有测试。团队需要通过 Constitution、Preset 或 Override 收紧默认行为。[任务模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/tasks-template.md)。

### 4. 规格可能漂移

Spec Kit 描述了多种持久化模式，但不强制哪份工件是事实来源。团队如果不定义维护规则，`spec.md`、`plan.md`、`tasks.md` 和代码仍会产生分歧。[规格持久化模型](https://github.com/github/spec-kit/blob/v1.0.4/docs/concepts/spec-persistence.md)。

### 5. 初始化和第三方组件需要审查

对现有仓库执行 `specify init --here --force` 可能替换冲突的受管路径，官方建议先提交或暂存现有工作并审查初始化 Diff。[现有项目接入指南](https://github.com/github/spec-kit/blob/v1.0.4/docs/guides/existing-projects.md)。

社区 Extension、Preset、Bundle 和 Workflow 可能包含脚本或 Shell 步骤。社区目录默认主要用于发现，外部 URL 安装也有信任确认，但安装和运行前仍需代码审查。[`init` 的外部扩展信任逻辑](https://github.com/github/spec-kit/blob/v1.0.4/src/specify_cli/commands/init.py)、[Workflow Shell 安全说明](https://github.com/github/spec-kit/blob/v1.0.4/workflows/README.md)。

### 6. Workflow 的 Shell 插值存在明确风险

官方文档说明 Workflow 的 `run` 字段由系统 Shell 执行，插入的输入或 Agent 输出不会自动转义；不可信值必须通过枚举或白名单限制，不能把引号当作安全边界。[Workflow Shell 安全说明](https://github.com/github/spec-kit/blob/v1.0.4/workflows/README.md)。

## 适合什么场景

**较适合：**

- 从零开始、需求尚未结构化的新项目；
- 跨多个模块、需要架构设计的中大型功能；
- 团队希望不同 Agent 使用同一开发方法；
- 需要把需求、设计、任务和代码放入 Git 追踪；
- 合规、审计或跨角色协作要求较强的项目；
- 希望把组织规范制作成可复用 Prompt/Skill/Workflow 的平台团队。

**不宜完整套用：**

- 一两行即可修复且已有明确回归测试的小缺陷；
- 纯格式、重命名或机械迁移；
- 需求持续高速变化且团队不会维护规格；
- 没有自动化测试、静态检查和代码审查的仓库；
- 团队期待工具在没有人工业务判断时自动产出可靠规格。

## 与 Coding-Harness 的关系

### 高度一致的部分

Coding-Harness 已经具备以下类似思想：

- 根级 [`AGENTS.md`](/Users/yuanzhi.liu/Desktop/code/Coding-Harness/AGENTS.md) 定义长期工程原则；
- [`quality-first-coding`](/Users/yuanzhi.liu/Desktop/code/Coding-Harness/.agents/skills/quality-first-coding/SKILL.md) Skill 要求先写 Gherkin 和行为测试，再实现；
- [`tests/features/`](/Users/yuanzhi.liu/Desktop/code/Coding-Harness/tests/features) 保存用户可观察行为；
- [`docs/pm/tasks/task.md`](/Users/yuanzhi.liu/Desktop/code/Coding-Harness/docs/pm/tasks/task.md) 已有带依赖和验收口径的产品任务；
- [`coding-harness-design.md`](/Users/yuanzhi.liu/Desktop/code/Coding-Harness/docs/pm/architecture/coding-harness-design.md) 已定义产品架构、迭代和验收标准。

这意味着 Coding-Harness 已经处在“规格和工程约束进入仓库”的方向，并非必须依赖 Spec Kit 才能开始规格驱动开发。

### 需要解决的冲突

| Spec Kit 默认行为 | Coding-Harness 规则 | 接入处理 |
| --- | --- | --- |
| 测试只在规格显式要求时生成 | 新功能和缺陷修复必须先补测试 | 自定义 Preset，强制测试任务及红绿验证 |
| 默认模板采用通用目录示例 | 本仓库有明确 Controller、Service、Repository、Domain 分层 | 在 Constitution 和 Plan Override 中写入真实目录与调用方向 |
| 默认文档为英文 | 本仓库要求中文文档字符串，项目文档主要为中文 | 使用中文 Preset 或项目 Override |
| Spec Kit 会生成独立 `specs/` 工件 | 本仓库已有 `docs/pm` 和 `tests/features` | 明确两者关系，避免需求和任务出现两个事实来源 |
| 完整 SDD 流程可能自动修改大量工件 | 当前工作区已有未提交改动 | 只能在独立分支、worktree 或临时副本中试点并审查 Diff |

### 对本项目的建议

**建议：先把 Spec Kit 当作可参考和可试点的“需求到任务前端”，不要直接替换 Coding-Harness 的现有工程规则和任务系统。**

推荐试点方式：

1. 选择一个边界明确、尚未实现的中等功能，而不是整个产品路线图。
2. 在干净分支或独立 worktree 中运行 `specify init --here --force --integration codex`。
3. 将现有 `AGENTS.md` 的关键强制规则整理进 Constitution，但保持 `AGENTS.md` 为 Agent 的仓库级最终约束。
4. 制作项目 Preset，强制中文规格、Gherkin、测试先行、现有分层和既定验证命令。
5. 决定 `specs/` 与 `docs/pm/tasks/`、`tests/features/` 的唯一映射关系，避免并行维护两套需求。
6. 完成一次 `specify → clarify → plan → tasks → analyze` 后先停止，评审生成质量，再决定是否允许 `implement`。
7. 用返工次数、遗漏需求数、生成工件维护成本和最终测试通过情况评价试点，而不是只看 Agent 生成速度。

**项目判断：** 如果目标是让 Coding-Harness 自己提供规格驱动能力，更值得复用的是 Spec Kit 的工件模型、阶段边界、收敛循环和扩展分层思想；不一定需要把 `specify-cli` 作为 Coding-Harness 的运行时依赖。Coding-Harness 更关注受控工具、审批、恢复、ChangeSet、Verification 和多 Provider 执行，而 Spec Kit 更关注需求到实现的流程结构，两者可以互补。

## 最小体验方式

以下是官方当前推荐安装方式。使用前应将 `v1.0.4` 替换为经过团队验证的固定版本，不建议在生产流程中直接跟随未固定的主分支。[安装说明](https://github.com/github/spec-kit/blob/v1.0.4/README.md#-get-started)。

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v1.0.4
specify init demo-project --integration codex
cd demo-project
```

在 Codex 中依次执行：

```text
$speckit-constitution
$speckit-specify
$speckit-clarify
$speckit-plan
$speckit-tasks
$speckit-analyze
$speckit-implement
$speckit-converge
```

建议第一次只做一个小型示例项目，以便观察它创建的工件和 Agent 行为，不要直接在当前有未提交修改的 Coding-Harness 工作区初始化。

## 项目成熟度判断

- `specify-cli` 当前版本为 `1.0.4`，发布于 2026-09-02，要求 Python 3.11+，使用 MIT License。[v1.0.4 Release](https://github.com/github/spec-kit/releases/tag/v1.0.4)、[pyproject.toml](https://github.com/github/spec-kit/blob/v1.0.4/pyproject.toml)、[LICENSE](https://github.com/github/spec-kit/blob/v1.0.4/LICENSE)。
- 项目已经包含 CLI 单元测试、契约测试、集成测试、各 Agent 适配测试、安全路径测试和 Workflow 测试，工程范围已明显超过早期 Prompt 模板实验。[测试目录](https://github.com/github/spec-kit/tree/v1.0.4/tests)。
- 从 Changelog 看，项目仍以很高频率增加集成、扩展和安全修复；`1.0` 表示项目形成了完整形态，但不代表接口和流程已经停止演化。[CHANGELOG](https://github.com/github/spec-kit/blob/v1.0.4/CHANGELOG.md)、[README 的 1.0 说明](https://github.com/github/spec-kit/blob/v1.0.4/README.md)。

综合判断：**可以用于试验和团队内部项目，也具备较好的可扩展基础；但在组织级采用前仍应固定版本、审查第三方组件、定制模板，并建立规格维护与回归验证规则。**

## 资料来源

访问日期均为 2026-09-04。

### 项目与版本

- [GitHub Spec Kit 仓库](https://github.com/github/spec-kit)
- [Spec Kit v1.0.4](https://github.com/github/spec-kit/releases/tag/v1.0.4)
- [README](https://github.com/github/spec-kit/blob/v1.0.4/README.md)
- [CHANGELOG](https://github.com/github/spec-kit/blob/v1.0.4/CHANGELOG.md)
- [pyproject.toml](https://github.com/github/spec-kit/blob/v1.0.4/pyproject.toml)
- [MIT License](https://github.com/github/spec-kit/blob/v1.0.4/LICENSE)

### 方法和工件

- [SDD 概念](https://github.com/github/spec-kit/blob/v1.0.4/docs/concepts/sdd.md)
- [Agentic SDD](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/agentic-sdd.md)
- [规格模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/spec-template.md)
- [计划模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/plan-template.md)
- [任务模板](https://github.com/github/spec-kit/blob/v1.0.4/templates/tasks-template.md)
- [规格持久化模型](https://github.com/github/spec-kit/blob/v1.0.4/docs/concepts/spec-persistence.md)
- [现有项目接入指南](https://github.com/github/spec-kit/blob/v1.0.4/docs/guides/existing-projects.md)

### 实现与扩展

- [`specify init` 实现](https://github.com/github/spec-kit/blob/v1.0.4/src/specify_cli/commands/init.py)
- [Agent 集成源码](https://github.com/github/spec-kit/tree/v1.0.4/src/specify_cli/integrations)
- [Workflow 文档](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/workflows.md)
- [内置 SDD Workflow](https://github.com/github/spec-kit/blob/v1.0.4/workflows/speckit/workflow.yml)
- [Extensions](https://github.com/github/spec-kit/blob/v1.0.4/extensions/README.md)
- [Presets](https://github.com/github/spec-kit/blob/v1.0.4/presets/README.md)
- [Bundles](https://github.com/github/spec-kit/blob/v1.0.4/docs/reference/bundles.md)

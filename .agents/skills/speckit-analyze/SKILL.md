---
name: speckit-analyze
description: 任务生成后，对 spec.md、plan.md 和 tasks.md 进行非破坏性的跨产物一致性与质量分析。
compatibility: 需要包含 .specify/ 目录的 spec-kit 项目结构
metadata:
  author: github-spec-kit
  source: preset:coding-harness
---

# Speckit Analyze Skill

## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 执行前检查

**检查 Extension Hook（分析前）**：
- 检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果存在，读取该文件并查找 `hooks.before_analyze` 键下的条目。
- 如果 YAML 无法解析或无效，静默跳过 Hook 检查并正常继续。
- 过滤掉 `enabled` 被明确设为 `false` 的 Hook。没有 `enabled` 字段的 Hook 默认视为启用。
- 对每个剩余 Hook，**不要**尝试解释或求值其 `condition` 表达式：
  - 如果 Hook 没有 `condition` 字段，或该字段为 null/空，则视为可执行。
  - 如果 Hook 定义了非空 `condition`，跳过该 Hook，将条件求值留给 HookExecutor 实现。
- 根据 Hook 命令名构造调用命令时，将点号（`.`）替换为连字符（`-`）。例如：
  `speckit.git.commit` → `$speckit-git-commit`。
- 对每个可执行 Hook，根据其 `optional` 标志输出以下内容：
  - **可选 Hook**（`optional: true`）：
    ```
    ## Extension Hooks

    **Optional Pre-Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **强制 Hook**（`optional: false`）：
    ```
    ## Extension Hooks

    **Automatic Pre-Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}

    Wait for the result of the hook command before proceeding to the Goal.
    ```
    输出上述代码块后，必须实际调用 Hook 并等待其完成，再继续执行。调用方式与在当前
    Agent/Session 中自行运行该命令相同。仅输出代码块并不会运行 Hook。
- 如果没有注册 Hook，或 `.specify/extensions.yml` 不存在，则静默跳过。

## 目标

实现前，识别三个核心产物（`spec.md`、`plan.md`、`tasks.md`）之间的不一致、重复、歧义和
规格不足项。此命令只能在 `$speckit-tasks` 成功生成完整的 `tasks.md` 后运行。

## 操作约束

**严格只读**：不得修改任何文件。输出结构化分析报告，并可提供可选修复方案；调用任何后续
编辑命令前，必须获得用户明确批准。

**章程权威性**：在本分析范围内，项目章程（`.specify/memory/constitution.md`）**不可协商**。
与章程冲突的问题自动归为 CRITICAL，必须调整 Spec、Plan 或 Tasks，不得弱化、重新解释或
静默忽略原则。如果原则本身需要修改，必须在 `$speckit-analyze` 之外单独、明确地更新章程。

## 执行步骤

### 1. 初始化分析上下文

从仓库根目录运行一次
`.specify/scripts/bash/check-prerequisites.sh --json --require-spec --require-tasks --include-tasks`，
并从 JSON 中解析 FEATURE_DIR 和 AVAILABLE_DOCS。推导以下绝对路径：

- SPEC = FEATURE_DIR/spec.md
- PLAN = FEATURE_DIR/plan.md
- TASKS = FEATURE_DIR/tasks.md

如果缺少任何必需文件，应中止并报告错误，同时提示用户运行缺失的前置命令。参数中包含
单引号时（例如 "I'm Groot"），使用转义语法，如 `'I'\''m Groot'`；也可在条件允许时使用双引号。

### 2. 加载产物（渐进式披露）

仅从每个产物加载最低限度的必要上下文：

**从 spec.md：**

- 概述/上下文
- 功能需求
- 成功标准（可衡量结果，例如性能、安全性、可用性、用户成功和业务影响）
- User Story
- Edge Case（如果存在）

**从 plan.md：**

- 架构/技术栈选择
- Data Model 引用
- 阶段
- 技术约束

**从 tasks.md：**

- Task ID
- 描述
- 阶段分组
- 并行标记 `[P]`
- 引用的文件路径

**从章程：**

- 加载 `.specify/memory/constitution.md` 以验证原则

### 3. 构建语义 Model

创建内部表示，不要在输出中包含原始产物：

- **需求清单**：为每个功能需求（FR-###）和成功标准（SC-###）记录稳定 Key。存在明确
  FR-/SC- 标识符时，将其作为 Primary Key；也可推导祈使短语 Slug 以提升可读性，例如
  “用户可以上传文件”→ `user-can-upload-file`。仅包含需要构建工作的成功标准，例如
  压测基础设施和安全审计 Tool；排除上线后的结果指标和业务 KPI，例如“客服工单减少 50%”。
- **User Story/操作清单**：具有验收标准的离散用户操作。
- **任务覆盖映射**：将每个任务映射到一个或多个需求或 Story，可依据关键词、ID 或关键短语等
  明确引用 Pattern 推断。
- **章程规则集**：提取原则名称和 MUST/SHOULD 规范性陈述。

### 4. 检测轮次（节省 Token）

聚焦高价值发现。发现总数最多 50 条，其余内容在溢出摘要中汇总。

#### A. 重复检测

- 识别近似重复的需求。
- 标记质量较低、应合并的表述。

#### B. 歧义检测

- 标记缺少可衡量标准的模糊形容词，如“快速”“可扩展”“安全”“直观”“健壮”。
- 标记未解决的占位符，如 TODO、TKTK、`???`、`<placeholder>` 等。

#### C. 规格不足

- 含动词但缺少对象或可衡量结果的需求。
- 缺少对应验收标准的 User Story。
- 引用了 Spec/Plan 中未定义文件或 Component 的任务。

#### D. 章程一致性

- 与 MUST 原则冲突的任何需求或 Plan 元素。
- 缺失章程要求的章节或质量 Gate。

#### E. 覆盖缺口

- 没有任何关联任务的需求。
- 未映射到需求或 Story 的任务。
- 需要实际构建工作（性能、安全性、可用性）但未反映在任务中的成功标准。

#### F. 不一致

- 术语漂移，即同一概念在不同文件中名称不同。
- Plan 引用了 Spec 中不存在的 Data Entity，或反之。
- 任务顺序矛盾，例如 Integration 任务位于基础 Setup 任务之前且无依赖说明。
- 相互冲突的需求，例如一处要求 Next.js，另一处指定 Vue。

### 5. 严重级别

使用以下启发式规则确定发现优先级：

- **CRITICAL**：违反章程 MUST、缺少核心 Spec 产物，或零覆盖需求阻塞基础功能。
- **HIGH**：需求重复或冲突、安全/性能属性含糊、验收标准不可测试。
- **MEDIUM**：术语漂移、缺少非功能任务覆盖、Edge Case 规格不足。
- **LOW**：风格/措辞改进，或不影响执行顺序的轻微冗余。

### 6. 生成精简分析报告

按以下结构输出 Markdown 报告，不写入文件：

## 规格分析报告

| ID | 类别 | 严重级别 | 位置 | 摘要 | 建议 |
|----|------|----------|------|------|------|
| A1 | 重复 | HIGH | spec.md:L120-134 | 两项需求相似…… | 合并表述，保留更清晰的版本 |

每条发现增加一行；生成以类别首字母为前缀的稳定 ID。

**覆盖摘要表：**

| 需求 Key | 是否有任务？ | Task ID | 备注 |
|----------|--------------|---------|------|

**章程一致性问题：**（如果有）

**未映射任务：**（如果有）

**指标：**

- 需求总数
- 任务总数
- 覆盖率（至少有一个任务的需求占比）
- 歧义数量
- 重复数量
- CRITICAL 问题数量

### 7. 提供后续操作

在报告末尾输出精简的“后续操作”块：

- 如果存在 CRITICAL 问题：建议在 `$speckit-implement` 前解决。
- 如果只有 LOW/MEDIUM 问题：用户可以继续，但应提供改进建议。
- 给出明确命令建议，例如“运行 `$speckit-specify` 完善需求”“运行 `$speckit-plan` 调整架构”
  “手动编辑 `tasks.md`，增加对 `performance-metrics` 的覆盖”。

### 8. 提供修复建议

询问用户：“是否需要我为优先级最高的 N 个问题建议具体修复改动？”不得自动应用。

### 9. 检查 Extension Hook

报告后，检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果存在，读取该文件并查找 `hooks.after_analyze` 键下的条目。
- 如果 YAML 无法解析或无效，静默跳过 Hook 检查并正常继续。
- 过滤掉 `enabled` 被明确设为 `false` 的 Hook。没有 `enabled` 字段的 Hook 默认视为启用。
- 对每个剩余 Hook，**不要**尝试解释或求值其 `condition` 表达式：
  - 如果 Hook 没有 `condition` 字段，或该字段为 null/空，则视为可执行。
  - 如果 Hook 定义了非空 `condition`，跳过该 Hook，将条件求值留给 HookExecutor 实现。
- 根据 Hook 命令名构造调用命令时，将点号（`.`）替换为连字符（`-`）。
- 对每个可执行 Hook，根据其 `optional` 标志输出以下内容：
  - **可选 Hook**（`optional: true`）：
    ```
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **强制 Hook**（`optional: false`）：
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
    输出上述代码块后，必须实际调用 Hook 并等待其完成，再继续执行。仅输出代码块不会运行 Hook。
- 如果没有注册 Hook，或 `.specify/extensions.yml` 不存在，则静默跳过。

## 操作原则

### 上下文效率

- **最少的高价值 Token**：聚焦可执行发现，而非穷举文档。
- **渐进式披露**：逐步加载产物，不要将全部内容倾倒到分析中。
- **节省 Token 的输出**：发现表最多 50 行，超出部分汇总。
- **确定性结果**：内容未变化时，重新运行应产生一致的 ID 和数量。

### 分析指南

- **绝不修改文件**，这是只读分析。
- **绝不臆造缺失章节**，缺失时应准确报告。
- **优先处理章程违规**，此类问题始终为 CRITICAL。
- **使用实例而非穷举规则**，引用具体情况而非通用 Pattern。
- **妥善报告零问题结果**，输出包含覆盖统计的成功报告。

## 上下文

$ARGUMENTS


## Coding-Harness 分析补充规则

除核心产物分析外，以下情况应报告为阻塞性发现：

- 与适用的 `AGENTS.md` 规则或项目章程冲突。
- 变更行为缺少 Gherkin 或可执行测试。
- Controller 到 Repository、Tool 到 DB、Domain 到 Framework，或其他反向分层依赖。
- Frontend、API、Service、持久化和 CLI 之间的业务术语不一致。
- 缺少失败、权限、幂等性、兼容性或敏感数据行为定义。
- 未获得用户明确授权却修改 README 的任务。

只要仍有阻塞性发现未解决，就不得建议进入实现。

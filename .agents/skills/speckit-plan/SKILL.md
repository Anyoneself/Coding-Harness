---
name: speckit-plan
description: 使用 Plan Template 执行实现规划工作流并生成设计产物。
compatibility: 需要包含 .specify/ 目录的 spec-kit 项目结构
metadata:
  author: github-spec-kit
  source: preset:coding-harness
---

# Speckit Plan Skill

## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 执行前检查

**检查 Extension Hook（规划前）**：
- 检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果存在，读取该文件并查找 `hooks.before_plan` 键下的条目。
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

    Wait for the result of the hook command before proceeding to the Outline.
    ```
    输出上述代码块后，必须实际调用 Hook 并等待其完成，再继续执行。调用方式与在当前
    Agent/Session 中自行运行该命令相同。仅输出代码块并不会运行 Hook。
- 如果没有注册 Hook，或 `.specify/extensions.yml` 不存在，则静默跳过。

## 执行流程

1. **设置**：从仓库根目录运行 `.specify/scripts/bash/setup-plan.sh --json`，并从 JSON
   中解析 FEATURE_SPEC、IMPL_PLAN、SPECS_DIR 和 BRANCH。参数中包含单引号时（例如
   "I'm Groot"），使用转义语法，如 `'I'\''m Groot'`；也可在条件允许时使用双引号。

2. **加载上下文**：读取 FEATURE_SPEC 和 `.specify/memory/constitution.md`，并加载已复制的
   IMPL_PLAN Template。

3. **执行 Plan 工作流**：遵循 IMPL_PLAN Template 的结构：
   - 填写 Technical Context（未知项标记为 `NEEDS CLARIFICATION`）。
   - 根据章程填写 Constitution Check 章节。
   - 评估 Gate（存在未得到合理解释的违规时记为 ERROR）。
   - Phase 0：生成 `research.md`，解决所有 `NEEDS CLARIFICATION`。
   - Phase 1：生成 `data-model.md`、`contracts/` 和 `quickstart.md`。
   - 设计完成后重新评估 Constitution Check。

## 强制执行后 Hook

**向用户报告完成前，必须完成本章节。**

检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果不存在，或 `hooks.after_plan` 下没有注册 Hook，直接进入完成报告。
- 如果存在，读取该文件并查找 `hooks.after_plan` 键下的条目。
- 如果 YAML 无法解析或无效，静默跳过 Hook 检查并进入完成报告。
- 过滤掉 `enabled` 被明确设为 `false` 的 Hook。没有 `enabled` 字段的 Hook 默认视为启用。
- 对每个剩余 Hook，**不要**尝试解释或求值其 `condition` 表达式：
  - 如果 Hook 没有 `condition` 字段，或该字段为 null/空，则视为可执行。
  - 如果 Hook 定义了非空 `condition`，跳过该 Hook，将条件求值留给 HookExecutor 实现。
- 根据 Hook 命令名构造调用命令时，将点号（`.`）替换为连字符（`-`）。例如：
  `speckit.git.commit` → `$speckit-git-commit`。
- 对每个可执行 Hook，根据其 `optional` 标志输出以下内容：
  - **强制 Hook**（`optional: false`）- **每个强制 Hook 都必须输出 `EXECUTE_COMMAND:`**：
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
    输出上述代码块后，必须实际调用 Hook 并等待其完成，再继续执行。调用方式与在当前
    Agent/Session 中自行运行该命令相同。仅输出代码块并不会运行 Hook。
  - **可选 Hook**（`optional: true`）：
    ```
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```

## 完成报告

命令在 Phase 1 设计完成后结束。报告 Branch、IMPL_PLAN 路径和生成的产物。

## 阶段

### Phase 0：梳理与调研

1. **从上述 Technical Context 提取未知项**：
   - 每个 `NEEDS CLARIFICATION` → 调研任务
   - 每个依赖 → 最佳实践任务
   - 每个集成 → Pattern 调研任务

2. **生成并派发调研 Agent**：

   ```text
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **汇总调研结果**，按以下格式写入 `research.md`：
   - 决策：[选择了什么]
   - 理由：[为什么选择]
   - 考虑过的替代方案：[还评估了什么]

**输出**：解决所有 `NEEDS CLARIFICATION` 的 `research.md`

### Phase 1：设计与 Contract

**前置条件：** `research.md` 已完成

1. **从功能 Spec 提取 Entity** → `data-model.md`：
   - Entity 名称、字段和关系
   - 来自需求的验证规则
   - 适用时包含状态转换

2. **定义接口 Contract**（项目存在外部接口时）→ `/contracts/`：
   - 识别项目向用户或其他系统暴露的接口。
   - 使用适合项目类型的格式记录 Contract。
   - 示例：Library 的公共 API、CLI Tool 的命令 Schema、Web Service 的 Endpoint、
     Parser 的 Grammar、应用的 UI Contract。
   - 如果项目完全供内部使用（构建脚本、一次性 Tool 等），则跳过。

3. **创建 Quickstart 验证指南** → `quickstart.md`：
   - 记录可运行、可证明功能端到端有效的验证场景。
   - 包含前置条件、设置命令、测试/运行命令和预期结果。
   - 通过链接或引用指向 Contract 和 Data Model 细节，不要重复内容。
   - 不要包含完整实现代码、Model/Service/Controller 主体、Migration 或完整测试套件。
   - 此产物仅作为验证/运行指南；实现细节应放在 `tasks.md` 和实现阶段中。

**输出**：`data-model.md`、`/contracts/*`、`quickstart.md`

## 关键规则

- 文件系统操作使用绝对路径；文档内引用使用项目相对路径。
- Gate 失败或仍有未解决的澄清项时，报 ERROR。

## 完成条件

- [ ] 已执行 Plan 工作流并生成设计产物
- [ ] 已按上述“强制执行后 Hook”规则派发或跳过 Extension Hook
- [ ] 已向用户报告 Branch、Plan 路径和生成的产物


## Coding-Harness 规划规则

- 将 `AGENTS.md` 和 `.specify/memory/constitution.md` 作为强制规划 Gate。
- 检查真实仓库结构，并复用其中的 Controller、Service、Domain、Repository、DB、CLI、
  Agent、Tool 和 Infrastructure 边界。
- 完成的 Plan 中不得保留通用示例目录。
- 生成实现任务前，定义 Gherkin 场景、可执行测试层、失败路径、静态检查和端到端验证命令。
- 识别 Frontend、HTTP API、Service DTO、持久化、CLI、示例和架构文档中所有受影响的
  Contract。
- 新依赖和新抽象必须有当前、具体的需求，并给出明确理由。

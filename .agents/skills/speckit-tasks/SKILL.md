---
name: speckit-tasks
description: 根据现有设计产物，为功能生成可执行、按依赖排序的 tasks.md。
compatibility: 需要包含 .specify/ 目录的 spec-kit 项目结构
metadata:
  author: github-spec-kit
  source: preset:coding-harness
---

# Speckit Tasks Skill

## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 执行前检查

检查 `.specify/extensions.yml` 中的 `hooks.before_tasks`：

- YAML 无效时静默跳过；过滤 `enabled: false`。
- 没有 `condition` 或其值为 null/空时视为可执行；`condition` 非空时跳过，并将求值留给
  HookExecutor。
- 命令名中的点号替换为连字符，例如 `speckit.git.commit` → `$speckit-git-commit`。
- 可选 Hook 输出：

  ```text
  ## Extension Hooks

  **Optional Pre-Hook**: {extension}
  Command: `/{command}`
  Description: {description}

  Prompt: {prompt}
  To execute: `/{command}`
  ```

- 强制 Hook 输出：

  ```text
  ## Extension Hooks

  **Automatic Pre-Hook**: {extension}
  Executing: `/{command}`
  EXECUTE_COMMAND: {command}

  Wait for the result of the hook command before proceeding to the Outline.
  ```

  输出后必须实际调用 Hook，并等待完成再继续；仅输出代码块不会运行 Hook。
- 没有注册 Hook 或配置文件不存在时，静默跳过。

## 执行流程

1. **设置**：从仓库根目录运行 `.specify/scripts/bash/setup-tasks.sh --json`，解析
   FEATURE_DIR、TASKS_TEMPLATE_CONTENT、TASKS_TEMPLATE 和 AVAILABLE_DOCS。提供时，
   FEATURE_DIR 和 TASKS_TEMPLATE 必须是绝对路径；AVAILABLE_DOCS 是 FEATURE_DIR 下可用的
   文档名或相对路径列表，例如 `research.md`、`contracts/`。参数中包含单引号时（例如
   "I'm Groot"），使用 `'I'\''m Groot'`，也可在条件允许时使用双引号。

2. **加载设计文档**：
   - 必需：`plan.md`（技术栈、Library、结构）和 `spec.md`（带优先级的 User Story）。
   - 可选：`data-model.md`（Entity）、`contracts/`（接口 Contract）、`research.md`（决策）、
     `quickstart.md`（测试场景）。
   - 如果存在，读取 `.specify/memory/constitution.md` 中的项目原则和治理约束。
   - 并非所有项目都有全部文档，应根据实际可用内容生成任务。

3. **生成任务**：
   - 从 `plan.md` 提取技术栈、Library 和项目结构。
   - 从 `spec.md` 提取 User Story 及优先级（P1、P2、P3……）。
   - 将 Data Model Entity、接口 Contract 和调研决策映射到相应 User Story 或 Setup 任务。
   - 按 User Story 组织任务，生成 Story 完成顺序的依赖图和并行执行示例。
   - 验证每个 User Story 的任务完整，并可独立测试。

4. **生成 `tasks.md`**：使用 JSON 中的 TASKS_TEMPLATE_CONTENT 作为结构；旧版脚本未返回该
   字段时读取 TASKS_TEMPLATE。填写：
   - 来自 `plan.md` 的正确功能名称。
   - Phase 1：Setup。
   - Phase 2：所有 User Story 的阻塞性 Foundational 任务。
   - Phase 3+：按 Spec 优先级排列，每个 User Story 一个阶段。
   - 每个 Story 阶段包含目标、独立测试标准、测试任务和实现任务。
   - 最后阶段：Polish 和 Cross-Cutting Concern。
   - 精确文件路径、依赖章节、各 Story 的并行示例，以及 MVP 优先的增量交付策略。
   - 所有任务严格遵循下述 Checklist 格式。

## 强制执行后 Hook

向用户报告完成前，必须处理 `hooks.after_tasks`：

- 配置不存在、没有注册 Hook 或 YAML 无效时，进入完成报告。
- 过滤 `enabled: false`，按执行前检查规则处理 `condition` 和命令名。
- 每个强制 Hook 都必须输出 `EXECUTE_COMMAND:`，随后实际调用并等待完成：

  ```text
  ## Extension Hooks

  **Automatic Hook**: {extension}
  Executing: `/{command}`
  EXECUTE_COMMAND: {command}
  ```

- 可选 Hook 输出：

  ```text
  ## Extension Hooks

  **Optional Hook**: {extension}
  Command: `/{command}`
  Description: {description}

  Prompt: {prompt}
  To execute: `/{command}`
  ```

## 完成报告

输出生成的 `tasks.md` 路径及以下摘要：

- 任务总数和每个 User Story 的任务数。
- 识别出的并行机会。
- 每个 Story 的独立测试标准。
- 建议的 MVP 范围，通常仅包含 User Story 1。
- 格式验证结果：确认全部任务都有 Checkbox、ID、Label 和文件路径。

任务生成上下文：$ARGUMENTS

`tasks.md` 必须可立即执行；每个任务都要具体到 LLM 无需额外上下文即可完成。

## 任务生成规则

**关键要求**：任务必须按 User Story 组织，以支持独立实现和测试。

Core Spec Kit 中“测试可选”的规则不适用于本仓库，详见末尾强制规则。

### Checklist 格式（必需）

每个任务必须严格遵循：

```text
- [ ] [TaskID] [P?] [Story?] Description with file path
```

组成部分：

1. **Checkbox**：始终以 `- [ ]` 开头。
2. **Task ID**：按执行顺序连续编号，如 T001、T002、T003。
3. **`[P]` 标记**：仅在任务修改不同文件且不依赖未完成任务、确实可并行时使用。
4. **`[Story]` Label**：仅 User Story 阶段任务必需。
   - 使用 `[US1]`、`[US2]`、`[US3]` 等，对应 `spec.md` 中的 Story。
   - Setup、Foundational 和 Polish 阶段不使用 Story Label。
5. **描述**：明确动作并包含精确文件路径。

示例：

- 正确：`- [ ] T001 Create project structure per implementation plan`
- 正确：`- [ ] T005 [P] Implement authentication middleware in src/middleware/auth.py`
- 正确：`- [ ] T012 [P] [US1] Create User model in src/models/user.py`
- 正确：`- [ ] T014 [US1] Implement UserService in src/services/user_service.py`
- 错误：`- [ ] Create User model`，缺少 ID 和 Story Label。
- 错误：`T001 [US1] Create model`，缺少 Checkbox。
- 错误：`- [ ] [US1] Create User model`，缺少 Task ID。
- 错误：`- [ ] T001 [US1] Create model`，缺少文件路径。

### 任务组织

1. **User Story 是主要组织方式**：
   - 每个 P1、P2、P3 Story 有独立阶段。
   - 将所需 Model、Service、接口/UI 和测试映射到该 Story。
   - 标明 Story 依赖；大多数 Story 应能独立完成。

2. **Contract**：
   - 将每个接口 Contract 映射到所服务的 Story。
   - 对每个接口 Contract，在实现前创建可并行的 Contract Test 任务。

3. **Data Model**：
   - 将每个 Entity 映射到需要它的 Story。
   - 多个 Story 共用的 Entity 放入最早使用它的 Story 或 Foundational 阶段。
   - Entity 关系对应适当 Story 阶段中的 Service Layer 任务。

4. **Setup/Infrastructure**：
   - 共享 Infrastructure 放在 Setup。
   - 阻塞全部 Story 的任务放在 Foundational。
   - Story 专用设置放在该 Story 阶段。

### 阶段结构

- **Phase 1**：Setup。
- **Phase 2**：Foundational，所有 Story 开始前必须完成。
- **Phase 3+**：按优先级排列的 User Story。
  - Story 内顺序：Tests → Models → Services → Endpoints → Integration。
  - 每个阶段必须形成完整、可独立测试的增量。
- **最终阶段**：Polish 和 Cross-Cutting Concern。

## Coding-Harness 强制任务规则

- 每个变更的业务行为必须先在 `tests/features/` 下有 Gherkin 任务。
- 每个 Gherkin 场景必须映射到可执行的 Unit、Integration 或 End-to-End 测试任务。
- 测试任务位于生产实现任务之前，并要求新测试先因目标行为尚未实现而按预期失败。
- 每个 User Story 都包含成功、相关边界和明确失败路径测试。
- 使用精确仓库路径，遵守 Controller、Service、Domain、Repository、DB、CLI、Agent、Tool、
  Infrastructure 和 Frontend 的归属边界。
- 添加最终任务，运行受影响测试、`python -m unittest discover -s tests -v`、
  `ruff check .`、适用的 Frontend 检查、文档同步和 `$speckit-converge`。
- 除非用户明确要求发布或修改 README，否则不得添加 README 任务。

## 完成条件

- [ ] `tasks.md` 已生成，包含全部阶段、Task ID 和文件路径
- [ ] 已按规则派发或跳过 Extension Hook
- [ ] 已向用户报告任务数、Story 拆分和 MVP 范围

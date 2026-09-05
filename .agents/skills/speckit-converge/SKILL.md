---
name: speckit-converge
description: 对照功能 Spec、Plan 和 Tasks 评估当前代码库，并将尚未完成的工作追加为 tasks.md 中的新任务，供后续实现。
compatibility: 需要包含 .specify/ 目录的 spec-kit 项目结构
metadata:
  author: github-spec-kit
  source: preset:coding-harness
---

# Speckit Converge Skill

## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 执行前检查

**检查 Extension Hook（收敛前）**：

- 检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果存在，读取该文件并查找 `hooks.before_converge` 键下的条目。
- 如果 YAML 无法解析或无效，静默跳过 Hook 检查并正常继续。
- 过滤掉 `enabled` 被明确设为 `false` 的 Hook；没有 `enabled` 字段的 Hook 默认启用。
- 不要解释或求值 Hook 的 `condition`：
  - 没有 `condition` 字段，或字段为 null/空时，将 Hook 视为可执行。
  - `condition` 非空时跳过，将条件求值留给 HookExecutor。
- 构造调用命令时，将 Hook 命令名中的点号（`.`）替换为连字符（`-`），例如
  `speckit.git.commit` → `$speckit-git-commit`。
- 可选 Hook（`optional: true`）输出：

  ```text
  ## Extension Hooks

  **Optional Pre-Hook**: {extension}
  Command: `/{command}`
  Description: {description}

  Prompt: {prompt}
  To execute: `/{command}`
  ```

- 强制 Hook（`optional: false`）输出：

  ```text
  ## Extension Hooks

  **Automatic Pre-Hook**: {extension}
  Executing: `/{command}`
  EXECUTE_COMMAND: {command}

  Wait for the result of the hook command before proceeding to the Goal.
  ```

  输出后必须实际调用 Hook，并等待其完成再继续。调用方式与在当前 Agent/Session 中自行运行
  该命令相同；仅输出代码块不会运行 Hook。
- 没有注册 Hook 或配置文件不存在时，静默跳过。

## 目标

缩小功能产物要求与代码库当前实现之间的差距。将 `spec.md`、`plan.md` 和 `tasks.md` 作为
**唯一意图来源**，并以章程作为治理约束。评估当前代码，找出未满足、未完成或仅部分满足的
需求、验收标准、Plan 决策和已有任务；将每项剩余工作以新的、可追溯任务形式追加到
`tasks.md` 末尾，使 `$speckit-implement` 能完成它们。

此命令只能在 `$speckit-implement` 已针对当前 `tasks.md` 运行，并且 `$speckit-tasks`
已生成完整 `tasks.md` 后执行。

这**不是** Diff Tool，也不跟踪变更。它只评估代码当前状态与功能产物的差异，不使用 Git、
Branch 比较或历史记录。

## 操作约束

**只允许追加，绝不重写**：唯一允许的写入是在 `tasks.md` 末尾追加新的
`## Phase N: Convergence` 章节。不得：

- 以任何方式修改 `spec.md` 或 `plan.md`。
- 重写、重新编号、重新排序或删除任何已有任务，包括此前 Convergence 阶段的任务。
- 修改、创建或删除任何应用代码；完成追加任务是 `$speckit-implement` 的职责。

如果代码库已满足全部要求，必须保持 `tasks.md` **逐字节不变**，不得添加空的 Convergence
标题，并报告已收敛。

**章程权威性**：项目章程（`.specify/memory/constitution.md`）不可协商。违反 MUST 原则
的代码属于最高严重级别，并产生对应修复任务。如果章程仍是未填写的 Template，应妥善跳过
章程检查，而不是失败。

## 执行步骤

### 1. 初始化收敛上下文

从仓库根目录运行一次
`.specify/scripts/bash/check-prerequisites.sh --json --require-spec --require-tasks --include-tasks`，
解析 FEATURE_DIR 和 AVAILABLE_DOCS，并推导绝对路径：

- SPEC = FEATURE_DIR/spec.md
- PLAN = FEATURE_DIR/plan.md
- TASKS = FEATURE_DIR/tasks.md
- CONSTITUTION = `.specify/memory/constitution.md`（如果存在）

如果缺少 `spec.md`、`plan.md` 或 `tasks.md`，停止并明确提示应运行的前置命令：
缺少 Spec 时运行 `$speckit-specify`，缺少 Plan 时运行 `$speckit-plan`，缺少 Tasks 时运行
`$speckit-tasks`。不得生成部分结果。

参数中包含单引号时（例如 "I'm Groot"），使用 `'I'\''m Groot'`，也可在条件允许时使用双引号。

### 2. 加载产物（渐进式披露）

仅加载最低限度的必要上下文：

- `spec.md`：功能需求（FR-###）、需要构建工作的成功标准（SC-###，排除上线后结果指标和业务
  KPI）、User Story 及验收场景、Edge Case。
- `plan.md`：架构/技术栈选择、技术决策、Data Model 引用、阶段、指定的文件/Component
  Touch Point、技术约束。
- `tasks.md`：Task ID、描述、阶段分组、引用路径，用于计算下一个 ID 和阶段编号。
- 章程（如果不是未填写 Template）：原则名称和 MUST/SHOULD 规范性陈述。

### 3. 构建意图清单

创建内部 Model，不要回显原始产物：

- **需求清单**：为每个 FR-###、SC-###、User Story 验收场景（如 `US1/AC2`）建立稳定 Key；
  同时纳入产生可构建义务的 Plan 决策和章程原则。
- **代码范围映射**：根据 `plan.md` 和 `tasks.md` 中的文件路径，以及对需求概念的关键词搜索，
  推导待评估源码和 Component。评估范围必须限定于此，不得超出产物定义自行扩张。

### 4. 评估代码并分类发现

对意图清单中的每一项检查范围内的当前代码，仅在存在缺口时生成 `Finding`。Gap Type：

- **`missing`**：所需工作在代码中完全不存在。
- **`partial`**：已有实现，但未完全满足需求、验收标准或 Plan 决策。
- **`contradicts`**：代码行为与声明意图或章程 MUST 原则冲突。
- **`unrequested`**：代码包含 Spec、Plan 或 Tasks 未要求的工作。仅用于提醒；Converge 不删除
  代码，只追加用于审查、说明理由或移除的任务。

每个 `Finding` 记录稳定 ID、`source-ref`、`gap-type`、严重级别，以及包含证据（所观察文件
或区域）的简短说明。

Edge Case：

- 几乎没有代码时，将整个已定义范围视为 `missing` 剩余工作，而不是失败。
- 没有剩余工作时，生成零条发现，并执行步骤 7 的已收敛分支。

### 5. 分配严重级别

- **CRITICAL**：违反章程 MUST，或阻塞 P1 User Story 基础功能的 `missing`/`contradicts`。
- **HIGH**：核心功能需求或验收标准存在 `missing`/`partial`。
- **MEDIUM**：次要需求存在 `partial`，或 `unrequested` 内容缺少明确理由。
- **LOW**：轻微部分缺口、打磨项或低风险 `unrequested` 内容。

### 6. 在 Session 中展示发现摘要

追加任何内容前，先输出按严重级别组织的精简摘要，不写文件：

```markdown
## Convergence Findings

| ID | Gap Type | Severity | Source | Evidence | Remaining Work |
|----|----------|----------|--------|----------|----------------|
| F1 | missing  | HIGH     | FR-008 | Example: no append-only guard detected in path/to/module.py when writing tasks.md | Add append-only enforcement |
```

摘要指标包括：

- 已检查的需求/验收标准数量
- 已检查的 Plan 决策数量
- 已检查的章程原则数量，或 `skipped - template`
- 按 Gap Type 统计的发现数量
- 按严重级别统计的发现数量

### 7. 追加收敛任务，或报告已收敛

**存在一条或多条可执行发现时**（结果为 `tasks_appended`）：

1. 扫描所有已有 Task ID，令最大值为 `M`；最高已有阶段加 1 得到新阶段编号 `N`。
2. 在 `tasks.md` 末尾写入唯一的新章节标题 `## Phase N: Convergence`。
3. 每条可执行发现生成一个 Checklist Item，CRITICAL/HIGH 优先，ID 依次为
   `T{M+1:03d}`、`T{M+2:03d}`……：

   ```markdown
   - [ ] T042 <imperative description> per <source-ref> (<gap-type>)
   ```

   `<source-ref>` 指向任务来源，例如 `FR-003`、`SC-002`、`US1/AC2`、
   `plan: storage decision`、`Constitution II`。`<gap-type>` 必须是
   `missing`、`partial`、`contradicts` 或 `unrequested`。

   章程违规任务必须最先输出，并标记为 `CRITICAL`。
4. 不得复用或重新编号已有 ID。存在旧 Convergence 阶段时，在其后新增单独编号的阶段，
   不得修改旧阶段。

**没有可执行发现时**（结果为 `converged`）：

- 完全不修改 `tasks.md`，也不添加空阶段标题。
- 报告：**“已收敛，当前实现满足 Spec、Plan 和 Tasks。”**
- 包含已检查内容的摘要数量。

### 8. 提供后续操作

- `tasks_appended`：说明在何阶段追加了多少任务，建议运行 `$speckit-implement`；提示再次运行
  Converge 时应发现更少或没有剩余项。
- `converged`：建议进入 Review 或创建 PR；本功能定义范围内无需再次运行 Implement。

### 9. 检查 Extension Hook

结果生成后检查 `.specify/extensions.yml`：

- 读取 `hooks.after_converge`；YAML 无效时静默跳过。
- 过滤 `enabled: false`；按执行前检查中的规则处理 `condition`。
- 列出 Hook 前，先在 Session 中报告 `converged` 或 `tasks_appended`，让用户能决定是否运行
  可选后续命令。
- 将命令名中的点号替换为连字符。
- 可选 Hook 输出：

  ```text
  ## Extension Hooks

  **Optional Hook**: {extension}
  Command: `/{command}`
  Description: {description}

  Prompt: {prompt}
  To execute: `/{command}`
  ```

- 强制 Hook 输出：

  ```text
  ## Extension Hooks

  **Automatic Hook**: {extension}
  Executing: `/{command}`
  EXECUTE_COMMAND: {command}
  ```

  输出后必须实际调用并等待 Hook 完成。仅输出代码块不会运行 Hook。
- 没有注册 Hook 或配置文件不存在时，静默跳过。

## Coding-Harness 收敛补充规则

只有满足以下全部条件，实现才算收敛：

- 每个变更行为都能从 Spec 需求追溯到 Gherkin 场景和已通过的可执行测试。
- 不违反任何适用的 `AGENTS.md` 或章程规则。
- 受影响的 Frontend、API、Service、持久化、CLI、示例和架构 Contract 已同步。
- 相关测试、完整 Unit/Integration 测试套件、`ruff check .` 和适用的 Frontend 检查均有
  记录结果。
- 失败、权限、幂等性、兼容性和敏感数据处理符合 Spec。
- 与任务无关的 Working Tree 变更保持不动。

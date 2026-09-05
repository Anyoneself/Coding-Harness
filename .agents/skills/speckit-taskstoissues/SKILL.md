---
name: "speckit-taskstoissues"
description: "根据现有设计产物，将任务转换为可执行且按依赖排序的 GitHub Issue。"
compatibility: "需要包含 .specify/ 目录的 spec-kit 项目结构"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/taskstoissues.md"
---


## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 执行前检查

**检查 Extension Hook（任务转换为 Issue 前）**：
- 检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果存在，读取该文件并查找 `hooks.before_taskstoissues` 键下的条目。
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

1. 从仓库根目录运行
   `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`，
   并解析 FEATURE_DIR 和 AVAILABLE_DOCS 列表。所有路径必须为绝对路径。参数中包含单引号时
   （例如 "I'm Groot"），使用转义语法，如 `'I'\''m Groot'`；也可在条件允许时使用双引号。
1. **如果存在**：加载 `.specify/memory/constitution.md`，获取项目原则和治理约束。
1. 从已执行脚本的结果中提取 **tasks** 路径。
1. 运行以下命令获取 Git Remote：

```bash
git config --get remote.origin.url
```

> [!CAUTION]
> 只有当 Remote 是 GitHub URL 时，才能继续后续步骤。

1. **获取现有 Issue 以去重**：创建任何内容前，从 `tasks.md` 构建待处理的 Task ID 集合。
   每个 ID 都是 `T` 后跟**至少**三位数字，例如 `T001`。`$speckit-converge` 使用
   `T{M+1:03d}` 分配新 ID，这只是位数下限而非上限；文件超过 999 个任务后，ID 会包含
   四位或更多数字。然后使用 GitHub MCP Server 的 `list_issues` Tool 查找已覆盖这些 ID 的
   Issue。不要传递 `state`，省略该参数会同时返回 Open 和 Closed Issue。请求
   `perPage: 100` 以减少调用次数；该 Tool 使用 Cursor 分页，因此使用 `after` 参数请求后续页，
   值取自上一响应的 `endCursor`。将每个 Issue 标题与 Task ID Pattern `\bT\d{3,}\b`
   匹配。`{3,}` 支持四位及更长 ID；若使用 `\d{3}`，包含 `T1000` 的标题完全无法匹配，
   因为末尾的 `\b` 不能位于两个数字之间，导致该任务既未去重也未创建。Word Boundary 仍会
   阻止 `ST001` 这样的 Token 被匹配，并要求消费完整数字串，因此 `T100` 不会在 `T1000`
   中匹配。该 Pattern 也能识别 `T001 ...`、`T001: ...` 和 `[T001] ...` 等标题。匹配到
   当前 Task ID 后，将其标记为已有 Issue。所有 Task ID 均匹配后，或不存在更多页面时停止
   分页，避免在 ID 已全部确认后继续获取整个仓库的 Issue 历史。这样既限制大型仓库的调用次数，
   也能在重新生成 `tasks.md` 或再次调用 Skill 时防止重复。
1. 对列表中的每个任务，使用 GitHub MCP Server 在 Git Remote 对应的仓库中创建新 Issue。
   `tasks.md` 中的任务行以 Markdown Checkbox 开头，应先移除前缀 `- [ ]`，以及可能存在的
   `[P]` / `[US#]` 标记，以取得 Task ID 和描述。Issue 标题统一为
   `T001: <description>`，ID 只写一次，后接任务描述。例如，
   `- [ ] T001 Create project structure` 转换为 `T001: Create project structure`。
   - **跳过** Task ID 已存在于上一步现有 Issue 集合中的任务，并报告该情况，例如
     `T001 already has an issue, skipping`。
   - 只为尚无匹配 Issue 的任务创建 Issue。

> [!CAUTION]
> 在任何情况下，都不得在与 Remote URL 不匹配的仓库中创建 Issue。

## 执行后检查

**检查 Extension Hook（任务转换为 Issue 后）**：
检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果存在，读取该文件并查找 `hooks.after_taskstoissues` 键下的条目。
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
    输出上述代码块后，必须实际调用 Hook 并等待其完成，再继续执行。调用方式与在当前
    Agent/Session 中自行运行该命令相同。仅输出代码块并不会运行 Hook。
- 如果没有注册 Hook，或 `.specify/extensions.yml` 不存在，则静默跳过。

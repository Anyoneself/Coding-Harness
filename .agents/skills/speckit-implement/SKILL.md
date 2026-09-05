---
name: speckit-implement
description: 按 tasks.md 中定义的全部任务执行实现 Plan。
compatibility: 需要包含 .specify/ 目录的 spec-kit 项目结构
metadata:
  author: github-spec-kit
  source: preset:coding-harness
---

# Speckit Implement Skill

## Coding-Harness 实现前 Gate

执行核心实现工作流前：

1. 阅读适用的 `AGENTS.md`、`.specify/memory/constitution.md`、当前 `spec.md`、`plan.md`、
   `tasks.md` 和相关现有测试。
2. 如果缺少必需的 Spec、Plan、Task List 或最新分析，拒绝修改生产代码。
3. 实现前，在对应产物中解决分析阶段发现的阻塞问题。
4. 在对应生产代码任务前，先执行 Gherkin 和失败测试任务。
5. 保留用户无关变更，并将实现限制在已审查范围内。

即使生成的任务遗漏了要求，仓库的测试优先、中文 Docstring、类型、分层、安全和 README 规则
仍为强制规则。

## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 执行前检查

检查 `.specify/extensions.yml` 中的 `hooks.before_implement`：

- YAML 无效时静默跳过；过滤 `enabled: false`。
- 没有 `condition` 或其值为 null/空时视为可执行；`condition` 非空时跳过，并将求值留给
  HookExecutor。
- 命令名中的点号替换为连字符，例如 `speckit.git.commit` → `$speckit-git-commit`。
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

  Wait for the result of the hook command before proceeding to the Outline.
  ```

  输出后必须实际调用 Hook，并等待其完成再继续。仅输出代码块不会运行 Hook。
- 没有注册 Hook 或配置文件不存在时，静默跳过。

## 执行流程

1. 从仓库根目录运行
   `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`，解析
   FEATURE_DIR 和 AVAILABLE_DOCS。所有路径必须为绝对路径。参数中包含单引号时（例如
   "I'm Groot"），使用 `'I'\''m Groot'`，也可在条件允许时使用双引号。

2. **检查 Checklist 状态**（如果存在 FEATURE_DIR/checklists/）：
   - Checklist Marker 是只读 Gate：扫描 Checkbox 状态并报告；需要时询问是否继续，但不得
     修改 Checklist 文件或 Marker。
   - `checklists/requirements.md` 是由 `$speckit-specify` 和 `$speckit-clarify` 维护的内置
     Spec 质量 Checklist；`$speckit-checklist` 生成的自定义 Checklist 是 Reviewer 所有的
     需求质量审查产物。
   - 对自定义 Checklist，`[x]` 表示 Reviewer 判定需求质量标准已满足，不代表实现工作已完成。
   - 扫描 `checklists/` 中的全部 Checklist 文件。每个文件统计：
     - 总项数：匹配 `- [ ]`、`- [X]` 或 `- [x]` 的所有行。
     - 已勾选：匹配 `- [X]` 或 `- [x]` 的行。
     - 未勾选：匹配 `- [ ]` 的行。
   - 创建状态表：

     ```text
     | Checklist | Total | Checked | Unchecked | Status |
     |-----------|-------|---------|-----------|--------|
     | ux.md     | 12    | 12      | 0         | ✓ PASS |
     | test.md   | 8     | 5       | 3         | ✗ FAIL |
     | security.md | 6   | 6       | 0         | ✓ PASS |
     ```

   - 全部 Checklist 的未勾选项为 0 时，总体状态为 PASS；任一文件存在未勾选项时为 FAIL。
   - 存在未勾选项时，显示状态表后停止，并询问用户：
     “部分 Checklist 仍有未勾选项，是否仍继续实现？（yes/no）”
     等待回复；`no`、`wait` 或 `stop` 时终止，`yes`、`proceed` 或 `continue` 时进入步骤 3。
   - 全部已勾选时，显示 PASS 表并自动进入步骤 3。

3. 加载并分析实现上下文：
   - **必需**：读取 `tasks.md`，获取完整任务列表和执行 Plan。
   - **必需**：读取 `plan.md`，获取技术栈、架构和文件结构。
   - **如果存在**：读取 `data-model.md` 中的 Entity 和关系。
   - **如果存在**：读取 `contracts/` 中的 API Spec 和测试要求。
   - **如果存在**：读取 `research.md` 中的技术决策和约束。
   - **如果存在**：读取 `.specify/memory/constitution.md` 中的治理约束。
   - **如果存在**：读取 `quickstart.md` 中的 Integration 场景。

4. **验证项目设置**：
   - 根据实际项目设置创建或验证 Ignore 文件。
   - 运行以下命令判断是否为 Git 仓库；如果是，则创建或验证 `.gitignore`：

     ```sh
     git rev-parse --git-dir 2>/dev/null
     ```

   - 存在 Dockerfile 或 `plan.md` 使用 Docker 时，创建/验证 `.dockerignore`。
   - 存在 `.eslintrc*` 时，创建/验证 `.eslintignore`。
   - 存在 `eslint.config.*` 时，确保配置中的 `ignores` 覆盖必要 Pattern。
   - 存在 `.prettierrc*` 时，创建/验证 `.prettierignore`。
   - 存在 `.npmrc` 或 `package.json` 且项目需要发布时，创建/验证 `.npmignore`。
   - 存在 `*.tf` 时，创建/验证 `.terraformignore`。
   - 存在 Helm Chart 时，创建/验证 `.helmignore`。
   - Ignore 文件已存在时，只追加缺失的关键 Pattern；不存在时，根据检测到的技术创建完整
     Pattern 集。

   常见技术 Pattern：

   - **Node.js/JavaScript/TypeScript**：`node_modules/`、`dist/`、`build/`、`*.log`、`.env*`
   - **Python**：`__pycache__/`、`*.pyc`、`.venv/`、`venv/`、`dist/`、`*.egg-info/`
   - **Java**：`target/`、`*.class`、`*.jar`、`.gradle/`、`build/`
   - **C#/.NET**：`bin/`、`obj/`、`*.user`、`*.suo`、`packages/`
   - **Go**：`*.exe`、`*.test`、`vendor/`、`*.out`
   - **Ruby**：`.bundle/`、`log/`、`tmp/`、`*.gem`、`vendor/bundle/`
   - **PHP**：`vendor/`、`*.log`、`*.cache`、`*.env`
   - **Rust**：`target/`、`debug/`、`release/`、`*.rs.bk`、`*.rlib`、`*.prof*`、`.idea/`、
     `*.log`、`.env*`
   - **Kotlin**：`build/`、`out/`、`.gradle/`、`.idea/`、`*.class`、`*.jar`、`*.iml`、
     `*.log`、`.env*`
   - **C++**：`build/`、`bin/`、`obj/`、`out/`、`*.o`、`*.so`、`*.a`、`*.exe`、`*.dll`、
     `.idea/`、`*.log`、`.env*`
   - **C**：`build/`、`bin/`、`obj/`、`out/`、`*.o`、`*.a`、`*.so`、`*.exe`、`*.dll`、
     `autom4te.cache/`、`config.status`、`config.log`、`.idea/`、`*.log`、`.env*`
   - **Swift**：`.build/`、`DerivedData/`、`*.swiftpm/`、`Packages/`
   - **R**：`.Rproj.user/`、`.Rhistory`、`.RData`、`.Ruserdata`、`*.Rproj`、`packrat/`、`renv/`
   - **通用**：`.DS_Store`、`Thumbs.db`、`*.tmp`、`*.swp`、`.vscode/`、`.idea/`

   Tool 专用 Pattern：

   - **Docker**：`node_modules/`、`.git/`、`Dockerfile*`、`.dockerignore`、`*.log*`、`.env*`、
     `coverage/`
   - **ESLint**：`node_modules/`、`dist/`、`build/`、`coverage/`、`*.min.js`
   - **Prettier**：`node_modules/`、`dist/`、`build/`、`coverage/`、`package-lock.json`、
     `yarn.lock`、`pnpm-lock.yaml`
   - **Terraform**：`.terraform/`、`*.tfstate*`、`*.tfvars`、`.terraform.lock.hcl`
   - **Kubernetes/k8s**：`*.secret.yaml`、`secrets/`、`.kube/`、`kubeconfig*`、`*.key`、`*.crt`

5. 解析 `tasks.md` 的阶段、依赖、Task ID、描述、文件路径、`[P]` 标记和执行顺序。

6. 按 Task Plan 实现：
   - 逐阶段完成；顺序任务按顺序执行，`[P]` 任务可以并行。
   - 遵循 TDD，在对应实现任务前执行测试任务。
   - 修改相同文件的任务必须顺序执行。
   - 每个阶段结束时执行验证。

7. 实现顺序为 Setup、Tests、Core、Integration、Polish 与验证。Core 可包含 Model、Service、
   CLI Command 和 Endpoint；Integration 可包含数据库、Middleware、日志和外部 Service。

8. 进度与错误处理：
   - 每个任务完成后报告进度；非并行任务失败时停止。
   - `[P]` 任务失败时继续完成成功任务，并报告失败项。
   - 提供明确错误上下文和后续建议。
   - 已完成任务必须在 `tasks.md` 中标记为 `[X]`。

9. 完成验证：确认全部必需任务完成，实现符合原始 Spec 和技术 Plan，测试通过且覆盖率符合要求。

任务不完整或缺失时，建议先运行 `$speckit-tasks` 重新生成 `tasks.md`。

## 强制执行后 Hook

向用户报告完成前，必须处理 `.specify/extensions.yml` 中的 `hooks.after_implement`：

- 配置不存在或没有注册 Hook 时，进入完成报告；YAML 无效时静默跳过。
- 过滤 `enabled: false`，并按执行前检查规则处理 `condition` 和命令名。
- 每个强制 Hook（`optional: false`）都必须输出 `EXECUTE_COMMAND:`：

  ```text
  ## Extension Hooks

  **Automatic Hook**: {extension}
  Executing: `/{command}`
  EXECUTE_COMMAND: {command}
  ```

  随后实际调用并等待 Hook 完成；仅输出代码块不会运行 Hook。
- 可选 Hook（`optional: true`）输出：

  ```text
  ## Extension Hooks

  **Optional Hook**: {extension}
  Command: `/{command}`
  Description: {description}

  Prompt: {prompt}
  To execute: `/{command}`
  ```

## 完成报告

报告最终状态和已完成工作的摘要。

## 完成条件

- [ ] `tasks.md` 中的全部任务已完成并标记为 `[X]`
- [ ] 已根据 Spec、Plan 和测试覆盖验证实现
- [ ] 已按强制执行后 Hook 规则派发或跳过 Extension Hook
- [ ] 已向用户报告完成状态和工作摘要

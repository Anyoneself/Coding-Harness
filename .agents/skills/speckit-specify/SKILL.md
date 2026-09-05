---
name: speckit-specify
description: 根据自然语言功能描述创建或更新功能 Spec。
compatibility: 需要包含 .specify/ 目录的 spec-kit 项目结构
metadata:
  author: github-spec-kit
  source: preset:coding-harness
---

# Speckit Specify Skill

## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 执行前 Hook

检查 `.specify/extensions.yml` 中的 `hooks.before_specify`：

- YAML 无效时静默跳过；过滤 `enabled: false`。
- 没有 `condition` 或其值为 null/空时视为可执行；非空时跳过，将求值留给 HookExecutor。
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

- 强制 Hook 输出 `EXECUTE_COMMAND:`，随后实际调用并等待完成：

  ```text
  ## Extension Hooks

  **Automatic Pre-Hook**: {extension}
  Executing: `/{command}`
  EXECUTE_COMMAND: {command}
  ```

- 没有注册 Hook 或配置文件不存在时，静默跳过。

## 执行流程

触发消息中 `$speckit-specify` 后面的文本就是功能描述。即使下面字面显示 `$ARGUMENTS`，
也应假设本次对话中已提供描述；只有命令确实为空时才能要求用户重述。

1. **生成功能短名称**：
   - 从描述中提取最有意义的关键词，生成 2-4 个词的短名称。
   - 尽量使用“动作-名词”形式，例如 `add-user-auth`、`fix-payment-bug`。
   - 保留 OAuth2、API、JWT 等技术术语和缩写。
   - 名称应简短，但足以快速理解功能。

2. **可选 Branch 创建**：
   - 如果执行前的 `before_specify` Hook 成功运行，它会创建或切换 Git Branch，并返回包含
     BRANCH_NAME 和 FEATURE_NUM 的 JSON。记录这些值，但 Branch 名不决定 Spec 目录名。
   - 用户明确提供 GIT_BRANCH_NAME 时，将原值传给 Hook，跳过前后缀生成。

3. **创建 Spec 功能目录**：
   - 默认位于 `specs/`，除非用户明确提供 SPECIFY_FEATURE_DIRECTORY。
   - 解析顺序：
     1. 用户通过环境变量、参数或配置明确提供时，原样使用。
     2. 否则读取 `.specify/init-options.json` 中的 `feature_numbering`；兼容读取已废弃的
        `branch_numbering`。
        - `"timestamp"`：前缀为当前时间戳 `YYYYMMDD-HHMMSS`。
        - `"sequential"` 或缺省：扫描 `specs/`，使用下一个三位编号 `NNN`。
        - 目录名为 `<prefix>-<short-name>`，例如 `003-user-auth`。
        - 将 SPECIFY_FEATURE_DIRECTORY 设为 `specs/<directory-name>`。
        - 仅存在 `branch_numbering` 时，输出一行警告，提示重命名为 `feature_numbering`。
   - 创建目录；通过 Spec Kit Preset/Template 解析栈解析当前 `spec-template`，将其复制为
     `SPECIFY_FEATURE_DIRECTORY/spec.md`，并将该路径设为 SPEC_FILE。
   - 将实际解析出的目录写入 `.specify/feature.json`：

     ```json
     {
       "feature_directory": "<resolved feature dir>"
     }
     ```

   - 每次 `$speckit-specify` 只能创建一个功能。
   - Spec 目录名与 Git Branch 名相互独立。
   - Spec 目录和文件始终由此核心命令创建，不由 Hook 创建。

4. 读取已解析的当前 `spec-template`，理解必需章节。

5. 如果存在，读取 `.specify/memory/constitution.md` 中的项目原则和治理约束。

6. 生成 Spec：
   1. 从参数解析功能描述；为空时报告 ERROR：未提供功能描述。
   2. 提取 Actor、Action、Data 和 Constraint。
   3. 对不清楚的内容优先结合上下文和行业标准作合理推断。仅在以下条件全部成立时使用
      `[NEEDS CLARIFICATION: specific question]`：
      - 选择会显著影响功能范围或 UX。
      - 存在多个影响不同的合理解释。
      - 不存在合理默认值。
      最多三个 Marker，优先级为范围 > 安全/隐私 > UX > 技术细节。
   4. 填写 User Scenarios & Testing；无法确定清晰 User Flow 时报告 ERROR。
   5. 生成功能需求；每项必须可测试。未明确细节使用合理默认值，并在 Assumptions 中记录。
   6. 定义可衡量、与技术无关的成功标准，同时包含量化指标和定性结果，且无需实现细节即可验证。
   7. 涉及数据时识别 Key Entity。
   8. 成功时返回 Spec 已可进入 Plan。

7. 按 Template 的原有章节顺序和标题，将占位符替换为从功能描述推导出的具体内容，并写入
   SPEC_FILE。

## Spec 质量验证

写入初始 Spec 后，在 `SPECIFY_FEATURE_DIRECTORY/checklists/requirements.md` 创建内置质量
Checklist，结构遵循 Checklist Template，至少覆盖：

- **内容质量**：无实现细节；聚焦用户价值和业务需求；面向非技术 Stakeholder；必需章节完整。
- **需求完整性**：无 `NEEDS CLARIFICATION`；需求可测试且无歧义；成功标准可衡量且技术无关；
  验收场景完整；已识别 Edge Case；范围明确；已记录依赖和假设。
- **功能就绪**：功能需求有明确验收标准；User Scenario 覆盖主要 Flow；功能满足成功标准；
  Spec 中没有泄漏实现细节。
- **Notes**：未完成项必须在 `$speckit-clarify` 或 `$speckit-plan` 前修正。

逐项检查 Spec，并记录失败项和对应 Spec 位置。

- 全部通过：将 Checklist 标记完成，进入强制执行后 Hook。
- 存在非澄清类失败：
  1. 列出失败项和具体问题。
  2. 更新 Spec 修复问题。
  3. 重新验证，最多三轮。
  4. 三轮后仍失败时，在 Checklist Notes 中记录剩余问题并警告用户。
- 仍有 `[NEEDS CLARIFICATION]`：
  1. 提取全部 Marker；超过三个时只保留按范围、安全、UX 排序最关键的三个，其余合理推断。
  2. 每个问题最多提供三个建议答案和一个 Custom 选项，使用：

     ```markdown
     ## Question [N]: [Topic]

     **Context**: [Quote relevant spec section]

     **What we need to know**: [Specific question from NEEDS CLARIFICATION marker]

     **Suggested Answers**:

     | Option | Answer | Implications |
     |--------|--------|--------------|
     | A      | [First suggested answer] | [What this means for the feature] |
     | B      | [Second suggested answer] | [What this means for the feature] |
     | C      | [Third suggested answer] | [What this means for the feature] |
     | Custom | Provide your own answer | [Explain how to provide custom input] |

     **Your choice**: _[Wait for user response]_
     ```

  3. Markdown 表格的 Pipe 和空格必须规范，分隔行至少三个连字符。
  4. 问题按 Q1-Q3 编号并一次全部展示，等待用户统一回复。
  5. 用用户答案替换 Marker，并重新验证。

每轮验证后都更新 Checklist 的当前通过/失败状态。

## 强制执行后 Hook

向用户报告完成前，必须处理 `hooks.after_specify`：

- 配置不存在、没有注册 Hook 或 YAML 无效时进入完成报告。
- 过滤 `enabled: false`，按执行前 Hook 规则处理 `condition` 和命令名。
- 每个强制 Hook 都必须输出 `EXECUTE_COMMAND:`，实际调用并等待完成；仅输出代码块不会运行 Hook。
- 可选 Hook 仅输出命令、Description 和 Prompt。

## 完成报告

向用户报告：

- SPECIFY_FEATURE_DIRECTORY 功能目录路径。
- SPEC_FILE 路径。
- Checklist 结果摘要。
- 是否已可进入 `$speckit-clarify` 或 `$speckit-plan`。

Branch 创建由 `before_specify` Git Extension Hook 处理；Spec 目录和文件始终由核心命令处理。

## 快速指南

- 聚焦用户需要**什么**以及**为什么需要**。
- 避免描述如何实现，不写技术栈、API 或代码结构。
- 面向业务 Stakeholder，而不是开发者。
- 不要将 Checklist 嵌入 Spec；Checklist 是单独产物。
- 必需章节每个功能都要完成；可选章节仅在相关时保留；不适用的章节应删除，不写 `N/A`。

### AI 生成规则

- 使用上下文、行业标准和常见 Pattern 合理补全缺口，并在 Assumptions 中记录默认值。
- 最多三个 `NEEDS CLARIFICATION`，仅用于无合理默认值且会显著影响范围、安全或 UX 的决策。
- 像 Tester 一样思考；每个模糊需求都应无法通过“可测试且无歧义”检查。
- 通常不需要询问数据保留、标准 Web/Mobile 性能预期、友好错误消息、常规 Auth 方式，以及
  适合项目类型的 REST/GraphQL、函数调用或 CLI 参数等 Integration Pattern。

### 成功标准

成功标准必须：

1. **可衡量**：包含时间、百分比、数量或比率等指标。
2. **技术无关**：不提 Framework、语言、数据库或 Tool。
3. **用户导向**：描述用户或业务结果，而非系统内部实现。
4. **可验证**：无需了解实现细节即可测试或验证。

良好示例：

- 用户可在三分钟内完成结账。
- 系统支持 10,000 名并发用户。
- 95% 的搜索在一秒内返回结果。
- 任务完成率提升 40%。

应避免 API 响应时间、数据库 TPS、React Render 效率或 Redis 命中率等实现指标；将其改写为
用户可感知的结果。

## Coding-Harness Spec 规则

- 最终确定 Spec 前，读取适用的 `AGENTS.md` 和 `docs/pm/` 下相关文档。
- 功能产物使用中文，保留代码标识符、Protocol 名称、公式和既有英文技术术语。
- 存在产品 Task ID 时进行关联，但不要把整个产品 Roadmap 复制进功能 Spec。
- 每个 User Story 都必须包含适合 `tests/features/` 的可观察 Given/When/Then 验收场景。
- 明确写出失败行为、兼容边界、安全约束和 Out-of-Scope 行为。
- Spec 阶段不得修改生产代码、测试、README 或无关项目文档。

## 完成条件

- [ ] Spec 已写入 SPEC_FILE，并通过质量 Checklist 验证
- [ ] 已按规则派发或跳过 Extension Hook
- [ ] 已向用户报告功能目录、Spec 路径和 Checklist 结果

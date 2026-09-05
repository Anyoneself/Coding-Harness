---
name: "speckit-constitution"
description: "根据交互输入或已提供的原则创建或更新项目章程。"
compatibility: "需要包含 .specify/ 目录的 spec-kit 项目结构"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/constitution.md"
---


## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 范围约束

此命令的工作范围仅限更新项目章程本身。依赖模板和命令会在运行时读取章程，
此处不修改它们。

- 将用户输入的每一部分分类为章程内容或独立的非治理意图。
- 如果输入包含功能实现、代码生成、重构、构建或部署请求，**不得**执行这些请求，
  而应将其提取为待后续处理的意图。
- **不得**创建、修改或删除应用源文件、功能路由、Component、测试、部署文件，
  或其他与章程工作流无关的产物。
- 如果无法确定某项指令是否属于章程内容，修改前应先请求澄清。
- 完成章程更新后，为每个待后续处理的意图提供 `后续操作` 章节。列出原始意图，
  并建议适当的后续 Spec Kit 命令（例如 `$speckit-specify`），但不要调用该命令。
- 如果没有非治理意图，则省略 `后续操作` 章节。

## 执行前检查

**检查 Extension Hook（更新章程前）**：
- 检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果存在，读取该文件并查找 `hooks.before_constitution` 键下的条目。
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
    Agent/Session 中自行运行该命令相同（实际调用可能不同于上面展示的 `{command}` 字面 ID，
    例如 Skills 模式的 Agent 会以 `/skill:speckit-...` 或 `$speckit-...` 运行）。
    仅输出代码块并不会运行 Hook。
- 如果没有注册 Hook，或 `.specify/extensions.yml` 不存在，则静默跳过。

## 执行流程

你正在更新 `.specify/memory/constitution.md` 中的项目章程。执行命令时，通过 Spec Kit
Preset/Template 解析栈从 `constitution-template` 解析当前生效的章程骨架。

遵循以下执行流程：

1. 从仓库根目录运行 `.specify/scripts/bash/resolve-template.sh constitution-template --json`，
   并将 `TEMPLATE_CONTENT` 解析为当前模板。
   - 共享 Resolver 会依次应用项目覆盖、组合后的 Preset 层和 Extension 层，最后才回退到
     Core Template。继续之前解析**必须**成功。
   - 如果解析失败，停止并报告解析错误；不得仅使用某一个参与组合的 Template 层继续。
   - 如果 `.specify/memory/constitution.md` 存在，将其作为当前项目特定值和修订的来源。
     应用新解析的骨架时，保留仍然适用的信息。
   - 如果该文件不存在，则以解析出的 Template 作为初始文档。
   - 不要回写任何带版本的 Template 层。
   - 识别所有形如 `[ALL_CAPS_IDENTIFIER]` 的占位符。
   **重要**：用户需要的原则数量可能少于或多于 Template 中的数量。如果用户指定了数量，
   应尊重该要求，在遵循总体 Template 的前提下相应更新文档。

2. 收集或推导占位符的值：
   - 如果用户输入（对话）提供了值，使用该值。
   - 否则从现有仓库上下文（README、文档、已嵌入的早期章程版本）中推断。
   - 对于治理日期：`RATIFICATION_DATE` 是最初采纳日期（未知时询问或标记 TODO）；
     如有修改，`LAST_AMENDED_DATE` 为今天，否则保留原值。
   - `CONSTITUTION_VERSION` 必须按照语义化版本规则递增：
     - MAJOR：移除或重新定义治理规则/原则，且不向后兼容。
     - MINOR：新增原则/章节，或实质性扩展指导内容。
     - PATCH：澄清、措辞调整、拼写修复或非语义性优化。
   - 如果无法明确版本升级类型，最终确定前先说明判断理由。

3. 使用解析出的 Template 作为必需结构，起草更新后的章程：
   - 将每个占位符替换为具体文本。除项目有意暂不定义的 Template 插槽外，不得留下方括号
     Token；对任何保留项都必须明确说明理由。
   - 保留标题层级。注释替换后可删除，除非仍能提供有价值的说明。
   - 确保每个“原则”章节包含简洁的名称、说明不可协商规则的段落（或列表），以及在理由
     不明显时给出的明确理由。
   - 确保“治理”章节列出修订流程、版本策略和合规审查要求。

4. 生成同步影响报告（更新后以前置 HTML 注释形式写在章程文件顶部）：
   - 版本变化：旧版本 → 新版本
   - 修改的原则列表（如重命名，写为旧标题 → 新标题）
   - 新增章节
   - 删除章节
   - 有意延后处理的占位符及后续 TODO

5. 最终输出前验证：
   - 不存在未解释的方括号 Token。
   - 版本行与报告一致。
   - 日期采用 ISO 格式 `YYYY-MM-DD`。
   - 原则具有声明性、可测试性，且没有模糊表述（例如将“应该”改为 MUST/SHOULD，
     并在适当位置说明理由）。

6. 将完成的章程覆盖写回 `.specify/memory/constitution.md`。

7. 向用户输出最终摘要，包括：
   - 新版本及升级理由。
   - 需要人工跟进的 TODO 占位符或延后事项。
   - 建议的 Commit Message，例如：
     `docs: amend constitution to vX.Y.Z (principle additions + governance update)`。
   - 所有待后续处理的非治理意图对应的 `后续操作` 章节。

格式与风格要求：

- 严格使用 Template 中的 Markdown 标题，不得提升或降低标题层级。
- 长理由行应适当换行以保持可读性（最好少于 100 个字符），但不要为了硬性满足长度而
  产生不自然的断行。
- 章节之间仅保留一个空行。
- 避免行尾空白。

即使用户只提供部分更新（例如只修订一项原则），仍必须执行验证和版本决策步骤。

如果缺少关键信息（例如确实无法得知批准日期），插入
`TODO(<FIELD_NAME>): explanation`，并在同步影响报告的延后事项中列出。

只能写入 `.specify/memory/constitution.md`；不要创建或修改 Template 源文件。

## 执行后检查

**检查 Extension Hook（更新章程后）**：
检查项目根目录是否存在 `.specify/extensions.yml`。
- 如果存在，读取该文件并查找 `hooks.after_constitution` 键下的条目。
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
    Agent/Session 中自行运行该命令相同（实际调用可能不同于上面展示的 `{command}` 字面 ID，
    例如 Skills 模式的 Agent 会以 `/skill:speckit-...` 或 `$speckit-...` 运行）。
    仅输出代码块并不会运行 Hook。
- 如果没有注册 Hook，或 `.specify/extensions.yml` 不存在，则静默跳过。

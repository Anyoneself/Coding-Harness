---
name: "speckit-checklist"
description: "根据用户需求，为当前功能生成自定义 Checklist。"
compatibility: "需要包含 .specify/ 目录的 spec-kit 项目结构"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/checklist.md"
---

## Checklist 的用途：为需求文本编写 Unit Test

**核心概念**：Checklist 是**需求编写的 Unit Test**，用于验证特定领域需求的质量、清晰度和
完整性，不用于验证代码实现。

不应检查：

- “验证按钮是否能正确点击”
- “测试错误处理是否有效”
- “确认 API 是否返回 200”
- 代码或实现是否符合 Spec

应检查：

- “所有 Card 类型是否都定义了视觉层级要求？”（完整性）
- “‘突出显示’是否通过具体尺寸或位置进行了量化？”（清晰度）
- “所有交互元素的 Hover State 要求是否一致？”（一致性）
- “是否定义了键盘导航的无障碍要求？”（覆盖范围）
- “Spec 是否定义 Logo 图片加载失败时的行为？”（Edge Case）

如果把 Spec 看作自然语言编写的代码，Checklist 就是它的 Unit Test Suite。检查的是需求是否
写得完整、明确、无歧义并可进入实现，而不是实现是否工作。

### 归属与 Checkbox 生命周期

- 此命令生成的自定义 Checklist 是 Reviewer 所有的需求质量审查产物。
- `[x]` 表示 Reviewer 判定该需求质量标准已满足，不表示实现工作已完成。
- 此命令可以生成或追加 Checklist Item，但不得把新 Item 标记为 `[x]`。
- 只有 Reviewer 明确要求时，Agent 才可协助评估 Item。
- `checklists/requirements.md` 是由 `$speckit-specify` 和 `$speckit-clarify` 维护的内置
  Spec 质量 Checklist；该例外不适用于此处生成的自定义 Checklist。

## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## Extension Hook

生成前检查 `.specify/extensions.yml` 中的 `hooks.before_checklist`，生成后检查
`hooks.after_checklist`：

- YAML 无效时静默跳过；过滤 `enabled: false`。
- 没有 `condition` 或其值为 null/空时视为可执行；非空时跳过并将求值留给 HookExecutor。
- 命令名中的点号替换为连字符，例如 `speckit.git.commit` → `$speckit-git-commit`。
- 可选 Hook 输出：

  ```text
  ## Extension Hooks

  **Optional Hook**: {extension}
  Command: `/{command}`
  Description: {description}

  Prompt: {prompt}
  To execute: `/{command}`
  ```

- 强制 Hook 输出 `EXECUTE_COMMAND:`，随后必须实际调用并等待完成；仅输出代码块不会运行 Hook：

  ```text
  ## Extension Hooks

  **Automatic Hook**: {extension}
  Executing: `/{command}`
  EXECUTE_COMMAND: {command}
  ```

- 没有注册 Hook 或配置文件不存在时，静默跳过。

## 执行步骤

1. **设置**：从仓库根目录运行
   `.specify/scripts/bash/check-prerequisites.sh --json --template checklist-template`，解析
   FEATURE_DIR、AVAILABLE_DOCS 和 TEMPLATE_CONTENT。所有文件路径必须为绝对路径。参数中包含
   单引号时（例如 "I'm Groot"），使用 `'I'\''m Groot'`，也可在条件允许时使用双引号。

2. 如果存在，读取 `.specify/memory/constitution.md` 中的项目原则和治理约束。

3. **动态澄清意图**：根据用户措辞及 Spec/Plan/Tasks 信号，最多生成三个初始问题，不使用固定
   问题目录。问题必须：
   - 只询问会实质改变 Checklist 内容的信息。
   - 已由 `$ARGUMENTS` 明确回答时跳过。
   - 优先精确性而非覆盖面。

   生成时提取领域关键词（如 Auth、Latency、UX、API）、风险词（如“关键”“必须”“合规”）、
   Stakeholder（如 QA、Reviewer、安全团队）和明确交付物（如 a11y、Rollback、Contract）。
   将信号聚成最多四个候选重点并排序；在不明确时识别受众和使用时机；检测范围、深度、风险、
   排除边界和可衡量验收标准等缺失维度。

   可询问范围细化、风险优先级、审查深度、受众、明确排除项或缺失场景类别。提供选项时使用
   `Option | Candidate | Why It Matters` 表，最多 A-E；自由回答更清晰时不使用表格。不得要求
   用户重复已提供信息，也不得臆造类别。

   无法交互时默认：Standard 深度；代码相关场景的受众为 PR Reviewer，否则为 Author；重点取
   相关性最高的两个 Cluster。

   问题标记为 Q1/Q2/Q3。回答后，如果 Alternate、Exception、Recovery、Non-Functional 等
   场景类别中仍至少有两类不明确，可再问最多两个定向问题（Q4/Q5），每题附一行理由。总问题数
   不得超过五个；用户拒绝继续时停止。

4. **理解请求**：合并 `$ARGUMENTS` 和澄清答案，确定 Checklist 主题、用户明确要求的必备项、
   分类结构、受众和深度。只从 Spec/Plan/Tasks 推断缺失上下文，不得臆造。

5. **加载功能上下文**：从 FEATURE_DIR 读取 `spec.md`，以及存在时的 `plan.md` 和 `tasks.md`。
   仅加载与当前重点相关的部分；长内容应先摘要，只有发现缺口时再加载更多。

6. **生成 Checklist**：
   - 使用 TEMPLATE_CONTENT 作为结构，在 `FEATURE_DIR/checklists/` 下创建文件。
   - 文件名采用简短领域名称，如 `ux.md`、`api.md`、`security.md`。
   - 新文件的 ID 从 CHK001 开始；已有文件只追加，并从最后一个 CHK ID 继续编号。
   - 绝不删除或替换已有内容；所有新 Item 保持 `[ ]`。
   - 每个 Item 检查需求的完整性、清晰度、一致性、可衡量性或场景/Edge Case 覆盖。

### 分类结构

- 需求完整性
- 需求清晰度
- 需求一致性
- 验收标准质量
- 场景覆盖
- Edge Case 覆盖
- Non-Functional Requirement（性能、安全、无障碍等）
- 依赖与假设
- 歧义与冲突

### Item 编写规则

每个 Item 都应：

- 以询问需求质量的问题形式编写。
- 聚焦 Spec/Plan 中写了什么或缺少什么。
- 使用 `[Completeness]`、`[Clarity]`、`[Consistency]`、`[Measurability]` 等质量维度。
- 检查已有需求时引用 `[Spec §X.Y]`；检查缺失项时使用 `[Gap]`。
- 检查 Primary、Alternate、Exception/Error、Recovery 和 Non-Functional 场景。
- 状态变更涉及失败恢复时，检查 Resilience/Rollback 要求。

至少 80% 的 Item 必须带可追溯引用：Spec 章节，或 `[Gap]`、`[Ambiguity]`、`[Conflict]`、
`[Assumption]` Marker。如果没有 ID 体系，应添加：
“是否建立了需求和验收标准的 ID 体系？[Traceability]”

正确示例：

- “是否为所有 API 失败模式定义了错误处理要求？[Gap]”
- “‘快速加载’是否通过明确时间阈值量化？[Clarity, Spec §NFR-2]”
- “不同页面的导航要求是否一致？[Consistency, Spec §FR-10]”
- “是否定义了无数据时的 Zero State？[Coverage, Edge Case]”
- “‘平衡的视觉权重’是否可客观验证？[Measurability, Spec §FR-2]”

禁止：

- 以 Verify、Test、Confirm、Check 加实现行为开头。
- 检查代码执行、用户操作或系统实际行为。
- 使用“正确显示”“正常工作”“符合预期”等实现验证表述。
- 编写 Click、Navigate、Render、Load、Execute 等行为测试。
- 编写 Test Case、Test Plan、QA Procedure 或具体实现细节。

候选 Item 超过 40 条时按风险和影响排序，合并近似重复项。低影响 Edge Case 超过五个时，可
合并为一条覆盖问题。

7. **结构**：遵循 `.specify/templates/checklist-template.md` 中的标题、Meta、分类标题、归属
   说明、Notes 和 ID 格式。如果 Template 不可用，使用 H1 标题、Purpose/Created Meta、
   Reviewer 归属说明、包含 `- [ ] CHK### <requirement item>` 的 `##` 分类章节，以及说明
   `$speckit-implement` 只读取 Marker 而不修改 Marker 的 Notes。

8. **报告**：输出 Checklist 文件绝对路径、Item 数量，以及本次是新建还是追加。摘要包含重点
   领域、深度、使用者/时机和已纳入的用户必备项。

每次 `$speckit-checklist` 调用使用一个简短、描述性的文件名，并新建或追加同类 Checklist。
不同类型使用不同文件；应使用清晰类型名，并在适当时清理过时 Checklist，避免目录混乱。

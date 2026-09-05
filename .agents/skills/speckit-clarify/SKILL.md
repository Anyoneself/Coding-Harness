---
name: "speckit-clarify"
description: "通过最多五个高针对性问题识别当前功能 Spec 中规格不足的部分，并将答案写回 Spec。"
compatibility: "需要包含 .specify/ 目录的 spec-kit 项目结构"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/clarify.md"
---

## 用户输入

```text
$ARGUMENTS
```

如果用户输入不为空，继续之前**必须**考虑该输入。

## 执行前 Hook

检查 `.specify/extensions.yml` 中的 `hooks.before_clarify`：

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

## 目标

检测并减少当前功能 Spec 中的歧义和缺失决策点，将澄清结果直接记录到 Spec 文件。

此工作流应在 `$speckit-plan` **之前**运行并完成。如果用户明确跳过澄清（例如进行探索性
Spike），可以继续，但必须警告后续返工风险会增加。

## 执行步骤

1. 从仓库根目录只运行一次
   `.specify/scripts/bash/check-prerequisites.sh --json --paths-only`，解析 FEATURE_DIR 和
   FEATURE_SPEC；可选记录 IMPL_PLAN、TASKS。JSON 解析失败时中止，并提示重新运行
   `$speckit-specify` 或检查功能 Branch 环境。参数中包含单引号时（例如 "I'm Groot"），使用
   `'I'\''m Groot'`，也可在条件允许时使用双引号。

2. 如果存在，读取 `.specify/memory/constitution.md` 中的项目原则和治理约束。

3. 读取当前 Spec，并按以下分类扫描歧义和覆盖情况。每类标记为 Clear、Partial 或 Missing，
   建立内部覆盖 Map；除非无需提问，否则不要输出原始 Map。

   - **功能范围与行为**：核心用户目标、成功标准、明确排除项、角色/Persona 差异。
   - **Domain 与 Data Model**：Entity、属性、关系、身份与唯一性、生命周期/状态转换、
     数据规模假设。
   - **交互与 UX Flow**：关键 User Journey、错误/空/加载状态、无障碍和本地化。
   - **Non-Functional 属性**：性能、扩展性、可靠性/可用性、Observability、安全/隐私、
     合规约束。
   - **Integration 与外部依赖**：外部 Service/API 及失败模式、导入导出格式、Protocol/版本。
   - **Edge Case 与失败处理**：负向场景、Rate Limit/Throttle、并发冲突解决。
   - **约束与取舍**：语言、存储、托管等技术约束，以及明确取舍或被否决方案。
   - **术语与一致性**：标准术语、应避免的同义词或废弃词。
   - **完成信号**：验收标准的可测试性和可衡量 Definition of Done。
   - **其他/占位符**：TODO、未解决决策、缺少量化的“健壮”“直观”等模糊词。

   Partial 或 Missing 类别可生成候选问题，但如果答案不会实质改变实现或验证策略，或更适合
   Plan 阶段，应跳过并在内部记录。

4. 在内部生成最多五个候选澄清问题，并按优先级排序，不要一次全部输出：
   - 整个 Session 最多五个问题。
   - 每题必须能通过 2-5 个互斥选项回答，或限制为不超过五个词的短答案。
   - 只询问会实质影响架构、Data Model、任务拆分、测试设计、UX、运行准备或合规验证的问题。
   - 优先覆盖影响最大的未解决类别，避免用低影响问题挤占高影响问题。
   - 排除已回答内容、纯风格偏好和不阻塞正确性的 Plan 执行细节。
   - 超过五个未解决类别时，按“影响 × 不确定性”选前五个。

5. **逐题交互**：
   - 每次只展示一个问题。
   - 问题行必须为完整问句，以 `**Question:**` 开头并以 `?` 结束；可在问号后附
     `(FR-023)` 形式的 ID。不得用主题标签、章节名或 Requirement ID 代替问题。
   - 问题后先写一句通俗的“为什么重要”，再给建议和选项。
   - 多选题先给 `**Recommended:** Option [X] - <reasoning>`，再使用：

     ```markdown
     | Option | Description |
     |--------|-------------|
     | A | <Option A description> |
     | B | <Option B description> |
     | C | <Option C description> |
     | Short | Provide a different short answer (<=5 words) |
     ```

     然后说明用户可回复选项字母、`yes`/`recommended` 接受建议，或提供短答案。
   - 无适合选项时给出 `**Suggested:** <answer> - <reasoning>`，并要求不超过五个词；用户可用
     `yes`/`suggested` 接受。
   - 接受答案前验证其匹配选项或符合长度。歧义时快速追问，但不计为新问题。
   - 用户表示 `done`、`good`、`no more`，已解决全部关键歧义，或达到五题时停止。
   - 不得提前透露后续问题队列。开始时没有有效问题，则立即报告无关键歧义。

6. **每个答案接受后立即集成**：
   - 首次集成时确保存在 `## Clarifications`，并在其下创建
     `### Session YYYY-MM-DD`（今天日期）子标题。
   - 追加：`- Q: <question> → A: <final answer>`。
   - 将答案应用到最适合的章节：
     - 功能歧义 → Functional Requirements。
     - 用户交互或角色差异 → User Story 或 Actors。
     - 数据形状 → Data Model 的字段、类型、关系和约束。
     - Non-Functional 约束 → Success Criteria > Measurable Outcomes。
     - Edge Case/负向 Flow → Edge Cases 或 Error Handling。
     - 术语冲突 → 全文统一标准术语；必要时只保留一次
       `(formerly referred to as "X")`。
   - 新答案使旧陈述失效时，应替换旧陈述，不得保留矛盾重复内容。
   - 每次集成后原子覆盖保存 Spec，避免上下文丢失。
   - 不重排无关章节；保持标题层级；新增内容简洁、可测试。

7. **每次写入后及最终验证**：
   - 每个已接受答案在 Clarifications Session 中恰有一条记录。
   - 已接受问题不超过五个。
   - 新答案针对的模糊占位符已消除，旧冲突陈述已移除。
   - Markdown 结构有效；只允许新增 `## Clarifications` 和 `### Session YYYY-MM-DD`。
   - 所有更新章节使用一致的标准术语。

8. 将更新后的 Spec 写回 FEATURE_SPEC。

9. **重新验证内置 Spec 质量 Checklist**：
   - 仅在 `FEATURE_DIR/checklists/requirements.md` 存在时执行。
   - 读取代码块外所有匹配 `- [ ]`、`- [x]` 或 `- [X]` 的 Checkbox 行，记录原状态和文本。
   - 根据更新后的 Spec 重新评估每项：
     - 新通过项将 `[ ]` 改为 `[x]`。
     - 回归项将 `[x]`/`[X]` 改为 `[ ]`。
     - 状态不变时完全保留原 Marker 大小写。
   - 只修改状态发生变化的 Checkbox Marker；标题、Meta、Notes、顺序和空白必须保持不变。
   - 记录 Newly Passing、Regression、Still Unchecked，以及通过数的前后变化，例如
     `12/16 → 15/16`，供完成报告使用。

## 行为规则

- 没有值得正式澄清的关键歧义时，报告“未发现值得正式澄清的关键歧义”，并建议继续。
- Spec 不存在时，提示先运行 `$speckit-specify`，不要在此创建新 Spec。
- 澄清单个问题的重试不算新问题，但总问题数绝不能超过五个。
- 除非缺失信息阻塞功能清晰度，否则避免猜测性技术栈问题。
- 尊重用户的 `stop`、`done`、`proceed` 等提前终止信号。
- 无需提问时输出精简覆盖摘要，并建议进入下一阶段。
- 达到配额后仍有高影响问题时，在 Deferred 中明确列出并说明理由。

优先级上下文：$ARGUMENTS

## 强制执行后 Hook

向用户报告完成前，必须处理 `hooks.after_clarify`。规则与执行前 Hook 相同；每个强制 Hook
必须输出 `EXECUTE_COMMAND:`，实际调用并等待完成。可选 Hook 仅展示命令和 Prompt。

## 完成报告

提问结束或提前终止后报告：

- 已提问并回答的问题数量。
- 更新后的 Spec 路径和修改的章节。
- 如果重新验证了 `requirements.md`，报告通过数变化、Newly Passing、Regression 和仍未勾选项。
- 按分类列出覆盖摘要，状态使用 Resolved、Deferred、Clear、Outstanding。
- 存在 Outstanding 或 Deferred 时，建议现在进入 `$speckit-plan`，还是稍后再次运行
  `$speckit-clarify`。
- 建议的下一条命令。

## 完成条件

- [ ] 已识别 Spec 歧义并将澄清集成到文件
- [ ] 存在 `requirements.md` 时已重新验证
- [ ] 已按规则派发或跳过 Extension Hook
- [ ] 已报告问题、修改章节、Checklist 状态和覆盖摘要

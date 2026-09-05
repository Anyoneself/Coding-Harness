# Coding-Harness Spec Kit 前置流程

## 目标

GitHub Spec Kit 作为功能开发前置流程，将自然语言需求逐步固化为可评审的规格、计划和任务。
它不替代 `AGENTS.md`、产品路线、Gherkin、可执行测试或人工代码评审。

本仓库固定使用 Spec Kit `v1.0.4` 和 Codex Skills 集成。项目级规则由
`.specify/memory/constitution.md` 和 `coding-harness` Preset 提供。

## 首次准备

```bash
./scripts/setup-spec-kit.sh
```

脚本使用 `uv tool` 隔离安装固定版本，并重新物化当前仓库的 Codex Skills。执行脚本需要
访问 GitHub；日常执行已提交的 Skills 不需要重复安装。

## 适用范围

以下改动必须先执行完整前置流程：

- 新功能和用户可观察行为变化；
- API、Schema、CLI JSON 或持久化契约变化；
- 跨模块重构、权限、安全、幂等或工作流变化；
- 影响多个文件的非平凡缺陷修复。

纯文档修正、注释、格式化、无行为变化的重命名和已有规格内的单个机械任务可按
`AGENTS.md` 规定跳过完整流程。

## 标准流程

```text
$speckit-specify
$speckit-clarify
$speckit-plan
$speckit-checklist
$speckit-tasks
$speckit-analyze
```

`$speckit-analyze` 没有阻塞问题后，才进入：

```text
$speckit-implement
$speckit-converge
```

如果 `$speckit-converge` 追加任务，继续执行实现和收敛，直至报告已收敛或记录明确阻塞。

## 工件职责

| 位置 | 职责 |
| --- | --- |
| `AGENTS.md` | 仓库最高工程规则 |
| `.specify/memory/constitution.md` | Spec Kit 执行时必须读取的项目原则摘要 |
| `specs/<feature>/` | 单个功能的规格、计划、设计和执行任务 |
| `docs/pm/` | 产品级路线、长期架构和跨功能任务 |
| `tests/features/` | 与用户故事对应的 Gherkin 行为场景 |
| `.agents/skills/speckit-*` | 由 Spec Kit 物化的 Codex 工作流入口 |

需求变化采用 Living Spec：先更新 `spec.md`，再同步计划、任务、测试和实现。产品级任务
不复制到 Feature Spec；Feature Spec 通过现有任务 ID 或业务术语建立追踪关系。

## 质量门禁

- 生成任务中的测试不是可选项。
- 每个变化的业务行为先有 Gherkin，再有失败的可执行测试，最后实现。
- 计划必须使用仓库真实目录和分层，不保留 Spec Kit 通用示例路径。
- Blocking 分析结果必须回到对应规格、计划或任务修正，不能只在实现中绕过。
- 完成前运行受影响测试、`python -m unittest discover -s tests -v`、`ruff check .` 和适用的前端检查。
- 未经用户明确要求，不得生成 README 修改任务。

## 升级

升级 Spec Kit 前先在独立 worktree 中执行：

1. 安装候选固定版本。
2. 运行 `specify integration upgrade codex`。
3. 检查 `.specify/`、`.agents/skills/speckit-*` 和 Preset 的 Diff。
4. 运行配置契约测试、全量测试和静态检查。
5. 通过后同步修改 `scripts/setup-spec-kit.sh`、`.specify/init-options.json` 和本说明中的版本。

不要让安装脚本直接跟随 `main` 或未固定版本。

## 已知状态

`specify integration status` 会把由 `coding-harness` Preset 合成的 6 个核心 Skill
报告为 `managed-files-modified`。这是因为 Codex 集成清单记录核心 Skill 哈希，而 Preset
会有意重写 `specify`、`plan`、`tasks`、`analyze`、`implement` 和 `converge` 的最终内容。

出现该警告时先确认这些 Skill 的 frontmatter 包含
`source: preset:coding-harness`，不要直接执行
`specify integration upgrade codex --force`，否则可能暂时覆盖项目门禁。正常同步使用
`./scripts/setup-spec-kit.sh` 或 `specify integration use codex`。

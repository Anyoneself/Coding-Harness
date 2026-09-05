---
name: coding-harness-frontend
description: 设计、实现和审查 Coding-Harness Web 工作台前端；适用于 React/TypeScript、产品视觉、交互状态、Turn 事件流、响应式布局、可访问性、性能和浏览器验收，不适用于后端执行规则实现。
---

# Coding-Harness 前端开发

把 Web 界面设计成可信、克制而有辨识度的工程工作台，而不是套着侧栏的聊天页面，也不是
由渐变、圆角卡片和装饰文案拼成的 AI 产品模板。

## 按需读取

- 涉及接口、SSE、状态或工作台结构时，先读
  [references/workbench-contract.md](references/workbench-contract.md)。
- 涉及新页面、视觉重构、组件样式、空状态或动效时，读
  [references/design-craft.md](references/design-craft.md)。
- 涉及 React 架构、性能、可访问性、测试或交付验收时，读
  [references/frontend-quality.md](references/frontend-quality.md)。

## 工作流程

1. 阅读入口组件、状态归约、样式、测试和相关后端 Schema。列出当前真实数据、真实操作、
   仅可展示信息和禁止出现的入口，不以参考图或产品规划代替已实现契约。
2. 用一句话明确当前页面的用户与核心任务。视觉改动先提出两个明显不同的方向，比较它们与
   工程执行语境的关系，再选择一个并形成基础色、字体层级、空间节奏和唯一主视觉。
3. 缺陷修复先写回归测试；用户可观察行为变化先更新 `tests/features/` 场景，再补
   Vitest/Testing Library 测试。
4. 使用 React、TypeScript 和 Vite 修改 `frontend/`；API、事件归约、持久化和视图保持
   单向依赖，不在 `application/static/` 构建产物中手工维护业务逻辑。
5. 在真实浏览器中检查桌面与移动视口。视觉任务必须查看截图，并至少进行一次删减式复盘：
   去掉不承载信息的文案、容器、标签、阴影或动效。
6. 按改动风险验证：受影响的状态完整验收，未受影响的状态运行现有回归测试；涉及 Python
   静态资源集成时再运行对应后端测试。

## 产品与设计判断

- Harness 的主角是当前工程、持续任务、执行证据和下一步操作，模型品牌和“AI 感”不是主角。
- 从任务语境产生视觉语言，不从常见 AI 产品模板中抽取零件。
- 一个页面只花一次视觉预算：允许一个有记忆点的背景、输入器、时间线或状态转换，其余界面
  保持安静。装饰必须强化空间、层级或状态，否则删除。
- 操作型页面优先扫描效率、稳定布局和局部反馈；不做营销式 Hero，不用介绍性文案替代功能。
- 文案使用用户语言和明确动词。空状态说明下一步，错误信息说明恢复方法，不解释系统自我形象。
- 样式不是固定主题。保留现有品牌连续性，但允许根据任务重新判断明暗、密度、材质和视觉重心；
  不因 Skill 中出现某种示例就机械复制。
- 完成前做“替换 Logo”检查：如果替换产品名后界面仍可原样用于任意 AI 聊天产品，说明
  Harness 的工程语境还不够具体。

## 实现边界

- 业务资源统一使用 Workspace、Thread、Turn、Event；界面可中文化，但不得创造后端不存在的
  状态、统计、审批、Diff 或操作。
- API、SSE、localStorage 和 Markdown 都是不可信边界，先解析、验证、归一化或清洗再渲染。
- 组件按稳定职责拆分；优先组合与显式变体，避免用多个布尔参数制造隐蔽模式。
- 受改动影响的运行中、空、失败、断流、终态、未配置、提交中或窄屏状态必须有明确表现。
- 使用 Lucide 等现有图标库；图标按钮有可访问名称，键盘焦点始终可见。
- 新增依赖前确认平台能力和现有依赖不能合理完成，并同步锁文件。

## 完成验证

- `npm test`
- `npm run typecheck`
- `npm run build`
- 视觉或布局改动使用真实浏览器检查至少 `1440×900` 和 `390×844`。
- 对受影响流程检查键盘路径、焦点、长文本、空数据、错误、运行中和 reduced-motion。
- 接口或构建产物路径变化时，同步 Python 集成测试和打包配置；除非用户明确要求，不修改
  README。

## 设计来源

本 Skill 综合了 Anthropic `frontend-design`、`webapp-testing` 与 Vercel
`react-best-practices`、`composition-patterns`、`web-design-guidelines` 的有效原则，
并按 Coding-Harness 的本地执行契约重新组织；不要在任务中照搬上游页面风格或与本仓库无关的
框架规则。

# Implementation Plan: 参考图升级前端工作台

**Branch**: `001-refresh-workbench-ui` | **Date**: 2026-09-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-refresh-workbench-ui/spec.md`

## Summary

在不改变 Workspace、Thread、Turn、Event、API Key 和 SSE 契约的前提下，把现有 Web 控制台收敛为参考图式的“工程入口画布”：桌面端使用稳定左侧任务导航、居中顶部视图导航、浅蓝流光主画布和宽任务输入器；首条任务发送后，在同一框架内转换为以公开消息和执行状态为中心的阅读布局；执行事件与 Turn 继续通过按需检查器展示。

实现以 `frontend/` 为唯一源码，复用现有 React 组件、Lucide 图标和 `workbench-flow.webp`。重构范围集中在工作台组件结构、可访问状态和 `frontend/src/styles.css` 的相关规则，删除重复覆盖造成的级联冲突；构建后由 Vite 统一生成 `application/static/`，不手工维护构建产物。

## Technical Context

**Language/Version**: TypeScript 6、React 19；Python 3.11+ 仅用于现有 FastAPI 静态托管与集成验证

**Primary Dependencies**: React 19.2、React DOM、Vite 8、Vitest 5、Testing Library、Lucide React、Marked、DOMPurify；不新增依赖

**Storage**: 浏览器 `localStorage` 保存最多 30 个经过归一化的本地 Thread 摘要、公开消息、活动任务 ID 和 Workspace ID；本功能不改变存储结构

**Testing**: `tests/features/frontend-workbench.feature`、Vitest、Testing Library、现有 Python `unittest` 集成测试，以及真实浏览器桌面/移动截图与交互验收

**Target Platform**: 由 FastAPI 同源托管的现代桌面与移动浏览器，支持 320 像素及以上视口

**Project Type**: Python Web 服务中的独立 React/Vite 前端

**Performance Goals**: 输入、发送、中断和导航交互不因装饰背景产生可感知延迟；流式回答持续更新时输入器与主布局保持稳定；抽屉和必要状态动画保持流畅，减少动态效果模式下立即降级

**Constraints**: 不新增或修改后端 API；不伪造多项目、分支、评估、工具、搜索、账户、模型切换、Diff 或 Verification；API Key 与隐藏推理不得进入浏览器持久化或公开界面；`npm run build` 会清空并重写 `application/static/`

**Scale/Scope**: 一个工作台页面、六个现有区域组件、一套客户端状态模型、一个现有背景资产、三个主要响应式断点和五类核心界面状态

## Constitution Check

*GATE: Phase 0 前检查通过；Phase 1 设计完成后再次检查通过。*

| Gate | Phase 0 前 | Phase 1 后 | 说明 |
|------|------------|------------|------|
| AGENTS.md 是最高约束 | PASS | PASS | 只规划前端职责与生成静态资源，不修改分层或 README |
| 先定义行为再实现 | PASS | PASS | Spec 已完成并澄清视觉还原标准，所有设计映射到 FR 与 User Story |
| 测试先行 | PASS | PASS | 先更新 Gherkin，再补 Vitest/Testing Library，最后实现并做浏览器验收 |
| 分层与契约一致 | PASS | PASS | HTTP/SSE、Domain 归约和 localStorage 规则保持现状；组件只负责展示与交互 |
| 安全、可审查、可验证 | PASS | PASS | 不公开密钥、隐藏推理或内部错误；构建产物、截图和测试结果均可审查 |
| 新依赖与新抽象有现实需求 | PASS | PASS | 复用现有依赖和组件，无新运行时依赖或预留抽象 |

不存在需要例外说明的 Constitution 违规。

## Project Structure

### Documentation (this feature)

```text
specs/001-refresh-workbench-ui/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── workbench-ui.md
└── tasks.md                 # 由后续 $speckit-tasks 生成
```

### Source Code (repository root)

```text
frontend/
├── index.html
├── public/
│   ├── favicon.svg
│   └── workbench-flow.webp
└── src/
    ├── api/
    │   ├── harness.ts
    │   ├── sse.ts
    │   └── sse.test.ts
    ├── components/
    │   ├── ApiKeyDialog.tsx
    │   ├── App.tsx
    │   ├── App.test.tsx
    │   ├── Composer.tsx
    │   ├── Inspector.tsx
    │   ├── MessageList.tsx
    │   ├── Sidebar.tsx
    │   └── TopNavigation.tsx
    ├── domain/
    │   ├── chat.ts
    │   ├── chat.test.ts
    │   ├── events.ts
    │   ├── events.test.ts
    │   └── types.ts
    ├── lib/
    │   ├── markdown.ts
    │   └── markdown.test.ts
    ├── test/
    │   └── setup.ts
    ├── main.tsx
    └── styles.css

application/
├── app.py                   # 继续同源托管生成后的静态资源
└── static/                  # npm run build 生成，不手工编辑

tests/
├── features/
│   └── frontend-workbench.feature
└── integration/
    ├── test_api_key_configuration.py
    └── test_execution_http.py
```

**Structure Decision**: 保留当前 Python Web 服务与独立 React 源码结构。工作台行为继续由 `App.tsx` 编排，HTTP/SSE 留在 `api/`，事件和本地历史规则留在 `domain/`，区域展示留在现有组件。除非测试证明现有组件职责无法表达，不新增页面层、状态 Provider 或通用设计系统。

## Implementation Strategy

### 1. 行为规格与失败测试

先把 Spec 中尚未完全落入现有 Gherkin 的行为写入 `tests/features/frontend-workbench.feature`，覆盖运行中任务管理禁用、配置读取失败、非终态断流、背景降级、长内容、键盘路径和减少动态效果。

随后在现有测试文件中补充可执行失败测试：

- `App.test.tsx`: 空状态真实上下文、禁止虚假入口、空状态到执行态、运行中中断、任务管理禁用、检查器同步、配置失败和可访问名称。
- `sse.test.ts` / `events.test.ts`: 非终态断流所需的事件终态判定、重复/倒序/未知事件和最终收敛。
- `chat.test.ts`: 继续保护不可信本地历史、数量上限和旧记录兼容。
- Python 集成测试仅在构建产物或公开接口断言需要同步时修改，不为纯视觉行为扩张后端测试。

### 2. 工作台状态与组件

- `App.tsx` 继续拥有活动任务、执行、配置、导航和抽屉状态；不引入新的全局状态层。
- `MessageList.tsx` 明确区分空任务入口和执行阅读流，删除不承载下一步操作的说明性文案。
- `Composer.tsx` 保持同一发送/中断主操作位置，空状态采用宽入口变体，执行态收敛到阅读宽度；项目、Workspace 和模型只展示真实值。
- `Sidebar.tsx` 保持任务历史、当前项目和连接状态，活动项同时使用语义属性、图标/文字和视觉状态。
- `TopNavigation.tsx` 仅保留工作台、执行事件、Turn，并继续驱动现有 Inspector 标签。
- `Inspector.tsx` 在桌面和移动端均使用按需覆盖式布局，补齐焦点与关闭路径所需语义。

### 3. 视觉系统与响应式布局

- 选择“冷静、通透、精密”的工程入口方向。
- 使用 `workbench-flow.webp` 作为唯一主视觉资产；不增加光球、粒子、持续漂移动画或第二套背景。
- 色彩限定为冰蓝画布、冷白表面、深蓝正文、灰蓝次要文字、蓝灰边界、工程蓝强调色，并保留独立状态色。
- 整理 `styles.css` 中与工作台相关的基础规则和后续重复覆盖，形成单套 Token、状态变体和断点级联；不进行无关 Markdown 或对话框样式重写。
- `>1180px` 固定任务侧栏，检查器覆盖；`761–1180px` 保留侧栏并压缩画布间距；`≤760px` 两侧区域均为独立抽屉；`≤560px` 收敛顶部信息和次要上下文。
- 矮屏桌面单独降低空状态垂直间距和输入器高度，确保主输入器留在首屏。
- `prefers-reduced-motion` 下停止等待点位移和抽屉过渡，不改变任何状态或操作。

### 4. 构建与静态托管

- 所有源码修改只发生在 `frontend/` 和对应测试/行为规格。
- 完成源码测试后运行 `npm run build`，由 Vite 重写 `application/static/index.html`、`app.js`、`styles.css` 和公开资产。
- 验证构建没有产生未被 `pyproject.toml` 包含的必要嵌套资源；若产生，应优先调整现有构建输出，避免无需求扩大 Python 打包规则。
- 通过 FastAPI 同源服务进行最终浏览器验收，不使用缺少 `/api` 代理的 Vite 开发服务作为端到端结论。

## Verification Strategy

### Gherkin

- 每个 User Story 至少对应一个可观察 Given/When/Then 场景。
- 失败路径包含配置读取失败、任务/Turn 创建失败、中断失败、非终态事件流结束和背景资源失败。

### Automated Tests

```bash
npm test
npm run typecheck
npm run build
python -m unittest discover -s tests -v
ruff check .
```

测试使用 Fake Provider、模拟 `fetch`、受控 ReadableStream、隔离的 localStorage 和固定时间，不访问公网或真实模型。

### Browser Acceptance

- 在 `1680×941`、`1024×768`、`390×844` 和最小 `320px` 宽度检查空状态、执行态、检查器、移动抽屉、配置对话框与连接错误。
- 截图确认参考图的六个核心视觉信号可辨认，但不做像素级相等断言。
- 检查页面级横向溢出、控件遮挡、长项目/模型/任务/错误文本、发送与中断尺寸稳定、抽屉焦点与退出路径。
- 使用键盘走通新建、输入、发送或中断、打开和关闭两侧区域。
- 启用 reduced-motion 后确认业务状态不丢失、非必要动画停止。
- 检查浏览器控制台和网络面板，无新增错误、未处理 Promise rejection 或缺失关键资源。

### Final Review

对桌面和移动截图进行一次删减式复盘，移除不承载项目上下文、执行状态或下一步操作的文案、标签、阴影和装饰。最终界面应明显属于 Coding-Harness 工程工作台，而不是替换 Logo 后仍成立的通用聊天产品。

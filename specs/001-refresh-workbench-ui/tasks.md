---

description: "参考图升级 Coding-Harness 前端工作台的可执行任务列表"
---

# Tasks: 参考图升级前端工作台

**Input**: `specs/001-refresh-workbench-ui/` 下的 `spec.md`、`plan.md`、`research.md`、`data-model.md`、`contracts/workbench-ui.md` 和 `quickstart.md`

**Prerequisites**: Spec 与 Plan 已完成；自定义 `checklists/ux.md` 需要 Reviewer 审查通过后才能进入实现

**Tests**: 本仓库强制测试先行。每个 User Story 必须先更新 Gherkin，再编写会因目标行为缺失而失败的可执行测试，最后修改生产代码。

**Organization**: 任务按 User Story 分阶段组织。Story 可以独立验收，但因共享 `App.test.tsx` 和 `styles.css`，单人实施时应按 US1 → US2 → US3 → US4 顺序执行。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 修改不同文件且不依赖同阶段未完成任务，可并行执行
- **[Story]**: 对应 `spec.md` 的 `[US1]`、`[US2]`、`[US3]`、`[US4]`
- 每项任务均包含精确仓库路径

## Phase 1: Setup

**Purpose**: 解除需求门禁并建立改动前基线

- [X] T001 由 Reviewer 审查 `specs/001-refresh-workbench-ui/checklists/ux.md`，将发现的问题先修正到 `specs/001-refresh-workbench-ui/spec.md`、`specs/001-refresh-workbench-ui/plan.md` 或 `specs/001-refresh-workbench-ui/contracts/workbench-ui.md`，并在确认需求质量后完成 Checkbox
- [X] T002 [P] 对 `frontend/src/` 运行现有 `npm test` 与 `npm run typecheck` 建立基线，若存在与本功能无关的失败则在 `specs/001-refresh-workbench-ui/tasks.md` 对应任务下注明而不修改无关代码

**Checkpoint**: 自定义 Checklist 已通过，现有前端测试与类型检查基线明确

---

## Phase 2: Foundational

**Purpose**: 清理所有 Story 共用的样式和测试基础，后续不得继续叠加冲突覆盖

**CRITICAL**: 本阶段完成前不得开始 User Story 的生产实现

- [X] T003 根据 `specs/001-refresh-workbench-ui/research.md` 的 CSS 决策，合并 `frontend/src/styles.css` 中重复的工作台 Token、布局和响应式覆盖，保持现有可观察行为并删除“流光玻璃工作台视觉层”“参考图版式对齐”之间的冲突定义
- [X] T004 [P] 在 `frontend/src/components/App.test.tsx` 整理可复用的公开配置、任务历史和 Fetch/SSE 测试准备代码，使后续 Story 能独立模拟 ready、unconfigured、HTTP 失败和流式执行状态
- [X] T005 [P] 在 `frontend/src/domain/events.test.ts` 补齐终态集合与未知事件保留的基线断言，确保后续断流处理不会改变现有事件归约契约

**Checkpoint**: 单套工作台样式级联和可复用测试基线已就绪，现有测试仍通过

---

## Phase 3: User Story 1 - 从品牌空状态发起任务 (Priority: P1) MVP

**Goal**: 用户在模型已就绪的空 Thread 中看到参考图式工程入口，并通过真实项目与模型上下文直接发起任务

**Independent Test**: 在公开配置 ready 且任务无消息时打开工作台，确认六个核心视觉信号、真实项目与模型、唯一输入入口和发送流程；在未配置或配置读取失败时确认安全引导与失败反馈

### Tests for User Story 1

- [X] T006 [US1] 在 `tests/features/frontend-workbench.feature` 先补充空状态真实上下文、禁止伪造分支/模型选择、首次发送过渡、配置未就绪和配置读取失败场景
- [X] T007 [US1] 在 `frontend/src/components/App.test.tsx` 添加 US1 可执行测试，覆盖真实项目/模型、无假入口、Enter 发送、Shift+Enter 换行、未配置打开对话框和配置读取失败；运行目标测试并确认其在生产实现前按预期失败

### Implementation for User Story 1

- [X] T008 [P] [US1] 调整 `frontend/src/components/MessageList.tsx` 的空任务入口，只保留品牌标识、真实项目和任务导向标题，移除不承载下一步操作的说明文案
- [X] T009 [P] [US1] 调整 `frontend/src/components/Composer.tsx` 的空状态上下文与主操作，保持真实项目、Workspace 边界、只读模型名称、20,000 字符限制和稳定发送/中断按钮位置
- [X] T010 [US1] 在 `frontend/src/components/App.tsx` 收敛 empty-ready、empty-unconfigured 和 connection-failed 的派生表现，保持现有 Workspace/Thread/Turn 创建与 API Key 安全流程
- [X] T011 [US1] 在 `frontend/src/styles.css` 实现工程入口画布：浅蓝流光背景、首屏品牌层级、宽输入器、冷静通透的视觉 Token，以及背景资源失败时仍成立的静态冰蓝画布
- [X] T012 [US1] 运行 `frontend/src/components/App.test.tsx` 和 `tests/features/frontend-workbench.feature` 对应 US1 场景，确认空状态入口可独立通过且未改变 API Key 不落 localStorage 的要求

**Checkpoint**: US1 可作为 MVP 独立演示，用户能从参考图式空状态安全发起任务

---

## Phase 4: User Story 2 - 在统一框架中浏览与管理任务 (Priority: P2)

**Goal**: 用户通过稳定 Sidebar 新建、识别、选择和移除最近任务，并始终确认当前唯一 Workspace

**Independent Test**: 使用多个合法本地任务记录，在非运行态完成新建、切换和移除；在运行态确认相关操作具有明确禁用状态且当前任务仍可观察和中断

### Tests for User Story 2

- [X] T013 [US2] 在 `tests/features/frontend-workbench.feature` 先补充任务分组、活动项非颜色状态、移除最后任务、单 Workspace 和运行中任务管理禁用场景
- [X] T014 [US2] 在 `frontend/src/components/App.test.tsx` 添加 US2 可执行测试，覆盖任务新建/切换/移除、活动项语义、运行中禁用原因和移动端选择后关闭 Sidebar；运行目标测试并确认其在生产实现前按预期失败
- [X] T015 [P] [US2] 在 `frontend/src/domain/chat.test.ts` 增加长标题、多字节标题、旧格式记录和最多 30 个任务分组排序边界测试，确认新增断言在规则缺失处先失败

### Implementation for User Story 2

- [X] T016 [P] [US2] 在 `frontend/src/domain/chat.ts` 完善 US2 测试所需的标题归一化、历史分组或兼容边界，只保留公开任务数据且继续拒绝敏感字段
- [X] T017 [US2] 在 `frontend/src/components/Sidebar.tsx` 明确活动任务、禁用原因、任务状态、当前唯一项目和连接状态的语义，不增加多项目或项目切换入口
- [X] T018 [US2] 在 `frontend/src/components/App.tsx` 保持运行中任务操作的一致禁用与状态连续性，确保选择、移除和新建不会静默产生歧义结果
- [X] T019 [US2] 在 `frontend/src/styles.css` 完成参考图式 Sidebar 层级、最近任务扫描密度、活动项非颜色提示、长文本截断和桌面固定/移动抽屉表现
- [X] T020 [US2] 运行 `frontend/src/components/App.test.tsx`、`frontend/src/domain/chat.test.ts` 和 `tests/features/frontend-workbench.feature` 对应 US2 场景，确认任务导航可独立通过

**Checkpoint**: US2 独立可用，任务历史与当前项目清晰且不会破坏运行中的 Turn

---

## Phase 5: User Story 3 - 查看执行态与检查器 (Priority: P2)

**Goal**: 首条任务发送后在同一工作台进入稳定执行阅读态，并按需查看 Event 或 Turn 信息

**Independent Test**: 使用受控 SSE 运行一个 Turn，确认公开消息、状态、中断、非终态断流失败以及 Event/Turn Inspector 的打开、切换和关闭不会丢失状态或压缩主画布

### Tests for User Story 3

- [X] T021 [US3] 在 `tests/features/frontend-workbench.feature` 先补充空状态到执行态、运行中主操作中断、Inspector 状态连续性、中断失败和非终态 SSE 结束场景
- [X] T022 [US3] 在 `frontend/src/components/App.test.tsx` 添加 US3 可执行测试，覆盖流式回答、终态持久化、部分回答断流失败、中断请求、Inspector 标签同步与关闭后状态保留；运行目标测试并确认其在生产实现前按预期失败
- [X] T023 [P] [US3] 在 `frontend/src/domain/events.test.ts` 增加 waiting_approval、failed、interrupted、cancelled、迟到事件和公开错误收敛测试，确认失败路径断言先于实现
- [X] T024 [P] [US3] 在 `frontend/src/api/sse.test.ts` 增加未知事件、多 data 行、尾块和畸形 JSON 边界测试，保证断流处理不破坏 SSE Parser

### Implementation for User Story 3

- [X] T025 [US3] 在 `frontend/src/components/App.tsx` 将非终态 SSE 结束转换为公开连接失败，保留已接收内容但不把部分回答持久化为成功，并保持中断失败后的当前执行
- [X] T026 [P] [US3] 在 `frontend/src/components/MessageList.tsx` 完成执行阅读流、公开错误和 live region 表现，避免逐 Token 重复播报或暴露非公开内容
- [X] T027 [P] [US3] 在 `frontend/src/components/Composer.tsx` 完成执行态收敛、稳定按钮尺寸和明确中断语义，不允许同一 Thread 并发提交
- [X] T028 [P] [US3] 在 `frontend/src/components/TopNavigation.tsx` 与 `frontend/src/components/Inspector.tsx` 完成工作台/Event/Turn 同步、覆盖式打开关闭、可访问标签和状态保留
- [X] T029 [US3] 在 `frontend/src/styles.css` 完成执行态背景降噪、消息阅读宽度、底部 Composer、覆盖式 Inspector、状态色与长事件文本表现
- [X] T030 [US3] 运行 `frontend/src/components/App.test.tsx`、`frontend/src/domain/events.test.ts`、`frontend/src/api/sse.test.ts` 和 `tests/features/frontend-workbench.feature` 对应 US3 场景，确认执行态与检查器可独立通过

**Checkpoint**: US3 独立可用，持续 Turn 可观察、可中断、可检查且不会把断流误报为成功

---

## Phase 6: User Story 4 - 在不同视口下完成核心流程 (Priority: P3)

**Goal**: 桌面、笔记本、移动和最小宽度下均可完成输入、观察、抽屉访问和中断，不发生横向溢出或遮挡

**Independent Test**: 在 1680×941、1024×768、390×844 和 320 像素宽度走通核心流程，并启用 reduced-motion、长文本和背景资源失败条件

### Tests for User Story 4

- [X] T031 [US4] 在 `tests/features/frontend-workbench.feature` 先补充四类验收视口、独立移动抽屉、长文本、键盘焦点、reduced-motion、矮屏桌面和背景资源失败场景
- [X] T032 [US4] 在 `frontend/src/components/App.test.tsx` 添加 US4 可执行 DOM 契约测试，覆盖两个抽屉独立控件、`aria-hidden`、活动导航、图标按钮名称和关闭后输入草稿保留；运行目标测试并确认其在生产实现前按预期失败

### Implementation for User Story 4

- [X] T033 [US4] 在 `frontend/src/components/App.tsx`、`frontend/src/components/Sidebar.tsx` 和 `frontend/src/components/Inspector.tsx` 完成抽屉互斥、关闭路径与焦点恢复所需的显式状态和语义
- [X] T034 [US4] 在 `frontend/src/styles.css` 完成 `>1180px`、`761–1180px`、`≤760px`、`≤560px` 和矮屏桌面的单套响应式规则，保证 320 像素宽度无页面级横向溢出
- [X] T035 [US4] 在 `frontend/src/styles.css` 完成 `prefers-reduced-motion` 静态替代，停止等待点位移和抽屉过渡，同时保留运行状态、焦点和全部操作
- [X] T036 [US4] 按 `specs/001-refresh-workbench-ui/quickstart.md` 在 1680×941、1024×768、390×844 和 320 像素宽度完成 US4 浏览器验收，检查长项目/模型/任务/错误文本、背景失败、键盘路径和控制台错误

**Checkpoint**: US4 独立通过，所有目标视口和辅助设置下核心任务流程可达

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 完成构建、全量回归、安全审查和最终视觉删减

- [X] T037 [P] 扫描 `frontend/src/components/` 与 `frontend/src/styles.css`，移除不承载真实项目上下文、执行状态或下一步操作的说明文案、重复容器、阴影和装饰，并保持所有修改函数具有中文文档字符串与完整类型
- [X] T038 [P] 审查 `frontend/src/domain/chat.ts`、`frontend/src/domain/events.ts`、`frontend/src/lib/markdown.ts` 和 `frontend/src/components/ApiKeyDialog.tsx` 的不可信输入与敏感信息边界，确认 API Key、隐藏推理、内部堆栈和完整本机路径不会进入公开界面或 localStorage
- [X] T039 运行 `npm test` 与 `npm run typecheck`，覆盖 `frontend/src/` 全部前端行为和严格类型检查
- [X] T040 运行 `npm run build`，由 `vite.config.ts` 生成 `application/static/index.html`、`application/static/app.js`、`application/static/styles.css` 和 `application/static/workbench-flow.webp`，不得手工编辑构建产物
- [X] T041 [P] 运行 `python -m unittest discover -s tests -v`，验证 `tests/integration/test_api_key_configuration.py`、`tests/integration/test_execution_http.py` 和其余后端回归
  - 2026-09-05：命令已执行；本功能相关 Integration 回归通过，另有 2 个既有 Spec Kit 配置测试因当前 `AGENTS.md` 与技能文案不匹配而失败，未修改无关文件。
- [X] T042 [P] 运行 `ruff check .`，确认 Python 静态检查无新增问题
- [X] T043 按 `specs/001-refresh-workbench-ui/quickstart.md` 通过 FastAPI 同源服务完成桌面与移动最终截图复盘，检查六个核心视觉信号、背景资源、网络、控制台、焦点、溢出和遮挡
- [X] T044 对照 `specs/001-refresh-workbench-ui/spec.md`、`specs/001-refresh-workbench-ui/contracts/workbench-ui.md` 和 `tests/features/frontend-workbench.feature` 复核全部需求追踪；仅在实际行为变化时同步相关架构或示例文档，不修改 `README.md`
- [X] T045 执行 `$speckit-converge`，对照 `specs/001-refresh-workbench-ui/tasks.md`、代码、测试和构建产物追加遗漏任务，直至功能收敛或记录明确阻塞

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: 无代码依赖；T001 的 Reviewer 门禁必须先完成
- **Phase 2 Foundational**: 依赖 Phase 1，阻塞全部 User Story 生产实现
- **Phase 3 US1**: 依赖 Phase 2，建议作为 MVP 首先完成
- **Phase 4 US2**: 逻辑上只依赖 Phase 2，但与 US1 共享 `App.test.tsx` 和 `styles.css`，单人实施建议在 US1 后执行
- **Phase 5 US3**: 逻辑上只依赖 Phase 2，但最终执行布局建立在统一空状态与 Sidebar 框架上，建议在 US1、US2 后集成
- **Phase 6 US4**: 依赖所选 Story 的最终 DOM 与视觉结构，完整交付时在 US1–US3 后执行
- **Phase 7 Polish**: 依赖计划交付的所有 User Story

### User Story Dependencies

- **US1 (P1)**: Foundation 完成后可独立实现和验收，是建议 MVP
- **US2 (P2)**: 使用现有 Thread 本地历史，可独立验收；不依赖新增后端能力
- **US3 (P2)**: 使用现有 Turn/Event/SSE，可独立验收；不依赖 US2 数据变化
- **US4 (P3)**: 响应式规则需要应用到最终选择交付的 US1–US3 界面结构

### Within Each User Story

1. 更新 `tests/features/frontend-workbench.feature`
2. 编写可执行测试并确认因目标行为缺失而失败
3. 修改 Domain/API 边界（仅该 Story 需要时）
4. 修改组件行为和语义
5. 修改视觉与响应式样式
6. 运行 Story 定向测试并独立验收

## Parallel Opportunities

- T004 与 T005 修改不同测试文件，可并行
- US1 的 T008 与 T009 修改不同组件，可在 T007 失败测试完成后并行
- US2 的 T015 可与 T014 并行，T016 可在 T015 后与 T017 并行
- US3 的 T023 与 T024 可并行；T026、T027、T028 修改不同组件，可在 T022–T024 后并行
- Phase 7 的 T037 与 T038 可并行；T041 与 T042 可在构建完成后并行
- 不并行修改 `frontend/src/components/App.test.tsx` 或 `frontend/src/styles.css`

## Parallel Example: User Story 3

```text
Task T023: 在 frontend/src/domain/events.test.ts 增加 Turn 失败与终态边界测试
Task T024: 在 frontend/src/api/sse.test.ts 增加 SSE Parser 边界测试

完成 T022–T024 后：

Task T026: 在 frontend/src/components/MessageList.tsx 完成执行阅读流
Task T027: 在 frontend/src/components/Composer.tsx 完成执行态输入器
Task T028: 在 frontend/src/components/TopNavigation.tsx 与 frontend/src/components/Inspector.tsx 完成检查器交互
```

## Implementation Strategy

### MVP First

1. 完成 T001–T005，解除需求门禁并建立共同基础
2. 完成 T006–T012，仅交付 US1
3. 停止并按 US1 Independent Test 验收
4. 通过后再决定是否继续任务导航、执行态和完整响应式

### Incremental Delivery

1. **US1**: 参考图式空任务入口可用于发起任务
2. **US2**: Sidebar 支持持续任务历史与安全管理
3. **US3**: 执行阅读流与 Inspector 形成完整 Turn 观察控制
4. **US4**: 所有目标视口、键盘和 reduced-motion 条件达到交付标准
5. **Polish**: 构建、全量测试、安全复核、截图删减和 Converge

## Notes

- `[P]` 仅表示文件级并行安全，不表示可以跳过依赖
- 测试任务必须在生产实现前完成，并先证明目标行为尚未实现
- `application/static/` 只由 `npm run build` 生成
- 不添加 README 修改任务
- 每个 Checkpoint 都可作为独立评审与暂停点

# UX Requirements Checklist: 参考图升级前端工作台

**Purpose**: 供 PR Reviewer 审查工作台视觉、交互、响应式、无障碍与失败降级需求是否完整、清晰、一致且可衡量
**Created**: 2026-09-05
**Feature**: [spec.md](../spec.md)

**Note**: 本清单由 `$speckit-checklist` 根据当前 Spec、Plan 和 UI Contract 生成。
**Review Ownership**: 本清单是 Reviewer 所有的需求质量审查产物；只有 Reviewer 判定标准满足后才可标记 `[x]`。
**Marker Semantics**: `[x]` 表示需求文本质量已通过审查，不表示实现工作已经完成。

## 需求完整性

- [x] CHK001 是否完整定义了空任务、配置未就绪、执行中、执行终态和连接失败五类工作台状态各自必须出现与退出的内容？[Completeness, Spec §FR-019, Data Model §WorkbenchPresentation]
- [x] CHK002 是否明确列出参考图六个核心视觉信号在空状态与执行态中的保留、弱化或移除规则？[Completeness, Spec §SC-005, Plan §视觉系统与响应式布局]
- [x] CHK003 是否为 Sidebar、顶部导航、主画布、Composer 和 Inspector 分别定义了信息职责与禁止承载的内容？[Completeness, Spec §FR-002–FR-010, Contract §2–§7]
- [x] CHK004 是否明确规定任务历史中标题、状态、分组、活动项和移除入口的最小信息集合？[Completeness, Spec User Story 2, Contract §3]
- [x] CHK005 是否说明配置读取中、模型名称缺失和 Workspace 路径无法派生项目名时应使用的具体展示文案或回退值？[Gap, Spec Edge Cases, Data Model §Workspace]
- [x] CHK006 是否为运行中被禁用的新建、切换和移除任务操作定义了可感知的原因说明，而不只是“保持禁用”？[Gap, Spec §FR-009, Failure Behavior]

## 需求清晰度

- [x] CHK007 “设计语言对齐”是否通过必须保留的视觉信号、允许调整的细节和禁止复制的假能力形成明确边界？[Clarity, Spec §Clarifications, §SC-005, Assumptions]
- [x] CHK008 “位于首屏视觉中心”的输入器要求是否具有足够明确的相对位置或可见性判定，避免不同实现产生相反布局？[Ambiguity, Spec User Story 1 Scenario 1]
- [x] CHK009 “足够操作空间”“清晰可读”“稳定层级”等描述是否均有视口、对比、遮挡或可达性标准支撑？[Clarity, Spec User Story 4, §FR-014, §SC-002]
- [x] CHK010 输入器从空状态宽入口收敛到执行阅读宽度时，是否明确哪些尺寸必须稳定、哪些尺寸允许变化？[Clarity, Spec §FR-007–FR-009, Contract §5–§6]
- [x] CHK011 “降低执行态背景对比度”是否定义了正文、状态和控件仍需满足的可读性结果？[Clarity, Spec User Story 3 Scenario 2, Research §决策 3]
- [x] CHK012 “适合鼠标和触摸操作”是否包含可评审的最小目标尺寸或等价可操作标准？[Measurability, Spec §FR-014]

## 需求一致性

- [x] CHK013 Spec、Plan、Data Model 与 UI Contract 是否一致使用 Workspace、Thread、Turn、Event 和 Inspector，且没有引入 Session、Conversation 或 Run 同义词？[Consistency, Contract §1]
- [x] CHK014 顶部导航的“工作台”“执行事件”“Turn”与 Inspector 标签、打开状态和关闭结果是否在所有文档中一致？[Consistency, Spec §FR-004, §FR-010, Contract §2, Data Model §WorkbenchView]
- [x] CHK015 “单 Workspace”约束是否与 Sidebar 的项目区域、Composer 上下文和 Out of Scope 中的多项目排除保持一致？[Consistency, Spec §FR-003, §FR-006, Compatibility Boundaries]
- [x] CHK016 模型名称的只读展示要求是否与禁止模型切换、未就绪状态和长名称截断规则保持一致？[Consistency, Spec §FR-005–FR-006, Edge Cases, Contract §5]
- [x] CHK017 发送与中断共用主操作位置的要求是否与运行中禁止并发 Turn、输入器禁用和失败反馈保持一致？[Consistency, Spec §FR-009, Contract §3, §5]
- [x] CHK018 背景采用静态主视觉的规划决定是否与 Spec 中“静态或轻量动态”假设存在需要消除的范围差异？[Conflict, Spec Assumptions, Research §决策 3]

## 验收标准质量

- [x] CHK019 SC-001 的“首次使用者”是否定义了样本条件、任务起点和成功判定，以便 90% 指标可重复评审？[Measurability, Spec §SC-001]
- [x] CHK020 SC-002 的“核心任务流程”是否明确包含哪些操作与状态，避免只对静态空状态判定无溢出？[Measurability, Spec §SC-002, §FR-019]
- [x] CHK021 SC-003 的“一次操作”和“两次操作”是否明确从哪个界面状态开始计数？[Clarity, Spec §SC-003]
- [x] CHK022 SC-004 的 20 次重复验收是否说明需覆盖哪些任务状态、输入内容或事件结果？[Measurability, Spec §SC-004]
- [x] CHK023 SC-005 是否把“可辨认”转化为 Reviewer 能一致判断的视觉存在性与层级标准？[Measurability, Spec §SC-005]
- [x] CHK024 SC-006 的键盘流程是否明确包含焦点进入抽屉、返回触发控件和对话框退出路径？[Coverage, Spec §SC-006, Contract §10]

## 场景覆盖

- [x] CHK025 是否同时覆盖首次进入空任务、从历史任务进入执行态和移除最后一个任务后返回空状态三种 Primary/Alternate 入口？[Coverage, Spec User Story 1–2]
- [x] CHK026 是否定义从“执行事件”切换到“Turn”、再返回“工作台”时 Inspector、活动导航和 ExecutionState 的连续性？[Coverage, Spec User Story 3, Contract §2, §7]
- [x] CHK027 是否覆盖 API Key 对话框打开期间 Sidebar、顶部导航、Composer 和焦点的交互优先级？[Gap, Spec User Story 1 Scenario 4, Contract §8]
- [x] CHK028 是否覆盖用户输入尚未发送时打开和关闭 Sidebar 或 Inspector 后草稿保留的要求？[Gap, Spec User Story 3 Scenario 4, Contract §7]
- [x] CHK029 是否覆盖 Turn 运行中 Inspector 已打开、随后中断成功或失败时的状态和可操作入口？[Coverage, Spec User Story 3 Scenario 5, Contract §8]

## Edge Case 与恢复

- [x] CHK030 是否为非终态 SSE 结束定义了部分回答、任务状态、重试提示和后续可操作性的完整恢复要求？[Resilience, Research §决策 7, Contract §8]
- [x] CHK031 是否为背景资源失败定义了无需该资源即可成立的颜色、对比和层级最低要求？[Resilience, Spec §FR-016, Contract §8]
- [x] CHK032 是否为超长项目名、模型名、任务名、消息、事件类型和错误文本分别规定截断、换行或滚动策略？[Completeness, Spec Edge Cases, Contract §9]
- [x] CHK033 是否说明重复、倒序、未知和终态后迟到事件对可见状态、事件数量和消息内容的统一处理要求？[Coverage, Spec Edge Cases, Data Model §ActivityEvent]
- [x] CHK034 是否定义 320 像素宽度与矮屏桌面同时出现时的优先布局和仍必须可达的操作？[Gap, Spec §FR-012, Plan §视觉系统与响应式布局]

## Non-Functional Requirement

- [x] CHK035 是否为浅蓝背景、半透明表面、焦点、正文和状态色定义可客观评审的颜色对比要求？[Gap, Spec §FR-013–FR-014]
- [x] CHK036 是否明确 reduced-motion 下哪些动画必须停止、哪些状态反馈必须保留，以及静态替代如何表达运行中？[Clarity, Spec §FR-015, Plan §视觉系统与响应式布局]
- [x] CHK037 是否为高频 SSE 更新期间的布局稳定和输入响应定义用户可感知的性能阈值？[Gap, Plan §Performance Goals]
- [x] CHK038 是否完整定义 API Key、隐藏推理、本机路径和第三方错误在导航、消息、Inspector、持久化与截图中的披露边界？[Security, Spec §FR-018, Constitution §V]

## 依赖、假设与冲突

- [x] CHK039 是否明确 `workbench-flow.webp` 是必需品牌资产还是可选增强，从而使资源缺失与打包要求不互相矛盾？[Assumption, Research §决策 3, Quickstart §3]
- [x] CHK040 是否说明不新增视觉测试依赖时，由谁在何时按哪些截图与浏览器条件完成需求评审？[Ownership, Plan §Browser Acceptance, Quickstart §9]

## Notes

- 所有条目初始保持 `[ ]`，等待 Reviewer 对需求文本进行审查。
- `[x]` 只表示需求质量标准已满足，不表示实现或测试已完成。
- `$speckit-implement` 只读取 Checkbox Marker 作为门禁，不得修改 Marker。
- `checklists/requirements.md` 由 `$speckit-specify` 和 `$speckit-clarify` 单独维护。
- 审查发现缺口时，应先更新 `spec.md`、`plan.md` 或 Contract，再在本清单记录结论。

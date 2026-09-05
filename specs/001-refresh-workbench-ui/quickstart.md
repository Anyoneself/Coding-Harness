# Quickstart: 验证参考图工作台升级

## 前置条件

- 当前分支为 `001-refresh-workbench-ui`。
- 已安装项目现有 Python 与 Node.js 依赖。
- 不使用真实公网模型执行自动化测试。
- 如需手工验证真实 Turn，使用本机已有安全配置，不把 API Key 写入命令、截图或文档。

## 1. 检查功能 Contract

先阅读：

- `specs/001-refresh-workbench-ui/spec.md`
- `specs/001-refresh-workbench-ui/data-model.md`
- `specs/001-refresh-workbench-ui/contracts/workbench-ui.md`

确认实现没有新增多项目、分支切换、评估、工具、搜索、账户或模型切换入口。

## 2. 运行前端行为测试

```bash
npm test
npm run typecheck
```

预期结果：

- 空状态、任务导航、发送/中断、Inspector、配置失败和事件归约测试通过。
- TypeScript 严格类型检查无错误。
- 测试不访问公网或真实模型。

## 3. 生成同源静态资源

```bash
npm run build
```

预期结果：

- `application/static/index.html` 引用 `/static/app.js` 和 `/static/styles.css`。
- `application/static/workbench-flow.webp` 可读取。
- 不需要手工编辑 `application/static/`。
- 未产生未被 Python 包配置包含的必要嵌套资源。

## 4. 运行后端回归与静态检查

```bash
python -m unittest discover -s tests -v
ruff check .
```

预期结果：

- 现有 Workspace、Thread、Turn、SSE、API Key 和静态首页集成测试通过。
- 不访问开发者本机数据库状态或公网。
- 静态检查无新增问题。

## 5. 启动同源工作台

```bash
python -m application serve --host 127.0.0.1 --port 8000
```

在浏览器打开 `http://127.0.0.1:8000/`。不要使用 `npm run dev` 作为端到端验收，因为当前 Vite 开发服务没有 `/api` 代理。

## 6. 桌面验收

依次使用 `1680×941` 和 `1024×768`：

1. 打开无消息任务，确认品牌、Sidebar、顶部导航、主标题、宽输入器和浅蓝流光背景均可辨认。
2. 确认项目名和模型名来自公开配置，没有分支选择器或假入口。
3. 输入任务，验证 `Shift+Enter` 换行和 `Enter` 发送。
4. 任务开始后，确认消息成为主要内容，输入器移动到底部且主操作切换为中断。
5. 打开“执行事件”和“Turn”，确认 Inspector 覆盖显示且关闭后主画布恢复。
6. 使用长项目名、长模型名、长任务名和长错误文本检查截断、换行和滚动。

预期结果：无页面级横向滚动、控件遮挡、布局跳动或虚假业务入口。

## 7. 移动验收

依次使用 `390×844` 和 320 像素宽度：

1. 确认 Sidebar 与 Inspector 默认关闭。
2. 分别打开和关闭任务导航与执行检查器。
3. 完成任务输入、发送或中断。
4. 打开 API Key 对话框并检查输入、显示/隐藏和提交按钮。
5. 检查安全区、长文本、抽屉遮罩和滚动。

预期结果：核心流程始终可达，无横向溢出，两个抽屉不会互相遮挡或留下不可退出状态。

## 8. 可访问性与降级验收

1. 只使用键盘完成新建、选择输入器、发送或中断、打开和关闭 Inspector。
2. 确认每个图标按钮具有可感知名称，焦点清晰可见。
3. 启用 `prefers-reduced-motion: reduce`，确认等待点和抽屉不再执行非必要运动。
4. 阻止 `workbench-flow.webp` 加载，确认静态冰蓝背景和全部业务操作仍可用。
5. 模拟配置读取失败、SSE 请求失败和非终态 SSE 结束，确认界面显示失败而非虚假成功。

## 9. 截图复盘

保存至少一张 `1680×941` 桌面截图和一张 `390×844` 移动截图，并检查：

- 第一视觉焦点是否为工程上下文与任务输入器。
- 去掉颜色后，布局层级是否仍然成立。
- 是否存在不承载真实信息的按钮、卡片、标签或说明文字。
- 执行态背景是否足够安静，正文是否清晰。
- 界面是否具有 Workspace、Thread、Turn 和 Event 的 Coding-Harness 工程语境。

发现问题时先删除多余视觉元素，再调整层级，最后才增加装饰。

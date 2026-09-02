# language: zh-CN
功能: 仅保留 Harness 新执行链
  场景: Web 任务通过资源链执行
    假如 用户已配置模型并选择工作区
    当 用户提交一个代码任务
    那么 前端应依次创建 Workspace、Thread 和 Turn
    并且 只通过 Turn 事件流观察执行结果

  场景: 旧对话链不可访问
    当 客户端请求旧的 chat 或 session 接口
    那么 服务应返回 404
    并且 应用不再装配旧 Chat Service

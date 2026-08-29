# language: zh-CN
功能: 首次运行配置 DeepSeek API Key
  为了无需编辑服务端文件即可开始使用 Coding-Harness
  作为本机用户
  我希望在前端安全地完成首次 API Key 配置

  场景: 首次配置后立即启用模型能力
    假如 当前服务尚未配置 DeepSeek API Key
    当 用户在首次配置界面提交有效 API Key
    那么 服务应返回模型已就绪
    并且 聊天服务和 Harness Runtime 无需重启即可使用模型
    并且 API 响应不得包含提交的 API Key

  场景: API Key 安全持久化
    假如 .env 中已经存在其他运行配置
    当 用户首次提交有效 API Key
    那么 原有运行配置应保持不变
    并且 DEEPSEEK_API_KEY 应被写入 .env
    并且 .env 文件权限应为 0600

  场景: 拒绝覆盖已经生效的 API Key
    假如 当前服务已经配置 DeepSeek API Key
    当 用户再次提交另一个 API Key
    那么 服务应返回 409 冲突
    并且 已生效和已持久化的 API Key 都不应改变

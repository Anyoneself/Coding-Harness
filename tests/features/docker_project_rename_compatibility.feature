# language: zh-CN
功能: 项目改名后的 Docker 基础设施兼容
  为了在 Coding-Harness 改名后继续使用已有的本地数据
  作为本地开发者
  我希望启动脚本能够接管原 My-Agent 创建的 Docker 资源

  场景: 在新目录中复用旧项目容器和网络
    假如 本机已经存在由 my-agent Compose 项目创建的容器和网络
    当 用户在 Coding-Harness 目录执行启动脚本
    那么 Compose 应继续使用 my-agent 作为基础设施项目标识
    并且 不应以 coding-harness 项目身份重复创建同名容器
    并且 原有 PostgreSQL 数据卷应保持不变

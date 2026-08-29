#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
STARTUP_TIMEOUT_SECONDS="${STARTUP_TIMEOUT_SECONDS:-240}"
INFRA_ONLY=false

show_help() {
  # 说明脚本负责的基础设施、环境和应用启动行为。
  cat <<'EOF'
用法：./scripts/start.sh [--infra-only] [application serve 参数]

一键启动 Coding-Harness：
  1. 确认 Docker 可用，macOS + Colima 环境会自动启动 Colima。
  2. 创建 .venv 并在缺少依赖时安装项目。
  3. 启动 PostgreSQL、Milvus、etcd 和 MinIO，并等待健康检查。
  4. 前台启动 Coding-Harness Web 服务。

选项：
  --infra-only   只启动基础设施，不启动 Web 服务
  -h, --help     显示帮助

示例：
  ./scripts/start.sh
  ./scripts/start.sh --host 0.0.0.0 --port 9000
  ./scripts/start.sh --infra-only
EOF
}

fail() {
  # 输出明确错误并终止启动流程。
  echo "[Coding-Harness] 错误：$*" >&2
  exit 1
}

select_compose_command() {
  # 兼容 Docker Compose 插件和独立 docker-compose 命令。
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_COMMAND=(docker compose)
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_COMMAND=(docker-compose)
    return
  fi
  fail "未找到 Docker Compose，请先安装 docker compose 或 docker-compose。"
}

ensure_docker() {
  # 优先复用现有 Docker；Colima 未启动时按 Milvus 最低资源要求启动。
  if docker info >/dev/null 2>&1; then
    return
  fi
  if command -v colima >/dev/null 2>&1; then
    echo "[Coding-Harness] Docker 尚未运行，正在启动 Colima（4 CPU / 8 GB）..."
    colima start --cpu 4 --memory 8
  fi
  docker info >/dev/null 2>&1 || fail "Docker 未运行，请先启动 Docker Desktop 或 Colima。"
}

select_python() {
  # 使用项目虚拟环境；不存在时以 Python 3.11+ 创建。
  if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    local bootstrap_python=""
    local candidate_name=""
    local candidate_path=""
    for candidate_name in python3.14 python3.13 python3.12 python3.11 python3 python; do
      candidate_path="$(command -v "${candidate_name}" 2>/dev/null || true)"
      if [[ -n "${candidate_path}" ]] && "${candidate_path}" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
        bootstrap_python="${candidate_path}"
        break
      fi
    done
    [[ -n "${bootstrap_python}" ]] || fail "未找到 Python 3.11 或更高版本。"
    echo "[Coding-Harness] 正在创建 .venv..."
    "${bootstrap_python}" -m venv "${PROJECT_ROOT}/.venv"
  fi
  PYTHON_COMMAND="${PROJECT_ROOT}/.venv/bin/python"
}

ensure_application_dependencies() {
  # 仅在关键运行依赖缺失时执行可编辑安装，避免每次启动重复下载。
  if "${PYTHON_COMMAND}" -c 'import fastapi, openai, psycopg, pymilvus' >/dev/null 2>&1; then
    return
  fi
  echo "[Coding-Harness] 正在安装项目依赖..."
  "${PYTHON_COMMAND}" -m pip install -e "${PROJECT_ROOT}"
}

ensure_environment_file() {
  # 首次运行复制安全的配置模板，但不覆盖用户已有配置。
  if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    return
  fi
  cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
  echo "[Coding-Harness] 已创建 .env；使用真实模型前请填写 DEEPSEEK_API_KEY。"
}

wait_for_container() {
  # 等待单个容器通过 Docker 健康检查，超时后输出相关日志。
  local service_name="$1"
  local container_name="$2"
  local deadline=$(( $(date +%s) + STARTUP_TIMEOUT_SECONDS ))
  local status=""
  while (( $(date +%s) < deadline )); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_name}" 2>/dev/null || true)"
    if [[ "${status}" == "healthy" || "${status}" == "running" ]]; then
      echo "[Coding-Harness] ${service_name} 已就绪。"
      return
    fi
    if [[ "${status}" == "unhealthy" || "${status}" == "exited" || "${status}" == "dead" ]]; then
      break
    fi
    sleep 2
  done
  "${COMPOSE_COMMAND[@]}" -f "${PROJECT_ROOT}/docker-compose.yml" ps >&2 || true
  "${COMPOSE_COMMAND[@]}" -f "${PROJECT_ROOT}/docker-compose.yml" logs --tail=80 "${service_name}" >&2 || true
  fail "${service_name} 未能在 ${STARTUP_TIMEOUT_SECONDS} 秒内通过健康检查（状态：${status:-unknown}）。"
}

start_infrastructure() {
  # 启动项目所需容器，并逐个确认服务健康。
  echo "[Coding-Harness] 正在启动 PostgreSQL 与 Milvus..."
  "${COMPOSE_COMMAND[@]}" -f "${PROJECT_ROOT}/docker-compose.yml" up -d
  wait_for_container postgres my-agent-postgres
  wait_for_container etcd my-agent-milvus-etcd
  wait_for_container minio my-agent-milvus-minio
  wait_for_container milvus my-agent-milvus
}

main() {
  # 编排环境准备、基础设施健康检查和 Web 服务前台启动。
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    show_help
    return
  fi
  if [[ "${1:-}" == "--infra-only" ]]; then
    INFRA_ONLY=true
    shift
  fi
  cd "${PROJECT_ROOT}"
  ensure_docker
  select_compose_command
  select_python
  ensure_application_dependencies
  ensure_environment_file
  start_infrastructure
  if [[ "${INFRA_ONLY}" == true ]]; then
    echo "[Coding-Harness] 基础设施已启动。"
    return
  fi
  echo "[Coding-Harness] 正在启动 Web 服务..."
  exec "${PYTHON_COMMAND}" -m application serve "$@"
}

main "$@"

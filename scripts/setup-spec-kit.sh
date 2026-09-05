#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SPEC_KIT_VERSION="v1.0.4"

fail() {
  # 输出 Spec Kit 初始化失败原因并终止。
  echo "[Coding-Harness] Spec Kit 错误：$*" >&2
  exit 1
}

install_spec_kit() {
  # 以隔离的 uv tool 固定安装仓库验证过的 Spec Kit 版本。
  command -v uv >/dev/null 2>&1 || fail "未找到 uv，请先安装 uv。"
  uv tool install specify-cli --force \
    --from "git+https://github.com/github/spec-kit.git@${SPEC_KIT_VERSION}"
}

synchronize_project_integration() {
  # 初始化缺失的项目工件，或重新物化已安装 Preset 对应的 Codex Skills。
  cd "${PROJECT_ROOT}"
  if [[ ! -f ".specify/init-options.json" ]]; then
    specify init --here --force --non-interactive \
      --integration codex --ignore-agent-tools
    return
  fi
  specify integration use codex
}

main() {
  # 安装固定版本并确认项目的 Spec Kit 与 Codex 集成可用。
  install_spec_kit
  synchronize_project_integration
  specify --version
  specify preset list
}

main "$@"

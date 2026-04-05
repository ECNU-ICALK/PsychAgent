#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="${WEB_DIR:-${SCRIPT_DIR}/src/web}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env.local}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [ ! -f "${WEB_DIR}/package.json" ]; then
  echo "[ERROR] 未找到前端工程: ${WEB_DIR}/package.json"
  echo "[HINT] 可通过 WEB_DIR 指定 web 目录，例如:"
  echo "       WEB_DIR=/path/to/PsychAgent_v0402/src/web ./run_frontend.sh"
  exit 1
fi

cd "${WEB_DIR}"

detect_rollup_native_pkg() {
  local platform arch
  platform="$(node -p 'process.platform' 2>/dev/null || true)"
  arch="$(node -p 'process.arch' 2>/dev/null || true)"

  if [ "${platform}" = "linux" ] && [ "${arch}" = "x64" ]; then
    if command -v ldd >/dev/null 2>&1 && ldd --version 2>&1 | grep -qi musl; then
      echo "@rollup/rollup-linux-x64-musl"
    else
      echo "@rollup/rollup-linux-x64-gnu"
    fi
    return 0
  fi

  if [ "${platform}" = "linux" ] && [ "${arch}" = "arm64" ]; then
    if command -v ldd >/dev/null 2>&1 && ldd --version 2>&1 | grep -qi musl; then
      echo "@rollup/rollup-linux-arm64-musl"
    else
      echo "@rollup/rollup-linux-arm64-gnu"
    fi
    return 0
  fi

  return 0
}

ensure_rollup_native_pkg() {
  local pkg="${1:-}"
  if [ -z "${pkg}" ]; then
    return 0
  fi

  if ! node -e "require.resolve('${pkg}')" >/dev/null 2>&1; then
    echo "[WARN] 缺少 Rollup 平台包 ${pkg}，尝试自动安装（npm optionalDependencies bug 兼容）..."
    npm install --no-save "${pkg}"
  fi
}

if [ ! -d node_modules ]; then
  npm install --include=optional
fi

ROLLUP_NATIVE_PKG="$(detect_rollup_native_pkg)"
ensure_rollup_native_pkg "${ROLLUP_NATIVE_PKG}"

# Keep frontend and backend defaults aligned.

BACKEND_HOST="${BACKEND_HOST:-localhost}"
VITE_API_BASE="${VITE_API_BASE:-http://${BACKEND_HOST}:${BACKEND_PORT:-8000}}" \
npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT:-5173}"

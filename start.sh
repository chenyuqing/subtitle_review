#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-5001}"
HOST="${HOST:-localhost}"
PID_FILE="$ROOT_DIR/.server.pid"
LOG_FILE="/tmp/subtitle-review.log"
UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.uv-cache}"
export UV_CACHE_DIR
mkdir -p "$UV_CACHE_DIR"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "Error: 检测到已有服务在运行 (PID $(cat "$PID_FILE"))，请先运行 stop.sh。" >&2
  exit 1
fi

# 检查端口是否被占用，如果被占用则强制释放后再启动
if lsof -i :"$PORT" >/dev/null 2>&1; then
  echo "端口 ${PORT} 被占用，尝试终止占用进程..."
  CONFLICT_PIDS="$(lsof -ti :"$PORT" || true)"
  if [ -n "$CONFLICT_PIDS" ]; then
    echo "$CONFLICT_PIDS" | xargs -r kill >/dev/null 2>&1 || true
    sleep 1
    # 若仍存在则强制杀掉
    for PID in $CONFLICT_PIDS; do
      if kill -0 "$PID" >/dev/null 2>&1; then
        echo "进程 $PID 未退出，执行强制终止"
        kill -9 "$PID" >/dev/null 2>&1 || true
      fi
    done
  fi
  if lsof -i :"$PORT" >/dev/null 2>&1; then
    echo "无法释放端口 ${PORT}，请手动检查后重试。" >&2
    exit 1
  fi
  echo "端口 ${PORT} 已释放，继续启动。"
fi

echo "启动本地 Web 服务： http://${HOST}:${PORT}"
uv run python -m app.server --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" >"$PID_FILE"
sleep 1
if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
  echo "服务启动失败，详见 $LOG_FILE" >&2
  cat "$LOG_FILE" >&2
  rm -f "$PID_FILE"
  exit 1
fi
echo "服务已后台运行 (PID ${SERVER_PID})，日志：$LOG_FILE"
echo "访问地址：http://${HOST}:${PORT}"
echo "若需停止，请执行 ./stop.sh"

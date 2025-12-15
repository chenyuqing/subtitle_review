#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.server.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "未找到运行中的服务 (缺少 $PID_FILE)。"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" >/dev/null 2>&1; then
  echo "停止服务 (PID $PID)..."
  kill "$PID"
  wait "$PID" 2>/dev/null || true
  echo "服务已停止。"
else
  echo "进程 $PID 不存在，清理 PID 文件。"
fi
rm -f "$PID_FILE"

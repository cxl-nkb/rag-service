#!/usr/bin/env bash
# RAG Service V2 启动脚本
# 用法: ./scripts/start.sh [--host HOST] [--port PORT] [--reload]
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$BASE_DIR/../../venv-rag/bin/python"
APP_DIR="$BASE_DIR/app"

HOST="${RAG_HOST:-127.0.0.1}"
PORT="${RAG_PORT:-8931}"
EXTRA_ARGS=""

for arg in "$@"; do
  case "$arg" in
    --reload) EXTRA_ARGS="--reload" ;;
    --host=*) HOST="${arg#--host=}" ;;
    --port=*) PORT="${arg#--port=}" ;;
  esac
done

cd "$APP_DIR"
exec "$PYTHON" -m uvicorn main:app --host "$HOST" --port "$PORT" "$EXTRA_ARGS"

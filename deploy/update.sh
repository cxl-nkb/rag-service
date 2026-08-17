#!/usr/bin/env bash
# rag-service 增量更新（生产已装后使用）：同步代码 + 资源 Drop-in，不动配置/数据
# 用法：sudo ./update.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "错误: 请用 root 运行（sudo ./update.sh）" >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${RAG_INSTALL_DIR:-/opt/rag-service}"
CONF_DIR=/etc/rag-service

echo "==> [1/3] 同步应用代码 → $APP_DIR/app"
cp -r "$SRC/app" "$APP_DIR/"

echo "==> [2/3] 生成资源限制 Drop-in（MemoryMax 从配置读取）"
DROPIN_DIR=/etc/systemd/system/rag-service.service.d
mkdir -p "$DROPIN_DIR"
MEM_MAX=$(grep -E "^  memory_max:" "$CONF_DIR/config.yaml" | head -1 | awk '{print $2}' | tr -d '"' || true)
if [ -z "$MEM_MAX" ]; then MEM_MAX="2G"; fi
cat > "$DROPIN_DIR/resource.conf" <<EOF
# rag-service 资源限制（改这里后 systemctl daemon-reload && restart）
[Service]
MemoryMax=${MEM_MAX}
EOF
systemctl daemon-reload
echo "    已写入 MemoryMax=${MEM_MAX}（改 /etc/rag-service/config.yaml 的 resources.memory_max 可调整）"

echo "==> [3/3] 重启服务"
systemctl restart rag-service

echo
echo "✅ 更新完成。验证："
echo "   systemctl status rag-service    # active (running)"
echo "   systemctl show rag-service -p MemoryCurrent   # 当前内存"
echo "   curl http://127.0.0.1:8931/health"
echo "   查看内存限制：systemctl show rag-service -p MemoryMax"

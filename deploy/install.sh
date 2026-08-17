#!/usr/bin/env bash
# rag-service 标准安装脚本（需 root，在可写 / 的环境执行）
# 安装到：/opt/rag-service（应用+venv） /etc/rag-service（配置） /var/lib/rag-service（数据）
#         /usr/local/bin/rag-service（入口） /lib/systemd/system/rag-service.service（单元）
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "错误: 请用 root 运行（sudo ./install.sh）" >&2
    exit 1
fi

# 源码目录（本文件位于 rag-service/deploy/install.sh）
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${RAG_INSTALL_DIR:-/opt/rag-service}"
CONF_DIR=/etc/rag-service
DATA_DIR=/var/lib/rag-service
BIN=/usr/local/bin/rag-service
SVC=/lib/systemd/system/rag-service.service

echo "==> [1/8] 创建专用用户 rag-service"
if ! id rag-service &>/dev/null; then
    useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin rag-service
    echo "    已创建系统用户 rag-service"
else
    echo "    用户已存在"
fi

echo "==> [2/8] 拷贝应用代码 → $APP_DIR"
mkdir -p "$APP_DIR"
cp -r "$SRC/app" "$SRC/config.yaml" "$SRC/eval_set.yaml" "$SRC/requirements.txt" "$APP_DIR/"

echo "==> [3/8] 创建虚拟环境并安装依赖"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> [4/8] 配置文件 → $CONF_DIR"
mkdir -p "$CONF_DIR"
if [ -f "$CONF_DIR/config.yaml" ]; then
    echo "    已有配置，保留（如需重置请手动覆盖）"
else
    cp "$SRC/config.yaml" "$CONF_DIR/config.yaml"
    echo "    ⚠️ 已复制默认配置——请编辑 $CONF_DIR/config.yaml"
    echo "       配置 datasources（指向你的知识库目录）后再启动服务！"
fi

echo "==> [5/8] 数据目录 → $DATA_DIR"
mkdir -p "$DATA_DIR"
chown -R rag-service:rag-service "$DATA_DIR"

echo "==> [6/8] 环境文件 /etc/rag-service/env"
cat > "$CONF_DIR/env" <<EOF
RAG_HOME=$APP_DIR
RAG_CONFIG=$CONF_DIR/config.yaml
RAG_DATA=$DATA_DIR
RAG_HOST=127.0.0.1
RAG_PORT=8931
EOF
chown -R rag-service:rag-service "$CONF_DIR"

echo "==> [7/8] 入口脚本 → $BIN"
install -m 755 "$SRC/deploy/rag-service" "$BIN"

echo "==> [8/8] systemd 单元 → $SVC"
cp "$SRC/deploy/rag-service.service" "$SVC"
# 资源限制 Drop-in（MemoryMax 从 config.yaml 的 resources.memory_max 读取）
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

echo
echo "✅ 安装完成。启动服务："
echo "   systemctl enable --now rag-service"
echo "   查看状态：systemctl status rag-service"
echo "   查看日志：journalctl -u rag-service -f"
echo
echo "   首次启动会自动构建索引（下载 BGE 模型，需几分钟）。"
echo "   配置修改：$CONF_DIR/config.yaml"
echo "   数据目录：$DATA_DIR"

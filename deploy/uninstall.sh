#!/usr/bin/env bash
# rag-service 卸载脚本（回滚 install.sh）
# 用法：sudo ./uninstall.sh [--purge]
#   （不带 --purge）保留数据 /var/lib/rag-service 与 rag-service 用户
#   （--purge）删除数据与用户（不可恢复）
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "错误: 请用 root 运行（sudo ./uninstall.sh）" >&2
    exit 1
fi

PURGE=false
if [ "${1:-}" = "--purge" ]; then
    PURGE=true
fi

echo "==> [1/5] 停止并禁用服务"
systemctl stop rag-service 2>/dev/null || true
systemctl disable rag-service 2>/dev/null || true

echo "==> [2/5] 删除 systemd 单元"
rm -f /lib/systemd/system/rag-service.service
systemctl daemon-reload

echo "==> [3/5] 删除入口与配置"
rm -f /usr/local/bin/rag-service
rm -rf /etc/rag-service

echo "==> [4/5] 删除应用（/opt/rag-service）"
rm -rf /opt/rag-service

echo "==> [5/5] 数据处理"
if $PURGE; then
    rm -rf /var/lib/rag-service
    userdel rag-service 2>/dev/null || true
    echo "    已删除数据目录与 rag-service 用户（--purge）"
else
    echo "    保留数据目录 /var/lib/rag-service 与用户（如需清除用 --purge）"
fi

echo
echo "✅ 卸载完成。"
[ $PURGE = false ] && echo "提示：数据仍在 /var/lib/rag-service，重新安装可复用索引；确认不要可加 --purge 清除。"

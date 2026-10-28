#!/bin/bash

set -e

# 生成配置文件
cat > /etc/snell-server/snell-server.conf << EOF
[snell-server]
listen = ${SNELL_LISTEN:-0.0.0.0:7177,[::]:7177}
psk = ${SNELL_PSK:-$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 16)}
mode = ${SNELL_MODE:-default}
EOF

if [ -n "${SNELL_DNS:-}" ]; then
    printf 'dns = %s\n' "${SNELL_DNS}" >> /etc/snell-server/snell-server.conf
fi

if [ -n "${SNELL_DNS_IP_PREFERENCE:-}" ]; then
    printf 'dns-ip-preference = %s\n' "${SNELL_DNS_IP_PREFERENCE}" >> /etc/snell-server/snell-server.conf
fi

if [ -n "${SNELL_EGRESS_INTERFACE:-}" ]; then
    printf 'egress-interface = %s\n' "${SNELL_EGRESS_INTERFACE}" >> /etc/snell-server/snell-server.conf
fi

# 显示生成的 PSK
if [ -z "${SNELL_PSK}" ]; then
    echo "Generated PSK: $(grep psk /etc/snell-server/snell-server.conf | cut -d= -f2 | tr -d ' ')"
fi

# 启动 snell-server
exec /usr/bin/snell-server -c /etc/snell-server/snell-server.conf 

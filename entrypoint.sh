#!/bin/bash

# 仅在未设置 SNELL_HOST 时设置默认值
if [ -z "${SNELL_HOST}" ]; then
    SNELL_HOST="::0"

    # 根据 SNELL_IPV6 设置正确的监听地址
    if [ "${SNELL_IPV6:-true}" = "false" ]; then
        SNELL_HOST="0.0.0.0"
    fi
fi

# 生成配置文件
cat > /etc/snell-server/snell-server.conf << EOF
[snell-server]
listen = ${SNELL_HOST}:${SNELL_PORT:-6333}
psk = ${SNELL_PSK:-$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 16)}
ipv6 = ${SNELL_IPV6:-true}
EOF

# 显示生成的 PSK
if [ -z "${SNELL_PSK}" ]; then
    echo "Generated PSK: $(grep psk /etc/snell-server/snell-server.conf | cut -d= -f2 | tr -d ' ')"
fi

# 启动 snell-server
exec /usr/bin/snell-server -c /etc/snell-server/snell-server.conf 

# snell-server Helm Chart

这个 chart 会部署一个 DaemonSet，每个节点运行 `snell-server` 和 `shadow-tls` 两个容器。默认使用 Pod 网络，`snell-server` 只监听 Pod 回环地址，`shadow-tls` 通过 ClusterIP Service 和 Traefik `IngressRouteTCP` 暴露。

## 默认行为

- 默认镜像为 `ghcr.io/xudongcc/snell-server:6.0.0`，客户端需配置 `version=6`
- `hostNetwork` 默认关闭，`dnsPolicy` 使用 `Default`
- `snell-server` 监听 `::1:7177`
- `shadow-tls` 监听 `::0:8443`
- `shadow-tls` 转发到同一个 Pod 网络命名空间内的 `::1:7177`
- `shadow-tls` 默认使用 epoll，避免 io_uring 等待被计入 I/O Pressure
- `shadowTLS.sni` 默认为 `gateway.icloud.com`
- Traefik `HostSNI` 默认跟随 `shadowTLS.sni`
- Service 默认只暴露 `shadow-tls` 端口，并使用 `internalTrafficPolicy: Local`
- Traefik backend 使用 `nativeLB: true`

## 安装

通常只需要覆盖两个密钥。Snell PSK 必须为 12–255 字节，建议使用 32 字符随机密钥；默认值仅作占位，部署时请替换。Helm 会在渲染时拒绝类型或长度不符合要求的 PSK。

```bash
helm upgrade snell-server oci://ghcr.io/xudongcc/helm-charts/snell-server \
  --install \
  --version 0.0.5 \
  --namespace snell-server \
  --create-namespace \
  --set-string snellServer.psk='replace-with-a-random-32-char-key' \
  --set-string shadowTLS.password='changeme'
```

## 常用配置

```yaml
snellServer:
  psk: "replace-with-a-random-32-char-key"

shadowTLS:
  password: "changeme"
  sni: "gateway.icloud.com"
  forceLegacyDriver: true
```

设置 `shadowTLS.forceLegacyDriver: false` 可以恢复使用 io_uring。

## Snell 环境变量

镜像支持以下环境变量，Helm 通过对应的 `snellServer` 配置传入：

| 环境变量 | Helm 配置 | 默认值 / 说明 |
| --- | --- | --- |
| `SNELL_PSK` | `psk` | 镜像未设置时生成随机值；Chart 默认占位值 `please-change-me`，须替换 |
| `SNELL_LISTEN` | `listen` | 镜像默认 `0.0.0.0:7177,[::]:7177`；Chart 为空时使用 `[::1]:<port>`，支持逗号分隔的多个地址 |
| `SNELL_MODE` | `mode` | `default`；支持 `default`、`unshaped`、`unsafe-raw` |
| `SNELL_DNS` | `dns` | 空，使用系统 DNS；可用逗号分隔多个 DNS 服务器地址 |
| `SNELL_DNS_IP_PREFERENCE` | `dnsIpPreference` | 空，使用上游默认行为；支持 `default`、`prefer-ipv4`、`prefer-ipv6`、`ipv4-only`、`ipv6-only` |
| `SNELL_EGRESS_INTERFACE` | `egressInterface` | 空；绑定出站 TCP、UDP 和 DNS 到指定网卡 |

监听地址统一通过 `SNELL_LISTEN` 设置，IPv6 地址须带方括号；DNS 地址族偏好由 `SNELL_DNS_IP_PREFERENCE` 控制。`mode` 必须与客户端一致；`unsafe-raw` 不提供加密，仅适合安全内网或已有安全隧道。

例如，直接运行镜像时可以传入：

```bash
docker run -d --name snell -p 7177:7177 \
  -e SNELL_PSK='replace-with-a-random-32-char-key' \
  -e SNELL_LISTEN='0.0.0.0:7177,[::]:7177' \
  -e SNELL_MODE=default \
  -e SNELL_DNS_IP_PREFERENCE=prefer-ipv4 \
  ghcr.io/xudongcc/snell-server:6.0.0
```

Helm 配置示例：

```yaml
snellServer:
  mode: default
  dns: "1.1.1.1,2606:4700:4700::1111"
  dnsIpPreference: prefer-ipv4
  # listen: "127.0.0.1:7177,[::1]:7177"
  # egressInterface: eth0
```

自定义 `listen` 时，监听端口需与 `snellServer.port` 保持一致；启用 shadow-tls 时，还需包含 `shadowTLS.serverHost` 指定的地址。出口网卡名称属于容器或 Pod 的网络命名空间，绑定网卡可能需要额外的系统权限。

如果需要让 Traefik 的入口 SNI 和 `shadowTLS.sni` 不同，可以显式覆盖：

```bash
--set-string traefik.ingressRouteTCP.hostSNI='example.com'
```

## 前置条件

集群里需要已经安装 Traefik CRD，并且 Traefik 有 `websecure` entryPoint。

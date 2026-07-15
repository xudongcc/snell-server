# snell-server Helm Chart

这个 chart 会部署一个 DaemonSet，每个节点运行 `snell-server` 和 `shadow-tls` 两个容器。默认使用 Pod 网络，`snell-server` 只监听 Pod 回环地址，`shadow-tls` 通过 ClusterIP Service 和 Traefik `IngressRouteTCP` 暴露。

## 默认行为

- `hostNetwork` 默认关闭，`dnsPolicy` 使用 `Default`
- `snell-server` 监听 `::1:6333`
- `shadow-tls` 监听 `::0:8443`
- `shadow-tls` 转发到同一个 Pod 网络命名空间内的 `::1:6333`
- `shadow-tls` 默认使用 epoll，避免 io_uring 等待被计入 I/O Pressure
- `shadowTLS.sni` 默认为 `gateway.icloud.com`
- Traefik `HostSNI` 默认跟随 `shadowTLS.sni`
- Service 默认只暴露 `shadow-tls` 端口，并使用 `internalTrafficPolicy: Local`
- Traefik backend 使用 `nativeLB: true`

## 安装

通常只需要覆盖两个密钥：

```bash
helm upgrade snell-server oci://ghcr.io/xudongcc/helm-charts/snell-server \
  --install \
  --namespace snell-server \
  --create-namespace \
  --set-string snellServer.psk='changeme' \
  --set-string shadowTLS.password='changeme'
```

## 常用配置

```yaml
snellServer:
  psk: "changeme"

shadowTLS:
  password: "changeme"
  sni: "gateway.icloud.com"
  forceLegacyDriver: true
```

设置 `shadowTLS.forceLegacyDriver: false` 可以恢复使用 io_uring。

如果需要让 Traefik 的入口 SNI 和 `shadowTLS.sni` 不同，可以显式覆盖：

```bash
--set-string traefik.ingressRouteTCP.hostSNI='example.com'
```

## 前置条件

集群里需要已经安装 Traefik CRD，并且 Traefik 有 `websecure` entryPoint。

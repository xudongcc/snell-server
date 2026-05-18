# snell-server Helm Chart

这个 chart 会部署一个 DaemonSet，每个节点运行 `snell-server` 和 `shadow-tls` 两个容器。默认不使用 `hostNetwork`，通过 ClusterIP Service 和 Traefik `IngressRouteTCP` 暴露 `shadow-tls`。

## 默认行为

- `snell-server` 监听 `::0:6333`
- `shadow-tls` 监听 `::0:8443`
- `shadow-tls` 转发到同一个 Pod 内的 `::1:6333`
- `shadowTLS.sni` 默认为 `gateway.icloud.com`
- Traefik `HostSNI` 默认跟随 `shadowTLS.sni`
- Service 使用 `internalTrafficPolicy: Local`
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
```

如果需要让 Traefik 的入口 SNI 和 `shadowTLS.sni` 不同，可以显式覆盖：

```bash
--set-string traefik.ingressRouteTCP.hostSNI='example.com'
```

## 前置条件

集群里需要已经安装 Traefik CRD，并且 Traefik 有 `websecure` entryPoint。

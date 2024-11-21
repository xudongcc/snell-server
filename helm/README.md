## 安装

1. 给要部署 snell 的节点添加标签和污点：

   ```bash
   kubectl label nodes <node-name> dedicated=proxy
   kubectl taint nodes <node-name> dedicated=proxy:NoExecute
   ```

2. 使用 helm 安装：

   ```bash
   helm upgrade snell-server oci://ghcr.io/xudongcc/snell-server/helm-charts \
   --install \
   --namespace snell-server \
   --create-namespace \
   --set snellServer.port=6333 \
   --set snellServer.psk=psk \
   --set shadowTLS.port=443 \
   --set shadowTLS.sni=gateway.icloud.com:443 \
   --set shadowTLS.password=password
   ```

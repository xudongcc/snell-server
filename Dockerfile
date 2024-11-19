FROM ubuntu AS download

ARG VERSION=4.1.1

ARG TARGETARCH
ARG ARCH=${TARGETARCH}

WORKDIR /tmp

RUN apt update && \
apt install -y wget unzip

RUN if [ "$TARGETARCH" = "arm64" ]; then ARCH="aarch64"; fi && \
    wget https://dl.nssurge.com/snell/snell-server-v${VERSION}-linux-${ARCH}.zip -O snell-server.zip && \
    unzip snell-server.zip

FROM ubuntu AS runtime

WORKDIR /etc/snell-server

COPY --from=download /tmp/snell-server /usr/bin/snell-server
COPY entrypoint.sh /usr/bin/entrypoint.sh

RUN chmod +x /usr/bin/entrypoint.sh

ENTRYPOINT ["/usr/bin/entrypoint.sh"]

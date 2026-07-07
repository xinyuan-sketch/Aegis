# 云浏览器容器：Xvfb + Chrome + x11vnc + websockify(noVNC)
# 多人共用同一个远程 Chrome（x11vnc -shared），网页内通过 noVNC 操作。
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:0 \
    RES=1440x900x24

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc fluxbox x11-utils \
        novnc websockify \
        python3 procps wget gnupg ca-certificates \
        fonts-wqy-zenhei fonts-noto-cjk \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm -f google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# 注入 noVNC 错误拦截脚本（吞掉浏览器扩展如 MetaMask 抛的未捕获错误弹窗）
COPY patch_novnc.py /tmp/patch_novnc.py
RUN python3 /tmp/patch_novnc.py

COPY start.sh /start.sh
RUN chmod +x /start.sh

# 6080: noVNC(HTTP+WS)
EXPOSE 6080
CMD ["/start.sh"]

# 云浏览器容器

团队共用的远程 Chrome：`Xvfb + Chrome + x11vnc + websockify(noVNC)`。多人同时连接同一屏操作（`x11vnc -shared`），网页内通过 noVNC 控制。

## 1. 构建并启动

```bash
cd deploy/cloud-browser
docker compose up -d --build
# 本机验证：浏览器打开 http://127.0.0.1:6080/vnc.html
```

容器名为 `aegis-cloud-browser`（Aegis 的重启按钮据此调用 `docker restart`）。

## 2. Nginx 反代（把 noVNC 挂到主站 /novnc，含 WebSocket 透传）

在 Aegis 的 `server {}` 里加：

```nginx
location /novnc/ {
    proxy_pass http://127.0.0.1:6080/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;   # VNC 长连接
    # 建议在此加 auth_request，仅登录用户可访问，避免裸奔
}
```

## 3. 告诉 Aegis noVNC 地址

在 Aegis 的 `.env` 里设置（然后重启 Aegis）：

```dotenv
AEGIS_CLOUD_BROWSER_URL=/novnc/vnc.html?autoconnect=1&resize=scale
AEGIS_CLOUD_BROWSER_CONTAINER=aegis-cloud-browser
```

设置后，工具页「云浏览器」会 iframe 嵌入 noVNC，显示在线人数（应用侧心跳），管理员可一键重启。

## 4. 重启按钮的前提

Aegis 后端执行 `docker restart aegis-cloud-browser`。因此 **运行 Aegis 的用户需有 docker 权限**（加入 `docker` 组，或 Aegis 容器挂载 `/var/run/docker.sock`）。没有权限时重启按钮会返回失败提示，不影响其它功能。

## 安全须知

- `x11vnc` 默认 `-nopw`（无密码）。**务必**只让 6080 绑定 `127.0.0.1`（compose 已如此），对外一律走 Nginx + 登录鉴权（`auth_request`），或给 x11vnc 设 `-passwd`。
- 远程 Chrome 是高权限入口，建议：限制该工具的授权用户、开启操作审计、必要时按需启停容器。
- 剪贴板双向同步由 noVNC 面板提供；如需企查查等站点的导出限流，可在此容器内加计数逻辑（参考主项目 credits/audit 思路）。

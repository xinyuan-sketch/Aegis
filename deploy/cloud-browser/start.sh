#!/bin/bash
# 云浏览器启动：Xvfb → 窗口管理器 → Chrome → x11vnc → websockify(noVNC)
# 关键：重启复用文件系统时会残留 X 锁 / 旧进程，先清理，再等显示就绪。

# 杀掉可能残留的旧进程（防止重复实例互相抢端口/显示）
pkill -x Xvfb 2>/dev/null || true
pkill -x x11vnc 2>/dev/null || true
pkill -x websockify 2>/dev/null || true
pkill -x chrome 2>/dev/null || true
sleep 1

# 清理上次残留的 X 锁 / socket（否则报 "Server is already active for display 0"）
rm -f /tmp/.X0-lock 2>/dev/null || true
rm -rf /tmp/.X11-unix 2>/dev/null || true
mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# 每次启动都重打 noVNC 补丁（幂等），确保重建/重启后错误拦截始终生效，不依赖镜像缓存
[ -f /tmp/patch_novnc.py ] && python3 /tmp/patch_novnc.py 2>/dev/null || true

# 1. 虚拟显示
Xvfb :0 -screen 0 "${RES}" -ac +extension GLX +render -noreset >/var/log/xvfb.log 2>&1 &

# 等 Xvfb 真正就绪（最多 ~8 秒）
for i in $(seq 1 20); do
    if xdpyinfo -display :0 >/dev/null 2>&1; then
        echo "Xvfb ready"; break
    fi
    sleep 0.4
done

# 2. 窗口管理器
fluxbox >/dev/null 2>&1 &

# 3. Chrome（容器内必须 --no-sandbox；独立 user-data-dir 防锁；--disable-dev-shm-usage 防崩）
google-chrome \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --user-data-dir=/tmp/chrome-profile \
    --start-maximized \
    --no-first-run \
    --no-default-browser-check \
    --window-position=0,0 \
    "about:blank" >/var/log/chrome.log 2>&1 &

# 4. VNC 服务（-shared 允许多人同连；后台运行）
x11vnc -display :0 -forever -shared -nopw -rfbport 5900 >/var/log/x11vnc.log 2>&1 &

# 5. websockify + noVNC，作为前台进程保持容器存活。
# 过滤客户端断连时的正常退出噪音（Terminate/Traceback/readinto 等），保留真实日志。
NOISE='Terminating child|Process Process-|^Traceback|^  File |^    |WebSockifyServer\.Terminate|raise self\.Terminate|do_SIGTERM|self\.terminate\(\)|handle_one_request|readinto|recv_into|^In exit$'
exec websockify --web=/usr/share/novnc 6080 localhost:5900 \
    2> >(grep --line-buffered -vE "$NOISE" >&2)

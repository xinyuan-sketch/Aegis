"""云浏览器：嵌入 noVNC，团队共用同一个远程 Chrome。

- noVNC 地址：config.CLOUD_BROWSER_URL；留空则按当前访问地址 + 端口自动推导
- 在线人数：应用侧心跳统计（近 20 秒内有心跳的用户数）
- 连接状态：后端主动探测容器可达性（带 5 秒缓存）
- 重启：管理员触发 docker restart（尽力而为，需宿主 docker 权限）
"""
import subprocess
import time
import urllib.request

from flask import (Blueprint, current_app, jsonify, render_template, request)
from flask_login import current_user, login_required

from ...core import audit
from ...core.rbac import require_tool

bp = Blueprint("browser", __name__, url_prefix="/tools/browser")

_online = {}            # {user_id: last_seen_ts}
_ONLINE_WINDOW = 20     # 秒
_reach_cache = {"ts": 0, "ok": False}
_REACH_TTL = 5          # 秒


def _online_count():
    now = time.time()
    for uid in [u for u, ts in _online.items() if now - ts > _ONLINE_WINDOW]:
        _online.pop(uid, None)
    return len(_online)


def _reachable():
    """探测容器是否可达（GET noVNC 页），5 秒缓存避免频繁请求。"""
    now = time.time()
    if now - _reach_cache["ts"] < _REACH_TTL:
        return _reach_cache["ok"]
    base = current_app.config.get("CLOUD_BROWSER_INTERNAL", "http://127.0.0.1:6080").rstrip("/")
    ok = False
    try:
        with urllib.request.urlopen(base + "/vnc.html", timeout=1.5) as r:
            ok = r.status == 200
    except Exception:
        ok = False
    _reach_cache.update({"ts": now, "ok": ok})
    return ok


def _browser_url():
    cfg = current_app.config
    url = (cfg.get("CLOUD_BROWSER_URL") or "").strip()
    if not url:
        # 自动推导：当前访问主机 + 配置端口 + 路径
        host = request.host.rsplit(":", 1)[0]
        url = f"{request.scheme}://{host}:{cfg['CLOUD_BROWSER_PORT']}{cfg['CLOUD_BROWSER_PATH']}"
    # 缓存破坏：避免 iframe 加载浏览器缓存里的旧 noVNC 页
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}_t={int(time.time())}"


@bp.route("/")
@login_required
@require_tool("browser")
def index():
    return render_template("browser/index.html", url=_browser_url())


@bp.route("/heartbeat", methods=["POST"])
@login_required
@require_tool("browser")
def heartbeat():
    # 首次心跳（新会话接入）记一条审计：谁在什么时候连了远程浏览器
    if current_user.id not in _online:
        audit.log("tool", "browser_connect")
    _online[current_user.id] = time.time()
    return jsonify({"online": _online_count(), "reachable": _reachable()})


@bp.route("/status")
@login_required
@require_tool("browser")
def status():
    return jsonify({"online": _online_count(), "reachable": _reachable()})


@bp.route("/restart", methods=["POST"])
@login_required
@require_tool("browser")
def restart():
    if not current_user.is_admin:
        return jsonify({"error": "仅管理员可重启"}), 403
    container = current_app.config.get("CLOUD_BROWSER_CONTAINER", "aegis-cloud-browser")
    try:
        subprocess.run(["docker", "restart", container],
                       timeout=40, check=True, capture_output=True)
        ok = True
    except Exception:
        ok = False
    audit.log("tool", "browser_restart", {"container": container, "ok": ok})
    return (jsonify({"ok": True}) if ok
            else (jsonify({"error": f"重启失败：确认容器名 {container} 正确且 Aegis 有 docker 权限"}), 502))

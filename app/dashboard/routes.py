"""仪表盘 blueprint：首页 shell + 实时数据接口 + 权限申请。"""
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from ..core import audit, notify, sysinfo
from ..core.rbac import has_tool
from ..extensions import db
from ..models import (ApiKey, AuditLog, Credential, CreditLedger,
                      DownloadFile, HashCache, NavLink, PermissionRequest,
                      QueryLog, Tool, ToolPermission, User)

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    # 智能分流：未登录访客看官网介绍页，登录用户进控制台
    if not current_user.is_authenticated:
        return redirect(url_for("site.landing"))
    tools = Tool.query.filter_by(is_enabled=True).order_by(Tool.sort_order).all()
    # 只展示当前用户有权限的工具
    visible = [t for t in tools if has_tool(current_user, t.key)]
    return render_template("dashboard/index.html", tools=visible)


# 全局聚合缓存：多用户/多标签轮询共享，TTL 内不重复做全表聚合。
# 每用户的 credits 不进缓存，始终取实时值。
_STATS_CACHE = {"ts": 0.0, "data": None}
_STATS_TTL = 5.0


def _global_stats():
    import time as _time
    now = _time.monotonic()
    if _STATS_CACHE["data"] is not None and now - _STATS_CACHE["ts"] < _STATS_TTL:
        return _STATS_CACHE["data"]
    data = _compute_global_stats()
    _STATS_CACHE.update(ts=now, data=data)
    return data


@bp.route("/api/dashboard/stats")
@login_required
def stats():
    """仪表盘实时数据：全局聚合走 5s 缓存，credits 取实时。"""
    payload = dict(_global_stats())
    payload["credits"] = current_user.credits
    return jsonify(payload)


def _compute_global_stats():
    today = datetime.combine(date.today(), datetime.min.time())

    today_logins = AuditLog.query.filter(
        AuditLog.category == "auth", AuditLog.action == "login_success",
        AuditLog.created_at >= today).count()
    total_logins = AuditLog.query.filter(
        AuditLog.category == "auth", AuditLog.action == "login_success").count()
    today_ops = AuditLog.query.filter(AuditLog.created_at >= today).count()
    total_ops = AuditLog.query.count()
    users_total = User.query.count()
    users_active = User.query.filter(User.last_login_at >= today).count()
    tools_count = Tool.query.filter_by(is_enabled=True).count()

    # 积分消耗排行 TOP 10（账本中的负向 delta 求和）
    rows = (db.session.query(User.username, func.sum(-CreditLedger.delta))
            .join(CreditLedger, CreditLedger.user_id == User.id)
            .filter(CreditLedger.delta < 0)
            .group_by(User.id)
            .order_by(func.sum(-CreditLedger.delta).desc())
            .limit(10).all())
    ranking = [{"name": name, "value": int(total or 0)} for name, total in rows]

    # 工具真实指标
    osint_counts = dict(db.session.query(QueryLog.provider, func.count())
                        .group_by(QueryLog.provider).all())
    configured = {r.provider for r in ApiKey.query.all()}
    vault_count = Credential.query.count()
    vault_expiring = Credential.query.filter(
        Credential.expires_at.isnot(None),
        Credential.expires_at <= datetime.utcnow() + timedelta(days=7)).count()

    # 其余模块指标
    hash_total = HashCache.query.count()
    hash_found = HashCache.query.filter_by(found=True).count()
    nav_links = NavLink.query.count()
    nav_clicks = int(db.session.query(func.coalesce(func.sum(NavLink.clicks), 0)).scalar() or 0)
    dl_files = DownloadFile.query.count()
    dl_bytes = int(db.session.query(func.coalesce(func.sum(DownloadFile.size), 0)).scalar() or 0)
    pending_reqs = PermissionRequest.query.filter_by(status="pending").count()

    def _human(n):
        for u in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
            n /= 1024
        return f"{n:.1f} PB"

    return {
        "today_ops": today_ops, "total_ops": total_ops,
        "today_logins": today_logins, "total_logins": total_logins,
        "users_total": users_total, "users_active": users_active,
        "tools_count": tools_count,
        "ranking": ranking,
        "hunter_count": osint_counts.get("hunter", 0),
        "fofa_count": osint_counts.get("fofa", 0),
        "shodan_count": osint_counts.get("shodan", 0),
        "vault_count": vault_count, "vault_expiring": vault_expiring,
        "hunter_on": "hunter" in configured,
        "fofa_on": "fofa" in configured,
        "shodan_on": "shodan" in configured,
        "hash_total": hash_total, "hash_found": hash_found,
        "nav_links": nav_links, "nav_clicks": nav_clicks,
        "dl_files": dl_files, "dl_size": _human(dl_bytes),
        "pending_reqs": pending_reqs,
    }


@bp.route("/api/dashboard/system")
@login_required
def system():
    """服务器状态（CPU/内存/网络/磁盘/运行时长）。"""
    return jsonify(sysinfo.collect())


@bp.route("/permissions/request", methods=["GET", "POST"])
@login_required
def request_permission():
    tool_key = request.args.get("tool") or request.form.get("tool_key")
    if request.method == "POST":
        reason = request.form.get("reason", "")
        exists = PermissionRequest.query.filter_by(
            user_id=current_user.id, tool_key=tool_key, status="pending"
        ).first()
        if not exists:
            db.session.add(PermissionRequest(
                user_id=current_user.id, tool_key=tool_key, reason=reason
            ))
            db.session.commit()
            audit.log("tool", "permission_requested", {"tool": tool_key})
            notify.send(f"🔐 <b>权限申请</b>\n用户：{current_user.username}\n"
                        f"工具：{tool_key}\n理由：{reason or '（无）'}")
        return redirect(url_for("dashboard.index"))

    tool = Tool.query.filter_by(key=tool_key).first()
    return render_template("dashboard/request.html", tool=tool, tool_key=tool_key)

"""后台管理 blueprint：用户 / 权限 / 审批 / 审计。

功能模块上线后再补 API Key 管理、工具设置、消耗排行等页面。
"""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user

import secrets

from ..core import audit, credits, notify, security, settings
from ..core.rbac import admin_required
from ..extensions import db
from ..models import (ApiKey, AuditLog, InviteCode, PermissionRequest, Tool,
                      ToolPermission, User, utcnow)
from config import Config

# 系统设置字段：(key, 标签, 类型)  type ∈ text/int/bool/regmode
SETTING_FIELDS = [
    ("site_name", "站点名称", "text"),
    ("registration_mode", "注册模式", "regmode"),
    ("captcha_enabled", "启用图形验证码（登录/注册）", "bool"),
    ("default_credits", "新用户默认积分", "int"),
    ("login_lock_threshold", "登录失败锁定阈值（次）", "int"),
    ("login_lock_minutes", "登录锁定时长（分钟）", "int"),
    ("trusted_device_days", "可信设备有效期（天）", "int"),
]

bp = Blueprint("admin", __name__, url_prefix="/admin")

# (key, 显示名, 次要字段标签或 None)
API_PROVIDERS = [("hunter", "Hunter", None), ("fofa", "FOFA", "FOFA 邮箱"),
                 ("shodan", "Shodan", None), ("hashes", "Hashes.com", None),
                 ("telegram", "Telegram Bot", "Chat ID")]


@bp.route("/users")
@admin_required
def users():
    page = request.args.get("page", 1, type=int)
    pg = User.query.order_by(User.id).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/users.html", users=pg.items, pg=pg)


@bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")
    if not username or not password:
        flash("用户名和密码必填", "error")
        return redirect(url_for("admin.users"))
    if User.query.filter_by(username=username).first():
        flash("用户名已存在", "error")
        return redirect(url_for("admin.users"))

    user = User(username=username, display_name=username, role=role,
                credits=Config.DEFAULT_CREDITS)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    audit.log("admin", "create_user", {"username": username, "role": role})
    flash(f"已创建用户 {username}", "ok")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/credits", methods=["POST"])
@admin_required
def adjust_credits(user_id):
    user = db.session.get(User, user_id)
    if user:
        amount = int(request.form.get("amount", 0))
        credits.grant(user, amount, reason="admin.adjust")
        audit.log("admin", "adjust_credits", {"user": user.username, "amount": amount})
        flash(f"已调整 {user.username} 积分 {amount:+d}", "ok")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id)
    if user and user.id != current_user.id:
        user.is_active = not user.is_active
        db.session.commit()
        audit.log("admin", "toggle_user",
                  {"user": user.username, "active": user.is_active})
    return redirect(url_for("admin.users"))


@bp.route("/permissions", methods=["GET", "POST"])
@admin_required
def permissions():
    if request.method == "POST":
        # 审批申请：approve / reject
        req_id = int(request.form["request_id"])
        decision = request.form["decision"]
        req = db.session.get(PermissionRequest, req_id)
        if req and req.status == "pending":
            req.status = "approved" if decision == "approve" else "rejected"
            req.reviewed_by = current_user.id
            req.reviewed_at = utcnow()
            if decision == "approve":
                already = ToolPermission.query.filter_by(
                    user_id=req.user_id, tool_key=req.tool_key).first()
                if not already:
                    db.session.add(ToolPermission(
                        user_id=req.user_id, tool_key=req.tool_key,
                        granted_by=current_user.id))
            db.session.commit()
            audit.log("admin", "review_permission",
                      {"request": req_id, "decision": decision})
        return redirect(url_for("admin.permissions"))

    pending = (PermissionRequest.query
               .filter_by(status="pending")
               .order_by(PermissionRequest.created_at).all())
    users = User.query.order_by(User.id).all()
    tools = Tool.query.order_by(Tool.sort_order).all()
    return render_template("admin/permissions.html",
                           pending=pending, users=users, tools=tools)


@bp.route("/permissions/grant", methods=["POST"])
@admin_required
def grant_permission():
    """管理员直接授权（不经申请）。"""
    user_id = int(request.form["user_id"])
    tool_key = request.form["tool_key"]
    already = ToolPermission.query.filter_by(
        user_id=user_id, tool_key=tool_key).first()
    if not already:
        db.session.add(ToolPermission(
            user_id=user_id, tool_key=tool_key, granted_by=current_user.id))
        db.session.commit()
        audit.log("admin", "grant_permission",
                  {"user_id": user_id, "tool": tool_key})
    return redirect(url_for("admin.permissions"))


@bp.route("/audit")
@admin_required
def audit_logs():
    from sqlalchemy import func
    category = request.args.get("category")
    page = request.args.get("page", 1, type=int)
    q = AuditLog.query
    if category:
        q = q.filter_by(category=category)
    pg = q.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    # 本页涉及用户 → 用户名映射
    uids = {log.user_id for log in pg.items if log.user_id}
    umap = dict(db.session.query(User.id, User.username)
                .filter(User.id.in_(uids)).all()) if uids else {}
    counts = dict(db.session.query(AuditLog.category, func.count())
                  .group_by(AuditLog.category).all())
    return render_template("admin/audit.html", pg=pg, umap=umap, category=category, counts=counts)


@bp.route("/apikeys", methods=["GET", "POST"])
@admin_required
def apikeys():
    """服务端共享 API Key 配置（Fernet 加密存储）。"""
    if request.method == "POST":
        provider = request.form["provider"]
        key = request.form.get("key", "").strip()
        extra = request.form.get("extra", "").strip()  # FOFA 邮箱 / Telegram Chat ID
        if key:
            row = ApiKey.query.filter_by(provider=provider).first()
            if not row:
                row = ApiKey(provider=provider, key_cipher=security.encrypt(key))
                db.session.add(row)
            else:
                row.key_cipher = security.encrypt(key)
            row.extra_cipher = security.encrypt(extra) if extra else None
            row.is_valid = _validate_key(provider)
            db.session.commit()
            audit.log("admin", "apikey_set", {"provider": provider})
            flash(f"{provider} Key 已保存", "ok")
        return redirect(url_for("admin.apikeys"))

    configured = {r.provider: r for r in ApiKey.query.all()}
    return render_template("admin/apikeys.html", providers=API_PROVIDERS,
                           configured=configured)


@bp.route("/tools", methods=["GET", "POST"])
@admin_required
def tools_settings():
    """工具设置：启用/禁用、名称、图标、排序、单次积分。"""
    if request.method == "POST":
        t = db.session.get(Tool, int(request.form["tool_id"]))
        if t:
            if request.form.get("action") == "toggle":
                t.is_enabled = not t.is_enabled
            else:
                t.name = request.form.get("name", t.name).strip() or t.name
                t.icon = request.form.get("icon", t.icon).strip() or t.icon
                t.sort_order = int(request.form.get("sort_order") or t.sort_order)
                t.cost = int(request.form.get("cost") or 0)
            db.session.commit()
            audit.log("admin", "tool_update", {"id": t.id, "key": t.key})
        return redirect(url_for("admin.tools_settings"))
    tools = Tool.query.order_by(Tool.sort_order).all()
    return render_template("admin/tools.html", tools=tools)


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def system_settings():
    """系统设置：站点/注册/验证码/积分/登录锁定 + 邀请码管理。"""
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "save":
            pairs = {}
            for key, _label, typ in SETTING_FIELDS:
                if typ == "bool":
                    pairs[key] = "1" if request.form.get(key) == "on" else "0"
                elif typ == "int":
                    raw = request.form.get(key, "").strip()
                    pairs[key] = str(int(raw)) if raw.lstrip("-").isdigit() else settings.get(key)
                elif typ == "regmode":
                    val = request.form.get(key, "approval")
                    pairs[key] = val if val in settings.REG_MODE_LABELS else "approval"
                else:
                    pairs[key] = request.form.get(key, "").strip() or settings.get(key)
            settings.set_many(pairs)
            audit.log("admin", "settings_update", {"keys": list(pairs)})
            flash("系统设置已保存", "ok")
        elif action == "gen_invite":
            n = min(max(request.form.get("count", 1, type=int) or 1, 1), 50)
            for _ in range(n):
                db.session.add(InviteCode(
                    code=secrets.token_urlsafe(9), created_by=current_user.id))
            db.session.commit()
            audit.log("admin", "invite_generate", {"count": n})
            flash(f"已生成 {n} 个邀请码", "ok")
        elif action == "del_invite":
            inv = db.session.get(InviteCode, request.form.get("invite_id", 0, type=int))
            if inv and not inv.is_used:
                db.session.delete(inv)
                db.session.commit()
        return redirect(url_for("admin.system_settings"))

    invites = InviteCode.query.order_by(InviteCode.id.desc()).limit(100).all()
    uids = {i.used_by for i in invites if i.used_by}
    umap = dict(db.session.query(User.id, User.username)
                .filter(User.id.in_(uids)).all()) if uids else {}
    pending_users = User.query.filter_by(is_active=False).count()
    return render_template("admin/settings.html", fields=SETTING_FIELDS,
                           values=settings.as_dict(), reg_labels=settings.REG_MODE_LABELS,
                           invites=invites, umap=umap, pending_users=pending_users)


@bp.route("/notify/test", methods=["POST"])
@admin_required
def notify_test():
    ok = notify.send("✅ <b>Aegis</b> 测试推送：Telegram 通知已接通。")
    flash("测试推送已发送，请查看 Telegram" if ok else "推送失败：请检查 Bot Token / Chat ID 或网络", "ok" if ok else "error")
    return redirect(url_for("admin.apikeys"))


def _validate_key(provider):
    """尝试用一个最小查询验证 Key 是否可用；网络不可达时返回 False，不报错。

    非 OSINT provider（如 hashes）不做联网校验，直接视为已保存。
    """
    if provider not in ("hunter", "fofa", "shodan"):
        return True
    try:
        from ..tools.osint import providers as prov
        prov.query(provider, "test" if provider == "shodan" else 'title="test"', size=1)
        return True
    except Exception:
        return False

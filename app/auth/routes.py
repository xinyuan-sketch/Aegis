"""认证 blueprint：登录 / 注册 / 验证码 / 登出 / 可信设备 / TOTP 二次验证。"""
import hashlib
import secrets
import time

from flask import (Blueprint, Response, flash, redirect, render_template,
                   request, session, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from ..core import audit, captcha, credits, notify, settings, totp
from ..extensions import db
from ..models import InviteCode, TrustedDevice, User, utcnow


def _client_line():
    return f"IP：{request.remote_addr}\nUA：{request.user_agent.string[:80]}"

bp = Blueprint("auth", __name__)

# 登录爆破防护：连续失败 N 次锁定 M 分钟（内存态，按 用户名+IP 计；阈值/时长走系统设置）
_LOGIN_FAILS = {}


def _fail_key(username):
    return f"{(username or '').lower()}|{request.remote_addr}"


def _lock_remaining(key):
    rec = _LOGIN_FAILS.get(key)
    if rec and rec.get("until", 0) > time.time():
        return int((rec["until"] - time.time()) / 60) + 1
    return 0


def _record_fail(key):
    """记一次失败；达到阈值则锁定并返回 True。"""
    threshold = settings.get_int("login_lock_threshold", 5)
    minutes = settings.get_int("login_lock_minutes", 10)
    rec = _LOGIN_FAILS.setdefault(key, {"n": 0, "until": 0})
    rec["n"] += 1
    if rec["n"] >= threshold:
        rec["until"] = time.time() + minutes * 60
        rec["n"] = 0
        return True
    return False


def _clear_fail(key):
    _LOGIN_FAILS.pop(key, None)


def _safe_next():
    """仅允许站内相对跳转，防开放重定向。"""
    nxt = request.args.get("next", "")
    # 必须以单个 / 开头且不是 //（协议相对）或含协议
    if nxt.startswith("/") and not nxt.startswith("//") and "://" not in nxt:
        return nxt
    return None


def _device_fingerprint():
    """基于 UA + 语言生成粗粒度设备指纹。生产可换更强的前端指纹方案。"""
    raw = f"{request.user_agent.string}|{request.headers.get('Accept-Language', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _has_trusted_device(user):
    dev = TrustedDevice.query.filter_by(
        user_id=user.id, fingerprint=_device_fingerprint()).first()
    return dev is not None and dev.is_valid


def _add_trusted_device(user):
    if _has_trusted_device(user):
        return
    db.session.add(TrustedDevice(
        user_id=user.id, fingerprint=_device_fingerprint(),
        name=request.user_agent.platform or "unknown",
        expires_at=TrustedDevice.make_expiry(settings.get_int("trusted_device_days", 30))))


def _finish_login(user, remember_device):
    login_user(user)
    user.last_login_at = utcnow()
    if remember_device:
        _add_trusted_device(user)
    db.session.commit()


@bp.route("/auth/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember_device = request.form.get("trust_device") == "on"

        if settings.get_bool("captcha_enabled") and not captcha.verify(request.form.get("captcha", "")):
            flash("验证码错误", "error")
            return render_template("auth/login.html"), 400

        key = _fail_key(username)
        left = _lock_remaining(key)
        if left:
            flash(f"尝试过于频繁，请 {left} 分钟后再试", "error")
            return render_template("auth/login.html"), 429

        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            audit.log("auth", "login_failed", {"username": username})
            locked = _record_fail(key)
            if locked:
                notify.send(f"🚨 <b>登录被锁定</b>（连续失败 {settings.get_int('login_lock_threshold', 5)} 次）\n用户名：{username}\n{_client_line()}")
            else:
                notify.send(f"⚠️ <b>登录失败</b>\n用户名：{username}\n{_client_line()}")
            flash("用户名或密码错误", "error")
            return render_template("auth/login.html"), 401
        _clear_fail(key)
        if not user.is_active:
            flash("账号已被禁用，请联系管理员", "error")
            return render_template("auth/login.html"), 403

        new_device = not _has_trusted_device(user)

        # 已开启 2FA 且非可信设备 → 进入二次验证
        if user.totp_enabled and new_device:
            session["pending_2fa_uid"] = user.id
            session["pending_2fa_trust"] = remember_device
            return redirect(url_for("auth.two_factor"))

        _finish_login(user, remember_device)
        audit.log("auth", "login_success", {"trusted": remember_device})
        if new_device:
            notify.send(f"🔓 <b>新设备登录</b>\n用户：{user.username}\n{_client_line()}")
        return redirect(_safe_next() or url_for("dashboard.index"))

    return render_template("auth/login.html")


@bp.route("/auth/2fa", methods=["GET", "POST"])
def two_factor():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    uid = session.get("pending_2fa_uid")
    if not uid:
        return redirect(url_for("auth.login"))
    user = db.session.get(User, uid)
    if user is None:
        session.pop("pending_2fa_uid", None)
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        code = request.form.get("code", "")
        if totp.verify(totp.user_secret(user), code):
            trust = session.pop("pending_2fa_trust", False)
            session.pop("pending_2fa_uid", None)
            _finish_login(user, trust)
            audit.log("auth", "login_2fa_ok")
            notify.send(f"🔓 <b>新设备登录</b>（2FA 通过）\n用户：{user.username}\n{_client_line()}")
            return redirect(url_for("dashboard.index"))
        audit.log("auth", "login_2fa_fail", {"uid": uid}, user_id=uid)
        notify.send(f"⚠️ <b>2FA 验证失败</b>\n用户：{user.username}\n{_client_line()}")
        flash("验证码错误", "error")

    return render_template("auth/two_factor.html")


@bp.route("/auth/captcha")
def captcha_img():
    """返回一张一次性 SVG 验证码，答案写入 session。"""
    resp = Response(captcha.new_svg(), mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@bp.route("/auth/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    mode = settings.get("registration_mode", "approval")
    if mode == "off":
        return render_template("auth/register.html", mode="off")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        invite = request.form.get("invite", "").strip()

        def _back(msg):
            flash(msg, "error")
            return render_template("auth/register.html", mode=mode), 400

        if settings.get_bool("captcha_enabled") and not captcha.verify(request.form.get("captcha", "")):
            return _back("验证码错误")
        if not (3 <= len(username) <= 32) or not username.replace("_", "").isalnum():
            return _back("用户名需 3–32 位，仅限字母/数字/下划线")
        if len(password) < 6:
            return _back("密码至少 6 位")
        if password != password2:
            return _back("两次输入的密码不一致")
        if User.query.filter_by(username=username).first():
            return _back("用户名已存在")

        inv = None
        if mode == "invite":
            inv = InviteCode.query.filter_by(code=invite, used_by=None).first()
            if not inv:
                return _back("邀请码无效或已被使用")

        active = mode in ("open", "invite")
        user = User(username=username, display_name=username, role="user",
                    credits=0, is_active=active)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # 拿到 user.id

        bonus = settings.get_int("default_credits", 100)
        if bonus:
            credits.grant(user, bonus, "register.bonus")  # 内部 commit
        if inv:
            inv.used_by = user.id
            inv.used_at = utcnow()
        db.session.commit()

        audit.log("auth", "register", {"username": username, "mode": mode, "active": active}, user_id=user.id)
        notify.send(f"🆕 <b>新用户注册</b>（{mode}）\n用户名：{username}\n"
                    f"状态：{'已激活' if active else '待管理员审批'}\n{_client_line()}")
        if active:
            flash("注册成功，请登录", "ok")
        else:
            flash("注册已提交，等待管理员审批激活后即可登录", "ok")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", mode=mode)


@bp.route("/auth/logout")
@login_required
def logout():
    audit.log("auth", "logout")
    logout_user()
    return redirect(url_for("auth.login"))

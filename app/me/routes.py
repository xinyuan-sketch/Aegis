"""个人中心：TOTP 二次验证管理 + 可信设备管理。"""
from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)
from flask_login import current_user, login_required

from ..core import audit, totp
from ..extensions import db
from ..models import TrustedDevice

bp = Blueprint("me", __name__, url_prefix="/me")


@bp.route("/security")
@login_required
def security():
    qr, secret = "", None
    if not current_user.totp_enabled and session.get("setup_totp_secret"):
        secret = session["setup_totp_secret"]
        uri = totp.provisioning_uri(secret, current_user.username)
        qr = totp.qr_svg(uri)
    devices = (TrustedDevice.query.filter_by(user_id=current_user.id)
               .order_by(TrustedDevice.created_at.desc()).all())
    return render_template("me/security.html", qr=qr, setup_secret=secret,
                           devices=devices, totp_available=totp.available())


@bp.route("/2fa/setup", methods=["POST"])
@login_required
def totp_setup():
    if not totp.available():
        flash("服务器未安装 pyotp，无法启用 2FA", "error")
    elif not current_user.totp_enabled:
        session["setup_totp_secret"] = totp.new_secret()
    return redirect(url_for("me.security"))


@bp.route("/2fa/enable", methods=["POST"])
@login_required
def totp_enable():
    secret = session.get("setup_totp_secret")
    code = request.form.get("code", "")
    if secret and totp.verify(secret, code):
        current_user.totp_secret_cipher = totp.encrypt(secret)
        current_user.totp_enabled = True
        session.pop("setup_totp_secret", None)
        db.session.commit()
        audit.log("security", "totp_enable")
        flash("二次验证已开启", "ok")
    else:
        flash("验证码错误，请重试", "error")
    return redirect(url_for("me.security"))


@bp.route("/2fa/disable", methods=["POST"])
@login_required
def totp_disable():
    code = request.form.get("code", "")
    if totp.verify(totp.user_secret(current_user), code):
        current_user.totp_enabled = False
        current_user.totp_secret_cipher = None
        db.session.commit()
        audit.log("security", "totp_disable")
        flash("二次验证已关闭", "ok")
    else:
        flash("验证码错误，未关闭", "error")
    return redirect(url_for("me.security"))


@bp.route("/devices/<int:did>/revoke", methods=["POST"])
@login_required
def revoke_device(did):
    dev = db.session.get(TrustedDevice, did)
    if dev and (dev.user_id == current_user.id or current_user.is_admin):
        db.session.delete(dev)
        db.session.commit()
        audit.log("security", "device_revoke", {"id": did})
        flash("已撤销该可信设备", "ok")
    return redirect(url_for("me.security"))

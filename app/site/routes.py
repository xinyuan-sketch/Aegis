"""公开站点：官网介绍页（无需登录）。"""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

bp = Blueprint("site", __name__)


@bp.route("/home")
def landing():
    return render_template("site/landing.html")


@bp.route("/welcome")
def welcome():
    # 已登录直接进控制台，未登录看介绍页
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("site.landing"))

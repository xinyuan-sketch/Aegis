"""Payload 生成器：标准反弹/正向 shell 多语言模板（离线拼接，不含免杀）。"""
from flask import Blueprint, render_template
from flask_login import login_required

from ...core.rbac import require_tool

bp = Blueprint("payload", __name__, url_prefix="/tools/payload")


@bp.route("/")
@login_required
@require_tool("payload")
def index():
    return render_template("payload/index.html")

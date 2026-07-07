"""工具箱：编码/解码、哈希、加解密、密码生成、JWT 解析等。全部在浏览器本地完成，
不经服务器（敏感数据不外传），仅做页面渲染。"""
from flask import Blueprint, render_template
from flask_login import login_required

from ...core.rbac import require_tool

bp = Blueprint("utils", __name__, url_prefix="/tools/utils")


@bp.route("/")
@login_required
@require_tool("utils")
def index():
    return render_template("utils/index.html")

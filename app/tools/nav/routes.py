"""安全导航：分类链接、搜索、点击统计、书签导入。"""
import re
from collections import OrderedDict

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required

from ...core import audit
from ...core.rbac import require_tool
from ...extensions import db
from ...models import NavLink

bp = Blueprint("nav", __name__, url_prefix="/tools/nav")


@bp.route("/")
@login_required
@require_tool("nav")
def index():
    kw = request.args.get("q", "").strip()
    q = NavLink.query
    if kw:
        like = f"%{kw}%"
        q = q.filter(db.or_(NavLink.name.ilike(like), NavLink.url.ilike(like),
                            NavLink.description.ilike(like)))
    page = request.args.get("page", 1, type=int)
    pg = (q.order_by(NavLink.category, NavLink.clicks.desc(), NavLink.sort_order)
          .paginate(page=page, per_page=60, error_out=False))
    # 当前页内按分类分组
    groups = OrderedDict()
    for l in pg.items:
        groups.setdefault(l.category or "未分类", []).append(l)
    return render_template("nav/index.html", groups=groups, kw=kw, pg=pg)


@bp.route("/add", methods=["POST"])
@login_required
@require_tool("nav")
def add():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    if not name or not url:
        flash("名称与链接必填", "error")
        return redirect(url_for("nav.index"))
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    db.session.add(NavLink(
        name=name, url=url, category=request.form.get("category", "未分类").strip() or "未分类",
        description=request.form.get("description", ""), created_by=current_user.id))
    db.session.commit()
    audit.log("tool", "nav_add", {"name": name})
    flash(f"已添加「{name}」", "ok")
    return redirect(url_for("nav.index"))


@bp.route("/<int:nid>/go")
@login_required
@require_tool("nav")
def go(nid):
    link = db.session.get(NavLink, nid)
    if not link:
        abort(404)
    link.clicks = (link.clicks or 0) + 1
    db.session.commit()
    return redirect(link.url)


@bp.route("/<int:nid>/delete", methods=["POST"])
@login_required
@require_tool("nav")
def delete(nid):
    link = db.session.get(NavLink, nid)
    if link and (current_user.is_admin or link.created_by == current_user.id):
        db.session.delete(link)
        db.session.commit()
        audit.log("tool", "nav_delete", {"id": nid})
    return redirect(url_for("nav.index"))


@bp.route("/import", methods=["POST"])
@login_required
@require_tool("nav")
def import_bookmarks():
    """导入浏览器导出的 HTML 书签（Netscape 格式）。"""
    f = request.files.get("file")
    category = request.form.get("category", "导入").strip() or "导入"
    if not f:
        flash("请选择书签文件", "error")
        return redirect(url_for("nav.index"))
    html = f.read().decode("utf-8", errors="ignore")
    # 提取 <A HREF="url" ...>name</A>
    pattern = re.compile(r'<A[^>]*HREF="([^"]+)"[^>]*>(.*?)</A>', re.IGNORECASE | re.DOTALL)
    count = 0
    for url, name in pattern.findall(html):
        name = re.sub(r"<[^>]+>", "", name).strip()
        if url.startswith(("http://", "https://")) and name:
            db.session.add(NavLink(name=name[:128], url=url[:512],
                                   category=category, created_by=current_user.id))
            count += 1
    db.session.commit()
    audit.log("tool", "nav_import", {"count": count})
    flash(f"已导入 {count} 条书签", "ok")
    return redirect(url_for("nav.index"))

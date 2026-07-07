"""代码片段 / 命令库：按语言与标签分类，私密或共享，一键复制。"""
from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required
from sqlalchemy import or_

from ...core import audit
from ...extensions import db
from ...models import Snippet, User

bp = Blueprint("snippets", __name__, url_prefix="/tools/snippets")

LANGUAGES = ["bash", "powershell", "python", "sql", "php", "javascript",
             "go", "ruby", "perl", "text", "regex", "http", "yaml", "其他"]


def _visible():
    return or_(Snippet.owner_id == current_user.id, Snippet.visibility == "public")


def _own(sid):
    s = db.session.get(Snippet, sid)
    if not s or (s.owner_id != current_user.id and not current_user.is_admin):
        abort(404)
    return s


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    lang = request.args.get("lang", "").strip()
    scope = request.args.get("scope", "")
    page = request.args.get("page", 1, type=int)

    query = Snippet.query.filter(_visible())
    if scope == "mine":
        query = query.filter(Snippet.owner_id == current_user.id)
    elif scope == "shared":
        query = query.filter(Snippet.visibility == "public", Snippet.owner_id != current_user.id)
    if lang:
        query = query.filter(Snippet.language == lang)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Snippet.title.ilike(like), Snippet.body.ilike(like), Snippet.tags.ilike(like)))

    pg = query.order_by(Snippet.updated_at.desc()).paginate(page=page, per_page=15, error_out=False)
    owners = dict(db.session.query(User.id, User.username)
                  .filter(User.id.in_({s.owner_id for s in pg.items})).all()) if pg.items else {}
    langs = [r[0] for r in db.session.query(Snippet.language).filter(_visible()).distinct().all()]
    return render_template("snippets/index.html", pg=pg, owners=owners, q=q,
                           lang=lang, scope=scope, languages=LANGUAGES, used_langs=langs)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        s = Snippet(owner_id=current_user.id,
                    title=request.form.get("title", "").strip() or "无标题",
                    language=request.form.get("language", "bash"),
                    body=request.form.get("body", ""),
                    tags=request.form.get("tags", "").strip(),
                    visibility="public" if request.form.get("visibility") == "public" else "private")
        db.session.add(s)
        db.session.commit()
        audit.log("tool", "snippet_create", {"id": s.id})
        flash("片段已保存", "ok")
        return redirect(url_for("snippets.index"))
    return render_template("snippets/edit.html", snippet=None, languages=LANGUAGES)


@bp.route("/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def edit(sid):
    s = _own(sid)
    if request.method == "POST":
        s.title = request.form.get("title", "").strip() or "无标题"
        s.language = request.form.get("language", "bash")
        s.body = request.form.get("body", "")
        s.tags = request.form.get("tags", "").strip()
        s.visibility = "public" if request.form.get("visibility") == "public" else "private"
        db.session.commit()
        audit.log("tool", "snippet_update", {"id": s.id})
        flash("已更新", "ok")
        return redirect(url_for("snippets.index"))
    return render_template("snippets/edit.html", snippet=s, languages=LANGUAGES)


@bp.route("/<int:sid>/delete", methods=["POST"])
@login_required
def delete(sid):
    s = _own(sid)
    db.session.delete(s)
    db.session.commit()
    audit.log("tool", "snippet_delete", {"id": sid})
    flash("已删除", "ok")
    return redirect(url_for("snippets.index"))

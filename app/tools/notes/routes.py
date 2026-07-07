"""笔记 / 知识库：Markdown，私密或团队共享，标签 + 全文搜索 + 置顶。

工作区功能：所有登录用户可用（不走工具授权）。可见性：本人 或 public。
"""
from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required
from sqlalchemy import or_

from ...core import audit
from ...extensions import db
from ...models import Note, User

bp = Blueprint("notes", __name__, url_prefix="/tools/notes")


def _visible_filter():
    """本人 或 公开。"""
    return or_(Note.owner_id == current_user.id, Note.visibility == "public")


def _get_visible(note_id):
    n = db.session.get(Note, note_id)
    if not n or not (n.owner_id == current_user.id or n.visibility == "public"):
        abort(404)
    return n


def _get_own(note_id):
    n = db.session.get(Note, note_id)
    if not n or (n.owner_id != current_user.id and not current_user.is_admin):
        abort(404)
    return n


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip()
    scope = request.args.get("scope", "")   # ""=全部可见, mine, shared
    page = request.args.get("page", 1, type=int)

    query = Note.query.filter(_visible_filter())
    if scope == "mine":
        query = query.filter(Note.owner_id == current_user.id)
    elif scope == "shared":
        query = query.filter(Note.visibility == "public", Note.owner_id != current_user.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Note.title.ilike(like), Note.body.ilike(like), Note.tags.ilike(like)))
    if tag:
        query = query.filter(Note.tags.ilike(f"%{tag}%"))

    pg = (query.order_by(Note.pinned.desc(), Note.updated_at.desc())
          .paginate(page=page, per_page=12, error_out=False))
    owners = dict(db.session.query(User.id, User.username)
                  .filter(User.id.in_({n.owner_id for n in pg.items})).all()) if pg.items else {}
    return render_template("notes/index.html", pg=pg, owners=owners,
                           q=q, tag=tag, scope=scope)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        n = Note(owner_id=current_user.id,
                 title=request.form.get("title", "").strip() or "无标题",
                 body=request.form.get("body", ""),
                 tags=request.form.get("tags", "").strip(),
                 visibility="public" if request.form.get("visibility") == "public" else "private",
                 pinned=request.form.get("pinned") == "on")
        db.session.add(n)
        db.session.commit()
        audit.log("tool", "note_create", {"id": n.id, "vis": n.visibility})
        flash("笔记已保存", "ok")
        return redirect(url_for("notes.view", note_id=n.id))
    return render_template("notes/edit.html", note=None)


@bp.route("/<int:note_id>")
@login_required
def view(note_id):
    n = _get_visible(note_id)
    owner = db.session.get(User, n.owner_id)
    return render_template("notes/view.html", note=n, owner=owner)


@bp.route("/<int:note_id>/edit", methods=["GET", "POST"])
@login_required
def edit(note_id):
    n = _get_own(note_id)
    if request.method == "POST":
        n.title = request.form.get("title", "").strip() or "无标题"
        n.body = request.form.get("body", "")
        n.tags = request.form.get("tags", "").strip()
        n.visibility = "public" if request.form.get("visibility") == "public" else "private"
        n.pinned = request.form.get("pinned") == "on"
        db.session.commit()
        audit.log("tool", "note_update", {"id": n.id})
        flash("已更新", "ok")
        return redirect(url_for("notes.view", note_id=n.id))
    return render_template("notes/edit.html", note=n)


@bp.route("/<int:note_id>/delete", methods=["POST"])
@login_required
def delete(note_id):
    n = _get_own(note_id)
    db.session.delete(n)
    db.session.commit()
    audit.log("tool", "note_delete", {"id": note_id})
    flash("已删除", "ok")
    return redirect(url_for("notes.index"))


@bp.route("/<int:note_id>/pin", methods=["POST"])
@login_required
def pin(note_id):
    n = _get_own(note_id)
    n.pinned = not n.pinned
    db.session.commit()
    return redirect(request.referrer or url_for("notes.index"))

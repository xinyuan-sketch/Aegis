"""全局搜索：跨笔记 / 片段 / 清单 / 凭证 / 导航一次搜到（仅返回当前用户可见项）。"""
from flask import Blueprint, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import (Checklist, Credential, NavLink, Note, Snippet)

bp = Blueprint("search", __name__)

_LIMIT = 8


@bp.route("/search")
@login_required
def index():
    q = request.args.get("q", "").strip()
    groups = []
    if q:
        like = f"%{q}%"
        uid = current_user.id

        notes = (Note.query
                 .filter(or_(Note.owner_id == uid, Note.visibility == "public"),
                         or_(Note.title.ilike(like), Note.body.ilike(like), Note.tags.ilike(like)))
                 .order_by(Note.updated_at.desc()).limit(_LIMIT).all())
        groups.append(("笔记", "note", [
            {"title": n.title, "sub": (n.body or "")[:80],
             "url": url_for("notes.view", note_id=n.id)} for n in notes]))

        snips = (Snippet.query
                 .filter(or_(Snippet.owner_id == uid, Snippet.visibility == "public"),
                         or_(Snippet.title.ilike(like), Snippet.body.ilike(like), Snippet.tags.ilike(like)))
                 .order_by(Snippet.updated_at.desc()).limit(_LIMIT).all())
        groups.append(("代码片段", "snippet", [
            {"title": f"{s.title}", "sub": f"[{s.language}] " + (s.body or "")[:70],
             "url": url_for("snippets.index", q=s.title)} for s in snips]))

        cls = (Checklist.query
               .filter(or_(Checklist.owner_id == uid, Checklist.visibility == "public"),
                       Checklist.title.ilike(like))
               .order_by(Checklist.created_at.desc()).limit(_LIMIT).all())
        groups.append(("清单", "check", [
            {"title": c.title, "sub": f"{len(c.items)} 项",
             "url": url_for("checklist.view", cid=c.id)} for c in cls]))

        creds = (Credential.query
                 .filter(or_(Credential.owner_id == uid, Credential.visibility == "public"),
                         or_(Credential.title.ilike(like), Credential.username.ilike(like)))
                 .limit(_LIMIT).all())
        groups.append(("凭证", "key", [
            {"title": c.title, "sub": c.username or "", "url": url_for("vault.index")} for c in creds]))

        navs = (NavLink.query
                .filter(or_(NavLink.name.ilike(like), NavLink.url.ilike(like), NavLink.description.ilike(like)))
                .limit(_LIMIT).all())
        groups.append(("导航", "compass", [
            {"title": n.name, "sub": n.url, "url": n.url, "external": True} for n in navs]))

    total = sum(len(items) for _, _, items in groups)
    return render_template("search.html", q=q, groups=groups, total=total)

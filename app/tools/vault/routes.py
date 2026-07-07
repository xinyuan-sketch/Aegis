"""凭证保险库：团队共享凭证，Fernet 加密存储。

- 8 种类型；公开（全团队可见）/ 私密（仅创建者 + 管理员）
- 敏感值加密入库；reveal 时解密并写安全审计
- CSV 导出（BOM 头，Excel 中文不乱码）
- 到期提醒
"""
import csv
import io

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, Response, url_for)
from flask_login import current_user, login_required

from ...core import audit, security
from ...core.rbac import require_tool
from ...extensions import db
from ...models import CREDENTIAL_TYPES, Credential, utcnow

bp = Blueprint("vault", __name__, url_prefix="/tools/vault")
TYPE_MAP = dict(CREDENTIAL_TYPES)


def _visible_query():
    """当前用户可见的凭证：管理员看全部；普通用户看公开的 + 自己创建的。"""
    q = Credential.query
    if not current_user.is_admin:
        q = q.filter(db.or_(Credential.visibility == "public",
                            Credential.owner_id == current_user.id))
    return q.order_by(Credential.updated_at.desc())


def _can_edit(cred):
    return current_user.is_admin or cred.owner_id == current_user.id


@bp.route("/")
@login_required
@require_tool("vault")
def index():
    page = request.args.get("page", 1, type=int)
    pg = _visible_query().paginate(page=page, per_page=24, error_out=False)
    return render_template("vault/index.html", creds=pg.items, pg=pg,
                           types=CREDENTIAL_TYPES, type_map=TYPE_MAP)


@bp.route("/new", methods=["POST"])
@login_required
@require_tool("vault")
def create():
    title = request.form.get("title", "").strip()
    secret = request.form.get("secret", "")
    if not title or not secret:
        flash("名称与密钥必填", "error")
        return redirect(url_for("vault.index"))

    expires = request.form.get("expires_at") or None
    from datetime import datetime
    exp_dt = None
    if expires:
        try:
            exp_dt = datetime.strptime(expires, "%Y-%m-%d")
        except ValueError:
            exp_dt = None

    cred = Credential(
        owner_id=current_user.id,
        title=title,
        ctype=request.form.get("ctype", "account"),
        username=request.form.get("username", ""),
        secret_cipher=security.encrypt(secret),
        url=request.form.get("url", ""),
        note=request.form.get("note", ""),
        visibility="public" if request.form.get("visibility") == "public" else "private",
        expires_at=exp_dt,
    )
    db.session.add(cred)
    db.session.commit()
    audit.log("security", "vault_create", {"title": title, "type": cred.ctype})
    flash(f"已保存凭证「{title}」", "ok")
    return redirect(url_for("vault.index"))


@bp.route("/<int:cid>/reveal", methods=["POST"])
@login_required
@require_tool("vault")
def reveal(cid):
    cred = db.session.get(Credential, cid)
    if not cred:
        abort(404)
    # 私密凭证仅创建者 / 管理员可见
    if cred.visibility != "public" and not _can_edit(cred):
        abort(403)
    audit.log("security", "vault_reveal", {"id": cid, "title": cred.title})
    try:
        secret = security.decrypt(cred.secret_cipher)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"secret": secret})


@bp.route("/<int:cid>/delete", methods=["POST"])
@login_required
@require_tool("vault")
def delete(cid):
    cred = db.session.get(Credential, cid)
    if not cred:
        abort(404)
    if not _can_edit(cred):
        abort(403)
    db.session.delete(cred)
    db.session.commit()
    audit.log("security", "vault_delete", {"id": cid, "title": cred.title})
    flash("已删除", "ok")
    return redirect(url_for("vault.index"))


@bp.route("/export.csv")
@login_required
@require_tool("vault")
def export_csv():
    creds = _visible_query().all()
    buf = io.StringIO()
    buf.write("﻿")  # BOM，Excel 中文不乱码
    w = csv.writer(buf)
    w.writerow(["名称", "类型", "账号", "密钥", "URL", "可见性", "备注", "到期", "创建时间"])
    for c in creds:
        try:
            secret = security.decrypt(c.secret_cipher)
        except ValueError:
            secret = "<解密失败>"
        w.writerow([c.title, TYPE_MAP.get(c.ctype, c.ctype), c.username or "", secret,
                    c.url or "", "公开" if c.visibility == "public" else "私密",
                    (c.note or "").replace("\n", " "),
                    c.expires_at.strftime("%Y-%m-%d") if c.expires_at else "",
                    c.created_at.strftime("%Y-%m-%d %H:%M")])
    audit.log("security", "vault_export", {"count": len(creds)})
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=credentials.csv"})

"""下载中心：文件统一管理。磁盘用 UUID 命名（防路径穿越），DB 存元数据。"""
import os
import uuid

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_file, url_for)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ...core import audit
from ...core.rbac import require_tool
from ...extensions import db
from ...models import DownloadFile

bp = Blueprint("download", __name__, url_prefix="/tools/download")


def _dir():
    path = current_app.config["DOWNLOAD_DIR"]
    os.makedirs(path, exist_ok=True)
    return path


def _human(n):
    n = n or 0
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _owned(fid):
    rec = db.session.get(DownloadFile, fid)
    if not rec:
        abort(404)
    if not (current_user.is_admin or rec.owner_id == current_user.id):
        abort(403)
    return rec


@bp.route("/")
@login_required
@require_tool("download")
def index():
    q = DownloadFile.query
    if not current_user.is_admin:
        q = q.filter_by(owner_id=current_user.id)
    page = request.args.get("page", 1, type=int)
    pg = q.order_by(DownloadFile.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    for f in pg.items:
        f.size_h = _human(f.size)
    return render_template("download/index.html", files=pg.items, pg=pg)


@bp.route("/upload", methods=["POST"])
@login_required
@require_tool("download")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("请选择文件", "error")
        return redirect(url_for("download.index"))
    display = secure_filename(f.filename) or "file"
    stored = uuid.uuid4().hex
    path = os.path.join(_dir(), stored)
    f.save(path)
    rec = DownloadFile(owner_id=current_user.id, filename=display,
                       stored_name=stored, size=os.path.getsize(path),
                       category=request.form.get("category", "上传"))
    db.session.add(rec)
    db.session.commit()
    audit.log("tool", "download_upload", {"file": display})
    flash(f"已上传「{display}」", "ok")
    return redirect(url_for("download.index"))


@bp.route("/<int:fid>/get")
@login_required
@require_tool("download")
def get(fid):
    rec = _owned(fid)
    path = os.path.join(_dir(), rec.stored_name)
    if not os.path.exists(path):
        abort(404)
    audit.log("tool", "download_get", {"file": rec.filename})
    return send_file(path, as_attachment=True, download_name=rec.filename)


@bp.route("/<int:fid>/rename", methods=["POST"])
@login_required
@require_tool("download")
def rename(fid):
    rec = _owned(fid)
    new = secure_filename(request.form.get("name", "").strip())
    if new:
        rec.filename = new
        db.session.commit()
        audit.log("tool", "download_rename", {"id": fid, "name": new})
    return redirect(url_for("download.index"))


@bp.route("/<int:fid>/delete", methods=["POST"])
@login_required
@require_tool("download")
def delete(fid):
    rec = _owned(fid)
    path = os.path.join(_dir(), rec.stored_name)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    db.session.delete(rec)
    db.session.commit()
    audit.log("tool", "download_delete", {"id": fid, "name": rec.filename})
    flash("已删除", "ok")
    return redirect(url_for("download.index"))

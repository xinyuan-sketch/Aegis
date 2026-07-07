"""渗透清单 / Checklist：按方法论列待办、勾选进度，可套用内置模板。"""
from flask import (Blueprint, abort, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import or_

from ...core import audit
from ...extensions import db
from ...models import Checklist, ChecklistItem, User

bp = Blueprint("checklist", __name__, url_prefix="/tools/checklist")

# 内置方法论模板
TEMPLATES = {
    "web": ("Web 应用渗透", [
        "信息收集：指纹、CMS、技术栈识别", "子域名 / 目录 / 端口枚举",
        "认证与会话：弱口令、爆破、会话固定", "越权测试（水平 / 垂直）",
        "注入：SQL / 命令 / 模板 / LDAP", "XSS（反射 / 存储 / DOM）",
        "CSRF / SSRF / XXE", "文件上传与包含", "业务逻辑漏洞",
        "敏感信息泄露", "整理复现步骤与报告",
    ]),
    "recon": ("外网信息收集", [
        "确认授权范围与目标资产", "WHOIS / DNS / 证书透明度",
        "子域名枚举", "端口与服务扫描", "指纹与 CMS 识别",
        "邮箱 / 员工 / 泄露凭证搜集", "GitHub / 网盘敏感信息", "资产梳理归档",
    ]),
    "intranet": ("内网渗透", [
        "本机信息收集与权限确认", "提权（内核 / 服务 / 配置）",
        "凭证抓取与横向探测", "内网存活与端口探测", "横向移动",
        "域内信息收集（如适用）", "权限维持（受控环境）", "清理与痕迹记录",
    ]),
}


def _visible():
    return or_(Checklist.owner_id == current_user.id, Checklist.visibility == "public")


def _get_visible(cid):
    c = db.session.get(Checklist, cid)
    if not c or not (c.owner_id == current_user.id or c.visibility == "public"):
        abort(404)
    return c


def _get_own(cid):
    c = db.session.get(Checklist, cid)
    if not c or (c.owner_id != current_user.id and not current_user.is_admin):
        abort(404)
    return c


def _progress(c):
    total = len(c.items)
    done = sum(1 for i in c.items if i.done)
    return done, total, (round(done / total * 100) if total else 0)


@bp.route("/")
@login_required
def index():
    lists = Checklist.query.filter(_visible()).order_by(Checklist.created_at.desc()).all()
    owners = dict(db.session.query(User.id, User.username)
                  .filter(User.id.in_({c.owner_id for c in lists})).all()) if lists else {}
    data = [(c, *_progress(c)) for c in lists]
    return render_template("checklist/index.html", data=data, owners=owners, templates=TEMPLATES)


@bp.route("/new", methods=["POST"])
@login_required
def new():
    title = request.form.get("title", "").strip()
    tpl = request.form.get("template", "")
    if tpl in TEMPLATES and not title:
        title = TEMPLATES[tpl][0]
    c = Checklist(owner_id=current_user.id, title=title or "新清单",
                  visibility="public" if request.form.get("visibility") == "public" else "private")
    db.session.add(c)
    db.session.flush()
    if tpl in TEMPLATES:
        for i, text in enumerate(TEMPLATES[tpl][1]):
            db.session.add(ChecklistItem(checklist_id=c.id, text=text, sort_order=i))
    db.session.commit()
    audit.log("tool", "checklist_create", {"id": c.id, "tpl": tpl or None})
    return redirect(url_for("checklist.view", cid=c.id))


@bp.route("/<int:cid>")
@login_required
def view(cid):
    c = _get_visible(cid)
    owner = db.session.get(User, c.owner_id)
    done, total, pct = _progress(c)
    editable = c.owner_id == current_user.id or current_user.is_admin
    return render_template("checklist/view.html", c=c, owner=owner,
                           done=done, total=total, pct=pct, editable=editable)


@bp.route("/<int:cid>/item", methods=["POST"])
@login_required
def add_item(cid):
    c = _get_own(cid)
    text = request.form.get("text", "").strip()
    if text:
        nxt = (max((i.sort_order for i in c.items), default=-1)) + 1
        db.session.add(ChecklistItem(checklist_id=c.id, text=text, sort_order=nxt))
        db.session.commit()
    return redirect(url_for("checklist.view", cid=cid))


@bp.route("/item/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_item(item_id):
    it = db.session.get(ChecklistItem, item_id)
    if not it:
        abort(404)
    c = db.session.get(Checklist, it.checklist_id)
    if c.owner_id != current_user.id and not current_user.is_admin:
        abort(403)
    it.done = not it.done
    db.session.commit()
    done, total, pct = _progress(c)
    return jsonify({"done": it.done, "pct": pct, "count": f"{done}/{total}"})


@bp.route("/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    it = db.session.get(ChecklistItem, item_id)
    if not it:
        abort(404)
    c = db.session.get(Checklist, it.checklist_id)
    if c.owner_id != current_user.id and not current_user.is_admin:
        abort(403)
    cid = it.checklist_id
    db.session.delete(it)
    db.session.commit()
    return redirect(url_for("checklist.view", cid=cid))


@bp.route("/<int:cid>/delete", methods=["POST"])
@login_required
def delete(cid):
    c = _get_own(cid)
    db.session.delete(c)
    db.session.commit()
    audit.log("tool", "checklist_delete", {"id": cid})
    flash("已删除", "ok")
    return redirect(url_for("checklist.index"))

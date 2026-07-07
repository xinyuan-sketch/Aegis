"""OSINT 查询：Hunter / FOFA / Shodan 统一入口。

流程：查询 → 缓存去重 → provider 请求 → 积分扣费 → 审计 → 结果 / CSV。
相同查询命中缓存则不重复请求、不重复扣费。
"""
import csv
import hashlib
import io
import json

from flask import (Blueprint, Response, jsonify, render_template, request)
from flask_login import current_user, login_required

from ...core import audit, credits
from ...core.rbac import require_tool
from ...extensions import db
from ...models import QueryCache, QueryLog, Tool
from . import providers

bp = Blueprint("osint", __name__, url_prefix="/tools/osint")


def _hash(provider, q, size):
    return hashlib.sha256(f"{provider}|{q}|{size}".encode()).hexdigest()


def _phash(provider, q, size, page):
    return hashlib.sha256(f"{provider}|{q}|{size}|{page}".encode()).hexdigest()


def _tool_cost():
    t = Tool.query.filter_by(key="osint").first()
    return t.cost if t else 0


@bp.route("/")
@login_required
@require_tool("osint")
def index():
    recent = (QueryLog.query.filter_by(user_id=current_user.id)
              .order_by(QueryLog.created_at.desc()).limit(15).all())
    return render_template("osint/index.html", recent=recent,
                           providers=providers.PROVIDERS, cost=_tool_cost())


@bp.route("/query", methods=["POST"])
@login_required
@require_tool("osint")
def do_query():
    provider = request.form.get("provider", "fofa")
    q = request.form.get("query", "").strip()
    size = min(int(request.form.get("size", 100) or 100), 1000)
    page = max(int(request.form.get("page", 1) or 1), 1)
    if provider not in providers.PROVIDERS:
        return jsonify({"error": "未知查询引擎"}), 400
    if not q:
        return jsonify({"error": "请输入查询语句"}), 400

    h = _phash(provider, q, size, page)
    cached = QueryCache.query.filter_by(provider=provider, query_hash=h).first()

    if cached:
        data = json.loads(cached.result_json)
        db.session.add(QueryLog(user_id=current_user.id, provider=provider, query_text=q,
                                result_count=cached.result_count, cost=0, cache_hit=True))
        db.session.commit()
        audit.log("tool", "osint_query", {"provider": provider, "query": q, "page": page, "cache": True})
        return jsonify({**data, "cached": True, "cost": 0, "page": page, "size": size})

    # 未命中缓存：扣费 + 请求
    cost = _tool_cost()
    try:
        credits.charge(current_user, cost, "osint.query")
    except credits.InsufficientCredits:
        return jsonify({"error": "积分不足，无法查询"}), 402

    try:
        data = providers.query(provider, q, size, page)
    except providers.ProviderError as exc:
        # 请求失败，退还积分
        if cost:
            credits.grant(current_user, cost, "osint.refund")
        return jsonify({"error": str(exc)}), 502

    db.session.add(QueryCache(provider=provider, query_hash=h, query_text=q,
                              result_json=json.dumps(data, ensure_ascii=False),
                              result_count=data.get("total", 0)))
    db.session.add(QueryLog(user_id=current_user.id, provider=provider, query_text=q,
                            result_count=data.get("total", 0), cost=cost, cache_hit=False))
    db.session.commit()
    audit.log("tool", "osint_query", {"provider": provider, "query": q, "page": page, "total": data.get("total", 0)})
    return jsonify({**data, "cached": False, "cost": cost, "page": page, "size": size})


@bp.route("/export.csv", methods=["POST"])
@login_required
@require_tool("osint")
def export_csv():
    provider = request.form.get("provider", "fofa")
    q = request.form.get("query", "").strip()
    size = min(int(request.form.get("size", 100) or 100), 1000)
    page = max(int(request.form.get("page", 1) or 1), 1)
    h = _phash(provider, q, size, page)
    cached = QueryCache.query.filter_by(provider=provider, query_hash=h).first()
    if cached:
        data = json.loads(cached.result_json)
    else:
        try:
            data = providers.query(provider, q, size, page)
        except providers.ProviderError as exc:
            return jsonify({"error": str(exc)}), 502

    buf = io.StringIO()
    buf.write("﻿")  # BOM
    w = csv.writer(buf)
    w.writerow(data.get("columns", []))
    for row in data.get("rows", []):
        w.writerow(row)
    audit.log("tool", "osint_export", {"provider": provider, "query": q})
    fname = f"{provider}_result.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})

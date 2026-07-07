"""Hash 查询：MD5 / SHA1 / SHA256 批量识别与查库。

流程：批量输入 → 算法识别 → 缓存命中（免费）→ 对未命中的在线查库 → 扣费 → 缓存 → 审计。
仅对「新发起在线查询」的 hash 扣费；缓存命中不扣费。
"""
import csv
import io

from flask import (Blueprint, Response, jsonify, render_template, request)
from flask_login import current_user, login_required

from ...core import audit, credits
from ...core.rbac import require_tool
from ...extensions import db
from ...models import HashCache, Tool
from . import providers

bp = Blueprint("hash", __name__, url_prefix="/tools/hash")


def _tool_cost():
    t = Tool.query.filter_by(key="hash").first()
    return t.cost if t else 0


@bp.route("/")
@login_required
@require_tool("hash")
def index():
    return render_template("hashtool/index.html", cost=_tool_cost())


@bp.route("/lookup", methods=["POST"])
@login_required
@require_tool("hash")
def lookup():
    raw = request.form.get("hashes", "")
    # 换行分隔、去重、去空
    items = []
    seen = set()
    for line in raw.replace(",", "\n").splitlines():
        h = line.strip().lower()
        if h and h not in seen:
            seen.add(h)
            items.append(h)
    if not items:
        return jsonify({"error": "请输入至少一个 hash"}), 400
    if len(items) > 200:
        return jsonify({"error": "单次最多 200 个"}), 400

    results = {}          # hash -> record
    pending = []          # 未缓存的 hash
    for h in items:
        cached = HashCache.query.filter_by(hash_value=h).first()
        if cached and cached.found:
            results[h] = {"hash": h, "algo": cached.algo,
                          "found": True, "plaintext": cached.plaintext or ""}
        else:
            pending.append(h)

    # 1) 本地字典反查（免费、离线）
    offline = providers.crack_offline(pending)

    # 2) 剩余未命中的走在线查库（仅在已配置 Key 时才尝试）
    still = [h for h in pending if h not in offline]
    online = {}
    online_error = None
    if still and providers.online_ready():
        online, online_error = providers.lookup_online(still)

    # 3) 计费：只对「在线新破解成功」的收费；离线命中 / 未命中 / 缓存 一律免费
    online_found = [h for h in still if online.get(h)]
    cost_each = _tool_cost()
    total_cost = cost_each * len(online_found)
    if total_cost:
        try:
            credits.charge(current_user, total_cost, "hash.lookup")
        except credits.InsufficientCredits:
            # 余额不足：不泄露在线破解结果，仅保留免费部分
            online, total_cost = {}, 0

    # 4) 汇总；仅缓存命中结果（负结果不缓存，便于日后字典扩充后再查）
    for h in pending:
        plain = offline.get(h) or online.get(h)
        found = plain is not None
        algo = providers.identify(h)
        if found and not HashCache.query.filter_by(hash_value=h).first():
            db.session.add(HashCache(hash_value=h, algo=algo,
                                     plaintext=plain, found=True))
        results[h] = {"hash": h, "algo": algo, "found": found, "plaintext": plain or ""}
    db.session.commit()

    audit.log("tool", "hash_lookup",
              {"count": len(items), "offline": len(offline), "online": len(still)})
    ordered = [results[h] for h in items]
    found_n = sum(1 for r in ordered if r["found"])
    return jsonify({"rows": ordered, "total": len(ordered), "found": found_n,
                    "cost": total_cost, "online_error": online_error})


@bp.route("/export.csv", methods=["POST"])
@login_required
@require_tool("hash")
def export_csv():
    raw = request.form.get("hashes", "")
    items = [l.strip().lower() for l in raw.replace(",", "\n").splitlines() if l.strip()]
    # 一次性批量取缓存，避免逐条查询（N+1）
    cmap = {c.hash_value: c for c in
            HashCache.query.filter(HashCache.hash_value.in_(items)).all()} if items else {}
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["hash", "算法", "是否命中", "明文"])
    for h in items:
        c = cmap.get(h)
        if c:
            w.writerow([h, c.algo, "是" if c.found else "否", c.plaintext or ""])
        else:
            w.writerow([h, providers.identify(h), "未查询", ""])
    audit.log("tool", "hash_export", {"count": len(items)})
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=hash_result.csv"})

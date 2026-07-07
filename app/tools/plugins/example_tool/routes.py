"""示例插件骨架 —— 复制本目录改名即可接入你自己的工具。

本文件是脚手架，**不含任何实际功能 / payload**。适用于你自行实现的模块，
包括本仓库不提供的「免杀执行器 / shellcode 加载器」等——把你的逻辑写进 run()。

已内置平台能力，直接复用：
  @require_tool("<key>")            权限门（需先在 tools 表 seed 该 key）
  credits.charge(user, n, "<原因>")  按次扣积分
  audit.log("tool", "<动作>", {...}) 审计留痕
  notify.send("...")                Telegram 通知（可选）

接入三步见同目录 README.md。
"""
from flask import Blueprint, jsonify, render_template_string, request
from flask_login import current_user, login_required

from ....core import audit, credits  # noqa: F401  (credits 供你按需扣费)
from ....core.rbac import require_tool

bp = Blueprint("example_tool", __name__, url_prefix="/tools/example")

TOOL_KEY = "example"  # 需与 tools 表中该工具的 key 一致

_PAGE = """
{% extends "base.html" %}
{% block title %}示例插件 · Aegis{% endblock %}
{% block content %}
<div class="page-head"><h1>示例插件</h1></div>
<div class="panel" style="margin-top:0">
  <label class="card-label">输入</label>
  <textarea id="in" rows="4" placeholder="在此输入..."></textarea>
  <div style="margin-top:12px"><button id="run">执行</button></div>
  <pre id="out" style="margin-top:12px;white-space:pre-wrap"></pre>
</div>
<script>
document.getElementById('run').onclick = async () => {
  const r = await fetch("/tools/example/run", {method:'POST',
    body:new URLSearchParams({input:document.getElementById('in').value})});
  document.getElementById('out').textContent = JSON.stringify(await r.json(), null, 2);
};
</script>
{% endblock %}
"""


@bp.route("/")
@login_required
@require_tool(TOOL_KEY)
def index():
    return render_template_string(_PAGE)


@bp.route("/run", methods=["POST"])
@login_required
@require_tool(TOOL_KEY)
def run():
    data = request.form.get("input", "")

    # === 在此实现你的逻辑 =====================================
    # 例如按次扣费：credits.charge(current_user, 1, "example.run")
    # 例如推送通知：notify.send("...")
    audit.log("tool", "example_run", {"len": len(data)})
    return jsonify({"error": "示例插件占位：请在 app/tools/plugins/example_tool/routes.py 的 run() 中实现逻辑"})
    # =========================================================

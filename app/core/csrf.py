"""轻量级会话级 CSRF 防护（零额外依赖）。

- 每会话生成一个随机 token，存 session。
- 对所有状态变更请求（非安全方法）强制校验：表单字段 csrf_token 或请求头 X-CSRFToken。
- 模板通过 {{ csrf_token() }} 取 token；base.html 输出为 <meta>，前端 JS 自动为
  所有 POST 表单与 fetch 注入，无需逐表单改造。
"""
import hmac
import secrets

from flask import abort, request, session

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_FORM_FIELD = "csrf_token"
_HEADER_NAMES = ("X-CSRFToken", "X-CSRF-Token", "X-Csrf-Token")


def get_token():
    """取当前会话 CSRF token，没有则惰性生成。"""
    tok = session.get("_csrf_token")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf_token"] = tok
    return tok


def init_app(app):
    @app.before_request
    def _csrf_protect():
        if request.method in _SAFE_METHODS:
            return
        real = session.get("_csrf_token")
        sent = request.form.get(_FORM_FIELD)
        if not sent:
            for name in _HEADER_NAMES:
                sent = request.headers.get(name)
                if sent:
                    break
        if not real or not sent or not hmac.compare_digest(str(real), str(sent)):
            abort(400, description="CSRF 校验失败，请刷新页面后重试")

    @app.context_processor
    def _inject_csrf():
        return {"csrf_token": get_token}

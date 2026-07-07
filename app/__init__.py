"""Flask 应用工厂。"""
from flask import Flask, url_for
from flask_login import current_user
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import Config
from .extensions import db, login_manager

# 已实现路由的工具 → 端点映射（未实现的工具在侧边栏显示为占位）
TOOL_ROUTES = {"vault": "vault.index", "osint": "osint.index",
               "hash": "hash.index", "nav": "nav.index",
               "download": "download.index", "payload": "payload.index",
               "browser": "browser.index", "utils": "utils.index"}


def _apply_sqlite_pragmas(pragmas):
    """在每个 SQLite 连接建立时应用 PRAGMA（WAL、busy_timeout 等）。"""

    @event.listens_for(Engine, "connect")
    def _set_pragmas(dbapi_conn, _record):
        # 仅对 sqlite3 连接生效
        if dbapi_conn.__class__.__module__.startswith("sqlite3"):
            cur = dbapi_conn.cursor()
            for key, value in pragmas.items():
                cur.execute(f"PRAGMA {key}={value};")
            cur.close()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        _apply_sqlite_pragmas(app.config["SQLITE_PRAGMAS"])

    db.init_app(app)
    login_manager.init_app(app)

    from .core import csrf
    csrf.init_app(app)

    from . import models  # noqa: F401  确保模型被注册

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    # 注册核心 blueprints
    from .auth.routes import bp as auth_bp
    from .dashboard.routes import bp as dashboard_bp
    from .admin.routes import bp as admin_bp
    from .me.routes import bp as me_bp
    from .site.routes import bp as site_bp
    from .search.routes import bp as search_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(me_bp)
    app.register_blueprint(site_bp)
    app.register_blueprint(search_bp)

    # 注册功能模块 blueprints（挂在核心平台层之上，互不依赖）
    from .tools.vault.routes import bp as vault_bp
    from .tools.osint.routes import bp as osint_bp
    from .tools.hashtool.routes import bp as hash_bp
    from .tools.nav.routes import bp as nav_bp
    from .tools.download.routes import bp as download_bp
    from .tools.payload.routes import bp as payload_bp
    from .tools.browser.routes import bp as browser_bp
    from .tools.utils.routes import bp as utils_bp
    from .tools.notes.routes import bp as notes_bp
    from .tools.snippets.routes import bp as snippets_bp
    from .tools.checklist.routes import bp as checklist_bp
    app.register_blueprint(vault_bp)
    app.register_blueprint(osint_bp)
    app.register_blueprint(hash_bp)
    app.register_blueprint(nav_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(payload_bp)
    app.register_blueprint(browser_bp)
    app.register_blueprint(utils_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(snippets_bp)
    app.register_blueprint(checklist_bp)

    import json as _json

    @app.template_filter("fromjson")
    def _fromjson(s):
        try:
            return _json.loads(s) if s else {}
        except Exception:
            return {}

    @app.context_processor
    def inject_site_settings():
        """站点级设置：所有模板（含登录/注册页）可用。"""
        from .core import settings as st
        try:
            return {"site_name": st.get("site_name", "Aegis"),
                    "captcha_on": st.get_bool("captcha_enabled"),
                    "reg_mode": st.get("registration_mode", "approval"),
                    "trusted_days": st.get_int("trusted_device_days", 30)}
        except Exception:
            return {"site_name": "Aegis", "captcha_on": False,
                    "reg_mode": "approval", "trusted_days": 30}

    @app.context_processor
    def inject_nav_tools():
        """侧边栏工具列表：所有已登录页面共享，仅显示当前用户有权限的工具。"""
        if not current_user.is_authenticated:
            return {}
        from .models import Tool, ToolPermission
        # 一次性取出当前用户的授权集合，避免逐工具查询（N+1）；管理员拥有全部
        if current_user.is_admin:
            allowed = None  # None 表示全部放行
        else:
            allowed = {p.tool_key for p in ToolPermission.query
                       .filter_by(user_id=current_user.id).all()}
        nav = []
        for t in Tool.query.filter_by(is_enabled=True).order_by(Tool.sort_order):
            if allowed is not None and t.key not in allowed:
                continue
            ep = TOOL_ROUTES.get(t.key)
            nav.append({"name": t.name, "icon": t.icon,
                        "url": url_for(ep) if ep else "#", "endpoint": ep})
        return {"nav_tools": nav}

    return app

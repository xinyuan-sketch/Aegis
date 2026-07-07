"""RBAC 权限装饰器。"""
from functools import wraps

from flask import abort, redirect, url_for
from flask_login import current_user

from ..models import ToolPermission


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def has_tool(user, tool_key: str) -> bool:
    """管理员拥有全部工具权限；普通用户需被显式授权。"""
    if user.is_admin:
        return True
    return (
        ToolPermission.query
        .filter_by(user_id=user.id, tool_key=tool_key)
        .first() is not None
    )


def require_tool(tool_key: str):
    """功能模块路由用：未授权则引导至权限申请页。"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not has_tool(current_user, tool_key):
                return redirect(url_for("dashboard.request_permission", tool=tool_key))
            return f(*args, **kwargs)
        return wrapper
    return decorator

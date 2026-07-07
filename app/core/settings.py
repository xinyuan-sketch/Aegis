"""数据库键值系统设置。

带默认值回退：未在 settings 表配置的项使用 DEFAULTS。读取用 flask.g 做每请求缓存，
避免同一请求内重复查询，也避免多 worker 间的长期缓存不一致。
"""
from flask import g, has_request_context

from ..extensions import db
from ..models import Setting

# 默认值（管理员未覆盖时生效）
DEFAULTS = {
    "site_name": "Aegis",
    "registration_mode": "approval",   # off / approval / invite / open
    "captcha_enabled": "1",            # 1 / 0
    "default_credits": "100",
    "login_lock_threshold": "5",
    "login_lock_minutes": "10",
    "trusted_device_days": "30",
}

# 注册模式可读名（供页面展示）
REG_MODE_LABELS = {
    "off": "关闭注册（仅管理员建号）",
    "approval": "需管理员审批",
    "invite": "邀请码注册",
    "open": "开放注册",
}


def _map():
    """当前 settings 表快照（每请求缓存一次）。"""
    if has_request_context():
        if "settings_map" not in g:
            g.settings_map = {s.key: s.value for s in Setting.query.all()}
        return g.settings_map
    return {s.key: s.value for s in Setting.query.all()}


def get(key, default=None):
    m = _map()
    if key in m and m[key] is not None:
        return m[key]
    return DEFAULTS.get(key, default)


def get_int(key, default=0):
    try:
        return int(get(key, default))
    except (TypeError, ValueError):
        return default


def get_bool(key):
    return str(get(key, "0")).lower() in ("1", "true", "on", "yes")


def set(key, value):
    row = db.session.get(Setting, key)
    if not row:
        row = Setting(key=key)
        db.session.add(row)
    row.value = str(value)
    db.session.commit()
    if has_request_context() and "settings_map" in g:
        g.settings_map[key] = str(value)


def set_many(pairs: dict):
    for k, v in pairs.items():
        row = db.session.get(Setting, k)
        if not row:
            row = Setting(key=k)
            db.session.add(row)
        row.value = str(v)
    db.session.commit()
    if has_request_context() and "settings_map" in g:
        for k, v in pairs.items():
            g.settings_map[k] = str(v)


def as_dict():
    d = dict(DEFAULTS)
    d.update({k: v for k, v in _map().items() if v is not None})
    return d

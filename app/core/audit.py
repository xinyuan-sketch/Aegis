"""审计服务：统一记录敏感操作。"""
import json

from flask import request
from flask_login import current_user

from ..extensions import db
from ..models import AuditLog


def log(category: str, action: str, detail: dict | None = None, user_id: int | None = None):
    """写一条审计日志。detail 会序列化为 JSON。"""
    if user_id is None and current_user.is_authenticated:
        user_id = current_user.id
    entry = AuditLog(
        user_id=user_id,
        category=category,
        action=action,
        detail=json.dumps(detail or {}, ensure_ascii=False),
        ip=request.remote_addr if request else None,
    )
    db.session.add(entry)
    db.session.commit()

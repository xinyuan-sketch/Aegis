"""Telegram 通知。Bot Token 与 Chat ID 存于 api_keys(provider='telegram')，Fernet 加密。

所有发送为尽力而为：未配置 / 网络失败均静默返回 False，绝不阻断主流程。
"""
from .security import decrypt
from ..models import ApiKey

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


def _config():
    row = ApiKey.query.filter_by(provider="telegram").first()
    if not row:
        return None, None
    try:
        token = decrypt(row.key_cipher)
        chat = decrypt(row.extra_cipher) if row.extra_cipher else None
    except ValueError:
        return None, None
    return token, chat


def enabled():
    token, chat = _config()
    return bool(token and chat)


def send(text: str) -> bool:
    """向配置的 Telegram 会话推送一条消息。"""
    if not _HAS_REQUESTS:
        return False
    token, chat = _config()
    if not (token and chat):
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=10)
        return r.ok
    except Exception:
        return False

"""Fernet 加密封装：用于凭证与 API Key 的可逆加密。

主密钥 AEGIS_MASTER_KEY 从环境变量读取，绝不入库。密码用不可逆 hash，
只有需要给用户复制回明文的密钥/凭证才用这里的可逆加密。
"""
from flask import current_app
from cryptography.fernet import Fernet, InvalidToken


def _fernet():
    key = current_app.config.get("MASTER_KEY")
    if not key:
        raise RuntimeError(
            "AEGIS_MASTER_KEY 未配置。生成方式："
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> bytes:
    """加密字符串，返回密文 bytes（存 LargeBinary）。"""
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(cipher: bytes) -> str:
    """解密密文，返回明文字符串。密钥不匹配会抛 InvalidToken。"""
    try:
        return _fernet().decrypt(cipher).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("解密失败：主密钥不匹配或数据损坏") from exc


def mask(value: str, keep: int = 2) -> str:
    """脱敏显示，仅保留首尾若干字符。"""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"

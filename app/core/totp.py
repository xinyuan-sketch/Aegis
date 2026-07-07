"""TOTP 二次验证辅助。密钥以 Fernet 加密存于 users.totp_secret_cipher。"""
import io

from .security import decrypt, encrypt  # noqa: F401 (encrypt 供路由使用)

try:
    import pyotp
    _HAS_PYOTP = True
except ImportError:
    _HAS_PYOTP = False

try:
    import qrcode
    import qrcode.image.svg
    _HAS_QR = True
except ImportError:
    _HAS_QR = False

ISSUER = "Aegis"


def available():
    return _HAS_PYOTP


def new_secret():
    return pyotp.random_base32()


def provisioning_uri(secret, username):
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def verify(secret, code):
    if not (_HAS_PYOTP and secret and code):
        return False
    try:
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:
        return False


def user_secret(user):
    if not user.totp_secret_cipher:
        return None
    try:
        return decrypt(user.totp_secret_cipher)
    except ValueError:
        return None


def qr_svg(uri):
    """返回 QR 的 SVG 字符串（不依赖 PIL）。"""
    if not _HAS_QR:
        return ""
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()

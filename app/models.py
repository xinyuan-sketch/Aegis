"""全部 ORM 模型（核心平台层）。功能模块的表在各模块迭代时补充。"""
from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.utcnow()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(64))
    role = db.Column(db.String(16), default="user", nullable=False)  # admin / user
    credits = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    wechat_openid = db.Column(db.String(64), unique=True, nullable=True)
    avatar_url = db.Column(db.String(255))
    totp_secret_cipher = db.Column(db.LargeBinary)   # TOTP 密钥（Fernet 加密）
    totp_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_login_at = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    # Flask-Login 用 is_active 判断能否登录；禁用用户直接被拒
    @property
    def is_active_flag(self):
        return self.is_active


class Tool(db.Model):
    __tablename__ = "tools"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    icon = db.Column(db.String(64), default="tool")
    sort_order = db.Column(db.Integer, default=0)
    is_enabled = db.Column(db.Boolean, default=True)
    cost = db.Column(db.Integer, default=1)  # 单次操作扣费


class ToolPermission(db.Model):
    __tablename__ = "tool_permissions"
    __table_args__ = (db.UniqueConstraint("user_id", "tool_key"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    tool_key = db.Column(db.String(32), nullable=False)
    granted_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow)


class PermissionRequest(db.Model):
    __tablename__ = "permission_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    tool_key = db.Column(db.String(32), nullable=False)
    reason = db.Column(db.String(255))
    status = db.Column(db.String(16), default="pending", index=True)  # pending/approved/rejected
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)


class TrustedDevice(db.Model):
    __tablename__ = "trusted_devices"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    fingerprint = db.Column(db.String(128), nullable=False, index=True)
    name = db.Column(db.String(64))
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def is_valid(self):
        return self.expires_at > utcnow()

    @staticmethod
    def make_expiry(days):
        return utcnow() + timedelta(days=days)


class CreditLedger(db.Model):
    """积分账本，只追加。每次扣费/充值写一条并同步 users.credits。"""
    __tablename__ = "credit_ledger"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    delta = db.Column(db.Integer, nullable=False)  # 正=充值 负=消耗
    balance_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    category = db.Column(db.String(16), index=True)  # auth/admin/tool/security
    action = db.Column(db.String(64))
    detail = db.Column(db.Text)  # JSON 字符串
    ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class ApiKey(db.Model):
    """服务端共享 API Key，密文存储（Fernet）。"""
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(32), unique=True, nullable=False)  # hunter/fofa/shodan
    key_cipher = db.Column(db.LargeBinary, nullable=False)
    extra_cipher = db.Column(db.LargeBinary)  # 备用密文字段（如 FOFA email）
    is_valid = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


# 凭证类型（共享账号中心）
CREDENTIAL_TYPES = [
    ("account", "账号密码"), ("apikey", "API Key"), ("cookie", "Cookie"),
    ("token", "Token"), ("ssh", "SSH 密钥"), ("license", "License"),
    ("email", "邮箱"), ("other", "其他"),
]


class Credential(db.Model):
    """团队共享凭证。敏感值 Fernet 加密存储，脱敏仅为 UI 层。"""
    __tablename__ = "credentials"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(128), nullable=False)
    ctype = db.Column(db.String(16), default="account")  # 见 CREDENTIAL_TYPES
    username = db.Column(db.String(255))                  # 账号/标识（明文，非敏感）
    secret_cipher = db.Column(db.LargeBinary, nullable=False)  # 密码/密钥密文
    url = db.Column(db.String(255))
    note = db.Column(db.Text)
    visibility = db.Column(db.String(8), default="private", index=True)  # public / private
    expires_at = db.Column(db.DateTime)                   # 到期提醒（可空）
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @property
    def is_expiring(self):
        if not self.expires_at:
            return False
        return (self.expires_at - utcnow()).days <= 7


class QueryLog(db.Model):
    """OSINT 查询记录（用于计数、审计、排行）。"""
    __tablename__ = "query_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    provider = db.Column(db.String(16), nullable=False, index=True)  # hunter/fofa/shodan
    query_text = db.Column("query", db.String(512))
    result_count = db.Column(db.Integer, default=0)
    cost = db.Column(db.Integer, default=0)
    cache_hit = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class QueryCache(db.Model):
    """OSINT 查询结果缓存，相同查询命中不重复扣费/请求。"""
    __tablename__ = "query_cache"
    __table_args__ = (db.UniqueConstraint("provider", "query_hash"),)

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(16), nullable=False)
    query_hash = db.Column(db.String(64), nullable=False, index=True)
    query_text = db.Column("query", db.String(512))
    result_json = db.Column(db.Text)  # 结果 JSON
    result_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)


class DownloadFile(db.Model):
    """下载中心文件元数据。磁盘用 UUID 存储，DB 记录展示名。"""
    __tablename__ = "download_files"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    filename = db.Column(db.String(255), nullable=False)   # 展示名
    stored_name = db.Column(db.String(64), nullable=False)  # 磁盘 UUID 名
    size = db.Column(db.Integer, default=0)
    category = db.Column(db.String(32), default="上传")     # 上传/报告/结果/截图
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class NavLink(db.Model):
    """安全导航链接。点击统计、分类、排序。"""
    __tablename__ = "nav_links"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(64), default="未分类", index=True)
    name = db.Column(db.String(128), nullable=False)
    url = db.Column(db.String(512), nullable=False)
    description = db.Column(db.String(255))
    clicks = db.Column(db.Integer, default=0)
    sort_order = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow)


class HashCache(db.Model):
    """Hash 解密结果缓存，相同 hash 秒出、不重复扣费。"""
    __tablename__ = "hash_cache"

    id = db.Column(db.Integer, primary_key=True)
    hash_value = db.Column(db.String(128), unique=True, nullable=False, index=True)
    algo = db.Column(db.String(16))  # md5/sha1/sha256/unknown
    plaintext = db.Column(db.String(512))
    found = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)


class Setting(db.Model):
    """系统设置键值表。管理员在「系统设置」页维护，未配置项回退到代码默认值。"""
    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)


class InviteCode(db.Model):
    """注册邀请码（单次使用）。邀请码注册模式下由管理员生成。"""
    __tablename__ = "invite_codes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    used_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow)
    used_at = db.Column(db.DateTime)

    @property
    def is_used(self):
        return self.used_by is not None


def _tag_list(tags):
    return [t.strip() for t in (tags or "").split(",") if t.strip()]


class Note(db.Model):
    """团队笔记 / 知识库（Markdown）。private 仅本人可见，public 团队共享。"""
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    tags = db.Column(db.String(255))                       # 逗号分隔
    visibility = db.Column(db.String(8), default="private", index=True)  # private/public
    pinned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @property
    def tag_list(self):
        return _tag_list(self.tags)


class Snippet(db.Model):
    """代码片段 / 命令库。可按语言与标签分类，一键复制。"""
    __tablename__ = "snippets"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    language = db.Column(db.String(32), default="bash")
    body = db.Column(db.Text)
    tags = db.Column(db.String(255))
    visibility = db.Column(db.String(8), default="private", index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @property
    def tag_list(self):
        return _tag_list(self.tags)


class Checklist(db.Model):
    """渗透清单 / Checklist（含若干条目）。"""
    __tablename__ = "checklists"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    visibility = db.Column(db.String(8), default="private", index=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    items = db.relationship("ChecklistItem", backref="checklist",
                            cascade="all, delete-orphan",
                            order_by="ChecklistItem.sort_order")


class ChecklistItem(db.Model):
    __tablename__ = "checklist_items"

    id = db.Column(db.Integer, primary_key=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey("checklists.id"), nullable=False, index=True)
    text = db.Column(db.String(500), nullable=False)
    done = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)

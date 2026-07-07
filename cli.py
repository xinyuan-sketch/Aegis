"""管理命令：初始化数据库、创建管理员、初始化工具。

  python cli.py init-db
  python cli.py create-admin <username> <password>
  python cli.py seed-tools
"""
import sys

from app import create_app
from app.extensions import db
from app.models import Tool, User
from config import Config

# 默认工具清单（对应各功能模块，后续增量接入）
DEFAULT_TOOLS = [
    ("osint", "OSINT 查询", "search", 10, 2),
    ("hash", "Hash 查询", "hash", 20, 1),
    ("vault", "共享凭证", "key", 30, 0),
    ("nav", "安全导航", "compass", 40, 0),
    ("download", "下载中心", "download", 50, 0),
    ("browser", "云浏览器", "monitor", 60, 0),
    ("payload", "Payload 生成器", "terminal", 70, 0),
    ("utils", "工具箱", "toolbox", 80, 0),
]


def init_db(app):
    with app.app_context():
        db.create_all()
    print("数据库已初始化。")


def create_admin(app, username, password):
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"用户 {username} 已存在。")
            return
        u = User(username=username, display_name=username, role="admin",
                 credits=Config.DEFAULT_CREDITS)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        print(f"管理员 {username} 已创建。")


def seed_tools(app):
    with app.app_context():
        for key, name, icon, order, cost in DEFAULT_TOOLS:
            if not Tool.query.filter_by(key=key).first():
                db.session.add(Tool(key=key, name=name, icon=icon,
                                    sort_order=order, cost=cost))
        db.session.commit()
        print("默认工具已写入。")


def migrate(app):
    """幂等 schema 同步：建新表 + 为既有表补新列（SQLite 轻量迁移）。"""
    from sqlalchemy import inspect, text
    # (表, 列名, 建列 DDL)
    COLUMN_ADDS = [
        ("api_keys", "extra_cipher", "ALTER TABLE api_keys ADD COLUMN extra_cipher BLOB"),
        ("users", "totp_secret_cipher", "ALTER TABLE users ADD COLUMN totp_secret_cipher BLOB"),
        ("users", "totp_enabled", "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT 0"),
    ]
    with app.app_context():
        db.create_all()  # 创建缺失的新表
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        for table, col, ddl in COLUMN_ADDS:
            if table in tables:
                cols = {c["name"] for c in insp.get_columns(table)}
                if col not in cols:
                    db.session.execute(text(ddl))
                    db.session.commit()
                    print(f"已为 {table} 添加 {col} 列。")
        print("schema 已同步。")


if __name__ == "__main__":
    app = create_app()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "init-db":
        init_db(app)
    elif cmd == "create-admin":
        create_admin(app, sys.argv[2], sys.argv[3])
    elif cmd == "seed-tools":
        seed_tools(app)
    elif cmd == "migrate":
        migrate(app)
    else:
        print(__doc__)

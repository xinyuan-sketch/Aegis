"""应用配置。所有敏感值从环境变量读取，不硬编码。"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("AEGIS_SECRET_KEY", "dev-insecure-key")
    MASTER_KEY = os.environ.get("AEGIS_MASTER_KEY", "")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "AEGIS_DATABASE_URI", f"sqlite:///{BASE_DIR / 'aegis.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SQLite 并发关键设置：WAL 模式 + busy_timeout，避免 "database is locked"。
    # 由 app 工厂在连接建立时通过 PRAGMA 应用。
    SQLITE_PRAGMAS = {
        "journal_mode": "WAL",
        "busy_timeout": 5000,
        "foreign_keys": 1,
    }

    ENV = os.environ.get("AEGIS_ENV", "production")

    # 新用户默认积分
    DEFAULT_CREDITS = 100
    # 可信设备有效期（天）
    TRUSTED_DEVICE_DAYS = 30
    # 下载中心文件存储目录
    DOWNLOAD_DIR = str(BASE_DIR / "data" / "downloads")
    # 单文件上传上限（50MB）
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    # 云浏览器 noVNC 地址。留空则按「当前访问地址 + 端口 + 路径」自动推导，无需手填。
    CLOUD_BROWSER_URL = os.environ.get("AEGIS_CLOUD_BROWSER_URL", "")
    CLOUD_BROWSER_PORT = os.environ.get("AEGIS_CLOUD_BROWSER_PORT", "6080")
    CLOUD_BROWSER_PATH = os.environ.get(
        "AEGIS_CLOUD_BROWSER_PATH", "/vnc.html?autoconnect=true&resize=scale")
    # 后端健康探测用的内部地址（服务器→容器）
    CLOUD_BROWSER_INTERNAL = os.environ.get(
        "AEGIS_CLOUD_BROWSER_INTERNAL", "http://127.0.0.1:6080")
    # 云浏览器容器名（重启用）
    CLOUD_BROWSER_CONTAINER = os.environ.get("AEGIS_CLOUD_BROWSER_CONTAINER", "aegis-cloud-browser")

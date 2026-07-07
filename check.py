#!/usr/bin/env python3
"""Aegis 环境自检 / 健康检测（dev 与 prod 通用）。

  python check.py                       静态检查 + 应用自举 + 冒烟测试
  python check.py --url http://127.0.0.1:8000   额外探测运行中的服务端点

任一检查失败即以非零码退出，便于脚本 / CI 判断。
"""
import argparse
import importlib
import os
import sys
from pathlib import Path

# Windows 控制台兼容：强制 UTF-8 输出，并启用 ANSI 颜色转义
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
if os.name == "nt":
    os.system("")  # 触发 Win10+ 虚拟终端序列处理

OK = "\033[32m✓\033[0m"
NO = "\033[31m✗\033[0m"

_failed = 0


def check(label, ok, detail=""):
    global _failed
    mark = OK if ok else NO
    if not ok:
        _failed += 1
    print(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="额外探测运行中的服务，如 http://127.0.0.1:8000")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    print("Aegis 自检")

    # 1. Python 版本
    check(f"Python {sys.version_info.major}.{sys.version_info.minor}",
          sys.version_info >= (3, 10), "需 >= 3.10")

    # 2. 依赖可导入
    deps_ok = True
    for mod in ("flask", "flask_sqlalchemy", "flask_login", "cryptography", "dotenv"):
        try:
            importlib.import_module(mod)
        except ImportError:
            deps_ok = False
            check(f"依赖 {mod}", False, "未安装，请 pip install -r requirements.txt")
    if deps_ok:
        check("依赖已全部安装", True)
    else:
        print("\n依赖缺失，后续检查跳过。")
        return 1

    # 3. .env / 密钥
    from dotenv import dotenv_values
    env = dotenv_values(root / ".env") if (root / ".env").exists() else {}
    check(".env 存在", (root / ".env").exists())
    check("AEGIS_SECRET_KEY 已设置", bool(env.get("AEGIS_SECRET_KEY")))
    master = env.get("AEGIS_MASTER_KEY", "")
    from cryptography.fernet import Fernet
    master_ok = False
    if master:
        try:
            Fernet(master.encode())
            master_ok = True
        except Exception:
            master_ok = False
    check("AEGIS_MASTER_KEY 是合法 Fernet 密钥", master_ok,
          "" if master_ok else "生成: python -c \"from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())\"")

    # 4. 应用自举 + 数据表 + 冒烟测试
    try:
        sys.path.insert(0, str(root))
        from app import create_app
        from app.extensions import db
        from sqlalchemy import inspect
        app = create_app()
        with app.app_context():
            tables = set(inspect(db.engine).get_table_names())
        need = {"users", "tools", "tool_permissions", "credit_ledger", "audit_logs"}
        check("应用工厂启动成功", True)
        check("数据表已初始化", need.issubset(tables),
              "" if need.issubset(tables) else f"缺表: {need - tables}，请 python cli.py init-db")

        client = app.test_client()
        r1 = client.get("/auth/login")
        check("GET /auth/login 返回 200", r1.status_code == 200, f"got {r1.status_code}")
        r2 = client.get("/")
        check("未登录访问 / 重定向到登录", r2.status_code in (301, 302), f"got {r2.status_code}")
    except Exception as exc:
        check("应用自举", False, repr(exc))

    # 5. 可选：探测运行中的服务
    if args.url:
        import urllib.request
        url = args.url.rstrip("/") + "/auth/login"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                check(f"HTTP 探测 {url}", resp.status == 200, f"got {resp.status}")
        except Exception as exc:
            check(f"HTTP 探测 {url}", False, repr(exc))

    print()
    if _failed:
        print(f"{NO} {_failed} 项未通过")
        return 1
    print(f"{OK} 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Aegis 生产一键部署 (Linux + systemd)。幂等，可重复执行做更新。
#   sudo bash deploy.sh
#
# 在代码所在目录就地部署：建 venv、装依赖、生成密钥、初始化库、
# 安装并启动 systemd 服务，最后跑健康检测。
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="aegis"
RUN_USER="${AEGIS_USER:-aegis}"
BIND="127.0.0.1:8000"
PY="${APP_DIR}/venv/bin/python"

echo "==> 部署目录: ${APP_DIR}"

# 0. root 检查
if [[ $EUID -ne 0 ]]; then echo "请用 sudo 运行"; exit 1; fi

# 1. 服务用户
if ! id "${RUN_USER}" &>/dev/null; then
    echo "==> 创建服务用户 ${RUN_USER}"
    useradd --system --no-create-home --shell /usr/sbin/nologin "${RUN_USER}"
fi

# 2. venv + 依赖
if [[ ! -d "${APP_DIR}/venv" ]]; then
    echo "==> 创建虚拟环境"
    python3 -m venv "${APP_DIR}/venv"
fi
echo "==> 安装依赖"
"${PY}" -m pip install -q --upgrade pip
"${PY}" -m pip install -q -r "${APP_DIR}/requirements.txt"

# 3. .env（缺失则生成随机密钥，权限 600）
if [[ ! -f "${APP_DIR}/.env" ]]; then
    echo "==> 生成 .env 与密钥"
    SECRET=$("${PY}" -c "import secrets;print(secrets.token_urlsafe(48))")
    MASTER=$("${PY}" -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
    cat > "${APP_DIR}/.env" <<EOF
AEGIS_SECRET_KEY=${SECRET}
AEGIS_MASTER_KEY=${MASTER}
AEGIS_DATABASE_URI=sqlite:///${APP_DIR}/aegis.db
AEGIS_ENV=production
EOF
    chmod 600 "${APP_DIR}/.env"
    echo "   已生成密钥。请备份 AEGIS_MASTER_KEY，丢失将无法解密凭证！"
fi

# 4. 数据库 —— 先 migrate 建表/补列，再按需建管理员
cd "${APP_DIR}"
FRESH=0
[[ ! -f "${APP_DIR}/aegis.db" ]] && FRESH=1
echo "==> 同步数据库 schema"
"${PY}" cli.py migrate
"${PY}" cli.py seed-tools
if [[ $FRESH -eq 1 ]]; then
    ADMIN_PW="${AEGIS_ADMIN_PW:-$("${PY}" -c "import secrets;print(secrets.token_urlsafe(9))")}"
    "${PY}" cli.py create-admin admin "${ADMIN_PW}"
    echo "   管理员 admin / ${ADMIN_PW} —— 请登录后尽快改密"
fi

# 5. 权限归属
chown -R "${RUN_USER}:${RUN_USER}" "${APP_DIR}"

# 6. systemd 单元（按实际路径生成，覆盖安装）
echo "==> 安装 systemd 服务"
cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=Aegis
After=network.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/gunicorn -c ${APP_DIR}/deploy/gunicorn.conf.py wsgi:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"
sleep 2

# 7. 健康检测
echo "==> 健康检测"
systemctl is-active --quiet "${SERVICE}" && echo "   服务 active" || { echo "   服务未启动，查看: journalctl -u ${SERVICE} -n 50"; exit 1; }
sudo -u "${RUN_USER}" "${PY}" "${APP_DIR}/check.py" --url "http://${BIND}" || exit 1

echo "==> 完成。反向代理请配置 deploy/nginx.conf（TLS）。"

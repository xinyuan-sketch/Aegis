<div align="center">

# Aegis

**自托管的团队安全工具箱平台**

一个单机可部署、模块化的安全团队协作平台：把 OSINT 查询、凭证保管、Hash 破解、Payload 生成、云浏览器、常用工具箱，以及笔记 / 片段库 / 清单等工作区功能，统一在一套带 RBAC 权限、积分账本与审计日志的门面之后。

Flask · SQLAlchemy · SQLite（可平滑迁移 PostgreSQL）· 零前端构建

</div>

---

## ✨ 功能总览

### 安全工具
- **OSINT 查询** — 聚合 Hunter / FOFA / Shodan，队列 + 结果缓存 + CSV 导出，按次计费。
- **Hash 破解** — 内置离线弱口令字典（MD5/SHA1/SHA256/SHA512，免费秒出），可选接入 hashes.com 在线查库（仅对成功破解计费）。
- **共享凭证库** — 团队账号 / API Key / Cookie / SSH 等 8 类，敏感值 Fernet 加密存储，私密 / 公开可见性，到期提醒。
- **安全导航** — 常用工具站点书签，分类、点击统计、一键复制 / 打开。
- **下载中心** — 团队文件（报告 / 结果 / 截图）集中存取。
- **Payload 生成器** — 反弹 / 绑定 Shell 22+ 模板（Bash/nc/socat/Python/PHP/PowerShell…）、MSFVenom 命令、监听器，支持 URL/Base64/PowerShell 编码。*基于公开标准模板，不含免杀。*
- **云浏览器** — 容器化 Xvfb + Chrome + noVNC，一次性隔离浏览环境。
- **工具箱** — 30+ 纯前端小工具：编码/解码、哈希、HMAC、AES/经典密码、JWT 解析、密码生成、正则测试、JSON、颜色、CIDR/子网、时间戳、UUID 等，数据不出浏览器。

### 工作区（登录即用）
- **笔记** — Markdown，私密 / 团队共享，标签 + 全文搜索 + 置顶。
- **代码片段库** — 命令 / payload / 正则收藏，按语言与标签分类，一键复制。
- **渗透清单** — 内置方法论模板（Web / 外网 / 内网），条目实时勾选 + 进度跟踪。
- **全局搜索** — 跨笔记 / 片段 / 清单 / 凭证 / 导航一次搜到。

### 平台与安全
- **认证** — 密码 PBKDF2 存储、可信设备免二次验证、TOTP 两步验证、登录爆破锁定。
- **注册** — 四档可切换（关闭 / 管理员审批 / 邀请码 / 开放）+ SVG 图形验证码。
- **RBAC + 审批流** — `@require_tool` 装饰器按工具授权，普通用户申请、管理员审批。
- **积分账本** — 只追加账本，扣费 / 充值与余额在同一事务内一致。
- **审计日志** — 登录、授权、Key 变更、凭证读取等敏感操作全量留痕。
- **CSRF 全站防护** — 会话级 token，表单与 fetch 自动携带校验。
- **Telegram 通知** — 登录 / 新设备 / 锁定 / 注册等事件实时推送。
- **系统设置** — 站点名、注册策略、验证码、默认积分、锁定阈值等可视化配置。
- **实时仪表盘** — CPU / 内存 / 磁盘 / 网络（非阻塞采样）+ 各模块指标 + 积分消耗排行。
- **深浅主题 · 响应式 · 侧边栏折叠**。

---

## 🚀 快速开始

> 默认监听 `http://127.0.0.1:5000`。首次启动会自动建虚拟环境、装依赖、生成密钥、初始化数据库并创建管理员。

### Windows（开发）
```powershell
.\dev.ps1            # 启动（默认管理员 admin / admin123，请尽快修改）
.\dev.ps1 -Reset     # 删库重建后启动
.\dev.ps1 -Check     # 仅环境自检
```

### Linux / macOS（手动）
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 生成 Fernet 主密钥填入 .env 的 AEGIS_MASTER_KEY：
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 并把 AEGIS_SECRET_KEY 改成一段长随机串

python cli.py migrate            # 建表 / 补列（幂等）
python cli.py seed-tools         # 写入默认工具
python cli.py create-admin admin '你的密码'
python run.py
```

### Linux 生产部署
```bash
sudo bash deploy.sh                              # 部署 + 启动 + 健康检测
python check.py --url http://127.0.0.1:8000      # 随时健康检测
```
配合 `deploy/gunicorn.conf.py`、`deploy/aegis.service`（systemd）、`deploy/nginx.conf`（TLS + 反代）。云浏览器见 `deploy/cloud-browser/`。

---

## 🧩 架构

```
Nginx (TLS, 静态, 反代, WebSocket)
   └── Gunicorn + Flask 应用工厂
         ├── 功能模块 (blueprints, 权限门后)
         │     OSINT · Hash · 凭证库 · 导航 · 下载 · Payload · 云浏览器 · 工具箱
         │     笔记 · 片段库 · 清单 · 全局搜索
         ├── 核心平台层
         │     认证 · RBAC + 审批 · 积分账本 · 审计 · CSRF · Fernet 加密 · 通知
         └── 数据访问层 (SQLAlchemy ORM)
               └── SQLite (WAL)  →  未来: PostgreSQL
```

- **模块即插件**：每个功能是独立 blueprint，挂在统一的权限门 / 审计 / 积分之后，互不依赖，可单独增量开发。
- **数据层可迁移**：ORM 起步 SQLite（WAL + busy_timeout），团队规模变大后平滑迁 PostgreSQL。
- **插件扩展点**：`app/tools/plugins/` 为受权限保护的第三方插件槽，由使用方自行挂载，本仓库不内置任何插件实现。

详见 [DESIGN.md](DESIGN.md)。

```
app/
├── __init__.py     应用工厂（SQLite PRAGMA、CSRF、上下文注入）
├── models.py       全部 ORM 模型
├── core/           security · rbac · audit · credits · settings · captcha · csrf · notify · sysinfo · totp
├── auth/ dashboard/ admin/ me/ site/ search/
├── tools/          osint · hashtool · vault · nav · download · payload · browser · utils · notes · snippets · checklist
├── templates/  static/
cli.py  config.py  run.py  wsgi.py  check.py
deploy/          gunicorn · systemd · nginx · cloud-browser
```

---

## 🔐 安全须知

- 密码用 werkzeug PBKDF2 **不可逆**存储；凭证 / API Key 用 **Fernet 可逆加密**，主密钥 `AEGIS_MASTER_KEY` 仅存环境变量、绝不入库。
- **`AEGIS_MASTER_KEY` 一旦丢失，所有密文将无法解密——务必备份。**
- 生产环境请务必：修改默认管理员密码、为 `AEGIS_SECRET_KEY` / `AEGIS_MASTER_KEY` 生成全新随机值、启用 HTTPS、按需关闭开放注册。
- `.env`、`*.db`、`instance/`、`data/` 已在 `.gitignore` 中，切勿提交密钥或数据库。

---

## ⚖️ 授权使用声明

Aegis 是面向**获授权**的安全测试与团队协作的工具集。请仅在你**拥有明确书面授权**的系统与网络上使用其中的查询、扫描、Payload、凭证等能力。使用者需自行遵守所在地区的法律法规；因未授权或非法使用造成的一切后果由使用者承担，项目作者与贡献者不承担任何责任。

Payload 生成器仅提供公开、通用的标准模板，**不包含免杀 / shellcode 加载等攻击载荷规避实现**。

---

## 📄 License

[MIT](LICENSE) © Aegis Contributors

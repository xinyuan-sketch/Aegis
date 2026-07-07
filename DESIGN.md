# Aegis 架构设计文档

团队级安全工具箱平台。本文档描述整体架构、数据模型、API 设计、目录结构与部署方案，作为后续增量开发的蓝图。

目标形态：单机服务器部署（systemd + Gunicorn + Nginx），数据层 SQLite（WAL）起步，ORM 用 SQLAlchemy 以便日后平滑迁移 PostgreSQL。

---

## 1. 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  Nginx (TLS, 静态资源, 反向代理, WebSocket 透传)              │
└───────────────┬─────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────┐
│  Gunicorn + Flask 应用工厂                                    │
│                                                               │
│  ┌─────────────── 功能模块层 (blueprints, 权限门后) ────────┐ │
│  │ OSINT │ Hash │ 凭证库 │ 导航 │ 下载 │ 云浏览器 │ 工具箱 │ │
│  │ Payload生成器 │ 笔记 │ 片段库 │ 清单 │ 全局搜索        │ │
│  │ [第三方插件槽: 由使用方自行挂载]                        │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────── 核心平台层 ──────────────────────────────┐ │
│  │ 认证(可信设备+TOTP+注册+验证码) │ RBAC+审批流 │ 积分账本 │ │
│  │ 审计日志 │ CSRF │ Fernet加密 │ Telegram通知 │ 系统设置   │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────── 数据访问层 (SQLAlchemy ORM) ─────────────┐ │
│  └───────────────────────────────────────────────────────┘ │
└───────────────┬─────────────────────────────────────────────┘
                │
        SQLite (WAL)  →  未来: PostgreSQL
```

设计原则：

- **核心平台层是地基**，所有功能模块都挂在权限门（RBAC 装饰器）之后，通过统一的积分服务扣费、统一的审计中间件记录。
- **功能模块用 blueprint 插件化**，彼此不直接依赖，可独立增量开发和联调。
- **第三方插件槽**：架构保留一个受权限保护的插件扩展点（`tools/plugins/` 目录 + 注册接口），由使用方自行挂载。本仓库不内置任何插件实现，也不包含免杀 / shellcode 加载等攻击载荷规避代码。

---

## 2. 数据模型

以下为核心平台层的表结构。功能模块各自的表（如凭证、导航链接、下载记录）在对应模块迭代时补充。

### users
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| username | str unique | 登录名 |
| password_hash | str | werkzeug 生成 |
| display_name | str | 显示名 |
| role | str | `admin` / `user` |
| credits | int | 当前积分余额 |
| is_active | bool | 启用/禁用 |
| wechat_openid | str null | 微信绑定 |
| avatar_url | str null | 微信头像 |
| created_at | datetime | |
| last_login_at | datetime null | |

### tools
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| key | str unique | 工具标识，如 `osint` |
| name | str | 侧边栏显示名 |
| icon | str | 图标 |
| sort_order | int | 排序 |
| is_enabled | bool | 是否显示 |
| cost | int | 单次操作扣费 |

### tool_permissions （用户 ↔ 工具授权）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| user_id | int FK | |
| tool_key | str | |
| granted_by | int FK null | 授权管理员 |
| created_at | datetime | |

### permission_requests （申请 → 审批流）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| user_id | int FK | 申请人 |
| tool_key | str | 申请的工具 |
| reason | str | 申请理由 |
| status | str | `pending`/`approved`/`rejected` |
| reviewed_by | int FK null | 审批人 |
| reviewed_at | datetime null | |
| created_at | datetime | |

### trusted_devices
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| user_id | int FK | |
| fingerprint | str | 设备指纹 |
| name | str | 设备名 |
| expires_at | datetime | 到期失效 |
| created_at | datetime | |

### credit_ledger （积分账本，只追加）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| user_id | int FK | |
| delta | int | 正=充值 负=消耗 |
| balance_after | int | 变动后余额 |
| reason | str | 消耗来源，如 `osint.query` |
| created_at | datetime | |

### audit_logs
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| user_id | int FK null | |
| category | str | `auth`/`admin`/`tool`/`security` |
| action | str | 具体动作 |
| detail | str | JSON 细节 |
| ip | str | 来源 IP |
| created_at | datetime | |

### api_keys （服务端共享 Key）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| provider | str | `hunter`/`fofa`/`shodan` |
| key_cipher | blob | Fernet 加密后的 Key |
| is_valid | bool | 最近一次验证结果 |
| updated_at | datetime | |

积分为只追加账本：任何扣费都写一条 `credit_ledger` 并同步更新 `users.credits`，两者在同一事务内完成，保证可追溯。

---

## 3. 安全设计

- **密码**：werkzeug `generate_password_hash`（PBKDF2），不可逆。
- **凭证/API Key**：Fernet 对称加密（可逆，供复制使用），主密钥 `AEGIS_MASTER_KEY` 从环境变量读取，绝不入库、不进仓库。密钥丢失=所有密文不可解，需在部署文档中强调备份。
- **可信设备**：设备指纹 + 到期时间，命中则登录免二次验证；管理员可撤销任意设备。
- **审计**：所有敏感操作（登录、授权、Key 变更、凭证读取）经统一装饰器写 `audit_logs`。
- **权限**：RBAC 装饰器 `@require_tool('osint')` 检查用户是否被授权该工具；未授权引导至申请页。管理员绕过所有工具门。
- **限流**：查询类接口按用户排队 + 频率限制，防 API 被封。

---

## 4. API / 路由设计（核心平台层）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET/POST | `/auth/login` | 登录（含可信设备判断） | 公开 |
| GET | `/auth/logout` | 登出 | 登录 |
| GET | `/` | 仪表盘 | 登录 |
| GET | `/api/dashboard/stats` | 仪表盘实时数据 | 登录 |
| GET/POST | `/permissions/request` | 提交权限申请 | 登录 |
| GET | `/me/devices` | 我的可信设备 | 登录 |
| GET | `/admin/users` | 用户管理 | admin |
| POST | `/admin/users` | 创建/批量创建用户 | admin |
| POST | `/admin/users/<id>/credits` | 积分调整 | admin |
| POST | `/admin/users/<id>/toggle` | 启用/禁用 | admin |
| GET/POST | `/admin/permissions` | 授权 / 审批申请 | admin |
| GET/POST | `/admin/apikeys` | API Key 配置 + 验证 | admin |
| GET | `/admin/audit` | 审计日志 | admin |

功能模块路由在各自 blueprint 内定义，统一前缀（如 `/tools/osint`），并挂 `@require_tool(...)`。

---

## 5. 目录结构

```
安全研究员/
├── DESIGN.md                  本文档
├── README.md                  快速上手
├── requirements.txt
├── config.py                  配置（从环境变量读取）
├── .env.example               环境变量样例
├── wsgi.py                    Gunicorn 入口
├── run.py                     开发入口
├── cli.py                     init-db / create-admin 命令
├── app/
│   ├── __init__.py            应用工厂
│   ├── extensions.py          db, login_manager 等扩展实例
│   ├── models.py              全部 ORM 模型
│   ├── core/
│   │   ├── security.py        Fernet 加密封装
│   │   ├── rbac.py            权限装饰器
│   │   ├── audit.py           审计服务
│   │   └── credits.py         积分服务
│   ├── auth/routes.py         认证 blueprint
│   ├── dashboard/routes.py    仪表盘 blueprint
│   ├── admin/routes.py        后台 blueprint
│   ├── tools/                 功能模块（增量开发）
│   │   └── plugins/           免杀等第三方插件槽（使用方挂载）
│   ├── templates/
│   └── static/
└── deploy/
    ├── gunicorn.conf.py
    ├── aegis.service      systemd 单元
    └── nginx.conf
```

---

## 6. 部署方案（单机）

```
[用户] → Nginx (443, TLS) → Gunicorn (127.0.0.1:8000) → Flask
                          → /static 直接由 Nginx 提供
                          → /vnc WebSocket 透传给云浏览器容器
```

- **Gunicorn**：SQLite 下 worker 数不宜过多（写锁竞争），起步 `workers=3`，配 `--timeout` 适配流式查询。
- **SQLite**：启动即开 WAL + `busy_timeout`，见 `config.py`。
- **systemd**：`aegis.service` 管理进程，`Restart=always`，环境变量走 `EnvironmentFile`。
- **密钥**：`AEGIS_SECRET_KEY`（session）与 `AEGIS_MASTER_KEY`（Fernet）放在 systemd 的 `EnvironmentFile`（权限 600），不进仓库。
- **云浏览器**：Xvfb+Chrome+x11vnc+websockify 单独容器化，Nginx 透传 WebSocket，是最该独立部署的重依赖模块。

---

## 7. 进度

- [x] 核心平台地基：应用工厂 + 认证 + 可信设备 + RBAC + 审批流 + 积分账本 + 审计 + 仪表盘 + 后台用户/权限管理。
- [x] OSINT 查询（Hunter/FOFA/Shodan，队列 + 缓存 + CSV）。
- [x] 凭证保险库（Fernet 加密，8 类型，公开/私密，到期提醒）。
- [x] Hash 破解（离线字典 + hashes.com 在线查库）、安全导航、下载中心。
- [x] Payload 生成器、工具箱（30+ 前端工具）、云浏览器（容器化）。
- [x] TOTP 两步验证、Telegram 通知、注册 + 图形验证码、登录爆破锁定、CSRF 全站防护、系统设置。
- [x] 工作区：笔记、代码片段库、渗透清单、全局搜索。
- [ ] 后续可选：子域名枚举、审计筛选导出、报告生成、PostgreSQL 迁移。

每个模块作为独立 blueprint 挂在核心平台层之上，互不阻塞。

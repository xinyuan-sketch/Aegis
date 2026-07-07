# 插件槽

功能模块以独立 blueprint 挂在核心平台层之上。第三方 / 敏感模块（例如你自行实现的**免杀执行器 / shellcode 加载器**）放在此目录，由使用方自行实现并注册，**不随本仓库分发实际逻辑**。

`example_tool/` 是一份可直接套用的骨架，已接好权限门、积分扣费、审计、通知，只需把你的逻辑写进 `run()`。

## 接入三步

以把 `example_tool` 接成一个 key 为 `example` 的工具为例：

### 1. 在 tools 表登记该工具
编辑 `cli.py` 的 `DEFAULT_TOOLS`，加一行（key、名称、图标、排序、单次积分）：

```python
("example", "示例插件", "terminal", 90, 1),
```

然后运行 `python cli.py seed-tools`（或直接 `.\dev.ps1` / `deploy.sh`，会自动 seed）。

### 2. 注册 blueprint 与路由映射
在 `app/__init__.py` 里：

```python
# 顶部 TOOL_ROUTES 加一项（决定侧边栏点击跳转）
TOOL_ROUTES = {..., "example": "example_tool.index"}

# 注册功能模块处加两行
from .tools.plugins.example_tool.routes import bp as example_bp
app.register_blueprint(example_bp)
```

### 3. 授权
管理员在后台「权限管理」把 `example` 工具授权给需要的用户；管理员自动拥有全部工具权限。

## 复用的平台能力

- `@require_tool("example")` —— 权限门，未授权自动跳转申请页
- `credits.charge(user, n, "example.run")` —— 按次扣积分，余额不足抛 `InsufficientCredits`
- `audit.log("tool", "动作", {...})` —— 写审计日志
- `notify.send("...")` —— Telegram 通知（后台配置 Bot 后生效）

## 说明

`example_tool` 默认**未注册**，是模板不是启用的功能。免杀 / shellcode 等模块的具体实现由你完成并自行承担合规责任。

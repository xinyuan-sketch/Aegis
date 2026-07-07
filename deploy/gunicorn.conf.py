# Gunicorn 配置。SQLite 下 worker 不宜多（写锁竞争）。
bind = "127.0.0.1:8000"
workers = 3
timeout = 120          # 适配流式查询等长请求
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = "info"

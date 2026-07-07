"""系统状态采集（psutil）。用于仪表盘服务器状态面板。

网络速率通过两次采样差值计算，模块级缓存上一次读数。
psutil 缺失时优雅降级，返回 {"error": ...}。
"""
import platform
import time

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

_APP_START = time.time()
_net_prev = {"t": None, "sent": 0, "recv": 0}

# 导入时预热非阻塞 CPU 采样：首次 interval=None 返回 0，预热后后续请求即得真实占用，
# 且不再每次阻塞 150ms。
if _HAS_PSUTIL:
    try:
        psutil.cpu_percent(interval=None, percpu=True)
    except Exception:
        pass


def _human_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _human_rate(bps):
    return _human_bytes(bps) + "/s"


def _fmt_duration(seconds):
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d} 天 {h} 小时"
    if h:
        return f"{h} 小时 {m} 分"
    return f"{m} 分钟"


def _os_pretty():
    try:
        if platform.system() == "Linux":
            info = {}
            with open("/etc/os-release") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.rstrip().split("=", 1)
                        info[k] = v.strip('"')
            return info.get("PRETTY_NAME", platform.platform())
    except Exception:
        pass
    return platform.platform()


def collect():
    if not _HAS_PSUTIL:
        return {"error": "psutil 未安装", "app_uptime_str": _fmt_duration(time.time() - _APP_START),
                "py_version": platform.python_version(),
                "os_name": platform.system(), "os_pretty": _os_pretty(),
                "uptime_str": "—"}

    # CPU（非阻塞：返回自上次调用以来的占用。已在导入时预热，避免首调 0；
    # 不再每次阻塞 150ms，显著降低轮询开销）
    per_cpu = psutil.cpu_percent(interval=None, percpu=True)
    cpu = [round(p, 1) for p in per_cpu]
    cpu_avg = round(sum(cpu) / len(cpu), 1) if cpu else 0.0

    # 内存
    vm = psutil.virtual_memory()
    gb = 1024 ** 3
    mem = {
        "total_gb": round(vm.total / gb, 1),
        "used_gb": round(vm.used / gb, 1),
        "free_gb": round(vm.available / gb, 1),
        "percent": round(vm.percent, 1),
    }

    # 磁盘（根分区 / 系统盘）
    root = "C:\\" if platform.system() == "Windows" else "/"
    du = psutil.disk_usage(root)
    disk = {
        "fs": root,
        "total_gb": round(du.total / gb, 1),
        "used_gb": round(du.used / gb, 1),
        "percent": round(du.percent, 1),
    }

    # 网络速率（两次采样差值）
    io = psutil.net_io_counters()
    now = time.time()
    if _net_prev["t"] is None:
        up = down = 0.0
    else:
        dt = max(now - _net_prev["t"], 1e-6)
        up = (io.bytes_sent - _net_prev["sent"]) / dt
        down = (io.bytes_recv - _net_prev["recv"]) / dt
    _net_prev.update({"t": now, "sent": io.bytes_sent, "recv": io.bytes_recv})

    # 系统运行时长
    sys_uptime = time.time() - psutil.boot_time()

    return {
        "os_name": platform.system(),
        "os_pretty": _os_pretty(),
        "uptime_str": _fmt_duration(sys_uptime),
        "app_uptime_str": _fmt_duration(time.time() - _APP_START),
        "py_version": platform.python_version(),
        "cpu": cpu,
        "cpu_avg": cpu_avg,
        "mem": mem,
        "disk": disk,
        "net": {"up": _human_rate(up), "down": _human_rate(down),
                "up_bps": round(up, 1), "down_bps": round(down, 1)},
    }

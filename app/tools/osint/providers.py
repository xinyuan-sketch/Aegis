"""OSINT provider 适配器：Hunter(hunter.how) / FOFA / Shodan。

统一返回 {"columns": [...], "rows": [[...], ...], "total": int}。
服务端共享 Key 从 api_keys 表读取（Fernet 解密）。
Key 未配置或请求失败时抛 ProviderError，由路由层转为友好提示。
"""
import base64
from datetime import date, timedelta
from urllib.parse import quote

from ...core import security
from ...models import ApiKey

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

PROVIDERS = ("hunter", "fofa", "shodan")
TIMEOUT = 20


class ProviderError(Exception):
    pass


def _get_key(provider):
    row = ApiKey.query.filter_by(provider=provider).first()
    if not row:
        raise ProviderError(f"{provider} 的 API Key 未配置，请联系管理员在后台设置")
    key = security.decrypt(row.key_cipher)
    extra = security.decrypt(row.extra_cipher) if row.extra_cipher else None
    return key, extra


def query(provider, q, size=100, page=1):
    if not _HAS_REQUESTS:
        raise ProviderError("requests 未安装，无法发起查询")
    if not q.strip():
        raise ProviderError("查询语句为空")
    page = max(int(page or 1), 1)
    if provider == "fofa":
        return _fofa(q, size, page)
    if provider == "hunter":
        return _hunter(q, size, page)
    if provider == "shodan":
        return _shodan(q, size, page)
    raise ProviderError(f"未知 provider: {provider}")


def _fofa(q, size, page):
    key, email = _get_key("fofa")
    qbase64 = base64.b64encode(q.encode()).decode()
    fields = "ip,port,host,title,domain,country"
    url = ("https://fofa.info/api/v1/search/all"
           f"?email={email or ''}&key={key}&qbase64={qbase64}"
           f"&page={page}&size={min(size, 10000)}&fields={fields}")
    try:
        r = requests.get(url, timeout=TIMEOUT).json()
    except Exception as exc:
        raise ProviderError(f"FOFA 请求失败：{exc}")
    if r.get("error"):
        raise ProviderError(f"FOFA：{r.get('errmsg', '未知错误')}")
    return {"columns": fields.split(","), "rows": r.get("results", []),
            "total": r.get("size", 0)}


def _shodan(q, size, page):
    key, _ = _get_key("shodan")
    url = f"https://api.shodan.io/shodan/host/search?key={key}&query={quote(q)}&page={page}"
    try:
        r = requests.get(url, timeout=TIMEOUT).json()
    except Exception as exc:
        raise ProviderError(f"Shodan 请求失败：{exc}")
    if "error" in r:
        raise ProviderError(f"Shodan：{r['error']}")
    cols = ["ip", "port", "org", "hostnames", "country"]
    rows = []
    for m in r.get("matches", [])[:size]:
        loc = m.get("location") or {}
        rows.append([m.get("ip_str"), m.get("port"), m.get("org", ""),
                     ",".join(m.get("hostnames", [])), loc.get("country_name", "")])
    return {"columns": cols, "rows": rows, "total": r.get("total", len(rows))}


def _hunter(q, size, page):
    key, _ = _get_key("hunter")
    qb64 = base64.urlsafe_b64encode(q.encode()).decode()
    end = date.today()
    start = end - timedelta(days=365)
    url = ("https://api.hunter.how/search"
           f"?api-key={key}&query={qb64}&page={page}&page_size={min(size, 100)}"
           f"&start_time={start}&end_time={end}")
    try:
        r = requests.get(url, timeout=TIMEOUT).json()
    except Exception as exc:
        raise ProviderError(f"Hunter 请求失败：{exc}")
    if r.get("code") != 200:
        raise ProviderError(f"Hunter：{r.get('message', '未知错误')}")
    data = r.get("data", {})
    cols = ["ip", "port", "domain", "protocol", "country"]
    rows = []
    for it in data.get("list", []):
        rows.append([it.get("ip"), it.get("port"), it.get("domain", ""),
                     it.get("protocol", ""), it.get("country", "")])
    return {"columns": cols, "rows": rows, "total": data.get("total", len(rows))}

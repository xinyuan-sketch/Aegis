"""Hash 识别与查库。

- identify(): 按长度/字符集识别算法（离线可用）
- crack_offline(): 内置常见弱口令字典，本地计算 md5/sha1/sha256/sha512 反查（免费、离线）
- lookup_online(): 可选，接入 hashes.com 搜索 API（后台配置 provider='hashes' 的 Key）
  未配置或网络不可达时返回空结果，不报错。
"""
import functools
import hashlib
import re

from ...core import security
from ...models import ApiKey

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_HEX = re.compile(r"^[0-9a-fA-F]+$")
_ALGO_BY_LEN = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}


def identify(h: str) -> str:
    h = h.strip()
    if _HEX.match(h) and len(h) in _ALGO_BY_LEN:
        return _ALGO_BY_LEN[len(h)]
    return "unknown"


# 内置常见弱口令字典（离线彩虹表来源）。可按需扩充或替换为外部 wordlist 文件。
COMMON_PASSWORDS = [
    "123456", "password", "123456789", "12345678", "12345", "1234567",
    "qwerty", "abc123", "111111", "123123", "admin", "letmein", "welcome",
    "monkey", "1234567890", "password1", "qwerty123", "1q2w3e4r", "000000",
    "iloveyou", "1234", "1qaz2wsx", "dragon", "sunshine", "654321", "master",
    "666666", "123321", "michael", "superman", "888888", "princess", "qwertyuiop",
    "passw0rd", "football", "baseball", "trustno1", "hello", "charlie", "aa123456",
    "donald", "password123", "root", "toor", "test", "test123", "guest", "user",
    "changeme", "secret", "administrator", "p@ssw0rd", "P@ssw0rd", "Passw0rd!",
    "admin123", "root123", "123qwe", "qwe123", "zxcvbnm", "asdfghjkl", "121212",
    "a123456", "5201314", "woaini", "woaini1314", "abcd1234", "abc12345",
    "1q2w3e", "qazwsx", "zaq12wsx", "q1w2e3r4", "1qazxsw2", "112233", "159357",
    "147258369", "987654321", "11111111", "00000000", "88888888", "123456a",
    "a12345", "123abc", "love", "flower", "shadow", "michael1", "jennifer",
    "hunter", "hunter2", "starwars", "letmein123", "welcome1", "welcome123",
    "login", "pass", "pass123", "temp", "temp123", "demo", "demo123", "oracle",
    "mysql", "postgres", "redhat", "linux", "server", "admin1", "administrator1",
    "222222", "333333", "555555", "777777", "999999", "101010", "abcabc",
    "asdf", "asdf1234", "qweasd", "1234abcd", "iloveu", "lovely", "cheese",
    "computer", "internet", "samsung", "google", "facebook", "whatever",
    "ncc1701", "batman", "andrew", "tigger", "buster", "soccer", "harley",
    "robert", "matthew", "daniel", "andrea", "joshua", "george", "thomas",
    "William", "banana", "orange", "apple", "chocolate", "cookie", "summer",
    "winter", "autumn", "spring", "freedom", "ginger", "pepper", "maggie",
    "purple", "yellow", "silver", "golden", "diamond", "money", "nicole",
    "jessica", "amanda", "ashley", "bailey", "hannah", "taylor", "jordan",
    "chelsea", "mustang", "camaro", "corvette", "porsche", "ferrari", "harley123",
]


@functools.lru_cache(maxsize=1)
def _rainbow():
    """构建 {hash_hex: plaintext} 反查表（md5/sha1/sha256/sha512）。惰性、缓存一次。"""
    table = {}
    for pw in COMMON_PASSWORDS:
        b = pw.encode()
        for algo in ("md5", "sha1", "sha256", "sha512"):
            table.setdefault(hashlib.new(algo, b).hexdigest(), pw)
    return table


def crack_offline(hashes):
    """本地字典反查，返回 {hash_lower: plaintext}。完全离线、免费。"""
    rb = _rainbow()
    return {h: rb[h] for h in hashes if h in rb}


def online_ready():
    """是否具备在线查库能力（requests 可用且已配置 hashes.com Key）。"""
    return _HAS_REQUESTS and ApiKey.query.filter_by(provider="hashes").first() is not None


def lookup_online(hashes):
    """在线查库。返回 (found_dict, error)。found_dict={hash_lower: plaintext}。

    注意：hashes.com 的 /api/search 按「每破解 1 条扣 1 个 hashes.com 积分」计费，
    与网页版「免费搜索」不同——账户无 hashes.com 积分时 API 会返回失败。
    """
    if not _HAS_REQUESTS:
        return {}, "服务端未安装 requests 库"
    if not hashes:
        return {}, None
    row = ApiKey.query.filter_by(provider="hashes").first()
    if not row:
        return {}, "未配置 hashes.com API Key"
    try:
        key = security.decrypt(row.key_cipher)
    except Exception:
        return {}, "API Key 解密失败，请在后台重新配置"
    result, error = {}, None
    # /api/search：POST，参数 key + hashes[] 数组，单次最多 250 条
    for i in range(0, len(hashes), 250):
        batch = hashes[i:i + 250]
        try:
            resp = requests.post(
                "https://hashes.com/en/api/search",
                data={"key": key, "hashes[]": batch},
                timeout=25,
            )
            data = resp.json()
        except Exception as e:
            error = f"请求 hashes.com 失败：{e}"
            continue
        if not data.get("success"):
            error = data.get("message") or "hashes.com 返回失败（常见原因：账户 hashes.com 积分不足）"
            continue
        for item in data.get("founds") or []:
            hv = (item.get("hash") or "").lower()
            pt = item.get("plaintext")
            if hv and pt:
                result[hv] = pt
    if result:
        error = None
    return result, error

"""自托管 SVG 图形验证码。

答案存 session（一次性，verify 后即失效）。纯服务端生成，不依赖第三方，也无需 PIL。
"""
import random

from flask import session

# 去除易混字符（0/O、1/I/L）
_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_COLORS = ["#6d5efc", "#37c0fe", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6"]
_W, _H, _N = 132, 44, 4


def new_svg():
    """生成新验证码，答案写入 session，返回 SVG 字符串。"""
    code = "".join(random.choice(_CHARS) for _ in range(_N))
    session["captcha"] = code
    return _render(code)


def verify(answer):
    """校验并作废（一次性）。"""
    want = session.pop("captcha", None)
    if not want or not answer:
        return False
    return answer.strip().upper() == want.upper()


def _render(code):
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}" '
         f'viewBox="0 0 {_W} {_H}" role="img" aria-label="captcha">']
    # 半透明底，兼顾深浅主题可读性
    p.append(f'<rect width="{_W}" height="{_H}" rx="8" fill="#7f7f7f" fill-opacity="0.10"/>')
    # 干扰线
    for _ in range(5):
        x1, y1 = random.randint(0, _W), random.randint(0, _H)
        x2, y2 = random.randint(0, _W), random.randint(0, _H)
        p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                 f'stroke="{random.choice(_COLORS)}" stroke-opacity="0.45" stroke-width="1"/>')
    # 干扰点
    for _ in range(22):
        p.append(f'<circle cx="{random.randint(0, _W)}" cy="{random.randint(0, _H)}" '
                 f'r="1" fill="{random.choice(_COLORS)}" fill-opacity="0.5"/>')
    # 字符（随机位移、旋转、颜色）
    for i, ch in enumerate(code):
        x = 18 + i * 28 + random.randint(-3, 3)
        y = 30 + random.randint(-4, 4)
        rot = random.randint(-26, 26)
        p.append(f'<text x="{x}" y="{y}" font-size="27" font-family="monospace" '
                 f'font-weight="700" fill="{random.choice(_COLORS)}" '
                 f'transform="rotate({rot} {x} {y})">{ch}</text>')
    p.append("</svg>")
    return "".join(p)

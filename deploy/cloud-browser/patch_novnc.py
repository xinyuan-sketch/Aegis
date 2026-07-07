#!/usr/bin/env python3
"""给 noVNC 打补丁，解决浏览器扩展（MetaMask 等钱包）注入 inpage.js 抛出的
未捕获错误被 noVNC 当成致命错误、弹框并中断渲染（黑屏）的问题。

做三件事（幂等）：
1. 中和 noVNC 的致命错误处理器 app/error-handler.js —— 这是关键：原处理器会把
   页面上任何未捕获错误（包括无关的扩展错误）当致命错误显示并可能中断 UI。
   替换成只 console 记录、不弹框、不中断的版本，noVNC 就会忽略扩展错误正常渲染。
2. 注入 CSS 隐藏残留的错误浮层 #noVNC_fallback_error（双保险）。
3. 注入捕获阶段 error 监听，吞掉 chrome-extension 来源的错误（双保险）。
"""
import glob
import os

MARK = "aegis-novnc-patch"

INJECT = (
    "<!--" + MARK + "-->"
    "<style>#noVNC_fallback_error,#noVNC_fallback_error.noVNC_open"
    "{display:none!important;visibility:hidden!important;}</style>"
    "<script>"
    "window.addEventListener('error',function(e){"
    "var f=(e&&e.filename)||'';var m=(e&&e.message)||'';"
    "if(f.indexOf('chrome-extension://')===0||String(m).indexOf('isMetaMask')>=0){"
    "e.stopImmediatePropagation&&e.stopImmediatePropagation();"
    "e.preventDefault&&e.preventDefault();return true;}},true);"
    "window.addEventListener('unhandledrejection',function(e){"
    "var s=String((e&&e.reason)||'');"
    "if(s.indexOf('chrome-extension')>=0||s.indexOf('isMetaMask')>=0){"
    "e.preventDefault&&e.preventDefault();}},true);"
    "</script>"
)

# 中和后的 error-handler.js：只记录，不弹框、不中断
NEUTRAL_HANDLER = (
    "// " + MARK + ": neutralized noVNC fatal-error handler.\n"
    "// 原处理器会把无关的浏览器扩展错误当致命错误弹框并中断渲染，这里只记录。\n"
    "window.addEventListener('error', function (e) {\n"
    "    try { console.warn('[noVNC ignored]', e && (e.message || e.filename)); } catch (_) {}\n"
    "}, false);\n"
    "window.addEventListener('unhandledrejection', function (e) {\n"
    "    try { console.warn('[noVNC ignored rejection]', e && e.reason); } catch (_) {}\n"
    "});\n"
)

# 1. 注入 vnc 页
for p in ("/usr/share/novnc/vnc.html", "/usr/share/novnc/vnc_lite.html"):
    if not os.path.exists(p):
        continue
    s = open(p, encoding="utf-8").read()
    if MARK in s:
        print("already patched", p)
    elif "<head>" in s:
        open(p, "w", encoding="utf-8").write(s.replace("<head>", "<head>" + INJECT, 1))
        print("patched", p)

# 2. 中和 error-handler.js（可能在 app/ 或其它路径，全部替换）
targets = set(glob.glob("/usr/share/novnc/**/error-handler.js", recursive=True))
targets.add("/usr/share/novnc/app/error-handler.js")
for p in targets:
    if not os.path.exists(p):
        continue
    cur = open(p, encoding="utf-8").read()
    if MARK in cur:
        print("already neutralized", p)
        continue
    open(p, "w", encoding="utf-8").write(NEUTRAL_HANDLER)
    print("neutralized", p)

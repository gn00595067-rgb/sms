"""
pdf.py — 列印版 HTML → PDF（Chromium，經 Playwright）

為什麼用瀏覽器引擎：中文、分頁、表頭重複、plotly 圖表全部交給 Chromium 的列印引擎，
跟使用者在瀏覽器按 Ctrl+P 得到的結果一模一樣，不會「格式跑掉」。

瀏覽器來源（依序嘗試）：
  1. Playwright 自帶的 Chromium（`playwright install chromium`；Streamlit Cloud 也用這個）
  2. Windows 內建 Edge（channel="msedge"），本機開發零安裝
  3. 已安裝的 Chrome（channel="chrome"）
都沒有 → 回傳 None，UI 改提供「列印版 HTML」讓使用者自己按 Ctrl+P。
"""
from __future__ import annotations

import html as _h
import os
import threading

from .doc import Doc
from .html import to_html, to_html_multi
from .theme import FONT_STACK, PAGE

_LOCK = threading.Lock()          # Streamlit 多執行緒：一次一個瀏覽器
_TIMEOUT_MS = 45_000

# 注意：模板是獨立文件，樣式要 inline、字級要明寫；font-family 內只能用單引號（外層是雙引號屬性）。
_FONT_ATTR = FONT_STACK.replace('"', "'")
_HEADER_TMPL = ('<div style="width:100%;font-family:{font};font-size:8.5px;color:#8a94a1;'
                'padding:0 11mm;display:flex;justify-content:space-between;">'
                '<span>{title}</span><span>{period}</span></div>')
_FOOTER_TMPL = ('<div style="width:100%;font-family:{font};font-size:8.5px;color:#8a94a1;'
                'padding:0 11mm;display:flex;justify-content:space-between;">'
                '<span>{who}{stamp}</span><span>第 <span class="pageNumber"></span> / '
                '<span class="totalPages"></span> 頁</span></div>')


_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"]
_INSTALLED = {"done": False}


def _candidates() -> list[dict]:
    out: list[dict] = []
    exe = os.environ.get("EXPORT_CHROMIUM")            # 明確指定（例：/usr/bin/chromium）
    if exe and os.path.exists(exe):
        out.append({"executable_path": exe})
    out.append({})                                       # Playwright 自帶 chromium
    for path in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
        if os.path.exists(path):
            out.append({"executable_path": path})
    out += [{"channel": "msedge"}, {"channel": "chrome"}]  # Windows / Mac 本機
    return out


def _launch(p):
    errors = []
    for kw in _candidates():
        try:
            return p.chromium.launch(headless=True, args=_ARGS, **kw)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            errors.append(f"{kw or 'chromium'}: {type(e).__name__}")
            # Playwright 自帶的 chromium 還沒下載 → 裝一次（Streamlit Cloud 第一次啟動）
            if not kw and "Executable doesn't exist" in msg and not _INSTALLED["done"]:
                _INSTALLED["done"] = True
                try:
                    import subprocess, sys
                    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                                   check=False, timeout=600, capture_output=True)
                    return p.chromium.launch(headless=True, args=_ARGS)
                except Exception as e2:  # noqa: BLE001
                    errors.append(f"install: {type(e2).__name__}")
    raise RuntimeError("找不到可用的瀏覽器：" + "; ".join(errors))


def available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    return True


def html_to_pdf(html: str, *, orientation: str = "landscape", title: str = "", period: str = "",
                who: str = "", stamp: str = "") -> bytes:
    from playwright.sync_api import sync_playwright

    m = PAGE[orientation]["margin"]
    header = _HEADER_TMPL.format(font=_FONT_ATTR, title=_h.escape(title), period=_h.escape(period))
    footer = _FOOTER_TMPL.format(font=_FONT_ATTR, who=(_h.escape(who) + "・") if who else "", stamp=_h.escape(stamp))
    with _LOCK, sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_content(html, wait_until="load", timeout=_TIMEOUT_MS)
            # 等 plotly 把每張圖畫完（沒有圖時立刻通過）
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('.js-plotly-plot')).every(el => el.querySelector('.main-svg'))",
                timeout=_TIMEOUT_MS)
            page.emulate_media(media="print")
            page.wait_for_timeout(150)
            return page.pdf(format="A4", landscape=(orientation == "landscape"), print_background=True,
                            display_header_footer=True, header_template=header, footer_template=footer,
                            margin=m, prefer_css_page_size=False)
        finally:
            browser.close()


def to_pdf(doc: Doc) -> bytes | None:
    """Doc → PDF bytes；環境沒有瀏覽器時回傳 None（呼叫端改給 HTML）。"""
    if not available():
        return None
    html = to_html(doc, plotly_js="inline", toolbar=False)
    try:
        return html_to_pdf(html, orientation=doc.orientation, title=doc.title, period=doc.period_text,
                           who=doc.generated_by, stamp=f"{doc.generated_at:%Y/%m/%d %H:%M}")
    except Exception as e:  # noqa: BLE001
        if os.environ.get("EXPORT_DEBUG"):
            raise
        return None


def to_pdf_multi(docs: list[Doc], pack_title: str, *, who: str = "", stamp: str = "") -> bytes | None:
    """月報包：多份 Doc → 一個 PDF（頁首顯示包名，頁碼連續）。"""
    if not available() or not docs:
        return None
    html = to_html_multi(docs, pack_title, plotly_js="inline", toolbar=False)
    try:
        return html_to_pdf(html, orientation=docs[0].orientation, title=pack_title,
                           period=docs[0].period_text, who=who or docs[0].generated_by,
                           stamp=stamp or f"{docs[0].generated_at:%Y/%m/%d %H:%M}")
    except Exception:  # noqa: BLE001
        if os.environ.get("EXPORT_DEBUG"):
            raise
        return None

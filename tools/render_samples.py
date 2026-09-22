"""把 samples/<dir>/*.html 用 Chromium 印成 PDF（驗收看版面用）。用法：python tools/render_samples.py samples/finance_2026-08"""
import glob, os, sys
from playwright.sync_api import sync_playwright
d = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    for f in sorted(glob.glob(os.path.join(d, "*.html"))):
        pg.goto("file://" + os.path.abspath(f)); pg.wait_for_timeout(150)
        pg.pdf(path=f[:-5] + ".pdf", prefer_css_page_size=True, print_background=True)
    b.close()
print("done")

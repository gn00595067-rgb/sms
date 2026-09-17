"""
core.docs — 每一頁「印出來的樣子」：不碰 streamlit 的 build_doc(f, user, **kw)。

- 頁面（pages_app/*）呼叫 build_doc 後交給 X.ui.render 畫畫面、X.ui.export_bar 產匯出。
- 月報包（scripts/export_pack.py）直接呼叫同一個 build_doc，不需要 streamlit runtime。

規約（tests/test_docs.py 用 ast 驗證）：core/docs/*.py 一律不得 import streamlit。
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.title("Welcome / 欢迎")
st.caption(
    "Document extraction and CCC classification workspace / 文档提取与 CCC 分类工作台"
)

st.subheader("What you can do / 功能")
capabilities = st.columns(3)
with capabilities[0].container(border=True, height="stretch"):
    st.markdown("**Upload / 上传**")
    st.write("PDF, JPG, JPEG, and PNG documents.")
with capabilities[1].container(border=True, height="stretch"):
    st.markdown("**Extract / 提取**")
    st.write("Preserve page text, tables, and key fields.")
with capabilities[2].container(border=True, height="stretch"):
    st.markdown("**Classify / 分类**")
    st.write("Authorization, CCC certification, or other.")

st.subheader("Getting started / 开始使用")
st.markdown(
    "1. Select **CCC verification / CCC 核验** from the menu.\n"
    "2. Upload one PDF or image.\n"
    "3. Click **Start / 开始解析** to run the pipeline.\n"
    "4. Review or download the extracted content."
)

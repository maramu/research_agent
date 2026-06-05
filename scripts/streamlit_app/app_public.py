# -*- coding: utf-8 -*-
"""
app_public.py — Instancia pública de research_agent (puerto 8502).

Lanzar desde scripts/streamlit_app/:
    PUBLIC_APP=true streamlit run app_public.py \
        --server.address 0.0.0.0 --server.port 8502
"""
from __future__ import annotations

import streamlit as st

from app_utils import check_password, is_public_app

st.set_page_config(page_title="research_agent · público", page_icon="🔬", layout="wide")

if not check_password("PUBLIC_APP_PASSWORD"):
    st.stop()

pg = st.navigation([
    st.Page("pages/2_RAG.py", title="RAG", icon="🔍"),
    st.Page("pages/7_Revision.py", title="Revisión bibliográfica", icon="📚"),
])

pg.run()

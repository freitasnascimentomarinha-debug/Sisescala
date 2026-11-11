"""Verificar documento (público, sem login): é a página que o QR code do PDF assinado abre. Mostra só o essencial."""
import streamlit as st

from sisescala.tela_verificacao import mostrar

st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],"
            "[data-testid='stExpandSidebarButton']{display:none !important}</style>", unsafe_allow_html=True)
mostrar(st.session_state["ctx"], completo=False)
st.markdown("[Entrar no SisEscala](/)")

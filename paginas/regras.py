"""Regras da escala: como ela funciona com a configuração atual (padrão x alterado)."""
import streamlit as st

from sisescala import ui
from sisescala.relatorio import html_regras, itens_configuracao, pdf_regras
from sisescala.sessao import barra_contexto, exigir_escala, pagina

P = pagina()
ctx = P.ctx
esc = exigir_escala(P)
alterados = sum(1 for _, its in itens_configuracao(ctx, esc) for i in its if i.alterado)
ui.cabecalho("Regras da escala", f"{esc.nome} · gerado a partir da configuração atual", "book",
             [ui.pill(f"{alterados} regra(s) alterada(s)", "ambar") if alterados else ui.pill("tudo no padrão", "verde")])
barra_contexto(P, periodo=False)
with st.container(border=True):
    st.html(html_regras(ctx, esc))
st.download_button("Baixar regras em PDF", pdf_regras(ctx, esc), f"regras_{esc.id}.pdf", "application/pdf",
                   type="primary", icon=":material/download:")

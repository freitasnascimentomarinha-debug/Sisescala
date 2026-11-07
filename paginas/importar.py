"""Importar planilha existente (CSV/XLSX) em três passos: enviar, revisar, aplicar."""
import streamlit as st

from sisescala import ui
from sisescala.importacao import MODELO_CSV, importar, ler_tabela
from sisescala.sessao import pagina

P = pagina()
ctx, uid = P.ctx, P.uid
prev = st.session_state.get("import_prev")
ui.cabecalho("Importar planilha", "Migre uma escala existente e continue do dia em que parou.", "upload")
ui.linha_do_tempo(["Enviar planilha", "Revisar", "Aplicar"], 1 if prev else 0)

esq, dir_ = st.columns([1, 1.2], gap="large")
with esq, st.container(border=True):
    ui.secao("1 · Enviar")
    st.caption("Colunas: Nome de guerra, Posto/Graduação, NIP, OM, Escala, Ordem, Último serviço e/ou Data, "
               "E-mail, Ramal e Celular. A escala continua do dia seguinte à última data da planilha.")
    st.download_button("Baixar modelo (CSV)", MODELO_CSV.encode("utf-8-sig"), "modelo_importacao.csv", "text/csv",
                       icon=":material/download:")
    arq = st.file_uploader("Planilha", type=["csv", "xlsx"], label_visibility="collapsed")
    sentido = st.selectbox("Ordem das linhas", ["topo_mais_antigo", "base_mais_antigo"],
                           format_func=lambda x: "1ª linha = mais antigo" if x == "topo_mais_antigo" else "última linha = mais antigo")
    criar = st.checkbox("Criar escalas que não existirem", True)
    subst = st.checkbox("Membros das escalas citadas = os da planilha", False)
    if arq and st.button("Revisar importação", type="primary", icon=":material/fact_check:"):
        try:
            st.session_state.import_prev = importar(ctx, ler_tabela(arq.getvalue(), arq.name), sentido=sentido,
                                                    criar_escalas=criar, dono_id=uid, substituir_membros=subst)
            st.rerun()
        except Exception as ex:  # planilha malformada
            st.error(f"Não consegui ler a planilha: {ex}")
with dir_, st.container(border=True):
    ui.secao("2 · Revisar e aplicar")
    if not prev:
        ui.vazio("Nada para revisar", "Envie uma planilha e clique em “Revisar importação”.", "upload")
    else:
        novo_ctx, rel = prev
        for t in rel.erros:
            st.error(t)
        ui.kpis([("Novos", len(rel.novos), "users", "verde"), ("Atualizados", len(rel.atualizados), "edit", "azul"),
                 ("Vínculos", rel.vinculos, "link", "violeta"), ("Escalas criadas", len(rel.escalas_criadas), "calendar", "ambar")])
        if rel.data_base:
            st.info(f"A escala continua em {rel.data_base:%d/%m/%Y}. " + "; ".join(
                f"{k}: último = {v}" for k, v in rel.continuidade.items()))
        for t in rel.avisos:
            st.warning(t)
        c1, c2, _ = st.columns([1, 1, 2])
        if not rel.erros and c1.button("Aplicar importação", type="primary", icon=":material/check:"):
            st.session_state.ctx = novo_ctx
            del st.session_state["import_prev"]
            st.session_state["toast"] = "Importação aplicada."
            st.rerun()
        if c2.button("Descartar"):
            del st.session_state["import_prev"]
            st.rerun()

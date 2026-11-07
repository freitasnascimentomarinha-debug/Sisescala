"""SisEscala – app Streamlit (protótipo). Rodar: streamlit run app.py"""
from datetime import date, timedelta

import streamlit as st

from sisescala.calendario import pontos_facultativos
from sisescala.demo import contexto_demo
from sisescala.modelos import Impedimento, DiaEspecial, Guarnecimento, Ocorrencia, TIPOS_IMPEDIMENTO
from sisescala.motor import gerar
from sisescala.pdf import gerar_pdf
from sisescala.previa import html_previa, periodo

st.set_page_config(page_title="SisEscala", layout="wide")
if "ctx" not in st.session_state:
    st.session_state.ctx = contexto_demo()
ctx = st.session_state.ctx

st.title("SisEscala – Detalhe de Serviço")
with st.sidebar:
    st.header("Configuração")
    ctx.uf = st.text_input("UF da OM (feriados)", ctx.uf, max_chars=2).upper()
    ctx.janela_devolucao_dias = st.number_input("Prazo de devolução (dias)", 1, 365, ctx.janela_devolucao_dias)
    ctx.janela_troca_dias = st.number_input("Janela de busca da troca forçada (dias)", 1, 60, ctx.janela_troca_dias)
    inicio = st.date_input("Início da prévia", date.today())
    dias_n = {"7 dias": 7, "15 dias": 15, "1 mês": 30}[st.radio("Período", ["7 dias", "15 dias", "1 mês"])]

aba_prev, aba_lanc, aba_pdf = st.tabs(["Prévia", "Lançamentos", "Detalhe (PDF)"])
dias = periodo(inicio, dias_n)
res = gerar(ctx, dias[-1])

with aba_prev:
    for av in res.avisos:
        if av.startswith("CONFLITO"):
            st.error(av)
    st.html(html_previa(ctx, res, dias))
    if res.devolucoes:
        st.subheader("Serviços a devolver")
        for dv in res.devolucoes:
            st.write(f"{ctx.militar(dv.militar_id).nome} – origem {dv.data_origem:%d/%m}, prazo {dv.prazo:%d/%m}")

with aba_lanc:
    nomes = {m.id: m.nome for m in ctx.militares}
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Impedimento")
        with st.form("imp", clear_on_submit=True):
            mid = st.selectbox("Militar", list(nomes), format_func=nomes.get)
            tipo = st.selectbox("Tipo", list(TIPOS_IMPEDIMENTO))
            i, f = st.date_input("Início", date.today()), st.date_input("Fim", date.today())
            motivo, anexo = st.text_input("Motivo"), st.text_input("Arquivo/link (obrigatório p/ dispensa)")
            if st.form_submit_button("Lançar"):
                imp = Impedimento(mid, tipo, i, None if tipo == "desembarque" else f, motivo, anexo)
                if erros := imp.validar():
                    st.error("; ".join(erros))
                else:
                    ctx.impedimentos.append(imp); st.rerun()
        st.subheader("Falta no serviço (avança o retém)")
        with st.form("oc", clear_on_submit=True):
            e = st.selectbox("Escala", [x.id for x in ctx.escalas], format_func=lambda x: ctx.escala(x).nome)
            m2 = st.selectbox("Militar escalado", list(nomes), format_func=nomes.get)
            dt, mot = st.date_input("Dia", date.today()), st.text_input("Motivo ")
            if st.form_submit_button("Lançar falta"):
                ctx.ocorrencias.append(Ocorrencia(dt, e, m2, mot)); st.rerun()
    with c2:
        st.subheader("Feriado / dia sem expediente")
        with st.form("de", clear_on_submit=True):
            dd = st.date_input("Data", date.today())
            tp = st.selectbox("Tipo", ["feriado", "sem_expediente"])
            ds = st.text_input("Descrição (ex.: aniversário da cidade, licença administrativa)")
            if st.form_submit_button("Lançar"):
                ctx.dias_especiais.append(DiaEspecial(dd, tp, ds)); st.rerun()
        with st.expander(f"Pontos facultativos de {inicio.year} (sugestões)"):
            for d, n in sorted(pontos_facultativos(inicio.year, ctx.uf).items()):
                st.write(f"{d:%d/%m} – {n}")
        st.subheader("Comando guarnece / não guarnece")
        with st.form("gu", clear_on_submit=True):
            e2 = st.selectbox("Escala ", [x.id for x in ctx.escalas], format_func=lambda x: ctx.escala(x).nome)
            dg, gu = st.date_input("Dia ", date.today()), st.checkbox("Guarnece", True)
            if st.form_submit_button("Lançar"):
                ctx.guarnecimentos.append(Guarnecimento(dg, e2, gu)); st.rerun()

with aba_pdf:
    om = st.text_input("Organização Militar")
    ins = st.text_area("Instruções do serviço")
    rec = st.text_area("Recomendações")
    reg = st.text_area("Regras (horário de parada, acumulação de trabalho etc.)")
    a1, a2, a3 = st.columns(3)
    ass = (a1.text_input("Detalhista"), a2.text_input("Encarregado do Detalhe"), a3.text_input("Vice-Diretor"))
    st.download_button("Gerar PDF", gerar_pdf(ctx, res, dias, om, ins, rec, reg, ass),
                       f"detalhe_{dias[0]:%Y%m%d}.pdf", "application/pdf")

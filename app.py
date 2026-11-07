"""SisEscala – app Streamlit (protótipo). Rodar: streamlit run app.py"""
from datetime import date

import streamlit as st

from sisescala import permissoes as pm
from sisescala.calendario import pontos_facultativos
from sisescala.demo import contexto_demo
from sisescala.modelos import (CATEGORIAS, TIPOS_IMPEDIMENTO, DiaEspecial, Escala, Evento, Guarnecimento,
                               Impedimento, Ocorrencia, Pertinencia, quartos_padrao)
from sisescala.motor import gerar, validar_escala
from sisescala.pdf import gerar_pdf
from sisescala.previa import html_previa, periodo

st.set_page_config(page_title="SisEscala", layout="wide")
if "ctx" not in st.session_state:
    st.session_state.ctx = contexto_demo()
ctx = st.session_state.ctx
nomes_u = {u.id: u.nome for u in ctx.usuarios}
nomes_m = {m.id: m.nome for m in ctx.militares}

with st.sidebar:
    st.header("SisEscala")
    # TODO: login real (senha com hash). Por ora o usuário é escolhido aqui.
    uid = st.selectbox("Usuário", list(nomes_u), format_func=nomes_u.get)
    visiveis = pm.escalas_visiveis(ctx, uid)
    if not visiveis:
        st.info("Você ainda não tem escalas. Crie uma na aba Escalas.")
    eid = st.selectbox("Escala", [e.id for e in visiveis], format_func=lambda i: ctx.escala(i).nome) \
        if visiveis else None
    st.divider()
    ctx.uf = st.text_input("UF da OM (feriados)", ctx.uf, max_chars=2).upper()
    ctx.janela_devolucao_dias = st.number_input("Prazo de devolução (dias)", 1, 365, ctx.janela_devolucao_dias)
    ctx.janela_troca_dias = st.number_input("Janela da troca forçada (dias)", 1, 60, ctx.janela_troca_dias)
    inicio = st.date_input("Início da prévia", date.today())
    dias_n = {"7 dias": 7, "15 dias": 15, "1 mês": 30}[st.radio("Período", ["7 dias", "15 dias", "1 mês"])]

dias = periodo(inicio, dias_n)
res = gerar(ctx, dias[-1])
esc = ctx.escala(eid) if eid else None
aba_prev, aba_pdf, aba_lanc, aba_esc = st.tabs(["Prévia", "Detalhe (PDF)", "Lançamentos", "Escalas"])

with aba_prev:
    if esc:
        for av in res.avisos:
            if av.startswith("CONFLITO"):
                st.error(av)
        st.html(html_previa(ctx, res, dias, esc.id))
        pend = [d for d in res.devolucoes if d.escala_id == esc.id]
        if pend:
            st.subheader("Serviços a devolver")
            for dv in pend:
                st.write(f"{nomes_m[dv.militar_id]} – origem {dv.data_origem:%d/%m}, prazo {dv.prazo:%d/%m}")

with aba_pdf:
    if esc:
        om = st.text_input("Organização Militar")
        ins = st.text_area("Instruções do serviço")
        rec = st.text_area("Recomendações")
        reg = st.text_area("Regras (horário de parada, acumulação de trabalho etc.)")
        a1, a2, a3 = st.columns(3)
        ass = (a1.text_input("Detalhista"), a2.text_input("Encarregado do Detalhe"), a3.text_input("Vice-Diretor"))
        st.download_button(f"Gerar PDF – {esc.nome}", gerar_pdf(ctx, res, dias, esc.id, om, ins, rec, reg, ass),
                           f"detalhe_{esc.id}_{dias[0]:%Y%m%d}.pdf", "application/pdf")

with aba_lanc:
    editaveis = [e.id for e in visiveis if pm.pode_editar(ctx, uid, e)]
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Impedimento / destaque (DTQ)")
        with st.form("imp", clear_on_submit=True):
            mid = st.selectbox("Militar", list(nomes_m), format_func=nomes_m.get)
            tipo = st.selectbox("Tipo", list(TIPOS_IMPEDIMENTO))
            i, f = st.date_input("Início", date.today()), st.date_input("Fim", date.today())
            motivo, anexo = st.text_input("Motivo / OM de destino"), st.text_input("Arquivo/link (obrigatório p/ dispensa)")
            if st.form_submit_button("Lançar"):
                imp = Impedimento(mid, tipo, i, None if tipo == "desembarque" else f, motivo, anexo)
                if erros := imp.validar():
                    st.error("; ".join(erros))
                else:
                    ctx.impedimentos.append(imp); st.rerun()
        if editaveis:
            st.subheader("Falta no serviço (avança o retém)")
            with st.form("oc", clear_on_submit=True):
                e = st.selectbox("Escala", editaveis, format_func=lambda x: ctx.escala(x).nome)
                m2 = st.selectbox("Militar escalado", list(nomes_m), format_func=nomes_m.get)
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
        if editaveis:
            st.subheader("Comando guarnece / não guarnece")
            with st.form("gu", clear_on_submit=True):
                e2 = st.selectbox("Escala ", editaveis, format_func=lambda x: ctx.escala(x).nome)
                dg, gu = st.date_input("Dia ", date.today()), st.checkbox("Guarnece", True)
                if st.form_submit_button("Lançar"):
                    ctx.guarnecimentos.append(Guarnecimento(dg, e2, gu)); st.rerun()
            evt = [e for e in editaveis if ctx.escala(e).modo == "eventos"]
            if evt:
                st.subheader("Evento (palestra, cerimônia, apoio...)")
                with st.form("ev", clear_on_submit=True):
                    e3 = st.selectbox("Escala  ", evt, format_func=lambda x: ctx.escala(x).nome)
                    de, desc = st.date_input("Data do evento", date.today()), st.text_input("Descrição")
                    hora, local = st.text_input("Hora"), st.text_input("Local")
                    vagas = st.number_input("Vagas (0 = padrão da escala)", 0, 99, 0)
                    if st.form_submit_button("Lançar evento"):
                        ctx.eventos.append(Evento(e3, de, desc, hora, local, vagas or None)); st.rerun()

with aba_esc:
    st.subheader("Criar escala")
    with st.form("nova", clear_on_submit=True):
        n1, n2, n3 = st.columns(3)
        nome = n1.text_input("Nome")
        cat = n2.selectbox("Categoria", list(CATEGORIAS), format_func=lambda c: CATEGORIAS[c][0])
        tipo_txt = n3.text_input("Tipo (ex.: Diária, Pernoite)")
        m1, m2_, m3 = st.columns(3)
        modo = m1.selectbox("Modo", ["corrida", "preta_vermelha", "eventos"])
        funciona = m2_.selectbox("Funciona em", ["todos", "uteis"], format_func=lambda x: "todos os dias" if x == "todos" else "só dias úteis")
        prio = m3.number_input("Prioridade (maior prevalece)", 1, 99, 1)
        p1, p2, p3, p4 = st.columns(4)
        por_dia = p1.number_input("Escalados por dia", 1, 20, 1)
        retem = p2.number_input("Retém por dia", 0, 5, 1)
        folgas = p3.number_input("Folgas mínimas entre serviços (2 = 2x1)", 0, 10, 2)
        horas_q = p4.selectbox("Quartos", [0, 4, 2, 3, 6], format_func=lambda h: "sem quartos" if h == 0 else f"de {h}h")
        membros = st.multiselect("Militares", list(nomes_m), format_func=nomes_m.get)
        refs = st.multiselect("Escalas que prevalecem sobre esta (compartilhadas com você)",
                              [e.id for e in visiveis], format_func=lambda i: ctx.escala(i).nome)
        if st.form_submit_button("Criar"):
            nova = Escala(f"e{len(ctx.escalas) + 1}", nome, dono_id=uid, categoria=cat, tipo=tipo_txt, modo=modo,
                          funciona_em=funciona, prioridade=prio, militares_dia=por_dia, retem_qtd=retem,
                          folgas_minimas=folgas, quartos=quartos_padrao(horas_q) if horas_q else [],
                          membros=[Pertinencia(m) for m in membros], participa_roxa=modo != "eventos")
            if erros := validar_escala(ctx, nova):
                st.error(" ".join(erros))
            else:
                ctx.escalas.append(nova)
                for r in refs:
                    pm.referenciar(ctx, uid, nova.id, r)
                st.rerun()
    st.subheader("Compartilhar acesso")
    minhas = [e for e in visiveis if e.dono_id == uid]
    if not minhas:
        st.caption("Você não é dono de nenhuma escala.")
    for e in minhas:
        with st.expander(e.nome):
            st.write({nomes_u.get(u, u): n for u, n in e.compartilhado_com.items()} or "Não compartilhada.")
            outros = [u for u in nomes_u if u != uid]
            cc1, cc2, cc3 = st.columns([2, 2, 1])
            com = cc1.selectbox("Usuário", outros, format_func=nomes_u.get, key=f"u{e.id}")
            niv = cc2.selectbox("Nível", ["leitura", "edicao", "revogar"], key=f"n{e.id}")
            if cc3.button("Aplicar", key=f"b{e.id}"):
                pm.compartilhar(ctx, uid, e.id, com, None if niv == "revogar" else niv); st.rerun()

"""Lançamentos: impedimentos e dispensas, dias especiais, guarnecimento, dispensa no dia e eventos.

Detalhista e auxiliar lançam. O auxiliar só nas escalas dele e só para os militares delas, e ninguém lança para si mesmo.
"""
from datetime import date

import streamlit as st

from sisescala import lancamentos as lc
from sisescala import ui
from sisescala.calendario import pontos_facultativos
from sisescala.modelos import (ROTULO_IMPEDIMENTO, TIPOS_IMPEDIMENTO, TIPOS_VISIVEIS, DiaEspecial, Evento, Guarnecimento,
                               Impedimento, Ocorrencia)
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid = P.ctx, P.uid
nomes_m = P.nomes_m
escalas_ok = lc.escalas_lancaveis(ctx, uid)
editaveis = [e.id for e in escalas_ok]
militares = lc.militares_lancaveis(ctx, uid)            # sem o próprio usuário
ui.cabecalho("Lançamentos", "Tudo que muda a escala: impedimentos e dispensas, dias sem expediente, guarnecimento e eventos.",
             "calendar", [ui.chip("Escalas", ", ".join(e.nome for e in escalas_ok) or "—")])
if not P.gerir:
    st.caption("Como auxiliar, você lança nas escalas em que é auxiliar e para os militares delas, menos para você mesmo.")
if not escalas_ok:
    ui.vazio("Sem permissão para lançar", "Só o detalhista e o auxiliar de uma escala lançam.", "shield")
    st.stop()

SECOES = {"Impedimentos": "Impedimentos e dispensas", "Dias": "Feriados e dias sem expediente",
          "Guarnece": "Comando guarnece", "Faltas": "Dispensado no dia do serviço", "Eventos": "Eventos"}
sec = st.segmented_control("Tipo de lançamento", list(SECOES), default="Impedimentos", format_func=SECOES.get,
                           key="lanc_sec", label_visibility="collapsed") or "Impedimentos"


def removivel(lista, rotulo, chave=""):
    itens = [x for x in lista if lc.pode_remover(ctx, uid, x)]
    with st.container(border=True):
        ui.secao("Lançados")
        if not itens:
            ui.vazio("Nada lançado", "", "list")
            return
        sel = st.multiselect("Selecione para remover", range(len(itens)), format_func=lambda i: rotulo(itens[i]), key=f"rm_{chave}")
        if sel and st.button("Remover selecionados", key=f"btn_{chave}", icon=":material/delete:"):
            escolhidos = [itens[i] for i in sel]
            agir(lambda: [lc.remover(ctx, uid, x) for x in escolhidos] and None, "Removido.")


def lancar(acao, ok):
    agir(acao, ok)


esq, dir_ = st.columns([1, 1.1], gap="large")
if sec == "Impedimentos":
    with esq, st.container(border=True):
        ui.secao("Novo impedimento ou dispensa")
        if not militares:
            ui.vazio("Sem militares", "Não há militares nas suas escalas.", "users")
        else:
            with st.form("imp", clear_on_submit=True, border=False):
                mid = st.selectbox("Militar", militares, format_func=nomes_m.get)
                tipo = st.selectbox("Situação", TIPOS_VISIVEIS,
                                    format_func=lambda t: f"{ROTULO_IMPEDIMENTO[t]}  ·  {TIPOS_IMPEDIMENTO[t]}")
                a, b = st.columns(2)
                i, f = a.date_input("Início", date.today(), format="DD/MM/YYYY"), b.date_input("Fim", date.today(), format="DD/MM/YYYY")
                motivo = st.text_input("Justificativa / OM de destino", help="Obrigatória para dispensas (baixa, falta ou com documento).")
                anexo = st.text_input("Arquivo ou link (obrigatório na dispensa com documento)")
                if st.form_submit_button("Lançar", type="primary", use_container_width=True):
                    lancar(lambda: lc.lancar_impedimento(ctx, uid, Impedimento(
                        mid, tipo, i, None if tipo == "desembarque" else f, motivo, anexo)), "Impedimento lançado.")
    with dir_:
        removivel(ctx.impedimentos, lambda x: f"{nomes_m.get(x.militar_id, x.militar_id)} – {ROTULO_IMPEDIMENTO.get(x.tipo, x.tipo)} "
                  f"{x.inicio:%d/%m}{'–' + format(x.fim, '%d/%m') if x.fim else ''} {x.motivo}", "imp")
elif sec == "Dias":
    with esq, st.container(border=True):
        ui.secao("Novo dia especial")
        with st.form("de", clear_on_submit=True, border=False):
            dd = st.date_input("Data", date.today(), format="DD/MM/YYYY")
            tp = st.selectbox("Tipo", ["feriado", "sem_expediente"], format_func=lambda t: "Feriado" if t == "feriado" else "Sem expediente")
            ds = st.text_input("Descrição", placeholder="Aniversário da cidade, licença administrativa…")
            if st.form_submit_button("Lançar", type="primary", use_container_width=True):
                lancar(lambda: lc.lancar_dia_especial(ctx, uid, DiaEspecial(dd, tp, ds)), "Dia lançado.")
        with st.expander(f"Pontos facultativos de {P.inicio.year} (sugestões)"):
            for d, n in sorted(pontos_facultativos(P.inicio.year, ctx.uf).items()):
                st.write(f"{d:%d/%m} – {n}")
    with dir_:
        removivel(ctx.dias_especiais, lambda x: f"{x.data:%d/%m} {x.tipo} {x.descricao}", "dias")
elif sec == "Guarnece":
    with esq, st.container(border=True):
        ui.secao("Decisão do comando")
        with st.form("gu", clear_on_submit=True, border=False):
            e2 = st.selectbox("Escala", editaveis, format_func=lambda x: ctx.escala(x).nome)
            dg = st.date_input("Dia", date.today(), format="DD/MM/YYYY")
            gu = st.toggle("Guarnece neste dia", True)
            if st.form_submit_button("Lançar", type="primary", use_container_width=True):
                lancar(lambda: lc.lancar_guarnecimento(ctx, uid, Guarnecimento(dg, e2, gu)), "Decisão lançada.")
    with dir_:
        removivel(ctx.guarnecimentos, lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: "
                  f"{'guarnece' if x.guarnece else 'não guarnece'}", "gu")
elif sec == "Faltas":
    with esq, st.container(border=True):
        ui.secao("Dispensado do serviço escalado (o retém avança)")
        if not militares:
            ui.vazio("Sem militares", "Não há militares nas suas escalas.", "users")
        else:
            with st.form("oc", clear_on_submit=True, border=False):
                e = st.selectbox("Escala", editaveis, format_func=lambda x: ctx.escala(x).nome)
                m2 = st.selectbox("Militar escalado", militares, format_func=nomes_m.get)
                dt = st.date_input("Dia do serviço", date.today(), format="DD/MM/YYYY")
                mot = st.text_input("Justificativa (obrigatória)", help="Baixa, falta ou outro motivo. Aparece na prévia e no detalhe.")
                st.caption("O militar passa a Dispensado (Disp) nesse dia, o retém avança e a prévia e o detalhe se reconfiguram.")
                if st.form_submit_button("Dispensar do serviço", type="primary", use_container_width=True):
                    lancar(lambda: lc.lancar_dispensa_no_dia(ctx, uid, Ocorrencia(dt, e, m2, mot.strip())),
                           "Dispensa lançada; o retém avançou e a escala foi reconfigurada.")
    with dir_:
        removivel(ctx.ocorrencias, lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: {nomes_m.get(x.militar_id)} dispensado – {x.motivo}", "falta")
else:
    evt = [e for e in editaveis if ctx.escala(e).modo == "eventos"]
    with esq, st.container(border=True):
        ui.secao("Novo evento (palestra, cerimônia, apoio…)")
        if not evt:
            ui.vazio("Nenhuma escala por evento", "Crie uma escala no modo “Por evento” em Escalas.", "calendar")
        else:
            with st.form("ev", clear_on_submit=True, border=False):
                e3 = st.selectbox("Escala", evt, format_func=lambda x: ctx.escala(x).nome)
                a, b = st.columns(2)
                de, desc = a.date_input("Data do evento", date.today(), format="DD/MM/YYYY"), b.text_input("Descrição")
                a, b, c = st.columns(3)
                hora, local = a.text_input("Hora"), b.text_input("Local")
                vagas = c.number_input("Vagas (0 = padrão)", 0, 99, 0)
                if st.form_submit_button("Lançar evento", type="primary", use_container_width=True):
                    lancar(lambda: lc.lancar_evento(ctx, uid, Evento(e3, de, desc, hora, local, vagas or None)), "Evento lançado.")
    with dir_:
        removivel(ctx.eventos, lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: {x.descricao}", "ev")

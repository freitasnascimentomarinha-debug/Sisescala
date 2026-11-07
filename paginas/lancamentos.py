"""Lançamentos: impedimentos, dias especiais, guarnecimento, faltas e eventos."""
from datetime import date

import streamlit as st

from sisescala import notificacoes as nt
from sisescala import ui
from sisescala.calendario import pontos_facultativos
from sisescala.modelos import (TIPOS_IMPEDIMENTO, DiaEspecial, Evento, Guarnecimento, Impedimento, Ocorrencia)
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid = P.ctx, P.uid
nomes_m = P.nomes_m
editaveis = [e.id for e in P.editaveis()]
ed_ids = set(editaveis)
ui.cabecalho("Lançamentos", "Tudo que muda a escala: impedimentos, dias sem expediente, guarnecimento, faltas e eventos.", "calendar")

SECOES = {"Impedimentos": "Impedimentos e destaques", "Dias": "Feriados e dias sem expediente",
          "Guarnece": "Comando guarnece", "Faltas": "Faltas no serviço", "Eventos": "Eventos"}
sec = st.segmented_control("Tipo de lançamento", list(SECOES), default="Impedimentos", format_func=SECOES.get,
                           key="lanc_sec", label_visibility="collapsed") or "Impedimentos"


def removivel(lista, rotulo, pertence=lambda x: True, chave=""):
    idx = [i for i, x in enumerate(lista) if pertence(x)]
    with st.container(border=True):
        ui.secao("Lançados")
        if not idx:
            ui.vazio("Nada lançado", "", "list")
            return
        sel = st.multiselect("Selecione para remover", idx, format_func=lambda i: rotulo(lista[i]), key=f"rm_{chave}")
        if sel and st.button("Remover selecionados", key=f"btn_{chave}", icon=":material/delete:"):
            for i in sorted(sel, reverse=True):
                del lista[i]
            st.session_state["toast"] = "Removido."
            st.rerun()


esq, dir_ = st.columns([1, 1.1], gap="large")
if sec == "Impedimentos":
    with esq, st.container(border=True):
        ui.secao("Novo impedimento / destaque (DTQ)")
        with st.form("imp", clear_on_submit=True, border=False):
            mid = st.selectbox("Militar", list(nomes_m), format_func=nomes_m.get)
            tipo = st.selectbox("Tipo", list(TIPOS_IMPEDIMENTO), format_func=lambda t: f"{TIPOS_IMPEDIMENTO[t]} · {t}")
            a, b = st.columns(2)
            i, f = a.date_input("Início", date.today(), format="DD/MM/YYYY"), b.date_input("Fim", date.today(), format="DD/MM/YYYY")
            motivo = st.text_input("Motivo / OM de destino")
            anexo = st.text_input("Arquivo ou link (obrigatório para dispensa)")
            if st.form_submit_button("Lançar", type="primary", use_container_width=True):
                imp = Impedimento(mid, tipo, i, None if tipo == "desembarque" else f, motivo, anexo)
                if erros := imp.validar():
                    st.error("; ".join(erros))
                else:
                    ctx.impedimentos.append(imp)
                    st.session_state["toast"] = "Impedimento lançado."
                    st.rerun()
    with dir_:
        removivel(ctx.impedimentos, lambda x: f"{nomes_m.get(x.militar_id, x.militar_id)} – {TIPOS_IMPEDIMENTO[x.tipo]} "
                  f"{x.inicio:%d/%m}{'–' + format(x.fim, '%d/%m') if x.fim else ''} {x.motivo}", chave="imp")
elif sec == "Dias":
    with esq, st.container(border=True):
        ui.secao("Novo dia especial")
        with st.form("de", clear_on_submit=True, border=False):
            dd = st.date_input("Data", date.today(), format="DD/MM/YYYY")
            tp = st.selectbox("Tipo", ["feriado", "sem_expediente"], format_func=lambda t: "Feriado" if t == "feriado" else "Sem expediente")
            ds = st.text_input("Descrição", placeholder="Aniversário da cidade, licença administrativa…")
            if st.form_submit_button("Lançar", type="primary", use_container_width=True):
                ctx.dias_especiais.append(DiaEspecial(dd, tp, ds))
                st.session_state["toast"] = "Dia lançado."
                st.rerun()
        with st.expander(f"Pontos facultativos de {P.inicio.year} (sugestões)"):
            for d, n in sorted(pontos_facultativos(P.inicio.year, ctx.uf).items()):
                st.write(f"{d:%d/%m} – {n}")
    with dir_:
        removivel(ctx.dias_especiais, lambda x: f"{x.data:%d/%m} {x.tipo} {x.descricao}", chave="dias")
elif sec == "Guarnece":
    with esq, st.container(border=True):
        ui.secao("Decisão do comando")
        if not editaveis:
            ui.vazio("Sem escalas para editar", "", "calendar")
        else:
            with st.form("gu", clear_on_submit=True, border=False):
                e2 = st.selectbox("Escala", editaveis, format_func=lambda x: ctx.escala(x).nome)
                dg = st.date_input("Dia", date.today(), format="DD/MM/YYYY")
                gu = st.toggle("Guarnece neste dia", True)
                if st.form_submit_button("Lançar", type="primary", use_container_width=True):
                    ctx.guarnecimentos.append(Guarnecimento(dg, e2, gu))
                    st.session_state["toast"] = "Decisão lançada."
                    st.rerun()
    with dir_:
        removivel(ctx.guarnecimentos, lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: "
                  f"{'guarnece' if x.guarnece else 'não guarnece'}", lambda x: x.escala_id in ed_ids, "gu")
elif sec == "Faltas":
    with esq, st.container(border=True):
        ui.secao("Falta no serviço (avança o retém)")
        if not editaveis:
            ui.vazio("Sem escalas para editar", "", "calendar")
        else:
            with st.form("oc", clear_on_submit=True, border=False):
                e = st.selectbox("Escala", editaveis, format_func=lambda x: ctx.escala(x).nome)
                m2 = st.selectbox("Militar escalado", list(nomes_m), format_func=nomes_m.get)
                dt = st.date_input("Dia", date.today(), format="DD/MM/YYYY")
                mot = st.text_input("Motivo")
                if st.form_submit_button("Lançar falta", type="primary", use_container_width=True):
                    ctx.ocorrencias.append(Ocorrencia(dt, e, m2, mot))
                    nt.notificar(ctx, nt.usuarios_do_militar(ctx, m2), "devolucao",
                                 f"Você tem um serviço a devolver: falta em {dt:%d/%m/%Y} ({ctx.escala(e).nome}), "
                                 f"prazo de {ctx.janela_devolucao_dias} dias. Veja a página Devoluções.", e)
                    st.session_state["toast"] = "Falta lançada; o retém avançou."
                    st.rerun()
    with dir_:
        removivel(ctx.ocorrencias, lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: {nomes_m.get(x.militar_id)}",
                  lambda x: x.escala_id in ed_ids, "falta")
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
                    ctx.eventos.append(Evento(e3, de, desc, hora, local, vagas or None))
                    st.session_state["toast"] = "Evento lançado."
                    st.rerun()
    with dir_:
        removivel(ctx.eventos, lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: {x.descricao}",
                  lambda x: x.escala_id in ed_ids, "ev")

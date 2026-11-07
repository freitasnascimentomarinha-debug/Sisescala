"""Cadastro de militares: buscar, editar, adicionar, excluir e vincular a escalas."""
from datetime import date

import pandas as pd
import streamlit as st

from sisescala import cadastro as cd
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid = P.ctx, P.uid
nomes_m = P.nomes_m


@st.dialog("Adicionar militar", width="large")
def dialogo_novo():
    a, b, c = st.columns(3)
    nm, pt, nip = a.text_input("Nome de guerra"), b.text_input("Posto/Graduação"), c.text_input("NIP")
    a, b, c = st.columns(3)
    om, ant = a.text_input("OM (sigla/código)"), b.number_input("Antiguidade (0 = mais moderno)", 0, 999, 0)
    em = c.text_input("E-mail")
    a, b = st.columns(2)
    ra, ce = a.text_input("Ramal"), b.text_input("Celular")
    if st.button("Adicionar", type="primary", use_container_width=True):
        agir(lambda: cd.adicionar_militar(ctx, nm, pt, nip, om, ant or None, em, ra, ce), "Militar adicionado.")


@st.dialog("Vincular à escala", width="large")
def dialogo_vincular():
    ed_esc = [e.id for e in P.editaveis()]
    if not ed_esc:
        st.info("Você não edita nenhuma escala.")
        return
    alvo = st.selectbox("Escala", ed_esc, format_func=lambda i: ctx.escala(i).nome)
    sel = st.multiselect("Militares", list(nomes_m), format_func=nomes_m.get)
    data_v = st.date_input("A partir de / até (mudança de escala)", date.today(), format="DD/MM/YYYY")
    c1, c2, c3 = st.columns(3)
    if c1.button("Adicionar", type="primary"):
        agir(lambda: cd.adicionar_a_escala(ctx, alvo, sel, data_v), "Militares adicionados à escala.")
    if c2.button("Encerrar na data"):
        agir(lambda: cd.remover_da_escala(ctx, alvo, sel, data_v), "Participação encerrada.")
    if c3.button("Remover de vez"):
        agir(lambda: cd.remover_da_escala(ctx, alvo, sel), "Militares removidos da escala.")


ui.cabecalho("Militares", "Cadastro único: antiguidade, contato e vínculo com as escalas.", "users",
             [ui.chip("Total", len(ctx.militares))])
b1, b2, b3 = st.columns([1.1, 1.2, 4])
if b1.button("Adicionar", type="primary", icon=":material/person_add:"):
    dialogo_novo()
if b2.button("Vincular à escala", icon=":material/link:"):
    dialogo_vincular()
busca = st.text_input("Buscar", placeholder="Nome, posto, NIP ou OM", label_visibility="collapsed", key="mil_busca")

linhas = [{"Excluir": False, "id": m.id, "Antiguidade": m.antiguidade, "Nome de guerra": m.nome, "Posto/Grad.": m.posto,
           "NIP": m.nip, "OM": m.om, "E-mail": m.email, "Ramal": m.ramal, "Celular": m.celular}
          for m in sorted(ctx.militares, key=lambda m: m.antiguidade)
          if not busca or busca.lower() in f"{m.nome} {m.posto} {m.nip} {m.om}".lower()]
if not ctx.militares:
    ui.vazio("Nenhum militar cadastrado", "Adicione militares ou importe uma planilha.", "users")
else:
    with st.container(border=True):
        ed = st.data_editor(pd.DataFrame(linhas), hide_index=True, width="stretch", disabled=["id"], key="mil_editor",
                            column_config={"id": None, "Excluir": st.column_config.CheckboxColumn(width="small"),
                                           "Antiguidade": st.column_config.NumberColumn(width="small")})
        c1, c2, _ = st.columns([1, 2, 3])
        if c1.button("Salvar edições", type="primary", icon=":material/save:"):
            def _salvar():
                for _, r in ed.iterrows():
                    cd.editar_militar(ctx, r["id"], nome=r["Nome de guerra"], posto=r["Posto/Grad."] or "", nip=r["NIP"] or "",
                                      om=r["OM"] or "", email=r["E-mail"] or "", ramal=r["Ramal"] or "", celular=r["Celular"] or "")
                for _, r in ed.sort_values("Antiguidade").iterrows():
                    if ctx.militar(r["id"]).antiguidade != int(r["Antiguidade"]):
                        cd.editar_militar(ctx, r["id"], antiguidade=int(r["Antiguidade"]))
            agir(_salvar, "Cadastro atualizado.")
        with c2.popover("Excluir marcados", icon=":material/delete:"):
            marcados = list(ed.loc[ed["Excluir"], "id"])
            st.warning(f"{len(marcados)} militar(es) marcado(s). A exclusão vale para o cadastro e todas as escalas.")
            if marcados and st.button("Confirmar exclusão", key="mil_del"):
                agir(lambda: cd.excluir_militares(ctx, marcados, uid), "Militares excluídos.")

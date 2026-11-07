"""Cadastro de militares: buscar, editar, adicionar, excluir e vincular a escalas."""
from datetime import date

import pandas as pd
import streamlit as st

from sisescala import cadastro as cd
from sisescala import gestao
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.componente import ordem_interativa
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid = P.ctx, P.uid
admin = P.user.admin
# O cadastro é global; cada detalhista enxerga e edita apenas os militares das escalas dele (o administrador, todos).
meus_ids = {p.militar_id for e in P.editaveis() for p in e.membros} if not admin else {m.id for m in ctx.militares}
meus_mil = [m for m in ctx.militares if m.id in meus_ids]
nomes_m = {m.id: m.nome for m in meus_mil}


@st.dialog("Adicionar militar", width="large")
def dialogo_novo():
    a, b, c = st.columns(3)
    nm, pt, nip = a.text_input("Nome de guerra"), b.text_input("Posto/Graduação"), c.text_input("NIP")
    a, b, c = st.columns(3)
    om, ant = a.text_input("OM (sigla/código)"), b.number_input("Antiguidade na escala (0 = no fim)", 0, 999, 0)
    em = c.text_input("E-mail")
    a, b = st.columns(2)
    ra, ce = a.text_input("Ramal"), b.text_input("Celular")
    ed_esc = [e.id for e in P.editaveis()]
    esc_id = st.selectbox("Escala que receberá o militar", ed_esc, format_func=lambda i: ctx.escala(i).nome) if ed_esc else ""
    if st.button("Adicionar", type="primary", use_container_width=True):
        def _novo():
            if not esc_id:
                raise ValueError("crie uma escala antes de adicionar militares")
            m = cd.adicionar_militar(ctx, nm, pt, nip, om, None, em, ra, ce)
            gestao.adicionar_militares(ctx, uid, esc_id, [m.id], date.today(), ant or None)
        agir(_novo, "Militar adicionado.")


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
        agir(lambda: gestao.adicionar_militares(ctx, uid, alvo, sel, data_v), "Militares adicionados à escala.")
    if c2.button("Encerrar na data"):
        agir(lambda: gestao.remover_militares(ctx, uid, alvo, sel, data_v), "Participação encerrada.")
    if c3.button("Remover de vez"):
        agir(lambda: gestao.remover_militares(ctx, uid, alvo, sel), "Militares removidos da escala.")


ui.cabecalho("Militares", "A antiguidade vale só dentro de cada escala; o cadastro (nome, NIP, contato) é um só.", "users",
             [ui.chip("Total", len(meus_mil))])
b1, b2, b3 = st.columns([1.1, 1.2, 4])
if b1.button("Adicionar", type="primary", icon=":material/person_add:"):
    dialogo_novo()
if b2.button("Vincular à escala", icon=":material/link:"):
    dialogo_vincular()
ed_ids = [e.id for e in P.editaveis()]
esc_sel = st.selectbox("Escala", ed_ids, format_func=lambda i: ctx.escala(i).nome, key="mil_escala") if ed_ids else ""
esc_obj = ctx.escala(esc_sel) if esc_sel else None
if esc_obj:
    meus_mil = [ctx.militar(i) for i in ctx.ordem_na_escala(esc_obj)]
if esc_obj and len(meus_mil) > 1:
    with st.expander("Mudar a antiguidade (arraste os nomes)", expanded=True, icon=":material/swap_vert:"):
        nova = ordem_interativa([{"id": m.id, "nome": m.nome, "posto": m.posto} for m in meus_mil],
                                key=f"ord_{esc_obj.id}")
        if nova:
            agir(lambda: gestao.definir_ordem_da_escala(ctx, uid, esc_obj.id, nova), "Antiguidade atualizada.")
busca = st.text_input("Buscar", placeholder="Nome, posto, NIP ou OM", label_visibility="collapsed", key="mil_busca")

linhas = [{"Excluir": False, "id": m.id, "Antiguidade": ctx.antig(esc_obj, m.id) if esc_obj else m.antiguidade, "Nome de guerra": m.nome, "Posto/Grad.": m.posto,
           "NIP": m.nip, "OM": m.om, "E-mail": m.email, "Ramal": m.ramal, "Celular": m.celular}
          for m in meus_mil
          if not busca or busca.lower() in f"{m.nome} {m.posto} {m.nip} {m.om}".lower()]
if not meus_mil:
    ui.vazio("Nenhum militar nas suas escalas", "Adicione militares ou importe uma planilha.", "users")
else:
    with st.container(border=True):
        ed = st.data_editor(pd.DataFrame(linhas), hide_index=True, width="stretch", disabled=["id", "Antiguidade"], key="mil_editor",
                            column_config={"id": None, "Excluir": st.column_config.CheckboxColumn(width="small"),
                                           "Antiguidade": st.column_config.NumberColumn("Nº na escala", width="small")})
        c1, c2, _ = st.columns([1, 2, 3])
        if c1.button("Salvar edições", type="primary", icon=":material/save:"):
            def _salvar():
                for _, r in ed.iterrows():
                    cd.editar_militar(ctx, r["id"], nome=r["Nome de guerra"], posto=r["Posto/Grad."] or "", nip=r["NIP"] or "",
                                      om=r["OM"] or "", email=r["E-mail"] or "", ramal=r["Ramal"] or "", celular=r["Celular"] or "")
            agir(_salvar, "Cadastro atualizado.")
        with c2.popover("Excluir marcados", icon=":material/delete:"):
            marcados = list(ed.loc[ed["Excluir"], "id"])
            st.warning(f"{len(marcados)} militar(es) marcado(s). Só é possível excluir quem está apenas nas suas escalas.")
            if marcados and st.button("Confirmar exclusão", key="mil_del"):
                agir(lambda: cd.excluir_militares(ctx, marcados, uid), "Militares excluídos.")

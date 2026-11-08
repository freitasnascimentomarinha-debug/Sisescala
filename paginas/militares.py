"""Militares de uma escala: cadastrar, incluir, reordenar a antiguidade, retirar da escala e excluir do cadastro."""
from datetime import date

import pandas as pd
import streamlit as st

from sisescala import cadastro as cd
from sisescala import gestao
from sisescala import ui
from sisescala.componente import ordem_interativa
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid = P.ctx, P.uid
admin = P.user.admin

ed_ids = [e.id for e in P.editaveis()]
ui.cabecalho("Militares", "Quem faz parte de cada escala, a ordem de antiguidade nela e os dados de cadastro.", "users")
if not ed_ids:
    ui.vazio("Você ainda não tem escala", "Crie uma escala em Escalas (ou importe uma planilha) para cadastrar militares nela.", "users")
    st.stop()

esc_id = st.selectbox("Escala", ed_ids, format_func=lambda i: ctx.escala(i).nome, key="mil_escala")
esc = ctx.escala(esc_id)
ctx.numerar_escala(esc)
membros = [ctx.militar(i) for i in ctx.ordem_na_escala(esc)]
st.caption(f"{len(membros)} militar(es) em {esc.nome}. A antiguidade vale só dentro desta escala: 1 é o mais antigo, "
           "o último é o mais moderno.")


def _de_outras_escalas() -> list[str]:
    """Militares já cadastrados que ainda não estão nesta escala (das minhas outras escalas; o administrador vê todos)."""
    aqui = {p.militar_id for p in esc.membros}
    if admin:
        return [m.id for m in ctx.militares if m.id not in aqui]
    return sorted({p.militar_id for e in P.editaveis() if e.id != esc_id for p in e.membros} - aqui)


@st.dialog("Cadastrar novo militar", width="large")
def dialogo_novo():
    st.caption(f"O militar é cadastrado e já entra na escala {esc.nome}.")
    a, b, c = st.columns(3)
    nm, pt, nip = a.text_input("Nome de guerra"), b.text_input("Posto/Graduação"), c.text_input("NIP")
    a, b, c = st.columns(3)
    om = a.text_input("OM (sigla/código)")
    pos = b.number_input("Posição na antiguidade", 0, len(membros) + 1, 0,
                         help="1 = o mais antigo da escala. Deixe 0 para entrar no fim da fila (o mais moderno).")
    em = c.text_input("E-mail")
    a, b = st.columns(2)
    ra, ce = a.text_input("Ramal"), b.text_input("Celular")
    st.caption("Só o nome é obrigatório. Posição: 1 = mais antigo · 0 = no fim (mais moderno).")
    if st.button("Cadastrar e incluir na escala", type="primary", use_container_width=True):
        def _novo():
            m = cd.adicionar_militar(ctx, nm, pt, nip, om, None, em, ra, ce)
            gestao.adicionar_militares(ctx, uid, esc_id, [m.id], date.today(), pos or None)
        agir(_novo, "Militar cadastrado e incluído na escala.")


@st.dialog("Incluir militar já cadastrado", width="large")
def dialogo_incluir():
    livres = _de_outras_escalas()
    if not livres:
        st.info("Não há outros militares cadastrados para incluir. Use **Cadastrar novo militar** ou importe uma planilha.")
        return
    st.caption(f"Escolha quem já está cadastrado (em outra escala sua) e quer entrar também em {esc.nome}.")
    nomes = {m.id: f"{m.posto} {m.nome}".strip() for m in ctx.militares}
    sel = st.multiselect("Militares", livres, format_func=nomes.get)
    a, b = st.columns(2)
    desde = a.date_input("Entra na escala em", date.today(), format="DD/MM/YYYY")
    pos = b.number_input("Posição na antiguidade", 0, len(membros) + len(sel) + 1, 0,
                         help="1 = o mais antigo da escala. Deixe 0 para entrar no fim da fila (o mais moderno).")
    if sel and st.button("Incluir na escala", type="primary", use_container_width=True):
        agir(lambda: gestao.adicionar_militares(ctx, uid, esc_id, sel, desde, pos or None), "Militares incluídos na escala.")


b1, b2, _ = st.columns([1.3, 1.6, 3])
if b1.button("Cadastrar novo", type="primary", icon=":material/person_add:"):
    dialogo_novo()
if b2.button("Incluir já cadastrado", icon=":material/group_add:"):
    dialogo_incluir()

if not membros:
    ui.vazio("Nenhum militar nesta escala", "Use Cadastrar novo, Incluir já cadastrado ou importe uma planilha.", "users")
    st.stop()

if len(membros) > 1:
    with st.expander("Mudar a antiguidade (arraste os nomes)", expanded=True, icon=":material/swap_vert:"):
        nova = ordem_interativa([{"id": m.id, "nome": m.nome, "posto": m.posto} for m in membros], key=f"ord_{esc_id}")
        if nova:
            agir(lambda: gestao.definir_ordem_da_escala(ctx, uid, esc_id, nova), "Antiguidade atualizada.")

busca = st.text_input("Buscar", placeholder="Nome, posto, NIP ou OM", label_visibility="collapsed", key="mil_busca")
linhas = [{"Marcar": False, "id": m.id, "Nº": ctx.antig(esc, m.id), "Nome de guerra": m.nome, "Posto/Grad.": m.posto,
           "NIP": m.nip, "OM": m.om, "E-mail": m.email, "Ramal": m.ramal, "Celular": m.celular}
          for m in membros if not busca or busca.lower() in f"{m.nome} {m.posto} {m.nip} {m.om}".lower()]
with st.container(border=True):
    ed = st.data_editor(pd.DataFrame(linhas), hide_index=True, width="stretch", disabled=["id", "Nº"], key="mil_editor",
                        column_config={"id": None, "Marcar": st.column_config.CheckboxColumn(width="small"),
                                       "Nº": st.column_config.NumberColumn("Antiguidade", width="small")})
    marcados = list(ed.loc[ed["Marcar"], "id"])
    c1, c2, c3, _ = st.columns([1.2, 1.4, 1.5, 1])
    if c1.button("Salvar dados", type="primary", icon=":material/save:"):
        def _salvar():
            for _, r in ed.iterrows():
                cd.editar_militar(ctx, r["id"], nome=r["Nome de guerra"], posto=r["Posto/Grad."] or "", nip=r["NIP"] or "",
                                  om=r["OM"] or "", email=r["E-mail"] or "", ramal=r["Ramal"] or "", celular=r["Celular"] or "")
        agir(_salvar, "Cadastro atualizado.")
    with c2.popover("Retirar da escala", icon=":material/person_remove:"):
        st.caption("Tira o militar só desta escala. Ele continua cadastrado e em outras escalas.")
        como = st.radio("Quando", ["agora", "data"], key="ret_como",
                        format_func={"agora": "Retirar agora", "data": "Retirar a partir de uma data (mudou de escala)"}.get)
        quando = st.date_input("A partir de", date.today(), format="DD/MM/YYYY", key="ret_data") if como == "data" else None
        st.write(f"{len(marcados)} militar(es) marcado(s).")
        if marcados and st.button("Confirmar retirada", key="ret_ok", type="primary"):
            agir(lambda: gestao.remover_militares(ctx, uid, esc_id, marcados, quando), "Militares retirados da escala.")
    with c3.popover("Excluir do cadastro", icon=":material/delete:"):
        st.warning(f"{len(marcados)} militar(es) marcado(s). Excluir apaga o militar do sistema todo (impedimentos, trocas, "
                   "escalas). Só é possível para quem está apenas nas suas escalas. **Tem certeza?**")
        if marcados and st.button("Sim, excluir do cadastro", key="mil_del"):
            agir(lambda: cd.excluir_militares(ctx, marcados, uid), "Militares excluídos.")

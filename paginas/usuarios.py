"""Administração de contas."""
import pandas as pd
import streamlit as st

from sisescala import auth, ui
from sisescala.sessao import agir, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
nomes_m = P.nomes_m
ui.cabecalho("Usuários", "Crie contas, redefina senhas e controle quem pode entrar.", "shield",
             [ui.chip("Contas", len(ctx.usuarios))])

with st.container(border=True):
    ctx.cadastro_aberto = st.toggle("Permitir que militares criem a própria conta (tela de login)", ctx.cadastro_aberto)
    st.caption("Conta nova não enxerga nenhuma escala até o detalhista compartilhar uma e aprovar o vínculo.")

with st.container(border=True):
    ui.secao("Contas")
    tab = [{"Login": u.login, "Nome": u.nome, "Perfil": u.perfil, "Admin": "sim" if u.admin else "",
            "Militar": nomes_m.get(u.militar_id, ""), "E-mail": u.email, "Ramal": u.ramal, "Celular": u.celular,
            "PIN": "sim" if u.pin_hash else "não", "Ativo": "sim" if u.ativo else "não",
            "Bloqueada até": f"{u.bloqueado_ate:%d/%m %H:%M}" if u.bloqueado_ate else ""} for u in ctx.usuarios]
    st.dataframe(pd.DataFrame(tab), hide_index=True, width="stretch")

esq, dir_ = st.columns(2, gap="large")
with esq, st.container(border=True):
    ui.secao("Nova conta")
    with st.form("novo_usuario", clear_on_submit=True, border=False):
        a, b = st.columns(2)
        lg, nm = a.text_input("Login"), b.text_input("Nome")
        sn = st.text_input("Senha provisória (8+)", type="password")
        a, b, c = st.columns(3)
        em, ra, ce = a.text_input("E-mail"), b.text_input("Ramal"), c.text_input("Celular")
        a, b = st.columns(2)
        perfil = a.selectbox("Perfil", list(auth.PERFIS), format_func=str.capitalize)
        sem_conta = [m.id for m in ctx.militares if not any(u.militar_id == m.id for u in ctx.usuarios)]
        mil = b.selectbox("Militar (vazio = a pessoa se vincula depois)", [""] + sem_conta, format_func=lambda i: nomes_m.get(i, "—"))
        adm = st.checkbox("Administrador")
        if st.form_submit_button("Criar conta", type="primary", use_container_width=True):
            try:
                auth.criar_usuario(ctx, uid, lg, nm, sn, perfil=perfil, militar_id=mil, admin=adm, email=em, ramal=ra,
                                   celular=ce, exigir_contato=True)
                st.session_state["toast"] = "Conta criada."
                st.rerun()
            except (ValueError, PermissionError) as ex:
                st.error(str(ex))
with dir_, st.container(border=True):
    ui.secao("Senha e situação da conta")
    alvo = st.selectbox("Conta", [u.id for u in ctx.usuarios],
                        format_func=lambda i: f"{ctx.usuario(i).login} – {ctx.usuario(i).nome}")
    nova = st.text_input("Nova senha (8+)", type="password", key="rs")
    c1, c2 = st.columns(2)
    if c1.button("Redefinir senha", type="primary"):
        agir(lambda: auth.redefinir_senha(ctx, uid, alvo, nova), "Senha redefinida.")
    ativo = ctx.usuario(alvo).ativo
    if c2.button("Desativar conta" if ativo else "Reativar conta"):
        agir(lambda: auth.definir_ativo(ctx, uid, alvo, not ativo), "Situação da conta atualizada.")

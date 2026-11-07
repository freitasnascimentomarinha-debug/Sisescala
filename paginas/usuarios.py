"""Administração de contas: aprovar cadastros, editar, bloquear/desbloquear, redefinir senha e excluir."""
import pandas as pd
import streamlit as st

from sisescala import auth, ui
from sisescala.sessao import agir, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
pend = auth.pendentes(ctx)
ui.cabecalho("Usuários", "Aprove cadastros e controle quem pode entrar no sistema.", "shield",
             [ui.chip("Contas", len(ctx.usuarios)), ui.chip("Pendentes", len(pend))])

with st.container(border=True):
    ctx.cadastro_aberto = st.toggle("Permitir que militares peçam cadastro (tela de login)", ctx.cadastro_aberto)
    st.caption("Todo cadastro novo fica pendente até você aprovar.")

with st.container(border=True):
    ui.secao("Cadastros aguardando aprovação")
    if not pend:
        ui.vazio("Nenhum cadastro pendente", "")
    for u in pend:
        c1, c2 = st.columns([3, 1.6])
        c1.html(ui.pessoa(u.nome, f"NIP {u.nip or u.login} · OM {u.om}", f"✉ {u.email} · ramal {u.ramal} · 📱 {u.celular}"))
        with c2:
            a, b = st.columns(2)
            if a.button("Aprovar", key=f"ap_{u.id}", type="primary", use_container_width=True):
                agir(lambda u=u: auth.aprovar_usuario(ctx, uid, u.id), "Cadastro aprovado.")
            if b.button("Rejeitar", key=f"rj_{u.id}", use_container_width=True):
                agir(lambda u=u: auth.rejeitar_usuario(ctx, uid, u.id), "Cadastro rejeitado.")

with st.container(border=True):
    ui.secao("Contas")
    tab = [{"NIP": u.nip or u.login, "Nome": u.nome, "OM": u.om, "Situação": u.situacao,
            "Admin": "sim" if u.admin else "", "E-mail": u.email, "Ramal": u.ramal, "Celular": u.celular,
            "PIN": "sim" if u.pin_hash else "não",
            "Bloqueada até": f"{u.bloqueado_ate:%d/%m %H:%M}" if u.bloqueado_ate else ""} for u in ctx.usuarios]
    st.dataframe(pd.DataFrame(tab), hide_index=True, width="stretch")

with st.container(border=True):
    ui.secao("Gerenciar uma conta")
    alvo_id = st.selectbox("Conta", [u.id for u in ctx.usuarios],
                           format_func=lambda i: f"{ctx.usuario(i).nip or ctx.usuario(i).login} – {ctx.usuario(i).nome}")
    al = ctx.usuario(alvo_id)
    esq, dir_ = st.columns(2, gap="large")
    with esq:
        with st.form(f"edit_{alvo_id}", border=False):
            a, b = st.columns(2)
            nip = a.text_input("NIP", al.nip or al.login)
            om = b.text_input("OM", al.om)
            nome = st.text_input("Nome", al.nome)
            a, b, c = st.columns(3)
            em, ra, ce = a.text_input("E-mail", al.email), b.text_input("Ramal", al.ramal), c.text_input("Celular", al.celular)
            adm = st.checkbox("Administrador", al.admin)
            if st.form_submit_button("Salvar alterações", type="primary", use_container_width=True):
                agir(lambda: auth.editar_usuario(ctx, uid, alvo_id, nome=nome, nip=nip, om=om, email=em, ramal=ra,
                                                 celular=ce, admin=adm), "Conta atualizada.")
    with dir_:
        if al.situacao == "bloqueado":
            if st.button("Desbloquear conta", type="primary", use_container_width=True):
                agir(lambda: auth.desbloquear_usuario(ctx, uid, alvo_id), "Conta desbloqueada.")
        elif al.situacao == "ativo":
            if st.button("Bloquear conta", use_container_width=True):
                agir(lambda: auth.bloquear_usuario(ctx, uid, alvo_id), "Conta bloqueada.")
        elif al.situacao in ("pendente", "rejeitado"):
            if st.button("Aprovar cadastro", type="primary", use_container_width=True):
                agir(lambda: auth.aprovar_usuario(ctx, uid, alvo_id), "Cadastro aprovado.")
        nova = st.text_input("Senha provisória (8+)", type="password", key=f"rs_{alvo_id}")
        if st.button("Redefinir senha", use_container_width=True):
            agir(lambda: auth.redefinir_senha(ctx, uid, alvo_id, nova), "Senha redefinida; a pessoa troca no próximo acesso.")
        with st.popover("Excluir conta", icon=":material/delete:", use_container_width=True):
            outros = [u.id for u in ctx.usuarios if u.id != alvo_id and u.ativo]
            donas = [e for e in ctx.escalas if e.dono_id == alvo_id]
            if donas:
                st.warning(f"Esta conta é detalhista de {len(donas)} escala(s). Passe-as a outra conta antes.")
                novo = st.selectbox("Passar as escalas para", outros, key=f"rt_{alvo_id}",
                                    format_func=lambda i: ctx.usuario(i).nome)
                if st.button("Reatribuir escalas", key=f"rb_{alvo_id}"):
                    agir(lambda: auth.reatribuir_escalas(ctx, uid, alvo_id, novo), "Escalas reatribuídas.")
            if st.button("Confirmar exclusão", key=f"ex_{alvo_id}", type="primary", disabled=bool(donas)):
                agir(lambda: auth.excluir_usuario(ctx, uid, alvo_id), "Conta excluída.")

"""Minha conta: contato, PIN e senha."""
import streamlit as st

from sisescala import auth, ui
from sisescala.sessao import agir, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
ui.cabecalho("Minha conta", f"NIP {user.login}" + (f" · {user.om}" if user.om else ""), "user",
             [ui.pill("PIN cadastrado", "verde") if user.pin_hash else ui.pill("Sem PIN", "vermelho")])

esq, dir_ = st.columns(2, gap="large")
with esq:
    with st.container(border=True):
        ui.secao("Contato")
        with st.form("meu_contato", border=False):
            em = st.text_input("E-mail", user.email)
            a, b = st.columns(2)
            ra, ce = a.text_input("Ramal", user.ramal), b.text_input("Celular", user.celular)
            if st.form_submit_button("Salvar contato", type="primary"):
                agir(lambda: auth.atualizar_contato(ctx, uid, em, ra, ce), "Contato atualizado.")
    with st.container(border=True):
        ui.secao("Senha")
        with st.form("minha_senha", clear_on_submit=True, border=False):
            sa, sn = st.text_input("Senha atual", type="password"), st.text_input("Nova senha (8+)", type="password")
            if st.form_submit_button("Trocar senha", type="primary"):
                agir(lambda: auth.trocar_senha(ctx, uid, sa, sn), "Senha alterada.")
with dir_:
    with st.container(border=True):
        ui.secao("PIN de assinatura")
        st.caption("O PIN (4 a 6 dígitos) confirma os pedidos de troca e devolução e assina as papeletas. "
                   "Fica guardado só como hash; 5 erros seguidos bloqueiam a conta por 5 minutos.")
        with st.form("meu_pin", clear_on_submit=True, border=False):
            ps = st.text_input("Senha da conta", type="password")
            pn = st.text_input("Novo PIN" if user.pin_hash else "PIN", type="password")
            if st.form_submit_button("Alterar PIN" if user.pin_hash else "Cadastrar PIN", type="primary"):
                agir(lambda: auth.alterar_pin(ctx, uid, ps, pn), "PIN salvo.")
    with st.container(border=True):
        ui.secao("Vínculo")
        if user.militar_id:
            m = ctx.militar(user.militar_id)
            st.html(ui.pessoa(m.rotulo, f"OM {m.om or '—'}", "", ui.pill("vinculado", "verde")))
        elif P.gerir:
            st.caption("Conta de gestão, sem vínculo com um militar.")
        else:
            st.page_link("paginas/vinculos.py", label="Vincular-me ao meu nome na escala", icon=":material/link:")

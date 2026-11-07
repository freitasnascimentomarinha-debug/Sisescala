"""O detalhista decide os pedidos de acesso às escalas dele."""
import streamlit as st

from sisescala import acessos as ac
from sisescala import ui
from sisescala.sessao import agir, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
pend = ac.pendentes_para(ctx, uid)
ui.cabecalho("Pedidos de acesso", "Quem pediu para ver as suas escalas.", "users",
             [ui.chip("Pendentes", len(pend))])
if not pend:
    ui.vazio("Nenhum pedido pendente", "")
for p in pend:
    ux, e = ctx.usuario(p.usuario_id), ctx.escala(p.escala_id)
    with st.container(border=True):
        c1, c2 = st.columns([3, 2])
        c1.html(ui.pessoa(ux.nome, f"NIP {ux.nip or ux.login} · OM {ux.om}", f"Escala: {e.nome} · {p.criado_em:%d/%m %H:%M}"))
        if p.mensagem:
            c1.caption(f"“{p.mensagem}”")
        with c2:
            if st.button("Aprovar (leitura)", key=f"a_{p.id}", type="primary", use_container_width=True):
                agir(lambda p=p: ac.aprovar(ctx, uid, p.id), "Acesso concedido.")
            motivo = st.text_input("Motivo da rejeição", key=f"mt_{p.id}")
            if st.button("Rejeitar", key=f"r_{p.id}", use_container_width=True):
                agir(lambda p=p, motivo=motivo: ac.rejeitar(ctx, uid, p.id, motivo), "Pedido rejeitado.")

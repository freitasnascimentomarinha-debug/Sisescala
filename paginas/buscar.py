"""Buscar escalas de outros detalhistas e pedir acesso."""
import streamlit as st

from sisescala import acessos as ac
from sisescala import ui
from sisescala.sessao import agir, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
ui.cabecalho("Buscar escalas", "Encontre a escala da sua OM e peça acesso ao detalhista.", "inbox")

termo = st.text_input("Buscar por nome da escala, tipo, OM ou detalhista", key="busca_termo")
achadas = ac.buscar(ctx, uid, termo)
if not achadas:
    ui.vazio("Nenhuma escala encontrada", "Só aparecem escalas que você ainda não enxerga.")
for e in achadas:
    with st.container(border=True):
        c1, c2 = st.columns([3, 1.4])
        c1.html(f'<b>{ui.esc(e.nome)}</b><br><small>{ui.esc(e.tipo)} · OM {ui.esc(e.om) or "—"} · '
                f'Detalhista: {ui.esc(ac.nome_do_detalhista(ctx, e))}</small>')
        if ac.pedido_pendente(ctx, uid, e.id):
            c2.html(ui.pill("Aguardando o detalhista", "ambar", False))
        else:
            with c2.popover("Pedir acesso", icon=":material/lock_open:", use_container_width=True):
                msg = st.text_area("Mensagem ao detalhista (opcional)", key=f"m_{e.id}")
                if st.button("Enviar pedido", key=f"p_{e.id}", type="primary"):
                    agir(lambda e=e, msg=msg: ac.pedir_acesso(ctx, uid, e.id, msg), "Pedido enviado ao detalhista.")

meus = ac.meus_pedidos(ctx, uid)
if meus:
    with st.container(border=True):
        ui.secao("Meus pedidos")
        tons = {"pendente": "ambar", "aprovado": "verde", "rejeitado": "vermelho", "cancelado": "cinza"}
        for p in meus:
            e = ctx.escala(p.escala_id)
            c1, c2 = st.columns([3, 1])
            extra = f" — {p.motivo_rejeicao}" if p.status == "rejeitado" and p.motivo_rejeicao else ""
            c1.markdown(f"**{e.nome if e else '(escala removida)'}** · {p.criado_em:%d/%m/%Y %H:%M}{extra}")
            c2.html(ui.pill(p.status.capitalize(), tons.get(p.status, "cinza"), False))
            if p.status == "pendente" and c2.button("Cancelar", key=f"c_{p.id}"):
                agir(lambda p=p: ac.cancelar(ctx, uid, p.id), "Pedido cancelado.")

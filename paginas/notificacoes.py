"""Notificações: avisos do sistema."""
import streamlit as st

from sisescala import notificacoes as nt
from sisescala import ui
from sisescala.sessao import pagina

P = pagina()
ctx, uid = P.ctx, P.uid
novas = nt.nao_lidas(ctx, uid)
ui.cabecalho("Notificações", "Pedidos, decisões, assinaturas e avisos das suas escalas.", "bell",
             [ui.pill(f"{novas} nova(s)", "azul")] if novas else None)
TIPO = {"papeleta": ("Papeleta", "violeta"), "disponibilidade": ("Disponibilidade", "verde"), "vinculo": ("Vínculo", "azul"),
        "devolucao": ("Devolução", "ambar")}
if novas and st.button("Marcar todas como lidas", icon=":material/done_all:"):
    nt.marcar_lidas(ctx, uid)
    st.rerun()
lista = nt.do_usuario(ctx, uid)[:60]
if not lista:
    ui.vazio("Nada por aqui", "Os avisos aparecem quando algo acontece nas suas escalas.", "bell")
else:
    with st.container(border=True):
        for n in lista:
            rot, tom = TIPO.get(n.tipo, (n.tipo.title(), "cinza"))
            st.html(f'<div class="item"><div class="tx" style="flex:1"><b style="font-weight:{700 if not n.lida else 500}">'
                    f'{ui.esc(n.texto)}</b><span>{n.criado_em:%d/%m/%Y %H:%M}</span></div>{ui.pill(rot, tom, False)}'
                    f'{ui.pill("novo", "azul") if not n.lida else ""}</div>')

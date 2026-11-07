"""Serviços a devolver: prazo, sugestões de dia e pedido de devolução."""
from datetime import date, datetime

import streamlit as st

from sisescala import papeletas as pp
from sisescala import ui
from sisescala.motor import gerar, respeita_descanso, sugerir_devolucao
from sisescala.sessao import agir, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
nomes_m = P.nomes_m
hoje = date.today()
ui.cabecalho("Devoluções", "Quem não deu um serviço devolve em outro dia, dentro do prazo, assumindo o serviço de um colega.", "undo",
             [ui.chip("Prazo", f"{ctx.janela_devolucao_dias} dias")])

esc_ids = {e.id for e in P.visiveis}
ed_ids = {e.id for e in P.editaveis()}
res_dev = gerar(ctx, max([ctx.data_base] + [d.prazo for d in P.res.devolucoes]))
meu_m = pp.militar_do_usuario(ctx, uid)
lista = [x for x in pp.devolucoes_em_aberto(ctx, res_dev, esc_ids)
         if x["devolucao"].militar_id == meu_m or x["devolucao"].escala_id in ed_ids]
if not lista:
    ui.vazio("Nenhum serviço a devolver", "Quando uma falta for lançada, ela aparece aqui com o prazo.", "check")

TOM = {"aberta": ("Aberta", "ambar"), "em_andamento": ("Em andamento", "azul"), "vencida": ("Prazo vencido", "vermelho")}
for x_ in lista:
    dv = x_["devolucao"]
    e_, mm = ctx.escala(dv.escala_id), ctx.militar(dv.militar_id)
    rot, tom = TOM[x_["estado"]]
    rest = x_["dias_restantes"]
    with st.container(border=True):
        st.html(f'<div style="display:flex;gap:.7rem;align-items:center;flex-wrap:wrap"><div style="font-weight:800;font-size:1.05rem;'
                f'color:#0F172A">{ui.esc(mm.nome)}</div>{ui.chip(e_.nome)}<div style="margin-left:auto">{ui.pill(rot, tom)}</div></div>')
        ui.campos([("Serviço não dado em", f"{dv.data_origem:%d/%m/%Y}"), ("Prazo para devolver", f"{dv.prazo:%d/%m/%Y}"),
                   ("Situação do prazo", f"vence em {rest} dia(s)" if rest >= 0 else f"vencido há {-rest} dia(s)")])
        if x_["estado"] == "em_andamento":
            p = x_["papeleta"]
            st.info(f"Devolução em andamento: papeleta {p.numero:04d} ({p.status}).")
            st.page_link("paginas/papeletas.py", label="Abrir a papeleta", icon=":material/swap_horiz:")
        elif x_["estado"] == "vencida":
            st.error("Prazo vencido. A decisão agora é do comando.")
        elif pp.pode_pedir_por(ctx, uid, e_.id, dv.militar_id):
            sug = sugerir_devolucao(ctx, res_dev, dv, exigir_descanso=False)[:10]
            if not sug:
                st.warning("Não há dia dentro do prazo em que o militar esteja livre e haja um colega de serviço.")
            else:
                chave = f"{e_.id}_{dv.militar_id}_{dv.data_origem}"
                opc = {f"{d_:%d/%m/%Y} · assume o serviço de {nomes_m[c_]}"
                       + ("" if respeita_descanso(res_dev, e_, dv.militar_id, d_) else "  ⚠ descanso curto"): (d_, c_)
                       for d_, c_ in sug}
                escolha = st.selectbox("Devolver em", list(opc), key=f"dvs_{chave}")
                c1, c2 = st.columns(2)
                mot_d = c1.text_input("Motivo (opcional)", key=f"dvm_{chave}")
                pin_d = c2.text_input("Seu PIN para confirmar", type="password", key=f"dvp_{chave}")
                if not user.pin_hash:
                    st.warning("Cadastre o seu PIN em Minha conta para pedir a devolução.")
                elif st.button("Pedir devolução", key=f"dvb_{chave}", type="primary"):
                    d2_, c2_ = opc[escolha]
                    agir(lambda: pp.criar_devolucao(ctx, uid, e_.id, dv.militar_id, dv.data_origem, c2_, d2_, mot_d,
                                                    datetime.now(), pin=pin_d), "Pedido de devolução criado.")

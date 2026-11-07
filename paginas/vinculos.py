"""Vínculos: o detalhista aprova quem é quem; o militar pede para se vincular ao seu nome."""
import streamlit as st

from sisescala import ui
from sisescala import vinculos as vc
from sisescala.sessao import agir, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
ui.cabecalho("Vínculos", "Liga a conta de um militar ao nome dele na escala.", "link",
             [ui.chip("Aguardando você", P.n_vinc)] if P.n_vinc else None)

if P.decide:
    with st.container(border=True):
        ui.secao("Pedidos aguardando decisão")
        st.caption("O militar criou a conta e pede para ser reconhecido como um militar de uma das suas escalas. Confira nome, "
                   "NIP e contato antes de aprovar. Para ele poder pedir, o detalhista compartilha a escala com o login dele (Gestão → Escalas).")
        fila = vc.pendentes_para(ctx, uid)
        if not fila:
            ui.vazio("Nenhum pedido pendente", "", "check")
        for v in fila:
            ux, mx = ctx.usuario(v.usuario_id), ctx.militar(v.militar_id)
            with st.container(border=True):
                c1, c2 = st.columns(2)
                c1.html(ui.pessoa(ux.nome, f"NIP {ux.login}", f"✉ {ux.email} · ramal {ux.ramal} · 📱 {ux.celular}",
                                  ui.pill("pediu", "ambar")))
                c2.html(ui.pessoa(mx.nome, f"{mx.posto} · NIP {mx.nip or '—'} · OM {mx.om or '—'}",
                                  f"Escala {ctx.escala(v.escala_id).nome}", ui.pill("persona", "azul")))
                st.caption(f"Pedido em {v.criado_em:%d/%m/%Y %H:%M}. O NIP foi conferido na solicitação.")
                k1, k2, _ = st.columns([1, 1, 2])
                if k1.button("Aprovar vínculo", key=f"va_{v.id}", type="primary", icon=":material/check:"):
                    agir(lambda: vc.aprovar(ctx, uid, v.id), "Vínculo aprovado.")
                with k2.popover("Rejeitar", icon=":material/close:"):
                    mrj = st.text_input("Motivo da rejeição", key=f"vrm_{v.id}")
                    if st.button("Confirmar rejeição", key=f"vr_{v.id}"):
                        agir(lambda: vc.rejeitar(ctx, uid, v.id, mrj), "Vínculo rejeitado.")
    with st.expander("Histórico de decisões"):
        dec = [v for v in ctx.vinculos if v.status != "pendente"]
        if not dec:
            st.caption("Sem decisões ainda.")
        for v in dec:
            st.write(f"{ctx.usuario(v.usuario_id).nome} → {ctx.militar(v.militar_id).nome}: **{v.status}**")

if not user.militar_id:
    with st.container(border=True):
        ui.secao("Vincular a minha conta ao meu nome na escala")
        meu = vc.pendente_do_usuario(ctx, uid)
        for v in [v for v in ctx.vinculos if v.usuario_id == uid and v.status == "rejeitado"][-1:]:
            st.error(f"Seu último pedido foi rejeitado: {v.motivo_rejeicao}")
        if meu:
            ui.linha_do_tempo(["Pedido enviado", "Decisão do detalhista", "Vinculado"], 1)
            st.info(f"Pedido enviado em {meu.criado_em:%d/%m/%Y %H:%M}: {ctx.militar(meu.militar_id).nome} em "
                    f"{ctx.escala(meu.escala_id).nome}. Aguardando o detalhista.")
            if st.button("Cancelar pedido de vínculo", icon=":material/block:"):
                agir(lambda: vc.cancelar(ctx, uid, meu.id), "Pedido cancelado.")
        elif not P.visiveis:
            ui.vazio("Sem acesso a escalas", f"Peça ao detalhista para compartilhar a escala com o seu login (NIP {user.login}).", "shield")
        else:
            ve = st.selectbox("Escala", [e.id for e in P.visiveis], format_func=lambda i: ctx.escala(i).nome)
            livres = vc.militares_livres(ctx, ve)
            vm = st.selectbox("Quem é você nesta escala?", livres,
                              format_func=lambda i: f"{ctx.militar(i).posto} {ctx.militar(i).nome}") if livres else None
            c1, c2, c3 = st.columns(3)
            vnip = c1.text_input("Seu NIP")
            vpin = c2.text_input("Crie um PIN (4 a 6 dígitos)", type="password")
            vpin2 = c3.text_input("Repita o PIN", type="password")
            st.caption("O PIN será usado para pedir trocas e assinar papeletas. O vínculo só vale depois que o detalhista aprovar.")
            if vm and st.button("Pedir vínculo", type="primary"):
                if vpin != vpin2:
                    st.error("Os PINs não são iguais.")
                else:
                    agir(lambda: vc.solicitar(ctx, uid, ve, vm, vnip, vpin), "Pedido de vínculo enviado.")
elif not P.decide:
    ui.vazio("Conta vinculada", f"Sua conta está vinculada a {ctx.militar(user.militar_id).nome}.", "check")

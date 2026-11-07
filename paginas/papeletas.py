"""Papeletas de troca e de devolução: acompanhamento, decisão e assinatura."""
import streamlit as st

from sisescala import papeletas as pp
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.pdf import pdf_papeleta
from sisescala.sessao import agir, contato, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
nomes_m, nomes_u = P.nomes_m, P.nomes_u
ui.cabecalho("Papeletas", "Pedidos de troca e de devolução de serviço, com decisão do detalhista e assinatura dos militares.",
             "swap", [ui.chip("Aguardando você", P.n_pend)] if P.n_pend else None)

FILTROS = {"Aguardando decisão": ("pendente",), "Em andamento": ("aprovada",), "Confirmadas": ("confirmada",),
           "Encerradas": ("rejeitada", "cancelada"), "Todas": ("pendente", "aprovada", "confirmada", "rejeitada", "cancelada")}
padrao = "Aguardando decisão" if P.n_pend else "Todas"
f = st.pills("Situação", list(FILTROS), default=padrao, key="pap_filtro") or "Todas"

lista = []
for e in P.visiveis:
    lista += pp.papeletas_visiveis(ctx, uid, e.id)
lista = sorted((p for p in lista if p.status in FILTROS[f]), key=lambda p: -p.numero)
if not lista:
    ui.vazio("Nenhuma papeleta aqui", "Peça uma troca na página Escala (clique no serviço do colega).", "swap")

TOM = {"pendente": ("Aguardando decisão", "ambar"), "aprovada": ("Aprovada · aguardando assinaturas", "azul"),
       "confirmada": ("Confirmada", "verde"), "rejeitada": ("Rejeitada", "vermelho"), "cancelada": ("Cancelada", "cinza")}


def _estagio(p):
    """(etapa atual, falhou) para a linha do tempo."""
    if p.status == "confirmada":
        return 4, False
    if p.status == "rejeitada":
        return 1, True
    if p.status == "cancelada":
        return (2 if p.decidido_em else 1), True
    if p.status == "aprovada":
        return (3 if not pp.faltam_assinar(ctx, p) else 2), False
    return 1, False


for p in lista:
    esc = ctx.escala(p.escala_id)
    x, y = ctx.militar(p.solicitante_id), ctx.militar(p.outro_id)
    eh_editor = pm.eh_detalhista(ctx, uid, esc)
    sou_parte = pp.e_parte(ctx, uid, p)
    rotulo, tom = TOM[p.status]
    tipo = "Devolução de serviço" if p.tipo == "devolucao" else "Troca de serviço"
    with st.container(border=True):
        st.html(f'<div style="display:flex;gap:.7rem;align-items:center;flex-wrap:wrap"><div style="font-weight:800;font-size:1.05rem;'
                f'color:var(--ink)">Papeleta nº {p.numero:04d}</div>{ui.chip(tipo)}{ui.chip(esc.nome)}'
                f'<div style="margin-left:auto">{ui.pill(rotulo, tom)}</div></div>')
        etapa, falhou = _estagio(p)
        ui.linha_do_tempo(["Pedido", "Decisão", "Assinaturas", "Confirmada"], etapa, falhou)
        if p.status == "aprovada":
            st.caption("A prévia já foi alterada. Falta cada parte assinar e o detalhista confirmar.")

        # --- as duas partes, com conta e assinatura
        c1, c2 = st.columns(2)
        sit = {s["militar"].id: s for s in pp.situacao_partes(ctx, p)}
        for col, m, papel in ((c1, x, "Quem pediu" if p.tipo == "troca" else "Quem devolve"),
                              (c2, y, "Troca com" if p.tipo == "troca" else "Serviço assumido de")):
            s_ = sit[m.id]
            if s_["assinou"]:
                selo = ui.pill(f"assinou {s_['em']:%d/%m %H:%M:%S}", "verde")
            elif p.status in pp.ABERTAS:
                selo = ui.pill("não assinou", "ambar")
            else:
                selo = ""
            conta = ("sem conta no sistema" if not s_["tem_conta"] else ("conta sem PIN" if not s_["tem_pin"] else "conta e PIN ok"))
            col.html(ui.pessoa(m.nome, f"{papel} · {m.posto} · NIP {m.nip or '—'}",
                               contato(ctx, m) + f" · {conta}", selo))
        ui.campos([("Serviço de " + x.nome, f"{p.data_solicitante:%d/%m/%Y}"), ("Serviço de " + y.nome, f"{p.data_outro:%d/%m/%Y}"),
                   ("Pedido em", f"{p.criado_em:%d/%m/%Y às %H:%M:%S}"),
                   ("Pedido por", nomes_u.get(p.criado_por, p.criado_por)), ("Motivo", p.motivo)])
        if p.motivo_rejeicao:
            st.error(f"Motivo da rejeição: {p.motivo_rejeicao}")

        # --- ações
        minha = pp.militar_do_usuario(ctx, uid)
        cols = iter(st.columns(4))
        if eh_editor and p.status == "pendente":
            if next(cols).button("Aprovar e trocar", key=f"ap_{p.id}", type="primary", icon=":material/check:", use_container_width=True):
                agir(lambda: pp.aprovar(ctx, uid, p.id), "Papeleta aprovada; troca aplicada na escala.")
            with next(cols).popover("Rejeitar", icon=":material/close:", use_container_width=True):
                rej = st.text_input("Motivo da rejeição", key=f"rjm_{p.id}")
                if st.button("Confirmar rejeição", key=f"rj_{p.id}"):
                    agir(lambda: pp.rejeitar(ctx, uid, p.id, rej), "Papeleta rejeitada.")
        if p.status in pp.ABERTAS and sou_parte and minha not in p.assinaturas:
            with next(cols).popover("Assinar com PIN", icon=":material/draw:", use_container_width=True):
                if not user.pin_hash:
                    st.warning("Cadastre o seu PIN em Minha conta para assinar.")
                pin_ass = st.text_input("Seu PIN", type="password", key=f"pin_{p.id}")
                st.caption("A data, a hora e o código do documento ficam registrados.")
                if st.button("Assinar", key=f"as_{p.id}", type="primary"):
                    agir(lambda: pp.assinar(ctx, p.id, uid, pin_ass), "Assinatura registrada.")
        if p.status == "pendente" and (sou_parte or p.criado_por == uid) and not eh_editor:
            if next(cols).button("Cancelar pedido", key=f"cp_{p.id}", icon=":material/block:", use_container_width=True):
                agir(lambda: pp.cancelar(ctx, uid, p.id, "cancelado pelo solicitante/parte"), "Pedido cancelado.")
        if eh_editor and p.status in pp.ABERTAS:
            with next(cols).popover("Assinatura externa", icon=":material/upload_file:", use_container_width=True):
                quem2 = st.selectbox("Militar", [p.solicitante_id, p.outro_id], format_func=nomes_m.get, key=f"exm_{p.id}")
                ref = st.text_input("Link ou nº do documento (gov.br, ICP, papel)", key=f"exr_{p.id}")
                if st.button("Registrar", key=f"ex_{p.id}"):
                    agir(lambda: pp.registrar_assinatura_externa(ctx, uid, p.id, quem2, ref), "Assinatura externa registrada.")
        if eh_editor and p.status == "aprovada":
            if next(cols).button("Confirmar", key=f"cf_{p.id}", type="primary", icon=":material/verified:", use_container_width=True):
                agir(lambda: pp.confirmar(ctx, uid, p.id), "Papeleta confirmada.")
        if eh_editor and p.status in ("aprovada", "confirmada"):
            with next(cols).popover("Cancelar troca", icon=":material/undo:", use_container_width=True):
                mcanc = st.text_input("Motivo do cancelamento", key=f"ccm_{p.id}")
                if st.button("Cancelar papeleta", key=f"cc_{p.id}"):
                    agir(lambda: pp.cancelar(ctx, uid, p.id, mcanc), "Papeleta cancelada; troca desfeita.")
        try:
            next(cols).download_button("PDF", pdf_papeleta(ctx, p), f"papeleta_{p.numero:04d}.pdf", "application/pdf",
                                       key=f"dl_{p.id}", icon=":material/download:", use_container_width=True)
        except StopIteration:
            st.download_button("Baixar PDF", pdf_papeleta(ctx, p), f"papeleta_{p.numero:04d}.pdf", "application/pdf",
                               key=f"dl_{p.id}", icon=":material/download:")
        with st.expander("Histórico"):
            for h in p.historico:
                st.html(f'<div class="item"><div class="tx"><b>{ui.esc(h[2])}</b><span>{h[0]:%d/%m/%Y %H:%M:%S}</span></div></div>')
st.caption("Assinatura pelo sistema: conta + PIN, com data, hora e código de verificação. Não substitui certificado "
           "ICP-Brasil; para isso o detalhista registra o documento assinado externamente.")

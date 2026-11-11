"""Assinar documentos: os detalhes de serviço que o detalhista enviou para assinatura das autoridades."""
import os
from datetime import datetime

import streamlit as st

from sisescala import assinaturas as asn
from sisescala import auth, textorico as tr, ui
from sisescala import verificacao as vf
from sisescala.pdf import renderizar_pdf
from sisescala.sessao import agir, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
pend = asn.para_assinar(ctx, uid)
ui.cabecalho("Assinar documentos", "Detalhes de serviço enviados para a assinatura das autoridades.", "file",
             [ui.chip("Aguardando você", len(pend))] if pend else None)


def _url_base() -> str:
    if os.environ.get("SISESCALA_URL"):
        return os.environ["SISESCALA_URL"]
    try:
        return str(st.context.url)
    except Exception:                                  # noqa: BLE001
        return ""


docs = asn.meus_documentos(ctx, uid)
if not docs:
    ui.vazio("Nenhum documento para você", "Quando o detalhista enviar um detalhe de serviço para assinatura (e você for o "
             "detalhista, o auxiliar, o encarregado ou o vice-diretor da escala), ele aparece aqui.", "inbox")
if not user.pin_hash and docs:
    st.warning("Você ainda não cadastrou o PIN. Cadastre em Minha conta para poder assinar.")
    st.page_link("paginas/conta.py", label="Cadastrar o PIN", icon=":material/key:")

pendentes_ids = {d.id: p for d, p in pend}
for d in docs:
    esc = ctx.escala(d.escala_id)
    conteudo = asn.conteudo(d)
    feitos = {a.papel: a for a in asn.assinaturas_do(ctx, d)}
    meus = asn.papeis_do_usuario(ctx, uid, esc)
    a_assinar = pendentes_ids.get(d.id, [])
    with st.container(border=True):
        ui.secao(f"{esc.nome} · {d.inicio:%d/%m} a {d.fim:%d/%m/%Y}")
        enviador = ctx.usuario(d.enviado_por)
        st.caption(f"Enviado por {enviador.nome if enviador else '—'} em {d.enviado_em:%d/%m/%Y às %H:%M}.")
        st.html('<div style="display:flex;flex-wrap:wrap;gap:.4rem;margin:.2rem 0 .6rem">' + "".join(
            ui.pill(f"{asn.ROTULO[p]} ✓ {feitos[p].nome}" if p in feitos else f"{asn.ROTULO[p]} · pendente",
                    "verde" if p in feitos else "ambar") for p in asn.PAPEIS) + "</div>")
        with st.expander("Conferir o conteúdo do documento"):
            linhas = "".join(
                f"<tr><td class='l'>{ln['data'][8:10]}/{ln['data'][5:7]}</td><td>"
                + ("<br>".join(ui.esc(x.lstrip('~')) for x in ln["efetivos"]) or "—") + "</td><td>"
                + ("<br>".join(ui.esc(x) for x in ln["retens"]) or "—") + "</td></tr>" if ln["funciona"] else
                f"<tr><td class='l'>{ln['data'][8:10]}/{ln['data'][5:7]}</td><td colspan=2><i>não guarnece</i></td></tr>"
                for ln in conteudo.get("linhas", []))
            st.html(f'<div style="overflow-x:auto"><table class="q"><tr><th>Dia</th><th>Escalados</th><th>Retém</th></tr>{linhas}</table></div>')
            for rot, txt in zip(("Instruções do serviço", "Recomendações", "Regras"), conteudo.get("textos", ["", "", ""])):
                if not tr.vazio(txt):
                    st.markdown(f"**{rot}**")
                    st.html(f'<div style="font-size:.85rem">{tr.para_html(txt)}</div>')
            for o in conteudo.get("obs", []):
                st.caption(o)
        carimbos = asn.carimbos(ctx, d, vf.url_de_verificacao(_url_base(), d.codigo)) if feitos else None
        c1, c2 = st.columns(2)
        c1.download_button("PDF sem assinatura", renderizar_pdf(conteudo, None, ctx), f"detalhe_{d.id}.pdf", "application/pdf",
                           icon=":material/download:", use_container_width=True, key=f"pdf0_{d.id}")
        if feitos:
            c2.download_button(f"PDF com as assinaturas já feitas ({len(feitos)} de 4)", renderizar_pdf(conteudo, carimbos, ctx),
                               f"detalhe_{d.id}_assinado.pdf", "application/pdf", icon=":material/verified:", type="primary",
                               use_container_width=True, key=f"pdf1_{d.id}")
        if a_assinar:
            papel = a_assinar[0]
            if len(a_assinar) > 1:
                papel = st.radio("Assinar como", a_assinar, format_func=asn.ROTULO.get, horizontal=True, key=f"as_p_{d.id}")
            pin = st.text_input("Seu PIN", type="password", key=f"as_pin_{d.id}")
            if st.button(f"Assinar como {asn.ROTULO[papel]}", key=f"as_ok_{d.id}", type="primary", icon=":material/draw:",
                         disabled=not user.pin_hash):
                agir(lambda d=d, papel=papel, pin=pin: asn.assinar(ctx, uid, d.id, papel, pin, agora=datetime.now()),
                     "Documento assinado.")
        elif meus:
            st.caption("Você já assinou este documento.")

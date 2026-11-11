"""Assinar documentos: os detalhes de serviço enviados para a assinatura das autoridades (assinar, rejeitar, acompanhar)."""
import os
from datetime import datetime

import streamlit as st

from sisescala import assinaturas as asn
from sisescala import textorico as tr, ui
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


todos = asn.todos_do_usuario(ctx, uid)
if not todos:
    ui.vazio("Nenhum documento para você", "Quando o detalhista enviar um detalhe de serviço para assinatura (e você for o "
             "detalhista, o auxiliar, o encarregado ou o vice-diretor), ele aparece aqui.", "inbox")
    st.stop()
if not user.pin_hash:
    st.warning("Você ainda não cadastrou o PIN. Cadastre em Minha conta para poder assinar.")
    st.page_link("paginas/conta.py", label="Cadastrar o PIN", icon=":material/key:")

pendentes_ids = {d.id: p for d, p in pend}
ENCERRADOS = ("cancelado", "rejeitado", "substituido")


def _assinei(d) -> bool:
    return any(a.usuario_id == uid for a in asn.assinaturas_do(ctx, d))


FILTROS = {"pend": "Aguardando minha assinatura", "assinei": "Assinados por mim", "completos": "Com as 4 assinaturas",
           "encerrados": "Cancelados / rejeitados", "todos": "Todos"}
padrao = "pend" if pend else "todos"
filtro = st.segmented_control("Mostrar", list(FILTROS), default=padrao, format_func=FILTROS.get, key="as_filtro") or padrao
nomes_docs = sorted({asn.nome_do_doc(ctx, d) for d in todos})
f2, f3 = st.columns(2)
doc_sel = f2.selectbox("Escala / documento", ["", *nomes_docs], format_func=lambda x: x or "Todos", key="as_doc")
busca = f3.text_input("Buscar", key="as_busca", placeholder="Título, data (ex.: 15/11) ou motivo")


def _casa(d) -> bool:
    if filtro == "pend" and not (d.id in pendentes_ids and d.status == "aberto"):
        return False
    if filtro == "assinei" and not _assinei(d):
        return False
    if filtro == "completos" and not (d.status == "aberto" and not asn.faltam(ctx, d)):
        return False
    if filtro == "encerrados" and d.status not in ENCERRADOS:
        return False
    if doc_sel and asn.nome_do_doc(ctx, d) != doc_sel:
        return False
    if busca.strip():
        alvo = f"{asn.nome_do_doc(ctx, d)} {d.inicio:%d/%m/%Y} {d.fim:%d/%m/%Y} {d.motivo}".lower()
        if busca.strip().lower() not in alvo:
            return False
    return True


docs = [d for d in todos if _casa(d)]
st.caption(f"{len(docs)} de {len(todos)} documento(s).")
if not docs:
    ui.vazio("Nada com esse filtro", "Mude o filtro acima para ver outros documentos.", "inbox")

for d in docs:
    esc = asn.fonte_do_doc(ctx, d)
    conteudo = asn.conteudo(d)
    feitos = {a.papel: a for a in asn.assinaturas_do(ctx, d)}
    meus = asn.papeis_do_usuario(ctx, uid, esc)
    a_assinar = pendentes_ids.get(d.id, []) if d.status == "aberto" else []
    with st.container(border=True):
        ui.secao(f"{esc.nome} · {d.inicio:%d/%m} a {d.fim:%d/%m/%Y}" + (" · documento unificado" if d.conjunto_id else ""))
        enviador = ctx.usuario(d.enviado_por)
        st.caption(f"Enviado por {enviador.nome if enviador else '—'} em {d.enviado_em:%d/%m/%Y às %H:%M}.")
        if d.status == "rejeitado":
            quem = ctx.usuario(d.encerrado_por)
            st.error(f"**Rejeitado** por {quem.nome if quem else '—'}"
                     + (f" em {d.encerrado_em:%d/%m/%Y %H:%M}" if d.encerrado_em else "") + f". Motivo: {d.motivo}")
        elif d.status == "cancelado":
            st.warning("**Envio cancelado** pelo detalhista. Este documento não vale mais.")
        elif d.status == "substituido":
            st.info("Substituído por uma versão mais nova. Esta não pode mais ser assinada.")
        if d.status == "aberto":
            st.html('<div style="display:flex;flex-wrap:wrap;gap:.4rem;margin:.2rem 0 .6rem">' + "".join(
                ui.pill(f"{asn.ROTULO[p]} ✓ {feitos[p].nome}" if p in feitos else f"{asn.ROTULO[p]} · pendente",
                        "verde" if p in feitos else "ambar") for p in asn.PAPEIS) + "</div>")
        with st.expander("Conferir o conteúdo do documento"):
            for sc in (conteudo.get("secoes") if conteudo.get("secoes") is not None else [{"nome": "", "linhas": conteudo.get("linhas", [])}]):
                if sc["nome"]:
                    st.markdown(f"**{sc['nome']}**")
                linhas = "".join(
                    f"<tr><td class='l'>{ln['data'][8:10]}/{ln['data'][5:7]}</td><td>"
                    + ("<br>".join(ui.esc(x.lstrip('~')) for x in ln["efetivos"]) or "—") + "</td><td>"
                    + ("<br>".join(ui.esc(x) for x in ln["retens"]) or "—") + "</td></tr>" if ln["funciona"] else
                    f"<tr><td class='l'>{ln['data'][8:10]}/{ln['data'][5:7]}</td><td colspan=2><i>não guarnece</i></td></tr>"
                    for ln in sc["linhas"])
                st.html(f'<div style="overflow-x:auto"><table class="q"><tr><th>Dia</th><th>Escalados</th><th>Retém</th></tr>{linhas}</table></div>')
            for rot, txt in zip(("Instruções do serviço", "Recomendações", "Regras"), conteudo.get("textos", ["", "", ""])):
                if not tr.vazio(txt):
                    st.markdown(f"**{rot}**")
                    st.html(f'<div style="font-size:.85rem">{tr.para_html(txt)}</div>')
            for o in conteudo.get("obs", []):
                st.caption(o)
        if d.status == "aberto":
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
        elif d.status == "aberto" and meus and _assinei(d):
            st.caption("Você já assinou este documento.")
        if d.status == "aberto" and meus and uid != d.enviado_por:
            with st.popover("Rejeitar este documento", icon=":material/block:"):
                st.write("O envio é encerrado e o detalhista recebe o seu motivo para corrigir e enviar de novo. "
                         "As assinaturas já feitas neste envio deixam de valer.")
                motivo = st.text_area("Motivo da rejeição (obrigatório)", key=f"rj_m_{d.id}", height=100)
                if st.button("Rejeitar documento", key=f"rj_ok_{d.id}", type="primary", disabled=len(motivo.strip()) < 5):
                    agir(lambda d=d, motivo=motivo: asn.rejeitar(ctx, uid, d.id, motivo), "Documento rejeitado; o detalhista foi avisado.")

"""Detalhe unificado: um só documento de serviço com várias escalas (fiscal, sentinela, contramestre...), com instruções,
recomendações e regras gerais, enviado para a assinatura das quatro autoridades."""
import os

import streamlit as st

from sisescala import assinaturas as asn
from sisescala import brasao as bs
from sisescala import conjuntos as cjs
from sisescala import textorico as tr
from sisescala import ui
from sisescala import verificacao as vf
from sisescala.componente import editor_texto
from sisescala.pdf import codigo_do_corpo, corpo_conjunto, gerar_pdf_conjunto, renderizar_pdf
from sisescala.sessao import agir, barra_contexto, pagina

P = pagina()
ctx, user, uid, res, dias = P.ctx, P.user, P.uid, P.res, P.dias
elegiveis = cjs.elegiveis(ctx, uid)
ui.cabecalho("Detalhe unificado", "Várias escalas num só documento de serviço, com as regras gerais e a assinatura das autoridades.",
             "file", [ui.chip("Período", f"{len(dias)} dia(s)")])
if not elegiveis:
    ui.vazio("Sem escalas para juntar", "Você precisa ser detalhista (ou auxiliar) de ao menos uma escala.", "calendar")
    st.stop()
barra_contexto(P, periodo=True, escala=False)


def _url_base() -> str:
    if os.environ.get("SISESCALA_URL"):
        return os.environ["SISESCALA_URL"]
    try:
        return str(st.context.url)
    except Exception:                                  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- escolha / criação do documento
meus = [c for c in ctx.conjuntos if c.dono_id == uid]
topo1, topo2 = st.columns([3, 1.4], vertical_alignment="bottom")
if meus:
    ids = [c.id for c in meus]
    if st.session_state.get("cj_sel") not in ids:
        st.session_state["cj_sel"] = ids[0]
    topo1.selectbox("Documento unificado", ids, format_func=lambda i: ctx.conjunto(i).nome, key="cj_sel")
with topo2.popover("Novo documento unificado", icon=":material/add:", use_container_width=True):
    novo_nome = st.text_input("Nome (título do documento)", key="cj_novo_nome", placeholder="Ex.: Escala de Serviço do Dia")
    marcar = st.multiselect("Escalas que ele reúne", [e.id for e in elegiveis], format_func=lambda i: ctx.escala(i).nome,
                            key="cj_novo_esc")
    if st.button("Criar", key="cj_criar", type="primary", disabled=not novo_nome.strip()):
        def _criar():
            c = cjs.criar(ctx, uid, novo_nome, marcar)
            st.session_state["cj_sel"] = c.id
        agir(_criar, "Documento criado.")
if not meus:
    ui.vazio("Nenhum documento unificado ainda",
             "Crie um (botão acima), escolha as escalas que ele reúne e defina as instruções e regras gerais. Depois é só enviar "
             "para assinatura todo dia ou a cada período.", "file")
    st.stop()

cj = ctx.conjunto(st.session_state["cj_sel"])
K = f"cj_{cj.id}_"
TEXTOS = {"ins": ("Instruções do serviço", "det_instrucoes"), "rec": ("Recomendações", "det_recomendacoes"),
          "reg": ("Regras gerais (horário de parada, acumulação de trabalho etc.)", "det_regras")}
for k, v in {"nome": cj.nome, "om": cj.om, "esc": cj.escala_ids, "a1": cj.ass_detalhista, "a4": cj.ass_auxiliar,
             "a2": cj.ass_encarregado, "a3": cj.ass_vice_diretor, "aux": cj.auxiliar_usuario_id,
             "enc": cj.encarregado_usuario_id, "vice": cj.vice_usuario_id}.items():
    st.session_state.setdefault(K + k, v)


def _abrir_editor(campo: str):
    titulo, atributo = TEXTOS[campo]

    @st.dialog(titulo, width="large")
    def _dialogo():
        r = editor_texto(tr.normalizar(getattr(cj, atributo)), key=f"{K}ed_{campo}")
        st.caption("Salvar grava o texto neste documento (sai em todos os envios).")
        if r and r.get("ts") != st.session_state.get(f"{K}ts_{campo}"):
            st.session_state[f"{K}ts_{campo}"] = r["ts"]
            novo = tr.normalizar(r["html"])
            agir(lambda: cjs.editar(ctx, uid, cj.id, **{atributo: novo}), f"{titulo.split(' (')[0]} salvo.")
    _dialogo()


esq, dir_ = st.columns([1.2, 1], gap="large")
with esq:
    with st.container(border=True):
        ui.secao("Documento")
        nome = st.text_input("Título do documento", key=K + "nome")
        om = st.text_input("OM (cabeçalho)", key=K + "om")
        escolhidas = st.multiselect("Escalas que o documento reúne (a ordem escolhida é a do documento)",
                                    [e.id for e in elegiveis], format_func=lambda i: ctx.escala(i).nome, key=K + "esc")
        _proprio = bs.bytes_de(cj.brasao_b64)
        cb1, cb2 = st.columns([1, 3])
        _padrao = ui.RAIZ / "assets" / "brasao.png"
        _prev = _proprio or (_padrao.read_bytes() if _padrao.exists() else None)
        if _prev:
            cb1.image(_prev, width=70)
        cb2.markdown("**Brasão:** " + ("o da OM (enviado por você)" if _proprio else "Armas Nacionais (padrão)"))
        arq = cb2.file_uploader("Trocar pelo brasão da sua OM (PNG ou JPG)", type=["png", "jpg", "jpeg"], key=K + "brasao")
        bb1, bb2 = cb2.columns(2)
        if bb1.button("Usar este brasão", key=K + "brasao_ok", disabled=arq is None, icon=":material/image:",
                      use_container_width=True):
            agir(lambda: cjs.editar(ctx, uid, cj.id, brasao_b64=bs.preparar(arq.getvalue())), "Brasão atualizado.")
        if _proprio and bb2.button("Voltar ao padrão", key=K + "brasao_rm", icon=":material/restart_alt:", use_container_width=True):
            agir(lambda: cjs.editar(ctx, uid, cj.id, brasao_b64=""), "Voltou ao brasão padrão.")
    with st.container(border=True):
        ui.secao("Instruções, recomendações e regras gerais")
        st.caption("Valem para o documento inteiro. Clique para escrever com negrito, itálico, sublinhado e listas.")
        for campo, (titulo, atributo) in TEXTOS.items():
            txt = getattr(cj, atributo)
            b, t = st.columns([1.5, 2], vertical_alignment="center")
            if b.button(titulo.split(" (")[0], key=f"{K}bt_{campo}", icon=":material/edit_note:", use_container_width=True, help=titulo):
                _abrir_editor(campo)
            t.caption(tr.resumo(txt) if not tr.vazio(txt) else "— vazio —")
    with st.container(border=True):
        ui.secao("Quem assina")
        st.caption("Você é o detalhista (responsável). Indique as **contas** do Auxiliar, do Encarregado do Detalhe e do "
                   "Vice-Diretor: elas recebem um aviso a cada envio e assinam em *Assinar documentos*. Cada uma precisa ter o "
                   "PIN cadastrado. Os nomes abaixo saem impressos no documento.")
        contas = [""] + [u.id for u in sorted(ctx.usuarios, key=lambda u: u.nome.lower()) if u.ativo]
        nome_conta = lambda i: "— ninguém —" if not i else f"{ctx.usuario(i).nome} · OM {ctx.usuario(i).om or '—'}"  # noqa: E731
        q1, q2, q3 = st.columns(3)
        aux_id = q1.selectbox("Auxiliar do Detalhista", contas, format_func=nome_conta, key=K + "aux")
        enc_id = q2.selectbox("Encarregado do Detalhe", contas, format_func=nome_conta, key=K + "enc")
        vice_id = q3.selectbox("Vice-Diretor", contas, format_func=nome_conta, key=K + "vice")
        n1, n4 = st.columns(2)
        n2, n3 = st.columns(2)
        nomes = (n1.text_input("Nome: Detalhista", key=K + "a1"), n4.text_input("Nome: Auxiliar do Detalhista", key=K + "a4"),
                 n2.text_input("Nome: Encarregado do Detalhe", key=K + "a2"), n3.text_input("Nome: Vice-Diretor", key=K + "a3"))
    salvo = (cj.nome, cj.om, cj.escala_ids, cj.ass_detalhista, cj.ass_auxiliar, cj.ass_encarregado, cj.ass_vice_diretor,
             cj.auxiliar_usuario_id, cj.encarregado_usuario_id, cj.vice_usuario_id)
    form = (nome.strip(), om.strip(), list(escolhidas), nomes[0], nomes[1], nomes[2], nomes[3], aux_id, enc_id, vice_id)
    pendente = salvo != form
    if st.button("Salvar documento", type="primary", icon=":material/save:", use_container_width=True, disabled=not pendente):
        def _salvar():
            c = cjs.editar(ctx, uid, cj.id, nome=nome, om=om.strip(), escala_ids=list(escolhidas), ass_detalhista=nomes[0],
                           ass_auxiliar=nomes[1], ass_encarregado=nomes[2], ass_vice_diretor=nomes[3])
            asn.designar_conjunto(ctx, uid, c, aux_id, enc_id, vice_id)
        agir(_salvar, "Documento salvo.")
    if pendente:
        st.warning("Há alterações não salvas. O PDF e o envio usam o que está salvo.")
    with st.popover("Excluir este documento", icon=":material/delete:"):
        st.write("O documento e os envios que ainda aguardam assinatura são cancelados. Os já assinados continuam verificáveis.")
        if st.button("Sim, excluir", key=K + "del", type="primary"):
            agir(lambda: (cjs.excluir(ctx, uid, cj.id), st.session_state.pop("cj_sel", None)), "Documento excluído.")

with dir_:
    with st.container(border=True):
        ui.secao("Resumo")
        faltam_esc = [i for i in cj.escala_ids if ctx.escala_ou_none(i) is None]
        if not cj.escala_ids:
            st.info("Escolha as escalas que o documento reúne e salve.")
        d0 = dias[0]
        linhas = ""
        for eid in cj.escala_ids:
            e = ctx.escala_ou_none(eid)
            if e is None:
                continue
            dia = res.dia(d0, e.id)
            ef = "<br>".join(ui.esc(ctx.militar(a.militar_id).nome) for a in dia.efetivos) if dia and dia.funciona else "—"
            rt = "<br>".join(ui.esc(ctx.militar(a.militar_id).nome) for a in dia.retens) if dia and dia.funciona else "—"
            linhas += f"<tr><td class='l'>{ui.esc(e.nome)}</td><td>{ef}</td><td>{rt}</td></tr>"
        if linhas:
            st.html(f'<div style="overflow-x:auto"><table class="q"><tr><th>Serviço</th><th>Efetivo ({d0:%d/%m})</th>'
                    f'<th>Retém</th></tr>{linhas}</table></div>')
        if len(dias) > 1:
            st.caption(f"O PDF traz os {len(dias)} dias de cada escala.")
        if faltam_esc:
            st.warning("Alguma escala deste documento foi apagada; salve para atualizar a lista.")
        corpo = corpo_conjunto(ctx, res, dias, cj)
        codigo = codigo_do_corpo(corpo)
        nome_arq = f"detalhe_unificado_{cj.id}_{dias[0]:%Y%m%d}"
        enviados = [d for d in ctx.detalhes_docs if d.conjunto_id == cj.id and d.status == "aberto"
                    and d.inicio == dias[0] and d.fim == dias[-1]]
        atual = next((d for d in enviados if d.codigo == codigo), None)
        st.download_button("PDF sem assinatura", gerar_pdf_conjunto(ctx, res, dias, cj), f"{nome_arq}.pdf", "application/pdf",
                           icon=":material/download:", use_container_width=True, type="secondary" if atual else "primary",
                           key="dl_cj_sem", disabled=not cj.escala_ids)
        ui.secao("Assinatura das autoridades")
        if atual:
            feitos = {a_.papel: a_ for a_ in asn.assinaturas_do(ctx, atual)}
            st.html('<div style="display:flex;flex-wrap:wrap;gap:.4rem;margin:.2rem 0 .6rem">' + "".join(
                ui.pill(f"{asn.ROTULO[p_]} ✓" if p_ in feitos else f"{asn.ROTULO[p_]} · pendente", "verde" if p_ in feitos else "ambar")
                for p_ in asn.PAPEIS) + "</div>")
            st.caption(f"Enviado em {atual.enviado_em:%d/%m/%Y %H:%M}. As autoridades assinam em **Documentos → Assinar documentos**.")
            if feitos:
                st.download_button(f"PDF com as assinaturas já feitas ({len(feitos)} de 4)",
                                   renderizar_pdf(asn.conteudo(atual), asn.carimbos(ctx, atual, vf.url_de_verificacao(_url_base(), atual.codigo)), ctx),
                                   f"{nome_arq}_assinado.pdf", "application/pdf", icon=":material/verified:", type="primary",
                                   use_container_width=True, key="dl_cj_com",
                                   help="Pode baixar a qualquer momento, mesmo que só algumas autoridades tenham assinado.")
            if st.button("Cancelar este envio", icon=":material/block:", key=f"{K}canc"):
                agir(lambda: asn.cancelar(ctx, uid, atual.id), "Envio cancelado.")
        else:
            if enviados:
                st.warning("O documento mudou depois do último envio. Envie de novo: as assinaturas da versão anterior não valem "
                           "para a nova.")
            st.caption("Envie para as autoridades assinarem. O conteúdo é congelado no envio: elas assinam exatamente o que está no PDF.")
            if st.button("Enviar para assinatura", icon=":material/send:", type="primary", use_container_width=True, key=f"{K}enviar",
                         disabled=pendente or not cj.escala_ids):
                agir(lambda: asn.enviar(ctx, uid, cj, dias, corpo, codigo), "Documento enviado para assinatura.")
            if pendente:
                st.caption("Salve as alterações para poder enviar.")
        if asn.papeis_do_usuario(ctx, uid, cj) and (atual or enviados):
            st.page_link("paginas/assinar.py", label="Assinar documentos", icon=":material/draw:", use_container_width=True)

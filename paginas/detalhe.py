"""Detalhe de serviço: monta o documento do período, com instruções e assinaturas."""
from datetime import datetime

import streamlit as st

import os

from sisescala import assinaturas as asn, brasao as bs, gestao, textorico as tr, ui, verificacao as vf
from sisescala.componente import editor_texto
from sisescala.modelos import rotulo_militar
from sisescala import permissoes as pm
from sisescala.permissoes import eh_detalhista
from sisescala.pdf import codigo_do_corpo, corpo_detalhe, gerar_pdf, renderizar_pdf
from sisescala.sessao import barra_contexto, agir, exigir_escala, pagina

P = pagina()
ctx, user, res, dias = P.ctx, P.user, P.res, P.dias
esc = exigir_escala(P)
ui.cabecalho("Detalhe de serviço", f"{esc.nome} · {dias[0]:%d/%m} a {dias[-1]:%d/%m/%Y}", "file",
             [ui.chip("Período", f"{len(dias)} dias")])

barra_contexto(P, periodo=True)
K = f"det_{esc.id}_"                  # chaves por escala: os campos nascem do que foi salvo na escala
CAMPOS = {"om": esc.om, "ins": tr.normalizar(esc.det_instrucoes), "rec": tr.normalizar(esc.det_recomendacoes),
          "reg": tr.normalizar(esc.det_regras), "a1": esc.ass_detalhista, "a4": esc.ass_auxiliar, "a2": esc.ass_encarregado, "a3": esc.ass_vice_diretor}
for k, v in CAMPOS.items():
    st.session_state.setdefault(K + k, v)  # mantém o que foi digitado ao navegar entre páginas
pode = eh_detalhista(ctx, P.uid, esc)
TEXTOS = {"ins": ("Instruções do serviço", "det_instrucoes"), "rec": ("Recomendações", "det_recomendacoes"),
          "reg": ("Regras (horário de parada, acumulação de trabalho etc.)", "det_regras")}


def _abrir_editor(campo: str):
    titulo, atributo = TEXTOS[campo]

    @st.dialog(titulo, width="large")
    def _dialogo():
        r = editor_texto(st.session_state[K + campo], key=f"{K}ed_{campo}")
        st.caption("Salvar grava o texto" + (" na escala (sai sempre no documento)." if pode else
                                             " só para esta sessão: apenas o detalhista grava na escala."))
        if r and r.get("ts") != st.session_state.get(f"{K}ts_{campo}"):
            st.session_state[f"{K}ts_{campo}"] = r["ts"]
            novo = tr.normalizar(r["html"])
            st.session_state[K + campo] = novo
            if pode:
                agir(lambda: gestao.editar_escala(ctx, P.uid, esc.id, **{atributo: novo}), f"{titulo.split(' (')[0]} salvo.")
            else:
                st.rerun()
    _dialogo()


def _url_base() -> str:
    """Endereço do app (para o QR code abrir a verificação): variável SISESCALA_URL ou o da própria página."""
    if os.environ.get("SISESCALA_URL"):
        return os.environ["SISESCALA_URL"]
    try:
        return str(st.context.url)
    except Exception:                                  # noqa: BLE001  (versões sem st.context.url)
        return ""


esq, dir_ = st.columns([1.2, 1], gap="large")
with esq:
    with st.container(border=True):
        ui.secao("Cabeçalho")
        om = st.text_input("OM que gerencia a escala (cabeçalho do documento)", key=K + "om")
        if not esc.om:
            st.caption("Dica: cadastre a OM em Gerenciar escalas para ela sair sempre no cabeçalho.")
        _proprio = bs.bytes_de(esc.brasao_b64)
        cb1, cb2 = st.columns([1, 3], vertical_alignment="top")
        _padrao = (ui.RAIZ / "assets" / "brasao.png")
        _prev = _proprio or (_padrao.read_bytes() if _padrao.exists() else None)
        if _prev:
            cb1.image(_prev, width=78)
        cb2.markdown("**Brasão do documento:** " + ("o brasão da OM (enviado por você)" if _proprio else "Armas Nacionais (padrão)"))
        if pode:
            arq = cb2.file_uploader("Trocar pelo brasão da sua OM (PNG ou JPG)", type=["png", "jpg", "jpeg"], key=K + "brasao",
                                    help="Sai centralizado acima de MARINHA DO BRASIL nos PDFs deste detalhe. Prefira PNG com fundo "
                                         "transparente.")
            outras = [e.id for e in ctx.escalas if e.id != esc.id and eh_detalhista(ctx, P.uid, e)]
            tambem = cb2.multiselect("Usar também nestes detalhes meus", outras, format_func=lambda i: ctx.escala(i).nome,
                                     key=K + "brasao_tb", placeholder="Só neste detalhe") if outras else []
            bb1, bb2 = cb2.columns(2)
            if bb1.button("Usar este brasão", key=K + "brasao_ok", disabled=arq is None, icon=":material/image:",
                          use_container_width=True):
                def _brasao():
                    novo_b64 = bs.preparar(arq.getvalue())
                    for eid in [esc.id, *tambem]:
                        gestao.editar_escala(ctx, P.uid, eid, brasao_b64=novo_b64)
                agir(_brasao, "Brasão atualizado.")
            if _proprio and bb2.button("Voltar ao padrão", key=K + "brasao_rm", icon=":material/restart_alt:",
                                       use_container_width=True):
                def _padrao_():
                    for eid in [esc.id, *tambem]:
                        gestao.editar_escala(ctx, P.uid, eid, brasao_b64="")
                agir(_padrao_, "Voltou ao brasão padrão (Armas Nacionais).")
        else:
            cb2.caption("Só o detalhista da escala troca o brasão.")
    with st.container(border=True):
        ui.secao("Textos do documento")
        st.caption("Clique para escrever com negrito, itálico, sublinhado e listas; o botão Salvar fica dentro da janela.")
        for campo, (titulo, _) in TEXTOS.items():
            txt = st.session_state[K + campo]
            b, t = st.columns([1.5, 2], vertical_alignment="center")
            if b.button(titulo.split(" (")[0], key=f"{K}bt_{campo}", icon=":material/edit_note:", use_container_width=True,
                        help=titulo):
                _abrir_editor(campo)
            t.caption(tr.resumo(txt) if not tr.vazio(txt) else "— vazio —")
    with st.container(border=True):
        ui.secao("Assinaturas")
        a1, a4 = st.columns(2)
        a2, a3 = st.columns(2)
        ass = (a1.text_input("Detalhista", key=K + "a1"), a4.text_input("Auxiliar do Detalhista", key=K + "a4"),
               a2.text_input("Encarregado do Detalhe", key=K + "a2"), a3.text_input("Vice-Diretor", key=K + "a3"))
    with st.container(border=True):
        ui.secao("Quem assina com PIN")
        st.caption("O detalhista (você) e o auxiliar do detalhista da escala assinam automaticamente. Indique as **contas** do "
                   "Encarregado do Detalhe e do Vice-Diretor: elas passam a ver este documento em *Assinar documentos* "
                   "e recebem um aviso a cada envio. Cada uma precisa ter o PIN cadastrado em Minha conta.")
        contas = [""] + [u.id for u in sorted(ctx.usuarios, key=lambda u: u.nome.lower()) if u.ativo]
        nome_conta = lambda i: "— ninguém (assina à mão) —" if not i else f"{ctx.usuario(i).nome} · OM {ctx.usuario(i).om or '—'}"  # noqa: E731
        q1, q2 = st.columns(2)
        enc_id = q1.selectbox("Encarregado do Detalhe", contas, contas.index(esc.encarregado_usuario_id)
                              if esc.encarregado_usuario_id in contas else 0, format_func=nome_conta, key=K + "enc", disabled=not pode)
        vice_id = q2.selectbox("Vice-Diretor", contas, contas.index(esc.vice_usuario_id) if esc.vice_usuario_id in contas else 0,
                               format_func=nome_conta, key=K + "vice", disabled=not pode)
        aux_nomes = [ctx.militar(m).nome for m in esc.auxiliares if ctx.militar(m)]
        st.caption("Auxiliar(es) do detalhista: " + (", ".join(aux_nomes) if aux_nomes else "nenhum (defina em Gerenciar escalas)"))
    ins, rec, reg = (st.session_state[K + c] for c in ("ins", "rec", "reg"))
    if st.button("Salvar OM, nomes e quem assina", type="primary", icon=":material/save:",
                 disabled=not pode, use_container_width=True,
                 help=None if pode else "Só o detalhista da escala salva estes dados."):
        def _salvar():
            asn.designar(ctx, P.uid, esc.id, enc_id, vice_id)
            gestao.editar_escala(ctx, P.uid, esc.id, om=om.strip(), ass_detalhista=ass[0], ass_auxiliar=ass[1],
                                 ass_encarregado=ass[2], ass_vice_diretor=ass[3])
        agir(_salvar, "Detalhe de serviço salvo.")
    st.caption("O que for salvo sai sempre preenchido no documento desta escala." if pode else
               "Somente o detalhista da escala pode salvar; você pode editar e gerar o PDF normalmente.")
with dir_:
    with st.container(border=True):
        ui.secao("Resumo do período")
        cab = "".join(f"<th>{d:%d/%m}<br><small>{'SEG TER QUA QUI SEX SÁB DOM'.split()[d.weekday()]}</small></th>" for d in dias[:10])
        ef, rt = "", ""
        for d in dias[:10]:
            dia = res.dia(d, esc.id)
            if not dia or not dia.funciona:
                ef += "<td class='para'>—</td>"
                rt += "<td class='para'>—</td>"
            else:
                ef += "<td>" + "<br>".join(ui.esc(ctx.militar(a.militar_id).nome) for a in dia.efetivos) + "</td>"
                rt += "<td>" + "<br>".join(ui.esc(ctx.militar(a.militar_id).nome) for a in dia.retens) + "</td>"
        st.html(f"""<div style="overflow-x:auto"><table class="q"><tr><th></th>{cab}</tr><tr><td class="l">Efetivo</td>{ef}</tr>
        <tr><td class="l">Retém</td>{rt}</tr></table></div>""")
        if len(dias) > 10:
            st.caption(f"Mostrando 10 de {len(dias)} dias; o PDF traz todos.")
        trocas = sum(1 for d in dias for a in (res.dia(d, esc.id).alocacoes if res.dia(d, esc.id) else []) if a.origem in ("tf", "t"))
        ui.campos([("Cabeçalho", f"MARINHA DO BRASIL · {om or '—'}"), ("Escala", esc.nome), ("Dias no documento", str(len(dias))), ("Trocas no período", str(trocas))])
        corpo = corpo_detalhe(ctx, res, dias, esc.id, om, ins, rec, reg, ass)
        codigo = codigo_do_corpo(corpo)
        nome_arq = f"detalhe_{esc.id}_{dias[0]:%Y%m%d}"
        enviados = [d for d in ctx.detalhes_docs if d.escala_id == esc.id and d.status == "aberto"
                    and d.inicio == dias[0] and d.fim == dias[-1]]
        atual = next((d for d in enviados if d.codigo == codigo), None)       # o enviado é igual ao que está na tela
        st.download_button("PDF sem assinatura", gerar_pdf(ctx, res, dias, esc.id, om, ins, rec, reg, ass),
                           f"{nome_arq}.pdf", "application/pdf", icon=":material/download:", use_container_width=True,
                           type="secondary" if atual else "primary", key="dl_det_sem")
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
                                   use_container_width=True, key="dl_det_com",
                                   help="Pode baixar a qualquer momento, mesmo que só algumas autoridades tenham assinado.")
            if pode and st.button("Cancelar este envio", icon=":material/block:", key=f"{K}canc"):
                agir(lambda: asn.cancelar(ctx, P.uid, atual.id), "Envio cancelado.")
        elif pode:
            enc_ = asn.encerrado_do_periodo(ctx, esc, dias)
            if enc_ and enc_.status == "rejeitado":
                quem_ = ctx.usuario(enc_.encerrado_por)
                st.error(f"**Rejeitado** por {quem_.nome if quem_ else '—'}" + (f" em {enc_.encerrado_em:%d/%m/%Y %H:%M}" if enc_.encerrado_em else "")
                         + f". Motivo: {enc_.motivo}. Corrija e envie de novo.")
            if enviados:
                st.warning("Você alterou o documento depois do último envio. Envie de novo: as assinaturas da versão anterior "
                           "não valem para a nova.")
            st.caption("Envie o documento para as autoridades assinarem. O conteúdo é congelado no envio: o que elas assinam é "
                       "exatamente o que está nesta tela agora.")
            if st.button("Enviar para assinatura", icon=":material/send:", type="primary", use_container_width=True,
                         key=f"{K}enviar"):
                def _enviar():
                    asn.enviar(ctx, P.uid, esc.id, dias, corpo, codigo)
                agir(_enviar, "Documento enviado para assinatura.")
        else:
            st.caption("Só o detalhista da escala envia o documento para assinatura.")
        if asn.papeis_do_usuario(ctx, P.uid, esc) and (atual or enviados):
            st.page_link("paginas/assinar.py", label="Assinar documentos", icon=":material/draw:", use_container_width=True)
        st.caption("Ajuste a escala e o período acima. O PDF inclui as observações de trocas e dispensas e as quatro assinaturas.")

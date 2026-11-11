"""Tela de verificação de documento (compartilhada): a página pública (sem login, aberta pelo QR code) mostra só o essencial; a
página dos usuários logados mostra também o conteúdo assinado, para comparar com o PDF."""
import streamlit as st

from sisescala import assinaturas as asn, textorico as tr, ui
from sisescala import verificacao as vf

MIN_PUBLICO = 16          # a consulta sem login exige mais caracteres do código (não dá para adivinhar)


def asn_nome_doc(a) -> str:
    import json
    try:
        return json.loads(asn.desempacotar(a.conteudo)).get("escala_nome", "") or a.escala_id
    except ValueError:
        return a.escala_id


def mostrar(ctx, completo: bool) -> None:
    ui.cabecalho("Verificar documento", "Confere a assinatura eletrônica num detalhe de serviço.", "shield")
    minimo = vf.MIN_PREFIXO if completo else MIN_PUBLICO
    with st.container(border=True):
        ui.secao("Código de verificação")
        st.caption("Leia o QR code do documento (abre esta página com o código já preenchido) ou digite o código SHA-256 do "
                   f"rodapé do PDF assinado. Pode ser o código inteiro ou o começo dele (mínimo de {minimo} caracteres).")
        inicial = st.query_params.get("codigo", "") if hasattr(st, "query_params") else ""
        codigo = st.text_input("Código", value=inicial, key="vf_codigo", placeholder="ex.: 3fa9c1…")
        a = vf.buscar(ctx, codigo, minimo) if codigo.strip() else None

        if not codigo.strip():
            ui.vazio("Informe o código", "Cole o código do documento para conferir.", "shield")
            return
        if a is None:
            st.error("Código não encontrado. Este documento não foi assinado eletronicamente neste sistema, o código está "
                     "incompleto ou errado, ou o documento é falso.")
            return
        if vf.integra(a):
            st.success("**Assinatura autêntica.** O código confere com o registro do sistema e o conteúdo gravado não foi alterado.")
        else:
            st.error("**Registro adulterado.** O conteúdo gravado não gera mais este código. Não confie neste documento.")
        nome_doc = asn_nome_doc(a)
        todas = vf.do_codigo(ctx, a.codigo)
        # sem login não se mostra o NIP (dado pessoal): só nome, papel e quando assinou
        ui.campos([(f"Assinado por ({asn.ROTULO.get(x.papel, x.papel)})",
                    f"{x.nome}" + (f" · NIP {x.nip}" if completo and x.nip else "") + f" · {x.em:%d/%m/%Y às %H:%M:%S}")
                   for x in todas] +
                  [("Documento", nome_doc), ("Período", f"{a.inicio:%d/%m/%Y} a {a.fim:%d/%m/%Y}"),
                   ("OM", a.om or "—"), ("Código completo", a.codigo)])
        if not completo:
            st.caption("Esta consulta é pública e mostra só o essencial. Quem tem acesso ao SisEscala vê também o conteúdo "
                       "assinado, em **Documentos → Verificar documento**.")
            return
        d = vf.descrever(ctx, a)
        with st.expander("O que foi assinado (compare com o PDF)", expanded=True):
            for nome_sc, dias_sc in d["secoes"]:
                if nome_sc:
                    st.markdown(f"**{nome_sc}**")
                linhas = "".join(
                    f"<tr><td class='l'>{dd[8:10]}/{dd[5:7]}</td><td>"
                    + ("<br>".join(ui.esc(x) for x in ef) or "—") + "</td><td>" + ("<br>".join(ui.esc(x) for x in rt) or "—") + "</td></tr>"
                    if fun else f"<tr><td class='l'>{dd[8:10]}/{dd[5:7]}</td><td colspan=2><i>não guarnece</i></td></tr>"
                    for dd, ef, rt, fun in dias_sc)
                st.html(f'<div style="overflow-x:auto"><table class="q"><tr><th>Dia</th><th>Escalados</th><th>Retém</th></tr>{linhas}</table></div>')
            for rot, txt in zip(("Instruções do serviço", "Recomendações", "Regras"), d["textos"]):
                if not tr.vazio(txt):
                    st.markdown(f"**{rot}**")
                    st.html(f'<div style="font-size:.9rem">{tr.para_html(txt)}</div>')
            for o in d["obs"]:
                st.caption(o)
        st.caption("A conferência prova que o código foi emitido por este sistema, por quem e quando. Para saber se o PDF em "
                   "mãos é o mesmo, compare o conteúdo acima com o documento.")

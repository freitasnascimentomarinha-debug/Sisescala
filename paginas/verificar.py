"""Verificar documento: confere o código (ou QR code) impresso no detalhe de serviço assinado pelo detalhista."""
import streamlit as st

from sisescala import textorico as tr, ui
from sisescala import verificacao as vf
from sisescala.sessao import pagina

P = pagina()
ctx = P.ctx
ui.cabecalho("Verificar documento", "Confere a assinatura eletrônica do detalhista num detalhe de serviço.", "shield")

with st.container(border=True):
    ui.secao("Código de verificação")
    st.caption("Digite o código SHA-256 que está no rodapé do PDF assinado (ou leia o QR code, que abre esta página com o "
               "código preenchido). Pode ser o código inteiro ou o começo dele (mínimo de 12 caracteres).")
    inicial = st.query_params.get("codigo", "") if hasattr(st, "query_params") else ""
    codigo = st.text_input("Código", value=inicial, key="vf_codigo", placeholder="ex.: 3fa9c1…")
    a = vf.buscar(ctx, codigo) if codigo.strip() else None

    if not codigo.strip():
        ui.vazio("Informe o código", "Cole o código do documento para conferir.", "shield")
    elif a is None:
        st.error("Código não encontrado. Este documento não foi assinado eletronicamente neste sistema, o código está "
                 "incompleto/errado ou o documento é falso.")
    else:
        ok = vf.integra(a)
        esc = ctx.escala(a.escala_id)
        if ok:
            st.success("**Assinatura autêntica.** O código confere com o registro do sistema e o conteúdo gravado não foi alterado.")
        else:
            st.error("**Registro adulterado.** O conteúdo gravado não gera mais este código. Não confie neste documento.")
        todas = vf.do_codigo(ctx, a.codigo)
        ui.campos([(f"Assinado por ({'Detalhista' if x.papel == 'detalhista' else 'Auxiliar do Detalhista'})",
                    f"{x.nome}" + (f" · NIP {x.nip}" if x.nip else "") + f" · {x.em:%d/%m/%Y às %H:%M:%S}") for x in todas] +
                  [("Escala", esc.nome if esc else a.escala_id), ("Período", f"{a.inicio:%d/%m/%Y} a {a.fim:%d/%m/%Y}"),
                   ("OM", a.om or "—"), ("Código completo", a.codigo)])
        d = vf.descrever(ctx, a)
        with st.expander("O que foi assinado (compare com o PDF)", expanded=True):
            linhas = "".join(
                f"<tr><td class='l'>{dd[8:10]}/{dd[5:7]}</td><td>{'<br>'.join(ui.esc(n + ' [' + s + ']') for n, s in itens) or '—'}</td></tr>"
                for dd, itens in d["dias"])
            st.html(f'<div style="overflow-x:auto"><table class="q"><tr><th>Dia</th><th>Escalados (efetivo e retém)</th></tr>{linhas}</table></div>')
            for rot, txt in zip(("Instruções do serviço", "Recomendações", "Regras"), d["textos"]):
                if not tr.vazio(txt):
                    st.markdown(f"**{rot}**")
                    st.html(f'<div style="font-size:.9rem">{tr.para_html(txt)}</div>')
        st.caption("A conferência prova que o código foi emitido por este sistema, por quem e quando. Para saber se o PDF em "
                   "mãos é o mesmo, compare o conteúdo acima com o documento.")

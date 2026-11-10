"""Detalhe de serviço: monta o documento do período, com instruções e assinaturas."""
import streamlit as st

from sisescala import gestao, ui
from sisescala.permissoes import eh_detalhista
from sisescala.pdf import gerar_pdf
from sisescala.sessao import barra_contexto, agir, exigir_escala, pagina

P = pagina()
ctx, res, dias = P.ctx, P.res, P.dias
esc = exigir_escala(P)
ui.cabecalho("Detalhe de serviço", f"{esc.nome} · {dias[0]:%d/%m} a {dias[-1]:%d/%m/%Y}", "file",
             [ui.chip("Período", f"{len(dias)} dias")])

barra_contexto(P, periodo=True)
K = f"det_{esc.id}_"                  # chaves por escala: os campos nascem do que foi salvo na escala
CAMPOS = {"om": esc.om, "ins": esc.det_instrucoes, "rec": esc.det_recomendacoes, "reg": esc.det_regras,
          "a1": esc.ass_detalhista, "a2": esc.ass_encarregado, "a3": esc.ass_vice_diretor}
for k, v in CAMPOS.items():
    st.session_state.setdefault(K + k, v)  # mantém o que foi digitado ao navegar entre páginas

esq, dir_ = st.columns([1.2, 1], gap="large")
with esq:
    with st.container(border=True):
        ui.secao("Cabeçalho e instruções")
        om = st.text_input("OM que gerencia a escala (cabeçalho do documento)", key=K + "om")
        if not esc.om:
            st.caption("Dica: cadastre a OM em Gerenciar escalas para ela sair sempre no cabeçalho.")
        ins = st.text_area("Instruções do serviço", key=K + "ins", height=120)
        rec = st.text_area("Recomendações", key=K + "rec", height=100)
        reg = st.text_area("Regras (horário de parada, acumulação de trabalho etc.)", key=K + "reg", height=100)
    with st.container(border=True):
        ui.secao("Assinaturas")
        a1, a2, a3 = st.columns(3)
        ass = (a1.text_input("Detalhista", key=K + "a1"), a2.text_input("Encarregado do Detalhe", key=K + "a2"),
               a3.text_input("Vice-Diretor", key=K + "a3"))
    pode = eh_detalhista(ctx, P.uid, esc)
    if st.button("Salvar OM, instruções, regras e assinaturas", type="primary", icon=":material/save:",
                 disabled=not pode, use_container_width=True,
                 help=None if pode else "Só o detalhista da escala salva estes dados."):
        agir(lambda: gestao.editar_escala(ctx, P.uid, esc.id, om=om.strip(), det_instrucoes=ins, det_recomendacoes=rec,
                                          det_regras=reg, ass_detalhista=ass[0], ass_encarregado=ass[1],
                                          ass_vice_diretor=ass[2]), "Detalhe de serviço salvo.")
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
        st.download_button("Gerar PDF do detalhe", gerar_pdf(ctx, res, dias, esc.id, om, ins, rec, reg, ass),
                           f"detalhe_{esc.id}_{dias[0]:%Y%m%d}.pdf", "application/pdf", type="primary",
                           icon=":material/download:", use_container_width=True)
        st.caption("Ajuste a escala e o período acima. O PDF inclui as observações de trocas e dispensas e as três assinaturas.")

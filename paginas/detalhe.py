"""Detalhe de serviço: monta o documento do período, com instruções e assinaturas."""
import streamlit as st

from sisescala import ui
from sisescala.pdf import gerar_pdf
from sisescala.sessao import barra_contexto, exigir_escala, pagina

P = pagina()
ctx, res, dias = P.ctx, P.res, P.dias
esc = exigir_escala(P)
ui.cabecalho("Detalhe de serviço", f"{esc.nome} · {dias[0]:%d/%m} a {dias[-1]:%d/%m/%Y}", "file",
             [ui.chip("Período", f"{len(dias)} dias")])

barra_contexto(P, periodo=True)
CAMPOS = ["det_om", "det_ins", "det_rec", "det_reg", "det_a1", "det_a2", "det_a3"]
for k in CAMPOS:                      # mantém o que foi digitado ao navegar entre páginas
    if k in st.session_state:
        st.session_state[k] = st.session_state[k]

esq, dir_ = st.columns([1.2, 1], gap="large")
with esq:
    with st.container(border=True):
        ui.secao("Cabeçalho e instruções")
        om = st.text_input("Organização Militar", key="det_om", placeholder="Ex.: Centro de Operações do Abastecimento")
        ins = st.text_area("Instruções do serviço", key="det_ins", height=120)
        rec = st.text_area("Recomendações", key="det_rec", height=100)
        reg = st.text_area("Regras (horário de parada, acumulação de trabalho etc.)", key="det_reg", height=100)
    with st.container(border=True):
        ui.secao("Assinaturas")
        a1, a2, a3 = st.columns(3)
        ass = (a1.text_input("Detalhista", key="det_a1"), a2.text_input("Encarregado do Detalhe", key="det_a2"),
               a3.text_input("Vice-Diretor", key="det_a3"))
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
        st.html(f"""<style>.q{{border-collapse:collapse;width:100%;font-size:.72rem}}.q th,.q td{{border:1px solid #E2E8F0;padding:5px;text-align:center}}
        .q th{{background:#F1F5F9;color:#334155}}.q .para{{color:#94A3B8}}.q td.l{{background:#F8FAFC;font-weight:700;text-align:left}}</style>
        <div style="overflow-x:auto"><table class="q"><tr><th></th>{cab}</tr><tr><td class="l">Efetivo</td>{ef}</tr>
        <tr><td class="l">Retém</td>{rt}</tr></table></div>""")
        if len(dias) > 10:
            st.caption(f"Mostrando 10 de {len(dias)} dias; o PDF traz todos.")
        trocas = sum(1 for d in dias for a in (res.dia(d, esc.id).alocacoes if res.dia(d, esc.id) else []) if a.origem in ("tf", "t"))
        ui.campos([("Escala", esc.nome), ("Dias no documento", str(len(dias))), ("Trocas no período", str(trocas))])
        st.download_button("Gerar PDF do detalhe", gerar_pdf(ctx, res, dias, esc.id, om, ins, rec, reg, ass),
                           f"detalhe_{esc.id}_{dias[0]:%Y%m%d}.pdf", "application/pdf", type="primary",
                           icon=":material/download:", use_container_width=True)
        st.caption("Ajuste o período na barra lateral. O PDF inclui as observações de troca e as três assinaturas.")

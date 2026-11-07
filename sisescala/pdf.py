"""PDF do detalhe de serviço: instruções, escalados, retém e assinaturas."""
from __future__ import annotations

from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .modelos import CATEGORIAS, Contexto, horarios_curtos
from .motor import Resultado

ASSINATURAS = ("Detalhista", "Encarregado do Detalhe", "Vice-Diretor")


def gerar_pdf(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
              instrucoes: str = "", recomendacoes: str = "", regras: str = "",
              nomes_assinantes: tuple[str, str, str] = ("", "", "")) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    st = getSampleStyleSheet()
    esc = ctx.escala(escala_id)
    cat = CATEGORIAS.get(esc.categoria, ("", ""))[0]
    el = [Paragraph(f"<b>DETALHE – {esc.nome.upper()}</b>{' – ' + om if om else ''}", st["Title"]),
          Paragraph(f"{cat}{' · ' + esc.tipo if esc.tipo else ''} · "
                    f"Período: {dias[0]:%d/%m/%Y} a {dias[-1]:%d/%m/%Y} · "
                    f"{esc.militares_dia} escalado(s) por dia · retém: {esc.retem_qtd}", st["Normal"]),
          Spacer(1, 6)]
    linhas = [["Data", "Escalados", "Retém"] + (["Evento"] if esc.modo == "eventos" else [])]
    obs: list[str] = []
    for d in dias:
        dia = res.dia(d, esc.id)
        dow = "SEG TER QUA QUI SEX SÁB DOM".split()[d.weekday()]
        if not dia or not dia.funciona:
            linhas.append([f"{d:%d/%m} {dow}", "não guarnece", "-"] + (["-"] if esc.modo == "eventos" else []))
            continue
        partes = []
        for a in dia.efetivos:
            h = f" ({horarios_curtos(a.horarios)})" if a.horarios else ""
            partes.append(f"{ctx.militar(a.militar_id).nome} [{a.sigla}]{h}")
            if a.obs and a.origem != "normal":
                obs.append(f"{d:%d/%m}: {a.obs}")
        rets = [f"{ctx.militar(a.militar_id).nome} [{a.sigla}]" for a in dia.retens]
        obs += [f"{d:%d/%m}: {a.obs}" for a in dia.retens if a.obs]
        lin = [f"{d:%d/%m} {dow}", Paragraph("<br/>".join(partes) or "-", st["BodyText"]),
               Paragraph("<br/>".join(rets) or "-", st["BodyText"])]
        if esc.modo == "eventos":
            lin.append(Paragraph(dia.descricao or "-", st["BodyText"]))
        linhas.append(lin)
    t = Table(linhas, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    el.append(t)
    for titulo, texto in (("Instruções do serviço", instrucoes), ("Recomendações", recomendacoes),
                          ("Regras (horário de parada, acumulação de trabalho etc.)", regras),
                          ("Observações (trocas e avanços)", "\n".join(dict.fromkeys(obs)))):
        if texto.strip():
            el += [Spacer(1, 8), Paragraph(f"<b>{titulo}</b>", st["Heading4"]),
                   Paragraph(texto.replace("\n", "<br/>"), st["BodyText"])]
    el.append(Spacer(1, 40))
    ass = Table([["_" * 32] * 3, [f"{nome or ''}" for nome in nomes_assinantes], list(ASSINATURAS)])
    ass.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    el.append(ass)
    doc.build(el)
    return buf.getvalue()

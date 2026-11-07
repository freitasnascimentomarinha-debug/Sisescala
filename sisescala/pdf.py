"""PDF do detalhe de serviço: instruções, escalados, retém e assinaturas."""
from __future__ import annotations

from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .modelos import Contexto
from .motor import Resultado

ASSINATURAS = ("Detalhista", "Encarregado do Detalhe", "Vice-Diretor")


def gerar_pdf(ctx: Contexto, res: Resultado, dias: list[date], om: str = "",
              instrucoes: str = "", recomendacoes: str = "", regras: str = "",
              nomes_assinantes: tuple[str, str, str] = ("", "", "")) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    st = getSampleStyleSheet()
    el = [Paragraph(f"<b>DETALHE DE SERVIÇO</b> – {om}", st["Title"]),
          Paragraph(f"Período: {dias[0]:%d/%m/%Y} a {dias[-1]:%d/%m/%Y}", st["Normal"]), Spacer(1, 6)]
    cab = ["Data"] + [e.nome for e in sorted(ctx.escalas, key=lambda e: -e.prioridade)] + ["Retém"]
    linhas = [cab]
    obs: list[str] = []
    for d in dias:
        lin = [f"{d:%d/%m} {'SEG TER QUA QUI SEX SÁB DOM'.split()[d.weekday()]}"]
        rets = []
        for e in sorted(ctx.escalas, key=lambda e: -e.prioridade):
            dia = res.dia(d, e.id)
            if not dia or not dia.funciona:
                lin.append("não guarnece")
                continue
            partes = []
            for a in dia.efetivos:
                if a.sigla == "Falta":
                    continue
                h = f" ({', '.join(a.horarios)})" if a.horarios else ""
                partes.append(f"{ctx.militar(a.militar_id).nome} [{a.sigla}]{h}")
                if a.obs and a.sigla != "SVÇ":
                    obs.append(f"{d:%d/%m}: {a.obs}")
            lin.append(Paragraph("<br/>".join(partes) or "-", st["BodyText"]))
            rets += [f"{ctx.militar(a.militar_id).nome} [{a.sigla}] ({e.sigla or e.nome})" for a in dia.retens]
            obs += [f"{d:%d/%m}: {a.obs}" for a in dia.retens if a.obs]
        lin.append(Paragraph("<br/>".join(rets) or "-", st["BodyText"]))
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

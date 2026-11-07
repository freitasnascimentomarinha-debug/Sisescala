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


def pdf_papeleta(ctx: Contexto, p, om: str = "", nomes_assinantes: tuple[str, str] = ("", "")) -> bytes:
    """Documento da papeleta de troca de serviço, para assinatura dos dois militares e do detalhista."""
    from .papeletas import hash_documento
    esc = ctx.escala(p.escala_id)
    x, y = ctx.militar(p.solicitante_id), ctx.militar(p.outro_id)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm)
    st = getSampleStyleSheet()
    P = lambda t, s="BodyText": Paragraph(t, st[s])  # noqa: E731
    dado = lambda m: f"{m.posto} {m.nome}".strip() + (f" – NIP {m.nip}" if m.nip else "")  # noqa: E731
    el = [P(f"<b>PAPELETA DE TROCA DE SERVIÇO Nº {p.numero:04d}</b>", "Title")]
    if om:
        el.append(P(om, "Heading3"))
    dados = [
        ["Escala", esc.nome + (f" ({esc.tipo})" if esc.tipo else "")],
        ["Pedido em", f"{p.criado_em:%d/%m/%Y} às {p.criado_em:%H:%M}"],
        ["Solicitante", dado(x)], ["Serviço do solicitante em", f"{p.data_solicitante:%d/%m/%Y}"],
        ["Troca com", dado(y)], ["Serviço do outro militar em", f"{p.data_outro:%d/%m/%Y}"],
        ["Motivo", p.motivo or "-"], ["Antecedência mínima da escala", f"{esc.antecedencia_horas}h"]]
    t = Table([[P(f"<b>{a}</b>"), P(b)] for a, b in dados], colWidths=[55 * mm, 115 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [Spacer(1, 6), t, Spacer(1, 10),
           P(f"Os militares abaixo concordam em permutar os serviços: {x.nome} dará o serviço do dia "
             f"{p.data_outro:%d/%m/%Y} e {y.nome} dará o serviço do dia {p.data_solicitante:%d/%m/%Y}, "
             f"ficando cientes de que a troca só vale após aprovação do Detalhista."),
           Spacer(1, 30)]
    def carimbo(mid):
        a = p.assinaturas.get(mid)
        if not a:
            return "_" * 30
        meio = "assinatura eletrônica" if a.metodo == "pin" else f"assinado externamente ({a.referencia})"
        return f"{meio}<br/>{a.em:%d/%m/%Y %H:%M}"
    cab = [[P(carimbo(p.solicitante_id)), P(carimbo(p.outro_id)), "_" * 30],
           [P(f"{nomes_assinantes[0] or dado(x)}<br/><b>Solicitante</b>"),
            P(f"{nomes_assinantes[1] or dado(y)}<br/><b>Militar permutante</b>"), P("<b>Detalhista</b>")]]
    ass = Table(cab, colWidths=[57 * mm] * 3)
    ass.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    el += [ass, Spacer(1, 18),
           P(f"<font size=7>Código de verificação (SHA-256): {hash_documento(ctx, p)}<br/>"
             f"Situação: {p.status.upper()}</font>")]
    doc.build(el)
    return buf.getvalue()

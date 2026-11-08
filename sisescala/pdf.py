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


def cabecalho_documento(st, om: str, titulo: str = "") -> list:
    """Cabeçalho oficial de todo documento: MARINHA DO BRASIL, a OM que gerencia a escala e o título."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import HRFlowable
    marinha = ParagraphStyle("marinha", parent=st["Normal"], alignment=1, fontSize=14, leading=17, fontName="Helvetica-Bold")
    orgao = ParagraphStyle("orgao", parent=st["Normal"], alignment=1, fontSize=11, leading=14)
    tit = ParagraphStyle("tit", parent=st["Normal"], alignment=1, fontSize=13, leading=16, fontName="Helvetica-Bold", spaceBefore=6)
    el = [Paragraph("MARINHA DO BRASIL", marinha)]
    if om.strip():
        el.append(Paragraph(om.strip().upper(), orgao))
    el.append(HRFlowable(width="100%", thickness=0.8, color=colors.black, spaceBefore=4, spaceAfter=4))
    if titulo:
        el.append(Paragraph(titulo, tit))
    return el


def gerar_pdf(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
              instrucoes: str = "", recomendacoes: str = "", regras: str = "",
              nomes_assinantes: tuple[str, str, str] = ("", "", "")) -> bytes:
    from reportlab.lib.styles import ParagraphStyle
    from .calendario import dia_util

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm)
    st = getSampleStyleSheet()
    esc = ctx.escala(escala_id)
    cat = CATEGORIAS.get(esc.categoria, ("", ""))[0]
    info = ParagraphStyle("info", parent=st["Normal"], alignment=1, fontSize=9.5, leading=12)
    cel = ParagraphStyle("cel", parent=st["Normal"], alignment=1, fontSize=8.5, leading=10.5)     # texto centralizado
    cab = ParagraphStyle("cab", parent=cel, fontName="Helvetica-Bold")
    eventos = esc.modo == "eventos"
    el = cabecalho_documento(st, om or esc.om, f"DETALHE DE SERVIÇO – {esc.nome.upper()}") + [
          Paragraph(f"{cat}{' · ' + esc.tipo if esc.tipo else ''} · "
                    f"Período: {dias[0]:%d/%m/%Y} a {dias[-1]:%d/%m/%Y} · "
                    f"{esc.militares_dia} escalado(s) por dia · retém: {esc.retem_qtd}", info),
          Spacer(1, 8)]
    linhas = [[Paragraph(t, cab) for t in ("Data", "Escalados", "Retém") + (("Evento",) if eventos else ())]]
    sombreados: list[int] = []
    obs: list[str] = []
    for d in dias:
        dia = res.dia(d, esc.id)
        dow = "SEG TER QUA QUI SEX SÁB DOM".split()[d.weekday()]
        data_cel = Paragraph(f"<b>{d:%d/%m}</b><br/>{dow}", cel)
        if not dia_util(d, ctx, esc):
            sombreados.append(len(linhas))                   # sáb, dom, feriado: fundo suave, como na prévia
        if not dia or not dia.funciona:
            linhas.append([data_cel, Paragraph("<i>não guarnece</i>", cel), Paragraph("-", cel)]
                          + ([Paragraph("-", cel)] if eventos else []))
            continue
        partes = []
        for a in dia.efetivos:
            h = f" ({horarios_curtos(a.horarios)})" if a.horarios else ""
            partes.append(f"{ctx.militar(a.militar_id).nome} [{a.sigla}]{h}")
            if a.obs and a.origem != "normal":
                obs.append(f"{d:%d/%m}: {a.obs}")
        for a in dia.alocacoes:                 # dispensado do serviço escalado: Disp + justificativa do detalhista
            if a.origem == "falta":
                partes.append(f"<i>{ctx.militar(a.militar_id).nome} [Disp]</i>")
                obs.append(f"{d:%d/%m}: {ctx.militar(a.militar_id).nome} – {a.obs}")
        rets = [f"{ctx.militar(a.militar_id).nome} [{a.sigla}]" for a in dia.retens]
        obs += [f"{d:%d/%m}: {a.obs}" for a in dia.retens if a.obs]
        lin = [data_cel, Paragraph("<br/>".join(partes) or "-", cel), Paragraph("<br/>".join(rets) or "-", cel)]
        if eventos:
            lin.append(Paragraph(dia.descricao or "-", cel))
        linhas.append(lin)
    # tabela mais estreita que as linhas de texto e centralizada no documento
    larguras = [18 * mm, 62 * mm, 38 * mm] + ([40 * mm] if eventos else [])
    t = Table(linhas, colWidths=larguras, repeatRows=1, hAlign="CENTER")
    estilo = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
              ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    estilo += [("BACKGROUND", (0, i), (-1, i), colors.Color(1, 0.94, 0.92)) for i in sombreados]
    t.setStyle(TableStyle(estilo))
    el.append(t)
    for i in ctx.impedimentos:                  # dispensas por período, com a justificativa
        if i.tipo in ("dispensa", "dispensa_justificada", "baixa") and i.motivo and any(i.cobre(d) for d in dias) \
                and any(p.militar_id == i.militar_id for p in esc.membros):
            fim = f"–{i.fim:%d/%m}" if i.fim else ""
            obs.append(f"{max(i.inicio, dias[0]):%d/%m}: {ctx.militar(i.militar_id).nome} – Dispensado ({i.inicio:%d/%m}{fim}): {i.motivo}")
    for titulo, texto in (("Instruções do serviço", instrucoes), ("Recomendações", recomendacoes),
                          ("Regras (horário de parada, acumulação de trabalho etc.)", regras),
                          ("Observações (trocas, dispensas e avanços)", "\n".join(dict.fromkeys(obs)))):
        if texto.strip():
            el += [Spacer(1, 8), Paragraph(f"<b>{titulo}</b>", st["Heading4"]),
                   Paragraph(texto.replace("\n", "<br/>"), st["BodyText"])]
    el.append(Spacer(1, 40))
    ass = Table([["_" * 26] * 3, [f"{nome or ''}" for nome in nomes_assinantes], list(ASSINATURAS)],
                colWidths=[57 * mm] * 3, hAlign="CENTER")
    ass.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    el.append(ass)
    doc.build(el)
    return buf.getvalue()


def pdf_papeleta(ctx: Contexto, p, om: str = "", nomes_assinantes: tuple[str, str] = ("", "")) -> bytes:
    """Documento da papeleta (troca ou devolução), com as assinaturas já feitas, data e hora."""
    from .papeletas import hash_documento
    esc = ctx.escala(p.escala_id)
    x, y = ctx.militar(p.solicitante_id), ctx.militar(p.outro_id)
    devolucao = p.tipo == "devolucao"
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm)
    st = getSampleStyleSheet()
    P = lambda t, s="BodyText": Paragraph(t, st[s])  # noqa: E731
    dado = lambda m: f"{m.posto} {m.nome}".strip() + (f" – NIP {m.nip}" if m.nip else "")  # noqa: E731
    titulo = "PAPELETA DE DEVOLUÇÃO DE SERVIÇO" if devolucao else "PAPELETA DE TROCA DE SERVIÇO"
    el = cabecalho_documento(st, om or esc.om, f"{titulo} Nº {p.numero:04d}")
    dados = [
        ["Escala", esc.nome + (f" ({esc.tipo})" if esc.tipo else "")],
        ["Pedido em", f"{p.criado_em:%d/%m/%Y} às {p.criado_em:%H:%M:%S}"],
        ["Solicitante", dado(x)],
        ["Dispensado do serviço de" if devolucao else "Serviço do solicitante em", f"{p.data_solicitante:%d/%m/%Y}"],
        ["Assume o serviço de" if devolucao else "Troca com", dado(y)],
        ["Data do serviço assumido" if devolucao else "Serviço do outro militar em", f"{p.data_outro:%d/%m/%Y}"],
        ["Motivo", p.motivo or "-"], ["Antecedência mínima da escala", f"{esc.antecedencia_horas}h"]]
    t = Table([[P(f"<b>{a}</b>"), P(b)] for a, b in dados], colWidths=[55 * mm, 115 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    if devolucao:
        texto = (f"{x.nome} devolve o serviço do qual foi dispensado em {p.data_solicitante:%d/%m/%Y}, assumindo o "
                 f"serviço de {y.nome} em {p.data_outro:%d/%m/%Y}, ciente de que a devolução só vale após a "
                 f"aprovação do Detalhista.")
    else:
        texto = (f"Os militares abaixo concordam em permutar os serviços: {x.nome} dará o serviço do dia "
                 f"{p.data_outro:%d/%m/%Y} e {y.nome} dará o serviço do dia {p.data_solicitante:%d/%m/%Y}, "
                 f"ficando cientes de que a troca só vale após aprovação do Detalhista.")
    el += [Spacer(1, 6), t, Spacer(1, 10), P(texto), Spacer(1, 24)]

    def carimbo(mid):
        a = p.assinaturas.get(mid)
        if not a:
            return "_" * 30 + "<br/><font size=7>(aguardando assinatura)</font>"
        m = ctx.militar(mid)
        meio = ("assinado eletronicamente com PIN" if a.metodo == "conta"
                else f"assinado externamente ({a.referencia})")
        return (f"{meio}<br/><b>{m.nome}</b>{' · NIP ' + m.nip if m.nip else ''}<br/>"
                f"em {a.em:%d/%m/%Y} às {a.em:%H:%M:%S}")
    decisao = ""
    if p.decidido_em and p.status != "pendente":
        det = ctx.usuario(p.decidido_por)
        decisao = (f"{p.status.upper()} por {det.nome if det else p.decidido_por} "
                   f"em {p.decidido_em:%d/%m/%Y} às {p.decidido_em:%H:%M:%S}")
    cab = [[P(carimbo(p.solicitante_id)), P(carimbo(p.outro_id)),
            P((decisao or "_" * 30) + "<br/><font size=7>(Detalhista)</font>")],
           [P(f"{nomes_assinantes[0] or dado(x)}<br/><b>Solicitante</b>"),
            P(f"{nomes_assinantes[1] or dado(y)}<br/><b>{'Colega' if devolucao else 'Militar permutante'}</b>"),
            P("<b>Detalhista</b>")]]
    ass = Table(cab, colWidths=[57 * mm] * 3)
    ass.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 8),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [ass, Spacer(1, 18),
           P(f"<font size=7>Código de verificação (SHA-256): {hash_documento(ctx, p)}<br/>"
             f"Situação: {p.status.upper()}</font>")]
    doc.build(el)
    return buf.getvalue()

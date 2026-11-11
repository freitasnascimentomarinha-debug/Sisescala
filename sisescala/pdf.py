"""PDF do detalhe de serviço: instruções, escalados, retém e assinaturas."""
from __future__ import annotations

from datetime import date
from html import escape as xml_escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .modelos import CATEGORIAS, Contexto, horarios_curtos, rotulo_militar
from .motor import Resultado

ASSINATURAS = ("Detalhista", "Encarregado do Detalhe", "Vice-Diretor")

# paleta institucional: azul-marinho, ouro e branco
NAVY, OURO, GELO, CINZA = "#0A2342", "#B8962E", "#EAF0F7", "#5B6573"
BRASAO = Path(__file__).resolve().parent.parent / "assets" / "brasao.png"     # Brasão de Armas (o arquivo oficial da OM)


def _cor(h: str):
    return colors.HexColor(h)


def brasao_flowable(ctx: Contexto | None = None, altura_mm: float = 19):
    """Brasão de Armas centralizado: o enviado pelo administrador (guardado no sistema) ou o arquivo assets/brasao.png;
    sem nenhum dos dois, nada (o cabeçalho segue igual)."""
    from .brasao import bytes_de
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    dados = bytes_de(getattr(ctx, "brasao_b64", "")) if ctx is not None else None
    if dados:
        fonte = BytesIO(dados)
    elif BRASAO.exists():
        fonte = str(BRASAO)
    else:
        return None
    w, h = ImageReader(fonte if isinstance(fonte, str) else BytesIO(dados)).getSize()
    img = Image(fonte if isinstance(fonte, str) else BytesIO(dados), width=altura_mm * mm * w / h, height=altura_mm * mm)
    img.hAlign = "CENTER"
    return img


def cabecalho_documento(st, om: str, titulo: str = "", ctx: Contexto | None = None) -> list:
    """Cabeçalho oficial, centralizado e em negrito: Brasão de Armas, MARINHA DO BRASIL, a OM, uma linha em branco e o título."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import HRFlowable
    marinha = ParagraphStyle("marinha", parent=st["Normal"], alignment=1, fontSize=14, leading=17, fontName="Helvetica-Bold",
                             textColor=_cor(NAVY))
    orgao = ParagraphStyle("orgao", parent=st["Normal"], alignment=1, fontSize=11, leading=14, fontName="Helvetica-Bold",
                           textColor=_cor(NAVY))
    tit = ParagraphStyle("tit", parent=st["Normal"], alignment=1, fontSize=13, leading=16, fontName="Helvetica-Bold",
                         textColor=_cor(NAVY))
    el = []
    if (b := brasao_flowable(ctx)) is not None:
        el += [b, Spacer(1, 3 * mm)]
    el.append(Paragraph("MARINHA DO BRASIL", marinha))
    if om.strip():
        el.append(Paragraph(xml_escape(om.strip().upper()), orgao))
    el.append(Spacer(1, 14))                                              # pula uma linha
    if titulo:
        el.append(Paragraph(titulo, tit))
    el.append(HRFlowable(width="100%", thickness=1.2, color=_cor(OURO), spaceBefore=5, spaceAfter=5))
    return el


def titulo_detalhe(nome_escala: str) -> str:
    """"DETALHE DE SERVIÇO DE <escala>", sem repetir quando o nome da escala já traz "Detalhe de serviço"."""
    import unicodedata
    plano = unicodedata.normalize("NFKD", nome_escala).encode("ascii", "ignore").decode().lower()
    n = xml_escape(nome_escala.strip().upper())
    return n if "detalhe de servic" in plano else f"DETALHE DE SERVIÇO DE {n}"


def corpo_detalhe(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
                  instrucoes: str = "", recomendacoes: str = "", regras: str = "",
                  nomes_assinantes: tuple[str, str, str] = ("", "", "")) -> str:
    """O conteúdo que a assinatura cobre, em JSON canônico: escala, período, OM, textos, assinantes e quem serve em cada dia."""
    import json
    esc = ctx.escala(escala_id)
    corpo = {"escala": esc.id, "escala_nome": esc.nome, "periodo": [dias[0].isoformat(), dias[-1].isoformat()],
             "om": om or esc.om, "textos": [instrucoes, recomendacoes, regras], "assinantes": list(nomes_assinantes),
             "dias": [[d.isoformat(), [(a.militar_id, a.sigla) for a in (res.dia(d, esc.id).alocacoes if res.dia(d, esc.id) else [])]]
                      for d in dias]}
    return json.dumps(corpo, sort_keys=True, ensure_ascii=False)


def codigo_do_corpo(corpo: str) -> str:
    import hashlib
    return hashlib.sha256(corpo.encode()).hexdigest()


def hash_detalhe(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
                 instrucoes: str = "", recomendacoes: str = "", regras: str = "",
                 nomes_assinantes: tuple[str, str, str] = ("", "", "")) -> str:
    """Código de verificação (SHA-256) do conteúdo do detalhe: muda se a escala, o período ou os textos mudarem."""
    return codigo_do_corpo(corpo_detalhe(ctx, res, dias, escala_id, om, instrucoes, recomendacoes, regras, nomes_assinantes))


def _qr(texto: str, lado_mm: float = 17):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    w = QrCodeWidget(texto, barLevel="M")
    x0, y0, x1, y1 = w.getBounds()
    lado = lado_mm * mm
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    d.add(w)
    return d


def gerar_pdf(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
              instrucoes: str = "", recomendacoes: str = "", regras: str = "",
              nomes_assinantes: tuple[str, str, str] = ("", "", ""), assinatura_detalhista: dict | None = None) -> bytes:
    """`assinatura_detalhista` ({nome, nip, em, hash, url}): carimba a assinatura eletrônica (PIN) do detalhista, com o
    código de verificação e o QR code que leva à página de verificação."""
    from reportlab.lib.styles import ParagraphStyle
    from .calendario import dia_util
    from .textorico import para_pdf, vazio

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=12 * mm, bottomMargin=16 * mm, title=f"Detalhe de serviço – {ctx.escala(escala_id).nome}",
                            author="SisEscala")
    st = getSampleStyleSheet()
    esc = ctx.escala(escala_id)
    cat = CATEGORIAS.get(esc.categoria, ("", ""))[0]
    info = ParagraphStyle("info", parent=st["Normal"], alignment=1, fontSize=9, leading=12, textColor=_cor(CINZA))
    cel = ParagraphStyle("cel", parent=st["Normal"], alignment=1, fontSize=8.5, leading=10.5)
    cab = ParagraphStyle("cab", parent=cel, fontName="Helvetica-Bold", textColor=colors.white)
    sec = ParagraphStyle("sec", parent=st["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=_cor(NAVY),
                         spaceBefore=9, spaceAfter=2)
    corpo_n = ParagraphStyle("corpo", parent=st["BodyText"], fontSize=9, leading=12)
    corpo_p = ParagraphStyle("corpop", parent=st["BodyText"], fontSize=7.5, leading=9.6, textColor=_cor("#2B3440"))   # letras pequenas
    eventos = esc.modo == "eventos"
    el = cabecalho_documento(st, om or esc.om, titulo_detalhe(esc.nome), ctx) + [
          Paragraph(f"{cat}{' · ' + esc.tipo if esc.tipo else ''} · "
                    f"Período: {dias[0]:%d/%m/%Y} a {dias[-1]:%d/%m/%Y} · "
                    f"{esc.militares_dia} escalado(s) por dia · retém: {esc.retem_qtd}", info),
          Spacer(1, 8)]
    linhas = [[Paragraph(t, cab) for t in ("Data", "Escalados", "Retém") + (("Evento",) if eventos else ())]]
    nao_uteis: list[int] = []
    obs: list[str] = []
    for d in dias:
        dia = res.dia(d, esc.id)
        dow = "SEG TER QUA QUI SEX SÁB DOM".split()[d.weekday()]
        data_cel = Paragraph(f"<b>{d:%d/%m}</b><br/>{dow}", cel)
        if not dia_util(d, ctx, esc):
            nao_uteis.append(len(linhas))                     # sáb, dom, feriado: fundo suave dourado
        if not dia or not dia.funciona:
            linhas.append([data_cel, Paragraph("<i>não guarnece</i>", cel), Paragraph("-", cel)]
                          + ([Paragraph("-", cel)] if eventos else []))
            continue
        partes = []
        for a in dia.efetivos:
            h = f" ({horarios_curtos(a.horarios)})" if a.horarios else ""
            partes.append(f"{xml_escape(rotulo_militar(ctx.militar(a.militar_id)))} [{a.sigla}]{h}")
            if a.obs and a.origem != "normal":
                obs.append(f"{d:%d/%m}: {xml_escape(a.obs)}")
        for a in dia.alocacoes:                 # dispensado do serviço escalado: Disp + justificativa do detalhista
            if a.origem == "falta":
                partes.append(f"<i>{xml_escape(rotulo_militar(ctx.militar(a.militar_id)))} [Disp]</i>")
                obs.append(f"{d:%d/%m}: {xml_escape(ctx.militar(a.militar_id).nome)} – {xml_escape(a.obs)}")
        rets = [f"{xml_escape(rotulo_militar(ctx.militar(a.militar_id)))} [{a.sigla}]" for a in dia.retens]
        obs += [f"{d:%d/%m}: {xml_escape(a.obs)}" for a in dia.retens if a.obs]
        lin = [data_cel, Paragraph("<br/>".join(partes) or "-", cel), Paragraph("<br/>".join(rets) or "-", cel)]
        if eventos:
            lin.append(Paragraph(xml_escape(dia.descricao or "-"), cel))
        linhas.append(lin)
    larguras = [17 * mm, 80 * mm, 52 * mm] + ([34 * mm] if eventos else [])
    t = Table(linhas, colWidths=larguras, repeatRows=1, hAlign="CENTER")
    estilo = [("BOX", (0, 0), (-1, -1), 0.8, _cor(NAVY)), ("INNERGRID", (0, 0), (-1, -1), 0.3, _cor("#B7C3D3")),
              ("BACKGROUND", (0, 0), (-1, 0), _cor(NAVY)), ("LINEBELOW", (0, 0), (-1, 0), 1.6, _cor(OURO)),
              ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]
    estilo += [("BACKGROUND", (0, i), (-1, i), _cor(GELO)) for i in range(2, len(linhas), 2)]            # zebra
    estilo += [("BACKGROUND", (0, i), (-1, i), _cor("#F6EBC8")) for i in nao_uteis]
    t.setStyle(TableStyle(estilo))
    el.append(t)
    for i in ctx.impedimentos:                  # dispensas por período, com a justificativa
        if i.tipo in ("dispensa", "dispensa_justificada", "baixa") and i.motivo and any(i.cobre(d) for d in dias) \
                and any(p.militar_id == i.militar_id for p in esc.membros):
            fim = f"–{i.fim:%d/%m}" if i.fim else ""
            obs.append(f"{max(i.inicio, dias[0]):%d/%m}: {xml_escape(ctx.militar(i.militar_id).nome)} – Dispensado "
                       f"({i.inicio:%d/%m}{fim}): {xml_escape(i.motivo)}")
    from reportlab.platypus import HRFlowable
    blocos = (("Instruções do serviço", instrucoes, corpo_p), ("Recomendações", recomendacoes, corpo_p),
              ("Regras (horário de parada, acumulação de trabalho etc.)", regras, corpo_p))
    for titulo, texto, estilo_txt in blocos:
        if not vazio(texto):
            el += [Paragraph(titulo, sec), HRFlowable(width="100%", thickness=0.5, color=_cor(OURO), spaceAfter=3),
                   Paragraph(para_pdf(texto), estilo_txt)]
    if obs:
        el += [Paragraph("Observações (trocas, dispensas e avanços)", sec),
               HRFlowable(width="100%", thickness=0.5, color=_cor(OURO), spaceAfter=3),
               Paragraph("<br/>".join(dict.fromkeys(obs)), corpo_p)]
    pequeno = ParagraphStyle("peq", alignment=1, leading=9, fontSize=7)
    linha_ass = "_" * 26
    if assinatura_detalhista:
        a = assinatura_detalhista
        texto = Paragraph(
            f"Assinado eletronicamente com PIN<br/><b>{xml_escape(a['nome'])}</b>"
            f"{' · NIP ' + xml_escape(a['nip']) if a.get('nip') else ''}<br/>em {a['em']:%d/%m/%Y} às {a['em']:%H:%M:%S}",
            pequeno)
        carimbo = Table([[_qr(a.get("url") or f"SISESCALA-VERIFICAR:{a['hash']}"), texto]], colWidths=[19 * mm, 38 * mm])
        carimbo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 1),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    else:
        carimbo = linha_ass
    ass = Table([[carimbo, linha_ass, linha_ass], [f"{nome or ''}" for nome in nomes_assinantes], list(ASSINATURAS)],
                colWidths=[57 * mm] * 3, hAlign="CENTER")
    ass.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                             ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("TEXTCOLOR", (0, 2), (-1, 2), _cor(NAVY)),
                             ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold")]))
    fecho = [Spacer(1, 12), ass]
    if assinatura_detalhista:
        fecho += [Spacer(1, 6), Paragraph(
            f"<font size=6.5 color='{CINZA}'>Código de verificação (SHA-256): {assinatura_detalhista['hash']}<br/>"
            f"Confira a autenticidade lendo o QR code ou na página “Verificar documento” do SisEscala (usuário logado).</font>",
            ParagraphStyle("hash", alignment=1, leading=8.5))]
    el.append(KeepTogether(fecho))

    def rodape(canvas, doc_):
        canvas.saveState()
        W, H = A4
        canvas.setFillColor(_cor(NAVY))
        canvas.rect(0, H - 4 * mm, W, 4 * mm, fill=1, stroke=0)
        canvas.setFillColor(_cor(OURO))
        canvas.rect(0, H - 4.9 * mm, W, 0.9 * mm, fill=1, stroke=0)
        canvas.setStrokeColor(_cor(OURO))
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, 11 * mm, W - 18 * mm, 11 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_cor(CINZA))
        canvas.drawString(18 * mm, 7 * mm, f"MARINHA DO BRASIL · {esc.nome}")
        canvas.drawRightString(W - 18 * mm, 7 * mm, f"Página {doc_.page}")
        canvas.restoreState()
    doc.build(el, onFirstPage=rodape, onLaterPages=rodape)
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
    dado = rotulo_militar
    titulo = "PAPELETA DE DEVOLUÇÃO DE SERVIÇO" if devolucao else "PAPELETA DE TROCA DE SERVIÇO"
    el = cabecalho_documento(st, om or esc.om, f"{titulo} Nº {p.numero:04d}", ctx)
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

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

ASSINATURAS = ("Detalhista", "Auxiliar do Detalhista", "Encarregado do Detalhe", "Vice-Diretor")
PAPEIS = ("detalhista", "auxiliar", "encarregado", "vice_diretor")      # quem assina eletronicamente (PIN), na ordem do documento


def nomes4(nomes) -> list[str]:
    """Nomes das quatro autoridades, na ordem do documento. Aceita a forma antiga de três (detalhista, encarregado, vice)."""
    n = list(nomes or [])
    if len(n) == 3:
        n = [n[0], "", n[1], n[2]]
    return (n + [""] * 4)[:4]

# paleta institucional: azul-marinho, ouro e branco
NAVY, OURO, GELO, CINZA = "#0A2342", "#B8962E", "#EAF0F7", "#5B6573"
BRASAO = Path(__file__).resolve().parent.parent / "assets" / "brasao.png"     # Brasão de Armas (o arquivo oficial da OM)


def _cor(h: str):
    return colors.HexColor(h)


def brasao_flowable(escala=None, altura_mm: float = 19):
    """Brasão centralizado acima de MARINHA DO BRASIL: o próprio da escala (enviado pelo detalhista, o brasão da OM dele) ou,
    na falta, as Armas Nacionais (assets/brasao.png). Sem nenhum dos dois, nada (o cabeçalho segue igual)."""
    from .brasao import bytes_de
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    dados = bytes_de(getattr(escala, "brasao_b64", "")) if escala is not None else None
    if dados:
        fonte = lambda: BytesIO(dados)                 # noqa: E731
    elif BRASAO.exists():
        fonte = lambda: str(BRASAO)                    # noqa: E731
    else:
        return None
    w, h = ImageReader(fonte()).getSize()
    img = Image(fonte(), width=altura_mm * mm * w / h, height=altura_mm * mm)
    img.hAlign = "CENTER"
    return img


def cabecalho_documento(st, om: str, titulo: str = "", escala=None) -> list:
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
    if (b := brasao_flowable(escala)) is not None:
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


def montar_snapshot(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
                    instrucoes: str = "", recomendacoes: str = "", regras: str = "",
                    nomes_assinantes: tuple = ("", "", "", "")) -> dict:
    """Tudo o que o PDF do detalhe mostra, já resolvido em texto (nomes, siglas, horários, observações). É esse conteúdo
    — e não os dados vivos da escala — que as autoridades assinam, e dele o PDF pode ser refeito a qualquer momento."""
    from .calendario import dia_util
    esc = ctx.escala(escala_id)
    cat = CATEGORIAS.get(esc.categoria, ("", ""))[0]
    obs: list[str] = []
    linhas = []
    for d in dias:
        dia = res.dia(d, esc.id)
        lin = {"data": d.isoformat(), "dow": "SEG TER QUA QUI SEX SÁB DOM".split()[d.weekday()],
               "util": bool(dia_util(d, ctx, esc)), "funciona": bool(dia and dia.funciona), "efetivos": [], "retens": [],
               "descricao": ""}
        if dia and dia.funciona:
            for a in dia.efetivos:
                h = f" ({horarios_curtos(a.horarios)})" if a.horarios else ""
                lin["efetivos"].append(f"{rotulo_militar(ctx.militar(a.militar_id))} [{a.sigla}]{h}")
                if a.obs and a.origem != "normal":
                    obs.append(f"{d:%d/%m}: {a.obs}")
            for a in dia.alocacoes:             # dispensado do serviço escalado: Disp + justificativa do detalhista
                if a.origem == "falta":
                    lin["efetivos"].append(f"~{rotulo_militar(ctx.militar(a.militar_id))} [Disp]")      # "~" = em itálico
                    obs.append(f"{d:%d/%m}: {ctx.militar(a.militar_id).nome} – {a.obs}")
            lin["retens"] = [f"{rotulo_militar(ctx.militar(a.militar_id))} [{a.sigla}]" for a in dia.retens]
            obs += [f"{d:%d/%m}: {a.obs}" for a in dia.retens if a.obs]
            lin["descricao"] = dia.descricao or ""
        linhas.append(lin)
    for i in ctx.impedimentos:                  # dispensas por período, com a justificativa
        if i.tipo in ("dispensa", "dispensa_justificada", "baixa") and i.motivo and any(i.cobre(d) for d in dias) \
                and any(p.militar_id == i.militar_id for p in esc.membros):
            fim = f"–{i.fim:%d/%m}" if i.fim else ""
            obs.append(f"{max(i.inicio, dias[0]):%d/%m}: {ctx.militar(i.militar_id).nome} – Dispensado "
                       f"({i.inicio:%d/%m}{fim}): {i.motivo}")
    return {"versao": 2, "escala_id": esc.id, "escala_nome": esc.nome, "om": om or esc.om,
            "titulo": titulo_detalhe(esc.nome),
            "subtitulo": f"{cat}{' · ' + esc.tipo if esc.tipo else ''} · Período: {dias[0]:%d/%m/%Y} a {dias[-1]:%d/%m/%Y} · "
                         f"{esc.militares_dia} escalado(s) por dia · retém: {esc.retem_qtd}",
            "periodo": [dias[0].isoformat(), dias[-1].isoformat()], "eventos": esc.modo == "eventos", "linhas": linhas,
            "textos": [instrucoes, recomendacoes, regras], "obs": list(dict.fromkeys(obs)), "nomes": nomes4(nomes_assinantes)}


def corpo_detalhe(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
                  instrucoes: str = "", recomendacoes: str = "", regras: str = "",
                  nomes_assinantes: tuple = ("", "", "", "")) -> str:
    """O conteúdo que a assinatura cobre, em JSON canônico (o `montar_snapshot` serializado)."""
    import json
    return json.dumps(montar_snapshot(ctx, res, dias, escala_id, om, instrucoes, recomendacoes, regras, nomes_assinantes),
                      sort_keys=True, ensure_ascii=False)


def codigo_do_corpo(corpo: str) -> str:
    import hashlib
    return hashlib.sha256(corpo.encode()).hexdigest()


def hash_detalhe(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
                 instrucoes: str = "", recomendacoes: str = "", regras: str = "",
                 nomes_assinantes: tuple = ("", "", "", "")) -> str:
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
              nomes_assinantes: tuple = ("", "", "", ""), assinaturas: dict | None = None) -> bytes:
    """PDF do detalhe a partir dos dados vivos da escala (ver `renderizar_pdf`)."""
    snap = montar_snapshot(ctx, res, dias, escala_id, om, instrucoes, recomendacoes, regras, nomes_assinantes)
    return renderizar_pdf(snap, assinaturas, ctx)


def renderizar_pdf(snap: dict, assinaturas: dict | None = None, ctx: Contexto | None = None) -> bytes:
    """PDF do detalhe a partir do `snap` (conteúdo congelado). `assinaturas`: {papel: {nome, nip, em}, "hash": código, "url": QR}
    com os papéis detalhista, auxiliar, encarregado e vice_diretor: cada autoridade que assinou com o PIN recebe o carimbo na sua
    posição; o código de verificação e o QR code saem uma vez, abaixo das assinaturas."""
    from datetime import date as _date
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import HRFlowable
    from .textorico import para_pdf, vazio

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=12 * mm, bottomMargin=16 * mm, title=f"Detalhe de serviço – {snap['escala_nome']}",
                            author="SisEscala")
    st = getSampleStyleSheet()
    info = ParagraphStyle("info", parent=st["Normal"], alignment=1, fontSize=9, leading=12, textColor=_cor(CINZA))
    cel = ParagraphStyle("cel", parent=st["Normal"], alignment=1, fontSize=8.5, leading=10.5)
    cab = ParagraphStyle("cab", parent=cel, fontName="Helvetica-Bold", textColor=colors.white)
    sec = ParagraphStyle("sec", parent=st["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=_cor(NAVY),
                         spaceBefore=9, spaceAfter=2)
    corpo_p = ParagraphStyle("corpop", parent=st["BodyText"], fontSize=7.5, leading=9.6, textColor=_cor("#2B3440"))   # letras pequenas
    eventos = snap["eventos"]
    el = cabecalho_documento(st, snap["om"], xml_escape(snap["titulo"]), ctx.escala(snap["escala_id"]) if ctx else None) + [Paragraph(xml_escape(snap["subtitulo"]), info),
                                                                                  Spacer(1, 8)]
    tabela = [[Paragraph(t, cab) for t in ("Data", "Escalados", "Retém") + (("Evento",) if eventos else ())]]
    nao_uteis: list[int] = []
    for ln in snap["linhas"]:
        d = _date.fromisoformat(ln["data"])
        data_cel = Paragraph(f"<b>{d:%d/%m}</b><br/>{ln['dow']}", cel)
        if not ln["util"]:
            nao_uteis.append(len(tabela))                     # sáb, dom, feriado: fundo suave dourado
        if not ln["funciona"]:
            tabela.append([data_cel, Paragraph("<i>não guarnece</i>", cel), Paragraph("-", cel)]
                          + ([Paragraph("-", cel)] if eventos else []))
            continue
        efet = [f"<i>{xml_escape(x[1:])}</i>" if x.startswith("~") else xml_escape(x) for x in ln["efetivos"]]
        lin = [data_cel, Paragraph("<br/>".join(efet) or "-", cel),
               Paragraph("<br/>".join(xml_escape(x) for x in ln["retens"]) or "-", cel)]
        if eventos:
            lin.append(Paragraph(xml_escape(ln["descricao"] or "-"), cel))
        tabela.append(lin)
    larguras = [17 * mm, 80 * mm, 52 * mm] + ([34 * mm] if eventos else [])
    t = Table(tabela, colWidths=larguras, repeatRows=1, hAlign="CENTER")
    estilo = [("BOX", (0, 0), (-1, -1), 0.8, _cor(NAVY)), ("INNERGRID", (0, 0), (-1, -1), 0.3, _cor("#B7C3D3")),
              ("BACKGROUND", (0, 0), (-1, 0), _cor(NAVY)), ("LINEBELOW", (0, 0), (-1, 0), 1.6, _cor(OURO)),
              ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]
    estilo += [("BACKGROUND", (0, i), (-1, i), _cor(GELO)) for i in range(2, len(tabela), 2)]            # zebra
    estilo += [("BACKGROUND", (0, i), (-1, i), _cor("#F6EBC8")) for i in nao_uteis]
    t.setStyle(TableStyle(estilo))
    el.append(t)
    blocos = (("Instruções do serviço", snap["textos"][0]), ("Recomendações", snap["textos"][1]),
              ("Regras (horário de parada, acumulação de trabalho etc.)", snap["textos"][2]))
    for titulo, texto in blocos:
        if not vazio(texto):
            el += [Paragraph(titulo, sec), HRFlowable(width="100%", thickness=0.5, color=_cor(OURO), spaceAfter=3),
                   Paragraph(para_pdf(texto), corpo_p)]
    if snap["obs"]:
        el += [Paragraph("Observações (trocas, dispensas e avanços)", sec),
               HRFlowable(width="100%", thickness=0.5, color=_cor(OURO), spaceAfter=3),
               Paragraph("<br/>".join(xml_escape(o) for o in snap["obs"]), corpo_p)]

    # ---- assinaturas: detalhista, auxiliar e encarregado em linha; o vice-diretor centralizado abaixo
    pequeno = ParagraphStyle("peq", alignment=1, leading=6.6, fontSize=5.6)
    ass_ = assinaturas or {}
    nomes = snap["nomes"]

    assinados = [p_ for p_ in PAPEIS if ass_.get(p_)]
    qr_ao_lado = len(assinados) == 1 and bool(ass_.get("hash"))          # uma só assinatura: o QR fica do lado do carimbo
    url_qr = ass_.get("url") or f"SISESCALA-VERIFICAR:{ass_.get('hash', '')}"

    def carimbo(papel):
        a = ass_.get(papel)
        if not a:
            return "_" * 26
        texto = Paragraph(f"Assinado eletronicamente com PIN<br/><b>{xml_escape(a['nome'].upper())}</b>"
                          f"<br/>{'NIP ' + xml_escape(a['nip']) + ' · ' if a.get('nip') else ''}{a['em']:%d/%m/%Y %H:%M:%S} (Brasília)",
                          pequeno)
        if not (qr_ao_lado and papel == assinados[0]):
            return texto
        t_ = Table([[_qr(url_qr, 14), texto]], colWidths=[15 * mm, 43 * mm])
        t_.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return t_

    def bloco(papeis, rotulos, nomes_, largura):
        tb = Table([[carimbo(p_) for p_ in papeis], [xml_escape(n) for n in nomes_], list(rotulos)],
                   colWidths=[largura] * len(papeis), hAlign="CENTER")
        tb.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("TEXTCOLOR", (0, 2), (-1, 2), _cor(NAVY)),
                                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"), ("FONTSIZE", (0, 2), (-1, 2), 7.5)]))
        return tb
    fecho = [Spacer(1, 16), bloco(PAPEIS[:3], ASSINATURAS[:3], nomes[:3], 58 * mm), Spacer(1, 14),
             bloco(PAPEIS[3:], ASSINATURAS[3:], nomes[3:], 58 * mm)]
    if ass_.get("hash"):
        txt = Paragraph(
            f"<font size=6.5 color='{CINZA}'><b>Código de verificação (SHA-256):</b><br/>{ass_['hash']}<br/>"
            f"Confira a autenticidade lendo o QR code ou na página “Verificar documento” do SisEscala (não precisa de login).</font>",
            ParagraphStyle("hash", alignment=0 if not qr_ao_lado else 1, leading=8.5))
        if qr_ao_lado:                                       # o QR já está do lado do carimbo: só o código, centralizado
            fecho += [Spacer(1, 10), txt]
        else:
            selo = Table([[_qr(url_qr), txt]], colWidths=[19 * mm, 110 * mm], hAlign="CENTER")
            selo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 1)]))
            fecho += [Spacer(1, 10), selo]
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
        canvas.drawString(18 * mm, 7 * mm, f"MARINHA DO BRASIL · {snap['escala_nome']}")
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
    el = cabecalho_documento(st, om or esc.om, f"{titulo} Nº {p.numero:04d}", esc)
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

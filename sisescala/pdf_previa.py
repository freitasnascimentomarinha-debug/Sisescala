"""PDF da prévia da escala: a tabela de calendário do sistema, no mesmo tema (verde-oliva escuro) e com as mesmas cores
de sigla da tela. Paisagem A4; períodos longos são divididos em blocos de dias com a coluna de nomes repetida."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .calendario import dia_util, nome_dia_nao_util, roxa_do_dia
from .modelos import CATEGORIAS, DISP, SVC, Contexto, formatar_nip, horarios_curtos, rotulo_militar
from .motor import Resultado, sigla_base
from .previa import LEGENDA_FIXA, _sigla_imp, cor_da_sigla, resumo_escala

# paleta do tema da tela (assets/estilo.css)
BG, CARD, CARD2, LINHA = "#10150B", "#192012", "#1F2817", "#323D24"
INK, SLATE, MUTED = "#EFEBDD", "#D3D0BC", "#9AA183"
VERDE, VERDE2 = "#6B8E3A", "#A3C265"
VAZIO = "#141A0E"
LOGO = Path(__file__).resolve().parent.parent / "static" / "logo_menu.png"
MAX_COLUNAS = 15


def _c(hexa: str):
    if len(hexa) == 4:                       # "#fff" -> "#ffffff" (o reportlab não aceita a forma curta)
        hexa = "#" + "".join(ch * 2 for ch in hexa[1:])
    return colors.HexColor(hexa)


def _mistura(base: str, tom: str, f: float):
    """Mistura `tom` sobre `base` (f = quanto do tom), como a transparência do tema na tela."""
    a, b = _c(base), _c(tom)
    return colors.Color(a.red * (1 - f) + b.red * f, a.green * (1 - f) + b.green * f, a.blue * (1 - f) + b.blue * f)


DOW = "SEG TER QUA QUI SEX SÁB DOM".split()


def pdf_previa(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, om: str = "",
               agora: datetime | None = None) -> bytes:
    esc = ctx.escala(escala_id)
    agora = agora or datetime.now()
    om = (om or esc.om or "").strip()
    cat = CATEGORIAS.get(esc.categoria, ("", ""))[0]
    refs = [ctx.escala(r) for r in esc.referencias if any(e.id == r for e in ctx.escalas)]
    ids = set(ctx.escalaveis(esc))
    militares = sorted((m for m in ctx.militares if m.id in ids), key=lambda m: ctx.antig(esc, m.id))

    def sty(nome, **kw):
        base = dict(fontName="Helvetica", fontSize=8, leading=10, textColor=_c(SLATE))
        base.update(kw)
        return ParagraphStyle(nome, **base)

    s_tit = sty("tit", fontName="Helvetica-Bold", fontSize=20, leading=23, textColor=_c(INK))
    s_sup = sty("sup", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=_c(VERDE2), charSpace=1.2)
    s_sub = sty("sub", fontSize=9, leading=12, textColor=_c(MUTED))
    s_rot = sty("rot", fontSize=6.5, leading=8, textColor=_c(MUTED), charSpace=0.6)
    s_val = sty("val", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=_c(INK))
    s_nome = sty("nome", fontName="Helvetica-Bold", fontSize=7.8, leading=9.4, textColor=_c(INK))
    s_nip = sty("nip", fontSize=6.3, leading=7.4, textColor=_c(MUTED))
    s_h = sty("h", fontName="Helvetica-Bold", fontSize=8, leading=9.5, alignment=1, textColor=_c(SLATE))
    s_hs = sty("hs", fontSize=5.8, leading=7, alignment=1, textColor=_c(MUTED))
    s_h4 = sty("h4", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=_c(INK), spaceBefore=8, spaceAfter=3)
    s_li = sty("li", fontSize=8, leading=11.2, leftIndent=8)
    s_leg = sty("leg", fontSize=7, leading=9, textColor=_c(SLATE))

    # ------------------------------------------------------------------ cabeçalho
    logo_h = 14 * mm
    logo = Image(str(LOGO), width=logo_h * 700 / 355, height=logo_h) if LOGO.exists() else Spacer(1, 1)
    titulo = [Paragraph("PRÉVIA DA ESCALA" + (f" · {om.upper()}" if om else ""), s_sup),
              Paragraph(esc.nome + (f" <font size=12 color='{MUTED}'>· {esc.tipo}</font>" if esc.tipo else ""), s_tit),
              Paragraph(f"{cat or 'Escala'} · período de {dias[0]:%d/%m/%Y} a {dias[-1]:%d/%m/%Y} "
                        f"({len(dias)} dias) · {esc.militares_dia} escalado(s) por dia · retém {esc.retem_qtd}", s_sub)]
    cab = Table([[logo, titulo]], colWidths=[logo_h * 700 / 355 + 6 * mm, None], hAlign="LEFT")
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                             ("TOPPADDING", (0, 0), (-1, -1), 0)]))

    # ------------------------------------------------------------------ cartões de saúde da escala
    rs = resumo_escala(ctx, esc, dias, hoje=agora.date())
    ritmo = f"{rs['ritmo_hoje']:g}x1"
    alerta = rs["ritmo_hoje"] < rs["minimo"]
    cards = [("RITMO HOJE", ritmo, f"mínimo {rs['minimo']}x1" + (" · ABAIXO" if alerta else ""), "#E58A6B" if alerta else VERDE2),
             ("PESSOAS NA ESCALA", str(rs["militares"]), "podem ser escaladas", VERDE2),
             ("IMPEDIDOS HOJE", str(rs["impedidos_hoje"]), f"no período: {rs['impedidos_periodo']}", "#E0B85C"),
             ("DISPONÍVEIS HOJE", str(rs["disponiveis_hoje"]), f"{rs['vagas']} vaga(s) por dia", VERDE2)]
    celulas = [[[Paragraph(r, s_rot), Paragraph(v, s_val), Paragraph(f"<font color='{cor}'>{d}</font>", s_rot)]
                for r, v, d, cor in cards]]
    larg_util = landscape(A4)[0] - 20 * mm
    w_card = (larg_util - 3 * 4 * mm) / 4
    # espaço entre os cartões: colunas vazias intercaladas
    larg2, linha = [], []
    for i, c in enumerate(celulas[0]):
        linha.append(c)
        larg2.append(w_card)
        if i < 3:
            linha.append("")
            larg2.append(4 * mm)
    pain = Table([linha], colWidths=larg2, hAlign="LEFT")
    est2 = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for i, (_, _, _, cor) in enumerate(cards):
        j = i * 2
        est2 += [("BACKGROUND", (j, 0), (j, 0), _c(CARD)), ("BOX", (j, 0), (j, 0), 0.6, _c(LINHA)),
                 ("LINEBEFORE", (j, 0), (j, 0), 2.6, _c(cor)), ("LEFTPADDING", (j, 0), (j, 0), 10)]
    pain.setStyle(TableStyle(est2))

    # ------------------------------------------------------------------ células da tabela
    obs: list[tuple[date, str]] = []

    def conteudo(m, d):
        """(lista de (sigla, extra, ref?), é dispensa?) do militar no dia, como na prévia da tela."""
        tags = []
        dia = res.dia(d, esc.id)
        for a in (dia.alocacoes if dia else []):
            if a.militar_id == m.id and a.origem != "falta":
                tags.append((a.sigla, horarios_curtos(a.horarios), False))
                if a.obs and a.origem != "normal":
                    obs.append((d, f"{m.nome}: {a.obs}"))
            elif a.militar_id == m.id:
                tags.append((DISP, "", False))
                obs.append((d, f"{m.nome}: {a.obs}"))
        for r in refs:
            dr = res.dia(d, r.id)
            for a in (dr.alocacoes if dr else []):
                if a.militar_id == m.id and a.origem != "falta":
                    tags.append((a.sigla, r.nome, True))
        if not tags and (s := _sigla_imp(ctx, m.id, d)):
            tags.append((s, "", False))
        return tags

    for i in ctx.impedimentos:
        if i.tipo in ("dispensa", "dispensa_justificada", "baixa") and i.militar_id in ids and i.motivo \
                and any(i.cobre(d) for d in dias):
            fim = f"–{i.fim:%d/%m}" if i.fim else ""
            obs.append((max(i.inicio, dias[0]), f"{ctx.militar(i.militar_id).nome}: Dispensado ({i.inicio:%d/%m}{fim}): {i.motivo}"))

    def classe(d):
        if esc.participa_roxa and roxa_do_dia(d, ctx, esc):
            return "roxa"
        return "util" if dia_util(d, ctx, esc) else "folga"

    blocos = [dias[i:i + MAX_COLUNAS] for i in range(0, len(dias), MAX_COLUNAS)]
    tabelas = []
    w_nome = 46 * mm
    for bloco in blocos:
        w_dia = (larg_util - w_nome) / len(bloco)
        head = [Paragraph("", s_h)]
        estilo = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                  ("BOX", (0, 0), (-1, -1), 0.8, _c(LINHA)), ("INNERGRID", (0, 0), (-1, -1), 0.4, _c(LINHA)),
                  ("BACKGROUND", (0, 0), (0, -1), _c(CARD)), ("BACKGROUND", (0, 0), (-1, 0), _c(CARD2)),
                  ("TOPPADDING", (0, 1), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 1), (-1, -1), 2.2),
                  ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                  ("LEFTPADDING", (0, 0), (0, -1), 6), ("LEFTPADDING", (1, 0), (-1, -1), 1.5),
                  ("RIGHTPADDING", (1, 0), (-1, -1), 1.5),
                  ("LINEBELOW", (0, 0), (-1, 0), 1.2, _c(VERDE))]
        for k, d in enumerate(bloco, 1):
            dia = res.dia(d, esc.id)
            sem = dia is None or not dia.funciona
            leg = nome_dia_nao_util(d, ctx, esc) or ("não guarnece" if sem else "")
            cl = classe(d)
            head.append([Paragraph(f"{d:%d/%m}", s_h), Paragraph(DOW[d.weekday()], s_h)] +
                        ([Paragraph(leg[:24], s_hs)] if leg else []))
            if cl == "folga":
                estilo.append(("BACKGROUND", (k, 0), (k, 0), _mistura(CARD2, "#EF4444", 0.22)))
            elif cl == "roxa":
                estilo.append(("BACKGROUND", (k, 0), (k, 0), _mistura(CARD2, "#A08246", 0.32)))
        linhas = [head]
        for r, m in enumerate(militares, 1):
            nip = f"<br/><font size=6.3 color='{MUTED}'>{formatar_nip(m.nip)}</font>" if (m.nip or "").strip() else ""
            lin = [Paragraph(f"{rotulo_militar(m, com_nip=False)}{nip}", s_nome)]
            for k, d in enumerate(bloco, 1):
                dia = res.dia(d, esc.id)
                cl = classe(d)
                fundo = _mistura(VAZIO, "#EF4444", 0.10) if cl == "folga" else \
                    _mistura(VAZIO, "#A08246", 0.16) if cl == "roxa" else _c(VAZIO)
                tags = conteudo(m, d)
                if tags:
                    bg, fg = cor_da_sigla(tags[0][0])
                    partes = []
                    for sigla, extra, ref in tags:
                        p = f"<b>{sigla}</b>" + (f"<br/><font size=5.6>{extra}</font>" if extra else "")
                        partes.append(f"<i>{p}</i>" if ref else p)
                    lin.append(Paragraph("<br/>".join(partes), ParagraphStyle(
                        "c", parent=s_h, textColor=_c(fg), fontSize=7.4, leading=8.6)))
                    estilo.append(("BACKGROUND", (k, r), (k, r), _c(bg)))
                    estilo.append(("LINEBEFORE", (k, r), (k, r), 0.4, _c(LINHA)))
                else:
                    lin.append("")
                    estilo.append(("BACKGROUND", (k, r), (k, r), fundo))
            linhas.append(lin)
        t = Table(linhas, colWidths=[w_nome] + [w_dia] * len(bloco), repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle(estilo))
        tabelas.append(t)

    # ------------------------------------------------------------------ legenda e observações
    sigla = sigla_base(esc)
    itens = list(LEGENDA_FIXA)
    if sigla != SVC:
        itens.insert(0, (sigla, CATEGORIAS.get(esc.categoria, ("", ""))[0] or "Escalação"))
    # duas linhas de legenda
    metade = (len(itens) + 1) // 2
    leg_tabs = []
    for parte in (itens[:metade], itens[metade:]):
        row, larg, est = [], [], []
        for n, (s, txt) in enumerate(parte):
            bg, fg = cor_da_sigla(s)
            row += [Paragraph(f"<b>{s}</b>", ParagraphStyle("lg", parent=s_h, textColor=_c(fg), fontSize=6.6, leading=8)),
                    Paragraph(txt, s_leg)]
            larg += [15 * mm, 33 * mm]
            est.append(("BACKGROUND", (2 * n, 0), (2 * n, 0), _c(bg)))
        tt = Table([row], colWidths=larg, hAlign="LEFT")
        tt.setStyle(TableStyle(est + [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
                                      ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("LEFTPADDING", (1, 0), (1, 0), 4)]
                                     + [("LEFTPADDING", (2 * n + 1, 0), (2 * n + 1, 0), 4) for n in range(len(parte))]))
        leg_tabs.append(tt)
    obs_txt = [Paragraph(f"<font color='{VERDE2}'><b>{d:%d/%m}</b></font> – {t}", s_li) for d, t in sorted(set(obs))]

    el = [cab, Spacer(1, 2 * mm), pain, Spacer(1, 3 * mm)]
    for i, t in enumerate(tabelas):
        el += [t, Spacer(1, 3 * mm)]
    el.append(KeepTogether([Paragraph("LEGENDA", s_sup), Spacer(1, 1.5 * mm)] + leg_tabs))
    el.append(KeepTogether([Paragraph("Observações", s_h4)] + (obs_txt or [Paragraph("Sem trocas ou ocorrências no período.", s_li)])
                           if len(obs_txt) < 12 else [Paragraph("Observações", s_h4)]))
    if len(obs_txt) >= 12:
        el += obs_txt

    # ------------------------------------------------------------------ página (fundo, faixa e rodapé)
    W, H = landscape(A4)

    def fundo(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(_c(BG))
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        canvas.setFillColor(_c(VERDE))                               # faixa de destaque no topo
        canvas.rect(0, H - 3 * mm, W, 3 * mm, fill=1, stroke=0)
        canvas.setFillColor(_c(VERDE2))
        canvas.rect(0, H - 3 * mm, 38 * mm, 3 * mm, fill=1, stroke=0)
        canvas.setStrokeColor(_c(LINHA))
        canvas.setLineWidth(0.5)
        canvas.line(10 * mm, 9 * mm, W - 10 * mm, 9 * mm)
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(_c(MUTED))
        canvas.drawString(10 * mm, 5.6 * mm, f"SisEscala · {esc.nome} · gerado em {agora:%d/%m/%Y às %H:%M}")
        canvas.drawRightString(W - 10 * mm, 5.6 * mm, f"Página {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=9 * mm, bottomMargin=13 * mm, title=f"Prévia – {esc.nome}", author="SisEscala")
    doc.build(el, onFirstPage=fundo, onLaterPages=fundo)
    return buf.getvalue()

"""Relatório de regras de uma escala ("regra do jogo"): como a escala funciona com a configuração
atual, o que está no padrão e o que foi alterado, e a lógica fixa do sistema.

É gerado a partir da configuração viva: ajustou algo, o relatório muda.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from html import escape
from io import BytesIO

from .modelos import CATEGORIAS, TIPOS_IMPEDIMENTO, Contexto, Escala
from .motor import _ancestrais, _folgas, _sequencia


@dataclass
class Item:
    rotulo: str
    valor: str
    padrao: str
    explicacao: str

    @property
    def alterado(self) -> bool:
        return self.valor != self.padrao


def _padrao(cls, campo: str):
    for f in dataclasses.fields(cls):
        if f.name == campo:
            if f.default is not dataclasses.MISSING:
                return f.default
            if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                return f.default_factory()  # type: ignore[misc]
    return None


def _sn(v: bool) -> str:
    return "sim" if v else "não"


FUNCIONA = {"todos": "todos os dias", "uteis": "só em dias úteis (para em sábado, domingo, feriado e dia sem expediente)"}
MODO = {"corrida": "Corrida (uma fila única)", "preta_vermelha": "Preta e vermelha (duas filas)",
        "eventos": "Por evento (só nos dias de evento lançados)"}


def itens_configuracao(ctx: Contexto, esc: Escala) -> list[tuple[str, list[Item]]]:
    d = lambda c: _padrao(Escala, c)  # noqa: E731
    q = esc.quartos
    q_txt = (f"{len(q)} quartos de {(int(q[0].fim[:2]) - int(q[0].inicio[:2])) % 24 or 24}h" if q else "sem quartos")
    c_ctx = lambda c: _padrao(type(ctx), c)  # noqa: E731
    return [
        ("Natureza da escala", [
            Item("Categoria", CATEGORIAS[esc.categoria][0], CATEGORIAS[d("categoria")][0],
                 "Serviço usa a sigla SVÇ; as demais categorias usam sigla própria e nunca têm prioridade sobre serviço."),
            Item("Modo", MODO[esc.modo], MODO[d("modo")], "Define as filas e em quais dias a escala roda."),
            Item("Funciona em", "nos dias de evento" if esc.modo == "eventos" else FUNCIONA[esc.funciona_em],
                 FUNCIONA[d("funciona_em")],
                 "O comando pode, por dia, mandar guarnecer ou não guarnecer (lançamento manual)."),
            Item("Participa da escala roxa", _sn(esc.participa_roxa), _sn(d("participa_roxa")),
                 "Em recesso (período roxo) a fila roxa começa do zero e as demais ficam congeladas."),
        ]),
        ("Quantidades", [
            Item("Escalados por dia", str(esc.militares_dia), str(d("militares_dia")),
                 "Quantos militares dão o serviço (ou compõem a escalação) em cada dia."),
            Item("Retém por dia", str(esc.retem_qtd), str(d("retem_qtd")),
                 "Quantos ficam sobre aviso para avançar se o escalado não puder."),
            Item("Quartos", q_txt, "sem quartos",
                 "Os quartos são distribuídos de forma intercalada entre os escalados do dia, com rendição entre eles."),
        ]),
        ("Justiça da escala", [
            Item("Folgas mínimas entre serviços", f"{esc.folgas_minimas} (mínimo {esc.folgas_minimas}x1)",
                 f"{d('folgas_minimas')} (mínimo {d('folgas_minimas')}x1)",
                 "O mesmo militar nunca dá serviço em dias seguidos nem com menos folgas que isso, "
                 "inclusive entre filas (ex.: sexta preta e sábado vermelha)."),
            Item("Prioridade", str(esc.prioridade), str(d("prioridade")),
                 "Em conflito entre escalas do mesmo responsável, a de maior prioridade prevalece "
                 "(a outra faz a troca forçada)."),
            Item("Escalações que não são serviço respeitam o serviço", _sn(esc.respeita_servicos),
                 _sn(d("respeita_servicos")),
                 "Palestras, cerimônias, cursos, apoio etc. só escalam quem não está de efetivo serviço no dia."),
        ]),
        ("Parâmetros gerais", [
            Item("UF da OM (feriados)", ctx.uf, str(c_ctx("uf")),
                 "Feriados nacionais e estaduais vêm prontos; municipais e licenças são lançados à mão."),
            Item("Prazo para devolver serviço (dias)", str(ctx.janela_devolucao_dias),
                 str(c_ctx("janela_devolucao_dias")),
                 "Quem não deu o serviço e fez o retém avançar pode devolvê-lo em outro dia, por papeleta assinada."),
            Item("Janela de busca da troca forçada (dias)", str(ctx.janela_troca_dias),
                 str(c_ctx("janela_troca_dias")),
                 "Quanto o sistema procura, antes e depois, um parceiro para a troca forçada."),
        ]),
    ]


LOGICA_FIXA = [
    "A ordem da fila vai do mais antigo ao mais moderno, em círculo, a partir de quem deu o último serviço.",
    "Cada escala tem filas independentes (corrida, preta, vermelha, roxa). A fila que não é a do dia fica "
    "congelada e retoma de onde parou. A roxa começa do zero para todos.",
    "Quem está de férias, curso, dispensa, baixa, destaque (DTQ) ou desembarcado é pulado sem perder o seu lugar na ordem; "
    "desembarcado sai da fila.",
    "O retém do dia é o próximo da fila depois dos escalados. Se um escalado não puder dar o serviço, o retém "
    "avança para efetivo e os reténs dos dias seguintes avançam junto.",
    "Quem é pulado por ainda estar de folga não perde a vez: entra na primeira oportunidade.",
    "Troca forçada (TF): se o militar cai em duas escalações no mesmo dia, prevalece a de maior prioridade "
    "(ou a escala referenciada). Na outra, o sistema procura a melhor troca de datas com outro militar da escala "
    "para que ele dê as duas; o motivo aparece em Observações.",
    "Serviço sempre prevalece sobre palestra, cerimônia, curso, visitação religiosa, apoio e demais escalações. "
    "O retém de serviço não impede essas escalações.",
    "Troca consensual (T) só vale com papeleta aceita pelas duas partes.",
    "Escala referenciada (de outro responsável) prevalece sobre a que a referencia; escalas sem referência "
    "entre responsáveis diferentes não se influenciam.",
    "O resultado de um dia não depende do tamanho da prévia (7, 15 ou 30 dias).",
]


def texto_funcionamento(ctx: Contexto, esc: Escala) -> list[str]:
    cat = CATEGORIAS[esc.categoria][0]
    p = []
    if esc.modo == "eventos":
        p.append(f"{esc.nome} é uma escalação de {cat.lower()}: só há escalados nos dias em que um evento é lançado. "
                 f"Cada evento usa {esc.militares_dia} militar(es) por padrão, na ordem de antiguidade da fila.")
    else:
        filas = ("uma fila única" if esc.modo == "corrida" else
                 "duas filas: preta (dias úteis) e vermelha (sábado, domingo e feriado)")
        p.append(f"{esc.nome} ({cat}) roda {FUNCIONA[esc.funciona_em]}, com {filas}.")
        p.append(f"Em cada dia escalam-se {esc.militares_dia} militar(es) e ficam {esc.retem_qtd} de retém.")
    if esc.quartos:
        horas = (int(esc.quartos[0].fim[:2]) - int(esc.quartos[0].inicio[:2])) % 24 or 24
        p.append(f"O dia é dividido em {len(esc.quartos)} quartos de {horas}h, intercalados entre os escalados; "
                 f"a célula da prévia mostra a hora de início de cada quarto (ex.: 4h/16h).")
    f = _folgas(esc)
    if esc.modo != "eventos":
        p.append(f"Descanso mínimo: {f} folga(s) entre dois serviços do mesmo militar ({f}x1).")
    if esc.categoria != "servico":
        p.append("Esta escalação nunca tem prioridade sobre serviço: "
                 + ("só escala quem não está de efetivo serviço no dia." if esc.respeita_servicos else
                    "a regra de só escalar quem não está de serviço foi desligada nesta escala."))
    if esc.referencias:
        nomes = ", ".join(e.nome for e in ctx.escalas if e.id in _ancestrais(ctx, esc))
        p.append(f"Esta escala considera {nomes}: quem estiver de serviço lá é tratado como já escalado aqui.")
    return p


def situacao_atual(ctx: Contexto, esc: Escala, hoje: date | None = None) -> list[tuple[str, str]]:
    hoje = hoje or ctx.data_base
    out: list[tuple[str, str]] = [("Data-base (a escala continua daqui)", f"{ctx.data_base:%d/%m/%Y}")]
    filas = [("corrida",)] if esc.modo != "preta_vermelha" else [("preta",), ("vermelha",)]
    for (f,) in filas:
        ult = esc.ultimo_servico.get(f)
        seq = _sequencia(ctx, esc, hoje, ult)
        prox = ctx.militar(seq[0]).nome if seq else "—"
        out.append((f"Fila {f}: último serviço → próximo",
                    f"{ctx.militar(ult).nome if ult else 'início da fila'} → {prox}"))
    ordem = sorted((ctx.militar(p.militar_id) for p in esc.membros if p.ativo(hoje)), key=lambda m: m.antiguidade)
    out.append((f"Militares na escala ({len(ordem)})", ", ".join(f"{m.posto} {m.nome}".strip() for m in ordem) or "—"))
    imps = [i for i in ctx.impedimentos if i.militar_id in {p.militar_id for p in esc.membros}]
    out.append(("Impedimentos lançados", "; ".join(
        f"{ctx.militar(i.militar_id).nome} – {TIPOS_IMPEDIMENTO[i.tipo]} "
        f"{i.inicio:%d/%m}{'–' + format(i.fim, '%d/%m') if i.fim else '→'}" for i in imps) or "nenhum"))
    esp = [e for e in ctx.dias_especiais]
    out.append(("Dias especiais lançados", "; ".join(
        f"{e.data:%d/%m} {e.descricao or e.tipo}" for e in sorted(esp, key=lambda e: e.data)) or "nenhum"))
    gu = [g for g in ctx.guarnecimentos if g.escala_id == esc.id]
    out.append(("Guarnecimento decidido pelo comando", "; ".join(
        f"{g.data:%d/%m} {'guarnece' if g.guarnece else 'não guarnece'}" for g in gu) or "nenhum"))
    out.append(("Períodos roxos", "; ".join(
        f"{r.nome} ({r.inicio:%d/%m}–{r.fim:%d/%m})" for r in ctx.roxas) or "nenhum"))
    if esc.modo == "eventos":
        ev = [e for e in ctx.eventos if e.escala_id == esc.id]
        out.append(("Eventos lançados", "; ".join(
            f"{e.data:%d/%m} {e.descricao}" for e in sorted(ev, key=lambda e: e.data)) or "nenhum"))
    donos = {u.id: u.nome for u in ctx.usuarios}
    out.append(("Responsável", donos.get(esc.dono_id, esc.dono_id or "—")))
    out.append(("Compartilhada com", ", ".join(
        f"{donos.get(u, u)} ({n})" for u, n in esc.compartilhado_com.items()) or "ninguém"))
    return out


def html_regras(ctx: Contexto, esc: Escala) -> str:
    sec = ""
    for titulo, itens in itens_configuracao(ctx, esc):
        linhas = "".join(
            f"<tr><td>{escape(i.rotulo)}</td><td><b>{escape(i.valor)}</b></td>"
            f"<td>{'<span class=alt>alterado</span> padrão: ' + escape(i.padrao) if i.alterado else '<span class=pad>padrão</span>'}</td>"
            f"<td>{escape(i.explicacao)}</td></tr>" for i in itens)
        sec += f"<h4>{escape(titulo)}</h4><table class='reg'><tr><th>Regra</th><th>Valor</th><th>Situação</th><th>O que significa</th></tr>{linhas}</table>"
    como = "".join(f"<li>{escape(t)}</li>" for t in texto_funcionamento(ctx, esc))
    fixa = "".join(f"<li>{escape(t)}</li>" for t in LOGICA_FIXA)
    sit = "".join(f"<tr><td>{escape(k)}</td><td>{escape(v)}</td></tr>" for k, v in situacao_atual(ctx, esc))
    return f"""<style>.reg{{border-collapse:collapse;font:13px sans-serif;margin-bottom:8px}}
.reg td,.reg th{{border:1px solid #d0d7de;padding:4px 8px;text-align:left;vertical-align:top}} .reg th{{background:#f6f8fa}}
.alt{{background:#d29922;color:#000;border-radius:4px;padding:0 5px;font-weight:600}} .pad{{color:#57606a}}</style>
<h3>Regras do serviço – {escape(esc.nome)}</h3><h4>Como esta escala funciona</h4><ul>{como}</ul>{sec}
<h4>Situação atual</h4><table class='reg'>{sit}</table>
<h4>Lógica fixa do sistema (não configurável)</h4><ul>{fixa}</ul>"""


def pdf_regras(ctx: Contexto, esc: Escala, om: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    st = getSampleStyleSheet()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm)
    P = lambda t, s="BodyText": Paragraph(t, st[s])  # noqa: E731
    el = [P(f"<b>REGRAS DO SERVIÇO – {escape(esc.nome.upper())}</b>{' – ' + escape(om) if om else ''}", "Title"),
          P("Como esta escala funciona", "Heading3")]
    el += [P("• " + escape(t)) for t in texto_funcionamento(ctx, esc)]
    for titulo, itens in itens_configuracao(ctx, esc):
        rows = [["Regra", "Valor", "Situação", "O que significa"]] + [
            [P(escape(i.rotulo)), P(f"<b>{escape(i.valor)}</b>"),
             P(f"ALTERADO (padrão: {escape(i.padrao)})" if i.alterado else "padrão"), P(escape(i.explicacao))]
            for i in itens]
        t = Table(rows, colWidths=[40 * mm, 38 * mm, 30 * mm, 74 * mm], repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        el += [Spacer(1, 6), P(escape(titulo), "Heading4"), t]
    el += [P("Situação atual", "Heading3")] + [P(f"<b>{escape(k)}:</b> {escape(v)}") for k, v in situacao_atual(ctx, esc)]
    el += [P("Lógica fixa do sistema (não configurável)", "Heading3")] + [P("• " + escape(t)) for t in LOGICA_FIXA]
    doc.build(el)
    return buf.getvalue()

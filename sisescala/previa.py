"""Prévia em tabela de calendário (HTML) com siglas e cores."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

from .calendario import nome_dia_nao_util, dia_util, roxa_do_dia
from .modelos import (CURSO, DBQ, DISP, FALTA, FERIAS, BAIXA, RT, RT_T, RT_TF, SVC, SVC_T, SVC_TF,
                      TIPOS_IMPEDIMENTO, Contexto)
from .motor import Resultado

CORES = {  # sigla -> (fundo, texto)
    SVC: ("#1f6feb", "#fff"), SVC_TF: ("#d29922", "#000"), SVC_T: ("#8957e5", "#fff"),
    RT: ("#8b949e", "#fff"), RT_TF: ("#bf8700", "#fff"), RT_T: ("#6e40c9", "#fff"),
    FERIAS: ("#2da44e", "#fff"), DISP: ("#0e8a8a", "#fff"), DBQ: ("#cf222e", "#fff"),
    CURSO: ("#0969da", "#fff"), BAIXA: ("#e16f24", "#fff"), FALTA: ("#82071e", "#fff"),
}
LEGENDA = [
    (SVC, "Serviço"), (SVC_TF, "Serviço por troca forçada"), (SVC_T, "Serviço por troca consensual"),
    (RT, "Retém"), (RT_TF, "Troca forçada de retém"), (FERIAS, "Férias"), (DISP, "Dispensado"),
    (DBQ, "Desembarque"), (CURSO, "Curso"), (BAIXA, "Baixa"), (FALTA, "Não deu o serviço"),
]


def _sigla_imp(ctx: Contexto, mid: str, d: date) -> str | None:
    for i in ctx.impedimentos:
        if i.militar_id == mid and i.cobre(d):
            return TIPOS_IMPEDIMENTO[i.tipo]
    return None


def periodo(inicio: date, dias: int) -> list[date]:
    return [inicio + timedelta(days=i) for i in range(dias)]


def _tag(sigla: str, extra: str = "") -> str:
    bg, fg = CORES.get(sigla, ("#ccc", "#000"))
    txt = escape(sigla) + (f" <small>{escape(extra)}</small>" if extra else "")
    return f'<span class="t" style="background:{bg};color:{fg}">{txt}</span>'


def html_previa(ctx: Contexto, res: Resultado, dias: list[date]) -> str:
    esc_sigla = {e.id: (e.sigla or e.nome[:3].upper()) for e in ctx.escalas}
    cab = ""
    for d in dias:
        nome = nome_dia_nao_util(d, ctx)
        classe = "roxa" if roxa_do_dia(d, ctx) else ("util" if dia_util(d, ctx) else "folga")
        dow = "SEG TER QUA QUI SEX SÁB DOM".split()[d.weekday()]
        cab += (f'<th class="{classe}" title="{escape(nome or "")}">{d:%d/%m}<br>{dow}'
                f'{"<br><small>" + escape(nome) + "</small>" if nome else ""}</th>')
    linhas, obs = "", []
    for m in sorted(ctx.militares, key=lambda m: m.antiguidade):
        cel = ""
        for d in dias:
            tags = []
            for a in res.alocacoes_do_dia(d):
                if a.militar_id == m.id:
                    ex = esc_sigla[a.escala_id] + (" " + ",".join(a.horarios) if a.horarios else "")
                    tags.append(_tag(a.sigla, ex))
                    if a.obs and a.sigla != SVC:
                        obs.append((d, f"{m.nome} – {esc_sigla[a.escala_id]}: {a.obs}"))
            if not tags and (s := _sigla_imp(ctx, m.id, d)):
                tags.append(_tag(s))
            cel += f"<td>{''.join(tags)}</td>"
        linhas += f"<tr><th class='nome'>{escape(m.posto)} {escape(m.nome)}</th>{cel}</tr>"
    # retém do dia, por escala
    ret = ""
    for e in sorted(ctx.escalas, key=lambda e: -e.prioridade):
        cel = ""
        for d in dias:
            dia = res.dia(d, e.id)
            if not dia or not dia.funciona:
                cel += "<td class='para'>não guarnece</td>"
            else:
                nomes = [f"{_tag(a.sigla)} {escape(ctx.militar(a.militar_id).nome)}" for a in dia.retens]
                cel += f"<td>{'<br>'.join(nomes)}</td>"
        ret += f"<tr><th class='nome'>RT – {escape(e.nome)}</th>{cel}</tr>"
    obs_html = "".join(f"<li><b>{d:%d/%m}</b> – {escape(t)}</li>" for d, t in sorted(set(obs)))
    leg = " ".join(_tag(s) + f" {escape(t)}" for s, t in LEGENDA)
    return f"""<style>
.prev{{border-collapse:collapse;font:12px sans-serif}} .prev th,.prev td{{border:1px solid #d0d7de;padding:3px 4px;text-align:center;white-space:nowrap}}
.prev th.util{{background:#f6f8fa}} .prev th.folga{{background:#ffd8d8}} .prev th.roxa{{background:#d8c4f5}}
.prev th.nome{{text-align:left;background:#f6f8fa;position:sticky;left:0}}
.prev td.para{{color:#8b949e;font-style:italic}}
.t{{display:inline-block;border-radius:4px;padding:1px 5px;margin:1px;font-weight:600}} .t small{{font-weight:400}}
</style>
<div style="overflow-x:auto"><table class="prev"><tr><th></th>{cab}</tr>{linhas}
<tr><th colspan="{len(dias) + 1}" style="background:#eaeef2">Retém do dia</th></tr>{ret}</table></div>
<p>{leg}</p><h4>Observações</h4><ul>{obs_html or '<li>Sem trocas ou ocorrências no período.</li>'}</ul>"""

"""Prévia de UMA escala por vez: card de destaque + tabela de calendário com siglas e cores."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

from .calendario import dia_util, nome_dia_nao_util, roxa_do_dia
from .modelos import (BAIXA, CATEGORIAS, CURSO, DBQ, DISP, DTQ, FALTA, FERIAS, SVC, TIPOS_IMPEDIMENTO,
                      Contexto, Escala, horarios_curtos)
from .motor import Resultado, _folgas, sigla_base

CORES = {  # sigla base -> (fundo, texto)
    "SVÇ": ("#1f6feb", "#fff"), "RT": ("#8b949e", "#fff"),
    "PAL": ("#0a7d8c", "#fff"), "CUR": ("#0550ae", "#fff"), "VIS": ("#7d4e00", "#fff"),
    "CER": ("#953800", "#fff"), "APO": ("#116329", "#fff"), "OUT": ("#57606a", "#fff"),
    FERIAS: ("#2da44e", "#fff"), DISP: ("#0e8a8a", "#fff"), DBQ: ("#cf222e", "#fff"),
    CURSO: ("#0969da", "#fff"), BAIXA: ("#e16f24", "#fff"), FALTA: ("#82071e", "#fff"),
    DTQ: ("#6639ba", "#fff"),
}
COR_TF, COR_T = ("#d29922", "#000"), ("#8957e5", "#fff")

LEGENDA_FIXA = [
    ("SVÇ", "Serviço"), ("SVÇ (TF)", "Serviço por troca forçada"), ("SVÇ (T)", "Serviço por troca consensual"),
    ("RT", "Retém"), ("RT (TF)", "Troca forçada de retém"), (FERIAS, "Férias"), (DISP, "Dispensado"),
    (DBQ, "Desembarque"), (CURSO, "Curso"), (DTQ, "Destaque"), (BAIXA, "Baixa"), (FALTA, "Não deu o serviço"),
]


def periodo(inicio: date, dias: int) -> list[date]:
    return [inicio + timedelta(days=i) for i in range(dias)]


def cor_da_sigla(sigla: str) -> tuple[str, str]:
    if sigla.endswith("(TF)"):
        return COR_TF
    if sigla.endswith("(T)"):
        return COR_T
    return CORES.get(sigla.split(" ")[0], ("#ccc", "#000"))


def _tag(sigla: str, extra: str = "", cls: str = "") -> str:
    bg, fg = cor_da_sigla(sigla)
    txt = escape(sigla) + (f" <small>{escape(extra)}</small>" if extra else "")
    return f'<span class="t {cls}" style="background:{bg};color:{fg}">{txt}</span>'


def _sigla_imp(ctx: Contexto, mid: str, d: date) -> str | None:
    for i in ctx.impedimentos:
        if i.militar_id == mid and i.cobre(d):
            return TIPOS_IMPEDIMENTO[i.tipo]
    return None


def info_escala(ctx: Contexto, esc: Escala) -> list[tuple[str, str]]:
    """Informações de destaque do card."""
    cat = CATEGORIAS.get(esc.categoria, ("", ""))[0]
    donos = {u.id: u.nome for u in ctx.usuarios}
    modo = {"corrida": "Corrida", "preta_vermelha": "Preta e vermelha", "eventos": "Por evento"}[esc.modo]
    inf = [("Categoria", cat), ("Modo", modo), ("Prioridade", str(esc.prioridade)),
           ("Escalados por dia", str(esc.militares_dia)), ("Retém por dia", str(esc.retem_qtd)),
           ("Descanso mínimo", f"{_folgas(esc)} folga(s) por serviço (mín. {_folgas(esc)}x1)"),
           ("Militares na escala", str(len(esc.membros)))]
    if esc.quartos:
        q = esc.quartos[0]
        inf.append(("Quartos", f"{len(esc.quartos)} de {(int(q.fim[:2]) - int(q.inicio[:2])) % 24 or 24}h"))
    if esc.modo != "eventos":
        inf.append(("Funciona", "todos os dias" if esc.funciona_em == "todos" else "só em dias úteis"))
    if esc.dono_id:
        inf.append(("Responsável", donos.get(esc.dono_id, esc.dono_id)))
    if esc.referencias:
        nomes = ", ".join(ctx.escala(r).nome for r in esc.referencias if any(e.id == r for e in ctx.escalas))
        inf.append(("Considera (prevalece sobre esta)", nomes))
    if esc.compartilhado_com:
        inf.append(("Compartilhada com", ", ".join(
            f"{donos.get(u, u)} ({n})" for u, n in esc.compartilhado_com.items())))
    return inf


def _cabecalho_dias(ctx: Contexto, dias: list[date]) -> str:
    cab = ""
    for d in dias:
        nome = nome_dia_nao_util(d, ctx)
        classe = "roxa" if roxa_do_dia(d, ctx) else ("util" if dia_util(d, ctx) else "folga")
        dow = "SEG TER QUA QUI SEX SÁB DOM".split()[d.weekday()]
        cab += (f'<th class="{classe}" title="{escape(nome or "")}">{d:%d/%m}<br>{dow}'
                f'{"<br><small>" + escape(nome) + "</small>" if nome else ""}</th>')
    return cab


def html_previa(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, abertas=None) -> str:
    abertas = abertas or {}
    esc = ctx.escala(escala_id)
    ids = {p.militar_id for p in esc.membros}
    refs = [ctx.escala(r) for r in esc.referencias if any(e.id == r for e in ctx.escalas)]
    card = "".join(f"<div class='k'><span>{escape(k)}</span><b>{escape(v)}</b></div>"
                   for k, v in info_escala(ctx, esc))
    linhas, obs = "", []
    for m in sorted((m for m in ctx.militares if m.id in ids), key=lambda m: m.antiguidade):
        cel = ""
        for d in dias:
            tags = []
            dia = res.dia(d, esc.id)
            for a in (dia.alocacoes if dia else []):
                if a.militar_id == m.id and a.origem != "falta":
                    tags.append(_tag(a.sigla, horarios_curtos(a.horarios)))
                    if (d, m.id) in abertas and a.origem == "normal":
                        tags.append('<span class="pisca" title="Aberto a troca de serviço"></span>')
                    if a.obs and a.origem != "normal":
                        obs.append((d, f"{m.nome}: {a.obs}"))
                elif a.militar_id == m.id:
                    tags.append(_tag(FALTA))
                    obs.append((d, f"{m.nome}: {a.obs}"))
            for r in refs:  # de serviço numa escala de referência (prevalece)
                dr = res.dia(d, r.id)
                for a in (dr.alocacoes if dr else []):
                    if a.militar_id == m.id and a.origem != "falta":
                        tags.append(_tag(a.sigla, r.nome, "ref"))
            if not tags and (s := _sigla_imp(ctx, m.id, d)):
                tags.append(_tag(s))
            cel += f"<td>{''.join(tags)}</td>"
        linhas += f"<tr><th class='nome'>{escape(m.posto)} {escape(m.nome)}</th>{cel}</tr>"
    # retém do dia (e descrição de eventos)
    ret, desc = "", ""
    for d in dias:
        dia = res.dia(d, esc.id)
        if not dia or not dia.funciona:
            ret += "<td class='para'>não guarnece</td>"
            desc += "<td></td>"
        else:
            nomes = [f"{_tag(a.sigla)} {escape(ctx.militar(a.militar_id).nome)}" for a in dia.retens]
            ret += f"<td>{'<br>'.join(nomes) or '–'}</td>"
            desc += f"<td><small>{escape(dia.descricao)}</small></td>"
    extra_desc = f"<tr><th class='nome'>Evento</th>{desc}</tr>" if esc.modo == "eventos" else ""
    sigla = sigla_base(esc)
    leg = " ".join(_tag(s) + f" {escape(t)}" for s, t in LEGENDA_FIXA)
    if sigla != SVC:
        leg = _tag(sigla) + f" {escape(CATEGORIAS.get(esc.categoria, ('', ''))[0] or 'Escalação')} " + leg
    obs_html = "".join(f"<li><b>{d:%d/%m}</b> – {escape(t)}</li>" for d, t in sorted(set(obs)))
    if abertas:
        leg += ' <span class="pisca"></span> aberto a troca de serviço'
    return f"""<style>
.card{{border:1px solid #d0d7de;border-left:6px solid #1f6feb;border-radius:8px;padding:10px 14px;margin-bottom:10px;font:13px sans-serif;background:#f6f8fa}}
.card h3{{margin:0 0 6px;font-size:18px}} .card .grid{{display:flex;flex-wrap:wrap;gap:6px 22px}}
.k span{{display:block;color:#57606a;font-size:11px;text-transform:uppercase}} .k b{{font-size:14px}}
.prev{{border-collapse:collapse;font:12px sans-serif}} .prev th,.prev td{{border:1px solid #d0d7de;padding:3px 4px;text-align:center;white-space:nowrap}}
.prev th.util{{background:#f6f8fa}} .prev th.folga{{background:#ffd8d8}} .prev th.roxa{{background:#d8c4f5}}
.prev th.nome{{text-align:left;background:#f6f8fa;position:sticky;left:0}}
.prev td.para{{color:#8b949e;font-style:italic}}
.t{{display:inline-block;border-radius:4px;padding:1px 5px;margin:1px;font-weight:600}} .t small{{font-weight:400}}
.t.ref{{opacity:.55;outline:1px dashed #57606a}}
.pisca{{display:inline-block;width:10px;height:10px;border-radius:50%;background:#2da44e;margin-left:3px;vertical-align:middle;animation:pisca 1s infinite}}
@keyframes pisca{{0%,100%{{opacity:1;box-shadow:0 0 0 0 rgba(45,164,78,.7)}}50%{{opacity:.25;box-shadow:0 0 0 5px rgba(45,164,78,0)}}}}
</style>
<div class="card"><h3>{escape(esc.nome)}{' · ' + escape(esc.tipo) if esc.tipo else ''}</h3><div class="grid">{card}</div></div>
<div style="overflow-x:auto"><table class="prev"><tr><th></th>{_cabecalho_dias(ctx, dias)}</tr>{linhas}
<tr><th colspan="{len(dias) + 1}" style="background:#eaeef2;text-align:left">Retém do dia</th></tr>
<tr><th class='nome'>RT</th>{ret}</tr>{extra_desc}</table></div>
<p>{leg}{' <i>(tag tracejada = militar de serviço numa escala de referência)</i>' if refs else ''}</p>
<h4>Observações</h4><ul>{obs_html or '<li>Sem trocas ou ocorrências no período.</li>'}</ul>"""

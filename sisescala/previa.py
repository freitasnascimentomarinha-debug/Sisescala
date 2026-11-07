"""Prévia de UMA escala por vez: card de destaque + tabela de calendário com siglas e cores."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

from .calendario import dia_util, nome_dia_nao_util, roxa_do_dia
from .modelos import (CATEGORIAS, CURSO, DBQ, DISP, DTQ, FERIAS, SVC, TIPOS_IMPEDIMENTO, Contexto, Escala,
                      horarios_curtos)
from .motor import Resultado, _folgas, sigla_base

CORES = {  # sigla base -> (fundo, texto)
    "SVÇ": ("#4B6A2B", "#fff"), "RT": ("#6B7360", "#fff"),
    "PAL": ("#2F6F8F", "#fff"), "CUR": ("#4F7387", "#fff"), "VIS": ("#7D5B2C", "#fff"),
    "CER": ("#8A4B2A", "#fff"), "APO": ("#3B7A46", "#fff"), "OUT": ("#5A5F4F", "#fff"),
    FERIAS: ("#2F7D4F", "#fff"), DISP: ("#3F7F78", "#fff"), DBQ: ("#A8452F", "#fff"),
    CURSO: ("#4F7387", "#fff"),
    DTQ: ("#7A5C86", "#fff"),
}
COR_TF, COR_T = ("#C9992F", "#1B1405"), ("#8B6B3F", "#fff")

LEGENDA_FIXA = [
    ("SVÇ", "Serviço"), ("SVÇ (TF)", "Serviço por troca forçada"), ("SVÇ (T)", "Serviço por troca consensual"),
    ("RT", "Retém"), ("RT (TF)", "Troca forçada de retém"), (FERIAS, "Férias"), (DISP, "Dispensado (baixa, falta ou dispensa)"),
    (DBQ, "Desembarque"), (CURSO, "Curso"), (DTQ, "Destaque"),
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
           ("Militares na escala", str(len(ctx.escalaveis(esc))))]
    if esc.quartos:
        q = esc.quartos[0]
        inf.append(("Quartos", f"{len(esc.quartos)} de {(int(q.fim[:2]) - int(q.inicio[:2])) % 24 or 24}h"))
    if esc.modo != "eventos":
        inf.append(("Funciona", "todos os dias" if esc.funciona_em == "todos" else "só em dias úteis"))
    if esc.dono_id:
        inf.append(("Responsável", donos.get(esc.dono_id, esc.dono_id)))
    if esc.detalhista_id:
        inf.append(("Detalhista", ctx.militar(esc.detalhista_id).nome + (" (concorre)" if esc.detalhista_escalavel else " (fora da escala)")))
    if esc.auxiliares:
        inf.append(("Auxiliares" if len(esc.auxiliares) > 1 else "Auxiliar",
                    ", ".join(ctx.militar(a).nome for a in esc.auxiliares)))
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


def html_previa(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, abertas=None,
                com_card: bool = True) -> str:
    abertas = abertas or {}
    esc = ctx.escala(escala_id)
    ids = set(ctx.escalaveis(esc))           # detalhista não é escalado: não aparece na prévia
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
                elif a.militar_id == m.id:           # dispensado do serviço em que estava escalado
                    tags.append(_tag(DISP))
                    obs.append((d, f"{m.nome}: {a.obs}"))
            for r in refs:  # de serviço numa escala de referência (prevalece)
                dr = res.dia(d, r.id)
                for a in (dr.alocacoes if dr else []):
                    if a.militar_id == m.id and a.origem != "falta":
                        tags.append(_tag(a.sigla, r.nome, "ref"))
            if not tags and (s := _sigla_imp(ctx, m.id, d)):
                tags.append(_tag(s))
            cel += f"<td data-d='{d.isoformat()}' data-m='{m.id}'>{''.join(tags)}</td>"
        linhas += f"<tr><th class='nome'>{escape(m.posto)} {escape(m.nome)}</th>{cel}</tr>"
    for i in ctx.impedimentos:
        if i.tipo in ("dispensa", "dispensa_justificada", "baixa") and i.militar_id in ids and i.motivo \
                and any(i.cobre(d) for d in dias):
            fim = f"–{i.fim:%d/%m}" if i.fim else ""
            obs.append((max(i.inicio, dias[0]), f"{ctx.militar(i.militar_id).nome}: Dispensado ({i.inicio:%d/%m}{fim}): {i.motivo}"))
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
body,.prev,.card{{font-family:'Inter','Segoe UI',system-ui,sans-serif}}
body{{font-size:12.5px;color:#D3D0BC;margin:0;background:transparent}} p,li{{font-size:12.5px;line-height:1.9}}
h4{{font-size:13px;margin:14px 0 4px;color:#EFEBDD}} ul{{margin:4px 0 0 18px;padding:0}} b{{color:#EFEBDD}}
.card{{border:1px solid #323D24;border-left:6px solid #7FA24A;border-radius:12px;padding:10px 14px;margin-bottom:10px;font-size:13px;background:#192012}}
.card h3{{margin:0 0 6px;font-size:18px;color:#EFEBDD}} .card .grid{{display:flex;flex-wrap:wrap;gap:6px 22px}}
.k span{{display:block;color:#9AA183;font-size:11px;text-transform:uppercase}} .k b{{font-size:14px}}
.prev{{border-collapse:separate;border-spacing:0;font-size:12px;border:1px solid #323D24;border-radius:12px;overflow:hidden;background:#141A0E}}
.prev th,.prev td{{border-bottom:1px solid #2A3420;border-right:1px solid #2A3420;padding:5px 6px;text-align:center;white-space:nowrap}}
.prev th{{font-weight:700;color:#D3D0BC;background:#1F2817}} .prev th.util{{background:#1F2817}}
.prev th.folga{{background:rgba(239,68,68,.20);color:#F0B09A}} .prev th.roxa{{background:rgba(160,130,70,.28);color:#E3D3A8}}
.prev th.nome{{text-align:left;background:#192012;position:sticky;left:0;color:#EFEBDD}}
.prev td.para{{color:#9AA183;font-style:italic}}
.prev td[data-d]{{cursor:pointer}} .prev td[data-d]:hover{{background:rgba(127,162,74,.14)}}
.prev td.sel{{outline:2px solid #A3C265;outline-offset:-2px;background:rgba(127,162,74,.26)}}
.t{{display:inline-block;border-radius:7px;padding:2px 7px;margin:1px;font-weight:600}} .t small{{font-weight:400}}
.t.ref{{opacity:.6;outline:1px dashed #9AA183}}
.pisca{{display:inline-block;width:10px;height:10px;border-radius:50%;background:#B6F34A;margin-left:3px;vertical-align:middle;animation:pisca 1s infinite}}
@keyframes pisca{{0%,100%{{opacity:1;box-shadow:0 0 0 0 rgba(182,243,74,.75)}}50%{{opacity:.25;box-shadow:0 0 0 5px rgba(182,243,74,0)}}}}
</style>
{f"""<div class="card"><h3>{escape(esc.nome)}{' · ' + escape(esc.tipo) if esc.tipo else ''}</h3><div class="grid">{card}</div></div>""" if com_card else ""}
<div style="overflow-x:auto"><table class="prev"><tr><th></th>{_cabecalho_dias(ctx, dias)}</tr>{linhas}
<tr><th colspan="{len(dias) + 1}" style="background:#1F2817;color:#9AA183;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em">Retém do dia</th></tr>
<tr><th class='nome'>RT</th>{ret}</tr>{extra_desc}</table></div>
<p>{leg}{' <i>(tag tracejada = militar de serviço numa escala de referência)</i>' if refs else ''}</p>
<h4>Observações</h4><ul>{obs_html or '<li>Sem trocas ou ocorrências no período.</li>'}</ul>"""

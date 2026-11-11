"""Prévia de UMA escala por vez: card de destaque + tabela de calendário com siglas e cores."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

from .calendario import dia_util, nome_dia_nao_util, roxa_do_dia
from .modelos import (CATEGORIAS, CURSO, formatar_nip, rotulo_militar, DBQ, DISP, DTQ, FERIAS, SVC, TIPOS_IMPEDIMENTO, Contexto, Escala,
                      horarios_curtos)
from .motor import Resultado, _folgas, sigla_base

CORES = {  # sigla base -> (fundo, texto)
    "SVÇ": ("#4B6A2B", "#fff"), "RT": ("#6B7360", "#fff"),
    "PAL": ("#2F6F8F", "#fff"), "CUR": ("#4F7387", "#fff"), "VIS": ("#7D5B2C", "#fff"),
    "CER": ("#8A4B2A", "#fff"), "APO": ("#3B7A46", "#fff"), "OUT": ("#5A5F4F", "#fff"),
    FERIAS: ("#C23B3B", "#fff"), DISP: ("#3F7F78", "#fff"), DBQ: ("#0B0B0B", "#fff"),   # férias vermelho, DBQ preto
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
    borda = "border:1px solid #8A8F78;" if bg == "#0B0B0B" else ""        # a etiqueta preta precisa de contorno no fundo escuro
    txt = escape(sigla) + (f" <small>{escape(extra)}</small>" if extra else "")
    return f'<span class="t {cls}" style="background:{bg};color:{fg};{borda}">{txt}</span>'


def _nome_html(m) -> str:
    """Coluna de nomes: `2ºSG-PL Freitas` e, embaixo, o NIP (11.0316.11)."""
    nip = f"<small>({escape(formatar_nip(m.nip))})</small>" if (m.nip or "").strip() else ""
    return f"{escape(rotulo_militar(m, com_nip=False))}{nip}"


def _sigla_imp(ctx: Contexto, mid: str, d: date) -> str | None:
    for i in ctx.impedimentos:
        if i.militar_id == mid and i.cobre(d):
            return TIPOS_IMPEDIMENTO[i.tipo]
    return None


def resumo_escala(ctx: Contexto, esc: Escala, dias: list[date], hoje: date | None = None) -> dict:
    """Saúde da escala: quantos disponíveis para cada vaga de serviço ("N x 1": cada um volta a servir a cada N dias
    se todos os disponíveis de hoje entrarem na fila), quem está impedido (férias, curso, dispensa, desembarque,
    destaque...) hoje e no período, e quando volta o primeiro impedido."""
    hoje = hoje or date.today()
    ids = set(ctx.escalaveis(esc))
    vagas = max(1, esc.militares_dia)
    imps = [i for i in ctx.impedimentos if i.militar_id in ids]
    hoje_ids = {i.militar_id for i in imps if i.cobre(hoje)}
    periodo_ids, por_tipo = set(), {}
    for i in imps:
        if any(i.cobre(d) for d in dias):
            periodo_ids.add(i.militar_id)
            por_tipo.setdefault(TIPOS_IMPEDIMENTO[i.tipo], set()).add(i.militar_id)
    disp_hoje = len(ids) - len(hoje_ids)
    # pior dia do período: menos disponíveis por vaga
    pior_d, pior_disp = min(((d, len(ids) - len({i.militar_id for i in imps if i.cobre(d)})) for d in dias),
                            key=lambda t: t[1], default=(None, len(ids)))
    retornos = sorted(i.fim + timedelta(days=1) for i in imps if i.cobre(hoje) and i.fim)
    return {"folgas": _folgas(esc), "minimo": _folgas(esc) + 1, "militares": len(ids), "vagas": vagas,
            "impedidos_hoje": len(hoje_ids), "impedidos_periodo": len(periodo_ids), "disponiveis_hoje": disp_hoje,
            "ritmo_hoje": round(disp_hoje / vagas, 1), "ritmo_pior": round(pior_disp / vagas, 1), "pior_dia": pior_d,
            "proximo_retorno": retornos[0] if retornos else None,
            "voltam_no_dia": sum(1 for r in retornos if retornos and r == retornos[0]),
            "por_tipo": {k: len(v) for k, v in sorted(por_tipo.items())}}


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


def _classe_do_dia(ctx: Contexto, d: date, esc) -> str:
    """Como o dia conta para a coluna da tabela: roxa, útil (preta) ou folga (vermelha)."""
    if esc.participa_roxa and roxa_do_dia(d, ctx, esc):
        return "roxa"
    return "util" if dia_util(d, ctx, esc) else "folga"


def _cabecalho_dias(ctx: Contexto, dias: list[date], esc=None, res=None, ancora: date | None = None) -> str:
    cab = ""
    for d in dias:
        nome = nome_dia_nao_util(d, ctx, esc)
        classe = _classe_do_dia(ctx, d, esc)
        dow = "SEG TER QUA QUI SEX SÁB DOM".split()[d.weekday()]
        dia = res.dia(d, esc.id) if (res is not None and esc is not None) else None
        sem = res is not None and (dia is None or not dia.funciona)
        legenda = nome or ("não guarnece" if sem else "")
        marca = " data-ancora" if d == ancora else ""
        classe += " pas" if (ancora and d < ancora) else ""
        cab += (f'<th class="{classe}"{marca} title="{escape(legenda)}">{d:%d/%m}<br>{dow}'
                f'{"<br><small>" + escape(legenda) + "</small>" if legenda else ""}</th>')
    return cab


def html_previa(ctx: Contexto, res: Resultado, dias: list[date], escala_id: str, abertas=None,
                com_card: bool = True, ancora: date | None = None) -> str:
    """`ancora`: primeiro dia "de hoje em diante". Os dias de `dias` anteriores a ele aparecem esmaecidos, à esquerda,
    e a tabela abre rolada até a âncora; o scroll para trás mostra os dias que já passaram."""
    abertas = abertas or {}
    esc = ctx.escala(escala_id)
    ids = set(ctx.escalaveis(esc))           # detalhista não é escalado: não aparece na prévia
    refs = [ctx.escala(r) for r in esc.referencias if any(e.id == r for e in ctx.escalas)]
    card = "".join(f"<div class='k'><span>{escape(k)}</span><b>{escape(v)}</b></div>"
                   for k, v in info_escala(ctx, esc))
    linhas, obs = "", []
    for m in sorted((m for m in ctx.militares if m.id in ids), key=lambda m: ctx.antig(esc, m.id)):
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
            classe_td = _classe_do_dia(ctx, d, esc) + ("" if (dia and dia.funciona) else " sem") \
                + (" pas" if (ancora and d < ancora) else "")
            cel += f"<td class='{classe_td}' data-d='{d.isoformat()}' data-m='{m.id}'>{''.join(tags)}</td>"
        linhas += f"<tr><th class='nome'>{_nome_html(m)}</th>{cel}</tr>"
    for i in ctx.impedimentos:
        if i.tipo in ("dispensa", "dispensa_justificada", "baixa") and i.militar_id in ids and i.motivo \
                and any(i.cobre(d) for d in dias):
            fim = f"–{i.fim:%d/%m}" if i.fim else ""
            obs.append((max(i.inicio, dias[0]), f"{ctx.militar(i.militar_id).nome}: Dispensado ({i.inicio:%d/%m}{fim}): {i.motivo}"))
    # descrição dos eventos (o retém já aparece na própria tabela, na linha de cada militar)
    desc = ""
    for d in dias:
        dia = res.dia(d, esc.id)
        desc += ("<td></td>" if (not dia or not dia.funciona) else f"<td><small>{escape(dia.descricao)}</small></td>")
    extra_desc = f"<tr><th class='nome'>Evento</th>{desc}</tr>" if esc.modo == "eventos" else ""
    sigla = sigla_base(esc)
    leg = " ".join(_tag(s) + f" {escape(t)}" for s, t in LEGENDA_FIXA)
    if sigla != SVC:
        leg = _tag(sigla) + f" {escape(CATEGORIAS.get(esc.categoria, ('', ''))[0] or 'Escalação')} " + leg
    obs_html = "".join(f"<li><b>{d:%d/%m}</b> – {escape(t)}</li>" for d, t in sorted(set(obs)))
    if abertas:
        leg += ' <span class="pisca"></span> aberto a troca de serviço'
    # larguras: a tabela ocupa a largura disponível (7, 15 ou 30 dias), colunas de dias iguais; com muitos dias ganha
    # largura mínima por dia e rola na horizontal só se não couber
    n = len(dias)
    nv = len([d for d in dias if not ancora or d >= ancora]) or n      # dias visíveis sem rolar
    nome_w, dia_min = 132, (96 if nv <= 7 else 48 if nv <= 15 else 52)
    larg_min = nome_w + dia_min * n
    colgrupo = f'<colgroup><col style="width:{nome_w}px">' + f'<col style="width:calc((100% - {nome_w}px) / {n})">' * n + '</colgroup>'
    larg = f"calc((100% - {nome_w}px) * {n} / {nv} + {nome_w}px)"
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
body,.prev,.card{{font-family:'Inter','Segoe UI',system-ui,sans-serif}}
body{{font-size:12.5px;color:#D3D0BC;margin:0;background:transparent}} p,li{{font-size:12.5px;line-height:1.9}}
h4{{font-size:13px;margin:14px 0 4px;color:#EFEBDD}} ul{{margin:4px 0 0 18px;padding:0}} b{{color:#EFEBDD}}
.card{{border:1px solid #323D24;border-left:6px solid #7FA24A;border-radius:12px;padding:10px 14px;margin-bottom:10px;font-size:13px;background:#192012}}
.card h3{{margin:0 0 6px;font-size:18px;color:#EFEBDD}} .card .grid{{display:flex;flex-wrap:wrap;gap:6px 22px}}
.k span{{display:block;color:#9AA183;font-size:11px;text-transform:uppercase}} .k b{{font-size:14px}}
.prev{{border-collapse:separate;border-spacing:0;font-size:12px;border:1px solid #323D24;border-radius:12px;overflow:hidden;background:#141A0E;
  width:100%;table-layout:fixed}}
.prev th small{{display:block;font-weight:400;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.prev.dens .t{{display:block;padding:2px 2px;font-size:10.5px;line-height:1.15;text-align:center;margin:2px auto;max-width:100%;overflow:hidden}}
.prev.dens .t small{{display:block;font-size:9px}}
.prev.dens th,.prev.dens td{{padding:4px 2px}}
.prev th,.prev td{{border-bottom:1px solid #2A3420;border-right:1px solid #2A3420;padding:5px 6px;text-align:center;white-space:nowrap}}
.prev th{{font-weight:700;color:#D3D0BC;background:#1F2817}} .prev th.util{{background:#1F2817}}
.prev th.folga{{background:rgba(239,68,68,.20);color:#F0B09A}} .prev th.roxa{{background:rgba(160,130,70,.28);color:#E3D3A8}}
.prev th.nome{{text-align:left;background:#192012;position:sticky;left:0;color:#EFEBDD;overflow:hidden;text-overflow:ellipsis;white-space:normal;line-height:1.25}}
.prev th.nome small{{white-space:nowrap}}
.prev td.folga{{background:rgba(239,68,68,.11)}} .prev td.roxa{{background:rgba(160,130,70,.16)}}
.prev td.sem{{background-image:repeating-linear-gradient(135deg,rgba(255,255,255,.035) 0 6px,transparent 6px 12px)}}
.prev .pas{{opacity:.55}}
.prev td.para{{color:#9AA183;font-style:italic}}
.prev td[data-d]{{cursor:pointer}} .prev td[data-d]:hover{{background:rgba(127,162,74,.14)}}
.prev td.sel{{outline:2px solid #A3C265;outline-offset:-2px;background:rgba(127,162,74,.26)}}
.t{{display:inline-block;border-radius:7px;padding:2px 7px;margin:1px;font-weight:600}} .t small{{font-weight:400}}
.t.ref{{opacity:.6;outline:1px dashed #9AA183}}
.pisca{{display:inline-block;width:10px;height:10px;border-radius:50%;background:#B6F34A;margin-left:3px;vertical-align:middle;animation:pisca 1s infinite}}
@keyframes pisca{{0%,100%{{opacity:1;box-shadow:0 0 0 0 rgba(182,243,74,.75)}}50%{{opacity:.25;box-shadow:0 0 0 5px rgba(182,243,74,0)}}}}
</style>
{f"""<div class="card"><h3>{escape(esc.nome)}{' · ' + escape(esc.tipo) if esc.tipo else ''}</h3><div class="grid">{card}</div></div>""" if com_card else ""}
<div style="overflow-x:auto"><table class="prev{' dens' if nv > 7 else ''}" style="min-width:{larg_min}px;width:{larg}">{colgrupo}<tr><th></th>{_cabecalho_dias(ctx, dias, esc, res, ancora)}</tr>{linhas}
{extra_desc}</table></div>
<p>{leg}{' <i>(tag tracejada = militar de serviço numa escala de referência)</i>' if refs else ''}</p>
<h4>Observações</h4><ul>{obs_html or '<li>Sem trocas ou ocorrências no período.</li>'}</ul>"""

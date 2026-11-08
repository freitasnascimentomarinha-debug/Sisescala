"""Calendário: dias úteis, feriados (nacional/estadual automáticos + manuais), roxa."""
from __future__ import annotations

from datetime import date

import holidays

from .modelos import Contexto

_cache: dict[tuple[str, int], dict[date, str]] = {}


def feriados_oficiais(ano: int, uf: str | None) -> dict[date, str]:
    chave = (uf or "", ano)
    if chave not in _cache:
        h = holidays.country_holidays("BR", subdiv=uf or None, years=ano, language="pt_BR")
        _cache[chave] = dict(h.items())
    return _cache[chave]


def pontos_facultativos(ano: int, uf: str | None) -> dict[date, str]:
    """Sugestões (não entram automaticamente): o comando decide e lança como dia especial."""
    h = holidays.country_holidays(
        "BR", subdiv=uf or None, years=ano, categories=("optional",), language="pt_BR")
    return dict(h.items())


def uf_da_escala(ctx: Contexto, esc=None) -> str:
    """UF usada nos feriados estaduais: a da escala (OM) ou, se vazia, a padrão do sistema."""
    return (esc.uf if esc is not None and esc.uf else ctx.uf)


def _especiais_do_dia(d: date, ctx: Contexto, esc=None) -> list:
    """Dias/períodos especiais que valem neste dia para a escala (os da própria escala antes dos gerais)."""
    achados = [e for e in ctx.dias_especiais if e.abrange(d) and (not e.escala_id or (esc is not None and e.escala_id == esc.id))]
    return sorted(achados, key=lambda e: 0 if e.escala_id else 1)


def nome_dia_nao_util(d: date, ctx: Contexto, esc=None) -> str | None:
    """Feriado ou dia sem expediente (período ou dia). Com `escala_id` vale só para essa escala; sem, vale para todas."""
    for e in _especiais_do_dia(d, ctx, esc):
        return e.descricao or ("Feriado" if e.tipo == "feriado" else "Sem expediente")
    return feriados_oficiais(d.year, uf_da_escala(ctx, esc)).get(d)


def conta_como(d: date, ctx: Contexto, esc=None) -> str:
    """Como o dia conta para a fila da escala: "preta" (útil), "vermelha" (sáb, dom, feriado, sem expediente) ou "roxa"."""
    if roxa_do_dia(d, ctx, esc):
        return "roxa"
    return "preta" if dia_util(d, ctx, esc) else "vermelha"


def dia_util(d: date, ctx: Contexto, esc=None) -> bool:
    for e in _especiais_do_dia(d, ctx, esc):          # o lançamento pode forçar a classe do dia
        if e.conta_como == "preta":
            return True
        if e.conta_como == "vermelha":
            return False
    return d.weekday() < 5 and nome_dia_nao_util(d, ctx, esc) is None


def roxa_do_dia(d: date, ctx: Contexto, esc=None):
    """Período roxo que cobre o dia. Com `esc`, só os da escala e os gerais (sem escala)."""
    return next((r for r in ctx.roxas if r.inicio <= d <= r.fim
                 and (esc is None or not r.escala_id or r.escala_id == esc.id)), None)

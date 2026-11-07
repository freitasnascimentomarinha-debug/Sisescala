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


def nome_dia_nao_util(d: date, ctx: Contexto) -> str | None:
    for e in ctx.dias_especiais:
        if e.data == d:
            return e.descricao or ("Feriado" if e.tipo == "feriado" else "Sem expediente")
    return feriados_oficiais(d.year, ctx.uf).get(d)


def dia_util(d: date, ctx: Contexto) -> bool:
    return d.weekday() < 5 and nome_dia_nao_util(d, ctx) is None


def roxa_do_dia(d: date, ctx: Contexto):
    return next((r for r in ctx.roxas if r.inicio <= d <= r.fim), None)

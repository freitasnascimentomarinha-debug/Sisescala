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


def nome_dia_nao_util(d: date, ctx: Contexto, esc=None) -> str | None:
    """Feriado ou dia sem expediente. Dia especial com `escala_id` vale só para essa escala; sem, vale para todas."""
    for e in ctx.dias_especiais:
        if e.data == d and (not e.escala_id or (esc is not None and e.escala_id == esc.id)):
            return e.descricao or ("Feriado" if e.tipo == "feriado" else "Sem expediente")
    return feriados_oficiais(d.year, uf_da_escala(ctx, esc)).get(d)


def dia_util(d: date, ctx: Contexto, esc=None) -> bool:
    return d.weekday() < 5 and nome_dia_nao_util(d, ctx, esc) is None


def roxa_do_dia(d: date, ctx: Contexto):
    return next((r for r in ctx.roxas if r.inicio <= d <= r.fim), None)

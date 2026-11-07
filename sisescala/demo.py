"""Dados de demonstração (substituídos pelo repositório Sheets/PostgreSQL)."""
from __future__ import annotations

from datetime import date

from .modelos import (Contexto, Escala, Militar, Pertinencia, PeriodoRoxa, quartos_padrao)

POSTOS = ["CMG", "CF", "CC", "CT", "1T", "2T", "SO", "1SG", "2SG", "3SG", "CB", "CB", "MN", "MN", "MN"]


def contexto_demo(base: date | None = None) -> Contexto:
    base = base or date.today()
    mil = [Militar(f"m{i}", f"Militar {i:02d}", POSTOS[i - 1], i) for i in range(1, 16)]
    ids = [m.id for m in mil]
    escalas = [
        Escala("per", "Pernoite", "PER", prioridade=5, modo="preta_vermelha", funciona_em="todos",
               militares_dia=3, quartos=quartos_padrao(4), membros=[Pertinencia(i) for i in ids[:10]]),
        Escala("dia", "Diária", "DIA", prioridade=1, modo="preta_vermelha", funciona_em="uteis",
               militares_dia=1, membros=[Pertinencia(i) for i in ids[4:]]),
    ]
    return Contexto(mil, escalas, base, roxas=[PeriodoRoxa(
        "fa", "Recesso de fim de ano", date(base.year, 12, 24), date(base.year + 1, 1, 2))])

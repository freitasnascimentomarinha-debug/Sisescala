"""Validação e normalização de contato (e-mail, ramal, celular)."""
from __future__ import annotations

import re

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def normalizar_celular(txt: str) -> str:
    d = re.sub(r"\D", "", txt or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    raise ValueError("celular inválido: informe DDD + número (10 ou 11 dígitos)")


def normalizar_contato(email: str, ramal: str, celular: str, obrigatorio: bool = True) -> tuple[str, str, str]:
    """Retorna (email, ramal, celular) normalizados. Com `obrigatorio`, os três são exigidos."""
    email, ramal, celular = (email or "").strip().lower(), (ramal or "").strip(), (celular or "").strip()
    erros = []
    if not email and not obrigatorio:
        pass
    elif not _EMAIL.match(email):
        erros.append("e-mail inválido")
    if ramal:
        r = re.sub(r"\D", "", ramal)
        if not 2 <= len(r) <= 8:
            erros.append("ramal inválido (2 a 8 dígitos)")
        ramal = r
    elif obrigatorio:
        erros.append("informe o ramal")
    if celular:
        try:
            celular = normalizar_celular(celular)
        except ValueError as ex:
            erros.append(str(ex))
    elif obrigatorio:
        erros.append("informe o celular")
    if erros:
        raise ValueError("; ".join(erros))
    return email, ramal, celular

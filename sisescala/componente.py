"""Componente Streamlit em JavaScript: prévia clicável.

O front-end fica em `componentes/previa/index.html` (JS puro, sem build). Ele desenha a tabela que o
Python gera (`html_previa`) e devolve ao Python qual célula foi clicada: {data, militar, ts}.
"""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_DIR = Path(__file__).resolve().parent.parent / "componentes" / "previa"
_componente = components.declare_component("previa_escala", path=str(_DIR))


def previa_interativa(html: str, selecionada: dict | None = None, key: str | None = None) -> dict | None:
    """Mostra a prévia e retorna o último clique ({data: 'AAAA-MM-DD', militar: id, ts: ms}) ou None."""
    return _componente(html=html, selecionada=selecionada, key=key, default=None)

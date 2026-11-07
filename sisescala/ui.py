"""Identidade visual do SisEscala: tema, ícones e componentes HTML reutilizáveis.

Tudo que o usuário digitou passa por `esc()` antes de ir para HTML.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
_ICONES = {  # traçados no estilo Lucide (ISC), 24x24, stroke currentColor
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
    "swap": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "check": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/><path d="M12 9v4M12 17h.01"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5M12 3v12"/>',
    "anchor": '<circle cx="12" cy="5" r="3"/><path d="M12 22V8M5 12H2a10 10 0 0 0 20 0h-3"/>',
    "home": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "undo": '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "key": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
}


COR_TOM = {"blue": "#60A5FA", "green": "#4ADE80", "amber": "#FBBF24", "red": "#F87171", "violet": "#A78BFA",
           "gray": "#A9B6CD", "white": "#FFFFFF", "muted": "#64748B"}


def icone(nome: str, tam: int | None = None, cor: str = "white") -> str:
    """Ícone como imagem embutida (o sanitizador do st.html remove <svg> inline)."""
    import base64
    c = COR_TOM.get(cor, cor)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" '
           f'stroke-linecap="round" stroke-linejoin="round">{_ICONES.get(nome, _ICONES["list"])}</svg>')
    b64 = base64.b64encode(svg.encode()).decode()
    lado = f"{tam}px" if tam else "100%"
    return f'<img alt="" src="data:image/svg+xml;base64,{b64}" style="width:{lado};height:{lado};display:block"/>'


def esc(txt) -> str:
    return escape(str(txt if txt is not None else ""))


def aplicar_tema() -> None:
    """Injeta a identidade visual (fonte, cores, cartões, menu). Chamada a cada execução."""
    css = (RAIZ / "assets" / "estilo.css").read_text("utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def iniciais(nome: str) -> str:
    p = [x for x in (nome or "?").replace(".", " ").split() if x]
    return (p[0][0] + (p[-1][0] if len(p) > 1 else "")).upper()


def avatar(nome: str) -> str:
    return f'<div class="avatar">{esc(iniciais(nome))}</div>'


TONS = {"azul": "blue", "verde": "green", "ambar": "amber", "vermelho": "red", "violeta": "violet", "cinza": "gray"}


def pill(texto: str, tom: str = "cinza", ponto: bool = True) -> str:
    t = TONS.get(tom, tom)
    return f'<span class="pill tone-{t}">{"<i></i>" if ponto else ""}{esc(texto)}</span>'


def chip(rotulo: str, valor: str = "") -> str:
    return f'<span class="chip">{esc(rotulo)}{f" <span>{esc(valor)}</span>" if valor != "" else ""}</span>'


def cabecalho(titulo: str, subtitulo: str = "", icon: str = "calendar", chips: list[str] | None = None) -> None:
    ch = f'<div class="ph-ch">{"".join(chips)}</div>' if chips else ""
    st.html(f'<div class="ph"><div class="ph-ic">{icone(icon, 24)}</div><div class="ph-tx"><h1>{esc(titulo)}</h1>'
            f'{f"<p>{esc(subtitulo)}</p>" if subtitulo else ""}</div>{ch}</div>')


def kpis(itens: list[tuple]) -> None:
    """itens: (rotulo, valor, icone, tom, nota)"""
    html = ""
    for it in itens:
        rotulo, valor, ic, tom = it[:4]
        nota = it[4] if len(it) > 4 else ""
        html += (f'<div class="kpi"><div class="kpi-ic tone-{TONS.get(tom, tom)}">{icone(ic, 22, TONS.get(tom, tom))}</div><div>'
                 f'<div class="kpi-n">{esc(valor)}</div><div class="kpi-l">{esc(rotulo)}</div>'
                 f'{f"<div class=kpi-s>{esc(nota)}</div>" if nota else ""}</div></div>')
    st.html(f'<div class="kpis">{html}</div>')


def secao(titulo: str) -> None:
    st.html(f'<div class="secao">{esc(titulo)}</div>')


def vazio(titulo: str, texto: str = "", icon: str = "inbox") -> None:
    st.html(f'<div class="vazio"><div style="width:34px;height:34px;margin:0 auto .4rem">{icone(icon, 34, "muted")}</div>'
            f'<b>{esc(titulo)}</b>{esc(texto)}</div>')


def campos(pares: list[tuple[str, str]]) -> None:
    st.html('<div class="grid2">' + "".join(
        f'<div class="f"><small>{esc(k)}</small><b>{esc(v) or "—"}</b></div>' for k, v in pares) + "</div>")


def pessoa(nome: str, linha1: str = "", linha2: str = "", selo: str = "") -> str:
    return (f'<div class="person">{avatar(nome)}<div style="flex:1"><b>{esc(nome)}</b>'
            f'<small>{esc(linha1)}</small>{f"<br><small>{esc(linha2)}</small>" if linha2 else ""}</div>{selo}</div>')


def linha_do_tempo(etapas: list[str], atual: int, falhou: bool = False) -> None:
    """Etapas já concluídas (verde), a atual (azul) e as próximas (cinza)."""
    html = ""
    for i, nome in enumerate(etapas):
        estado = "done" if i < atual else ("now" if i == atual else "")
        if falhou and i == atual:
            estado = "bad"
        marca = "✓" if estado == "done" else ("✕" if estado == "bad" else str(i + 1))
        html += f'<div class="step {estado}"><i>{marca}</i>{esc(nome)}</div>'
        if i < len(etapas) - 1:
            html += f'<div class="bar {"done" if i < atual else ""}"></div>'
    st.html(f'<div class="steps">{html}</div>')


def item_data(data, titulo: str, sub: str = "", selo: str = "") -> str:
    mes = "JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ".split()[data.month - 1]
    return (f'<div class="item"><div class="when"><small>{mes}</small>{data.day:02d}</div>'
            f'<div class="tx" style="flex:1"><b>{esc(titulo)}</b><span>{esc(sub)}</span></div>{selo}</div>')

"""Texto formatado (negrito, itálico, sublinhado, marcadores e numeração) dos campos do detalhe de serviço.

O editor da tela (componentes/editor) devolve HTML. Aqui esse HTML é **higienizado** (só um conjunto pequeno de
marcas, sem atributos) e convertido para o que cada saída entende: HTML seguro para a tela e marcação do reportlab
para o PDF. Texto simples (de antes do editor existir) continua valendo: quebras de linha viram linhas."""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

INLINE = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u"}
BLOCO = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr"}


class _Conv(HTMLParser):
    """Lê o HTML e monta uma lista de linhas; cada linha é uma lista de pedaços (texto, estilos) e um prefixo."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.linhas: list[dict] = []
        self.estilos: list[str] = []
        self.listas: list[list] = []        # pilha: ["ul"|"ol", contador]
        self._nova()

    def _nova(self, prefixo: str = "") -> None:
        self.linhas.append({"prefixo": prefixo, "partes": []})

    def _quebra(self) -> None:
        if self.linhas[-1]["partes"] or self.linhas[-1]["prefixo"]:
            self._nova()

    def handle_starttag(self, tag, attrs):
        if tag in INLINE:
            self.estilos.append(INLINE[tag])
        elif tag in ("ul", "ol"):
            self._quebra()
            self.listas.append([tag, 0])
        elif tag == "li":
            self._quebra()
            if self.listas:
                self.listas[-1][1] += 1
                lt, n = self.listas[-1]
                self.linhas[-1]["prefixo"] = "• " if lt == "ul" else f"{n}. "
        elif tag == "br":
            self._nova()
        elif tag in BLOCO:
            self._quebra()

    def handle_endtag(self, tag):
        if tag in INLINE and INLINE[tag] in self.estilos:
            self.estilos.remove(INLINE[tag])
        elif tag in ("ul", "ol"):
            if self.listas:
                self.listas.pop()
            self._quebra()
        elif tag in BLOCO:
            self._quebra()

    def handle_data(self, data):
        if data:
            self.linhas[-1]["partes"].append((data, tuple(dict.fromkeys(self.estilos))))


def _linhas(txt: str) -> list[dict]:
    if not re.search(r"<\s*/?\s*[a-zA-Z]", txt or ""):                 # texto simples
        txt = escape(txt or "").replace("\n", "<br>")
    c = _Conv()
    c.feed(txt or "")
    c.close()
    vistos = [ln for ln in c.linhas if ln["partes"] or ln["prefixo"]]
    while vistos and not "".join(t for t, _ in vistos[-1]["partes"]).strip() and not vistos[-1]["prefixo"]:
        vistos.pop()
    return vistos


def _fmt(partes, abre, fecha) -> str:
    out = ""
    for texto, est in partes:
        t = escape(texto)
        for e in est:
            t = f"{abre(e)}{t}{fecha(e)}"
        out += t
    return out


def vazio(txt: str) -> bool:
    return not any("".join(t for t, _ in ln["partes"]).strip() for ln in _linhas(txt))


def para_pdf(txt: str) -> str:
    """Marcação do reportlab (<b>, <i>, <u>, <br/>) já com os marcadores "• " e a numeração "1. "."""
    return "<br/>".join(ln["prefixo"] + _fmt(ln["partes"], lambda e: f"<{e}>", lambda e: f"</{e}>") for ln in _linhas(txt))


def para_html(txt: str) -> str:
    """HTML seguro para mostrar na tela (sem atributos, só b/i/u e quebras)."""
    return "<br>".join(escape(ln["prefixo"]) + _fmt(ln["partes"], lambda e: f"<{e}>", lambda e: f"</{e}>") for ln in _linhas(txt))


def para_editor(txt: str) -> str:
    """HTML higienizado para carregar no editor: listas voltam como <ul>/<ol> reais."""
    saida, aberta = [], ""
    for ln in _linhas(txt):
        pf = ln["prefixo"]
        tipo = "ul" if pf.startswith("•") else ("ol" if re.match(r"\d+\.", pf) else "")
        corpo = _fmt(ln["partes"], lambda e: f"<{e}>", lambda e: f"</{e}>")
        if aberta and aberta != tipo:
            saida.append(f"</{aberta}>")
            aberta = ""
        if tipo and not aberta:
            saida.append(f"<{tipo}>")
            aberta = tipo
        saida.append(f"<li>{corpo}</li>" if tipo else f"<div>{corpo or '<br>'}</div>")
    if aberta:
        saida.append(f"</{aberta}>")
    return "".join(saida)


def normalizar(txt: str) -> str:
    """O que se grava: o HTML higienizado (ou vazio)."""
    return "" if vazio(txt) else para_editor(txt)


def resumo(txt: str, n: int = 140) -> str:
    """Texto corrido curto para mostrar ao lado do botão."""
    plano = " ".join(ln["prefixo"] + "".join(t for t, _ in ln["partes"]) for ln in _linhas(txt)).strip()
    return plano if len(plano) <= n else plano[: n - 1].rstrip() + "…"

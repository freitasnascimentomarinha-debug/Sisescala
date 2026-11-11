"""Verificação das assinaturas eletrônicas do detalhista: o PDF traz um código (SHA-256 do conteúdo assinado) e um QR code;
a página "Verificar documento" (só para usuários logados) confere o código contra o registro gravado no sistema."""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import quote

from .modelos import AssinaturaDetalhe, Contexto

MIN_PREFIXO = 12          # aceita o código completo ou o começo dele (mínimo de caracteres, para não ser ambíguo)


def normalizar_codigo(txt: str) -> str:
    """Tira espaços, quebras e o prefixo 'SISESCALA-VERIFICAR:' (o que o leitor de QR code entrega) e põe em minúsculas."""
    t = re.sub(r"\s+", "", txt or "")
    t = re.sub(r"^.*[:=/]", "", t) if re.search(r"[:=/]", t) else t
    return t.lower()


def registrar(ctx: Contexto, usuario_id: str, escala_id: str, dias, corpo: str, codigo: str, nome: str, nip: str, om: str,
              agora: datetime | None = None, papel: str = "detalhista") -> AssinaturaDetalhe:
    """Grava a assinatura do detalhista (uma por código e usuário: assinar de novo o mesmo conteúdo não duplica)."""
    agora = agora or datetime.now()
    for a in ctx.assinaturas_detalhe:
        if a.codigo == codigo and a.usuario_id == usuario_id:
            return a
    a = AssinaturaDetalhe(codigo, escala_id, dias[0], dias[-1], usuario_id, nome, nip, om, agora, corpo, papel)
    ctx.assinaturas_detalhe.append(a)
    return a


def buscar(ctx: Contexto, codigo: str) -> AssinaturaDetalhe | None:
    c = normalizar_codigo(codigo)
    if len(c) < MIN_PREFIXO or not re.fullmatch(r"[0-9a-f]+", c):
        return None
    achadas = [a for a in ctx.assinaturas_detalhe if a.codigo.startswith(c)]
    return achadas[0] if len({a.codigo for a in achadas}) == 1 else None


def do_codigo(ctx: Contexto, codigo: str) -> list[AssinaturaDetalhe]:
    """Todas as assinaturas (detalhista e auxiliar) que cobrem exatamente este conteúdo, na ordem em que foram feitas."""
    return sorted((a for a in ctx.assinaturas_detalhe if a.codigo == codigo), key=lambda a: a.em)


def integra(a: AssinaturaDetalhe) -> bool:
    """O conteúdo gravado ainda gera o código assinado (o registro não foi alterado)."""
    import hashlib
    return hashlib.sha256(a.conteudo.encode()).hexdigest() == a.codigo


def descrever(ctx: Contexto, a: AssinaturaDetalhe) -> dict:
    """O que foi assinado, em forma legível: escala, período, textos e, por dia, quem estava escalado (com a sigla)."""
    try:
        c = json.loads(a.conteudo)
    except ValueError:
        return {"dias": [], "textos": ["", "", ""], "om": a.om, "assinantes": []}

    def nome(mid):
        m = ctx.militar(mid)
        return m.nome if m else mid
    dias = [(d, [(nome(mid), sig) for mid, sig in itens]) for d, itens in c.get("dias", [])]
    return {"escala": c.get("escala_nome", ""), "om": c.get("om", ""), "textos": c.get("textos", ["", "", ""]),
            "assinantes": c.get("assinantes", []), "dias": dias}


def url_de_verificacao(base: str, codigo: str) -> str:
    """Endereço que o QR code abre: a página de verificação com o código já preenchido ('' se não há endereço-base)."""
    base = (base or "").strip().split("?")[0].rstrip("/")
    if not base:
        return ""
    base = re.sub(r"/(escala|detalhe|verificar|painel|regras|papeletas|devolucoes|vinculos|conta)$", "", base)
    return f"{base}/verificar?codigo={quote(codigo)}"

"""Cadastro de militares: adicionar, editar, excluir (um ou vários) e vincular a escalas."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from .contatos import normalizar_contato
from .modelos import Contexto, Militar, Pertinencia
from .permissoes import PermissaoNegada, pode_editar


def _slug(txt: str) -> str:
    t = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "m"


def novo_id(ctx: Contexto, base: str) -> str:
    ids = {m.id for m in ctx.militares}
    cand, k = _slug(base), 2
    while cand in ids:
        cand, k = f"{_slug(base)}-{k}", k + 1
    return cand


def renumerar(ctx: Contexto) -> None:
    """Mantém a antiguidade única e sequencial (1 = mais antigo), preservando a ordem atual."""
    for i, m in enumerate(sorted(ctx.militares, key=lambda m: m.antiguidade), 1):
        m.antiguidade = i


def adicionar_militar(ctx: Contexto, nome: str, posto: str = "", nip: str = "", om: str = "",
                      antiguidade: int | None = None, email: str = "", ramal: str = "", celular: str = "",
                      detalhista: bool = False) -> Militar:
    if not nome.strip():
        raise ValueError("informe o nome de guerra")
    if nip and any(m.nip == nip for m in ctx.militares):
        raise ValueError(f"NIP {nip} já cadastrado")
    n = len(ctx.militares)
    pos = n + 1 if antiguidade is None else max(1, min(antiguidade, n + 1))
    for m in ctx.militares:
        if m.antiguidade >= pos:
            m.antiguidade += 1
    if email or ramal or celular:
        email, ramal, celular = normalizar_contato(email, ramal, celular, obrigatorio=False)
    novo = Militar(novo_id(ctx, nip or nome), nome.strip(), posto.strip(), pos, nip.strip(), om.strip(),
                   email, ramal, celular, detalhista)
    ctx.militares.append(novo)
    renumerar(ctx)
    return novo


def editar_militar(ctx: Contexto, mid: str, **campos) -> Militar:
    m = ctx.militar(mid)
    if "nip" in campos and campos["nip"] and any(o.nip == campos["nip"] and o.id != mid for o in ctx.militares):
        raise ValueError(f"NIP {campos['nip']} já cadastrado")
    for k in ("nome", "posto", "nip", "om"):
        if k in campos:
            setattr(m, k, str(campos[k]).strip())
    if "detalhista" in campos:
        m.detalhista = bool(campos["detalhista"])
    if any(k in campos for k in ("email", "ramal", "celular")):
        m.email, m.ramal, m.celular = normalizar_contato(
            campos.get("email", m.email), campos.get("ramal", m.ramal), campos.get("celular", m.celular),
            obrigatorio=False)
    if campos.get("antiguidade"):
        destino = max(1, min(int(campos["antiguidade"]), len(ctx.militares)))
        outros = sorted((o for o in ctx.militares if o.id != mid), key=lambda o: o.antiguidade)
        outros.insert(destino - 1, m)
        for i, o in enumerate(outros, 1):
            o.antiguidade = i
    return m


def _anterior_na_escala(ctx: Contexto, esc, mid: str) -> str | None:
    """Quem vem imediatamente antes de `mid` na ordem de antiguidade da escala (mantém a fila)."""
    ref = ctx.militar(mid).antiguidade
    cand = [ctx.militar(p.militar_id) for p in esc.membros if p.militar_id != mid]
    antes = [m for m in cand if m.antiguidade < ref]
    return max(antes, key=lambda m: m.antiguidade).id if antes else None


def _desvincular(ctx: Contexto, mid: str) -> None:
    for esc in ctx.escalas:
        for fila, u in list(esc.ultimo_servico.items()):
            if u == mid:
                ant = _anterior_na_escala(ctx, esc, mid)
                if ant:
                    esc.ultimo_servico[fila] = ant   # a fila segue de onde estava
                else:
                    del esc.ultimo_servico[fila]
        esc.membros = [p for p in esc.membros if p.militar_id != mid]


def excluir_militares(ctx: Contexto, ids: list[str], usuario_id: str | None = None) -> int:
    """Exclui do cadastro (todas as escalas). Se `usuario_id` for informado, só exclui quem
    pertence apenas a escalas que ele pode editar."""
    ids = [i for i in dict.fromkeys(ids) if any(m.id == i for m in ctx.militares)]
    if usuario_id is not None:
        for i in ids:
            for esc in ctx.escalas:
                if any(p.militar_id == i for p in esc.membros) and not pode_editar(ctx, usuario_id, esc):
                    raise PermissaoNegada(
                        f"{ctx.militar(i).nome} está na escala '{esc.nome}', que você não pode editar")
    for i in ids:
        _desvincular(ctx, i)
    alvo = set(ids)
    ctx.militares = [m for m in ctx.militares if m.id not in alvo]
    ctx.impedimentos = [x for x in ctx.impedimentos if x.militar_id not in alvo]
    ctx.ocorrencias = [x for x in ctx.ocorrencias if x.militar_id not in alvo]
    ctx.trocas = [t for t in ctx.trocas if t.saindo not in alvo and t.entrando not in alvo]
    renumerar(ctx)
    return len(ids)


def adicionar_a_escala(ctx: Contexto, escala_id: str, ids: list[str], desde: date | None = None) -> int:
    esc = ctx.escala(escala_id)
    n = 0
    for i in ids:
        ctx.militar(i)
        ativo = [p for p in esc.membros if p.militar_id == i and p.fim is None]
        if not ativo:
            esc.membros.append(Pertinencia(i, desde))
            n += 1
    return n


def remover_da_escala(ctx: Contexto, escala_id: str, ids: list[str], a_partir_de: date | None = None) -> int:
    """Com data: encerra a participação nessa data (mudou de escala). Sem data: remove de vez."""
    esc = ctx.escala(escala_id)
    n = 0
    for i in ids:
        if a_partir_de is None:
            antes = len(esc.membros)
            esc.membros = [p for p in esc.membros if p.militar_id != i]
            n += antes != len(esc.membros)
        else:
            for p in esc.membros:
                if p.militar_id == i and p.fim is None:
                    p.fim = a_partir_de
                    n += 1
    return n

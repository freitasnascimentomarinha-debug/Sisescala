"""Cadastro de militares: adicionar, editar, excluir (um ou vários) e vincular a escalas."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from .contatos import normalizar_contato
from .modelos import Contexto, Militar, Pertinencia
from .permissoes import PermissaoNegada, eh_detalhista


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
                      especialidade: str = "") -> Militar:
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
                   email, ramal, celular, especialidade.strip())
    ctx.militares.append(novo)
    renumerar(ctx)
    return novo


def editar_militar(ctx: Contexto, mid: str, **campos) -> Militar:
    m = ctx.militar(mid)
    if "nip" in campos and campos["nip"] and any(o.nip == campos["nip"] and o.id != mid for o in ctx.militares):
        raise ValueError(f"NIP {campos['nip']} já cadastrado")
    for k in ("nome", "posto", "nip", "om", "especialidade"):
        if k in campos:
            setattr(m, k, str(campos[k]).strip())
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
    ref = ctx.antig(esc, mid)
    antes = [i for i in ctx.ordem_na_escala(esc) if i != mid and ctx.antig(esc, i) < ref]
    return antes[-1] if antes else None


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
        ctx.numerar_escala(esc)


def excluir_militares(ctx: Contexto, ids: list[str], usuario_id: str | None = None) -> int:
    """Apaga militares do cadastro INTEIRO (baixo nível, com cascata). Com `usuario_id` (uso pela tela), só o
    administrador e só militares que não estão em nenhuma escala, sem conta vinculada e sem papeleta: tirar alguém de
    uma escala é `remover_da_escala`, não esta função."""
    ids = [i for i in dict.fromkeys(ids) if any(m.id == i for m in ctx.militares)]
    if usuario_id is not None:
        u = ctx.usuario(usuario_id)
        if not (u and u.admin and u.ativo):
            raise PermissaoNegada("só o administrador exclui militares do cadastro; para tirar da escala use "
                                  "\"Retirar da escala\"")
        for i in ids:
            nome = ctx.militar(i).nome
            if any(p.militar_id == i for e in ctx.escalas for p in e.membros):
                raise ValueError(f"{nome} ainda está em uma escala: retire-o dela antes de excluir do cadastro")
            if any(x.militar_id == i for x in ctx.usuarios):
                raise ValueError(f"{nome} está vinculado a uma conta: desvincule a conta antes")
            if any(i in (p.solicitante_id, p.outro_id) for p in ctx.papeletas):
                raise ValueError(f"{nome} tem papeletas registradas e não pode ser excluído; deixe-o fora das escalas")
    alvo = set(ids)
    for i in ids:
        _desvincular(ctx, i)
    for x in ctx.usuarios:                           # conta ligada a quem sumiu não pode ficar apontando para o vazio
        if x.militar_id in alvo:
            x.militar_id = ""
    for v in ctx.vinculos:
        if v.militar_id in alvo and v.status == "pendente":
            v.status = "cancelado"
    for c in ctx.convites_vinculo:
        if c.militar_id in alvo and c.status == "pendente":
            c.status = "cancelado"
    ctx.militares = [m for m in ctx.militares if m.id not in alvo]
    ctx.impedimentos = [x for x in ctx.impedimentos if x.militar_id not in alvo]
    ctx.ocorrencias = [x for x in ctx.ocorrencias if x.militar_id not in alvo]
    ctx.trocas = [t for t in ctx.trocas if t.saindo not in alvo and t.entrando not in alvo]
    renumerar(ctx)
    return len(ids)


def adicionar_a_escala(ctx: Contexto, escala_id: str, ids: list[str], desde: date | None = None,
                       posicao: int | None = None) -> int:
    """Entra na escala no FIM da antiguidade dela (ou na `posicao` pedida, 1 = mais antigo)."""
    esc = ctx.escala(escala_id)
    ctx.numerar_escala(esc)
    n = 0
    for i in ids:
        ctx.militar(i)
        ativo = [p for p in esc.membros if p.militar_id == i and p.fim is None]
        if not ativo:
            ja = ctx.ordem_na_escala(esc)
            esc.membros.append(Pertinencia(i, desde, None, 10 ** 6))      # provisório: vai para o fim
            n += 1
            if i in ja:                                                    # já esteve na escala: mantém o lugar antigo
                for p in esc.membros:
                    if p.militar_id == i:
                        p.antiguidade = ctx.antig(esc, i) if ctx.antig(esc, i) < 10 ** 6 else 0
            ctx.numerar_escala(esc)
    if posicao is not None and n:
        for i in ids:
            mover_na_escala(ctx, escala_id, i, posicao)
    return n


def definir_ordem(ctx: Contexto, escala_id: str, ids: list[str]) -> None:
    """Grava a ordem de antiguidade da escala (a lista tem de ter exatamente os membros dela)."""
    esc = ctx.escala(escala_id)
    ctx.numerar_escala(esc)
    if sorted(ids) != sorted(ctx.ordem_na_escala(esc)):
        raise ValueError("a lista não confere com os militares da escala; recarregue a página")
    pos = {i: k for k, i in enumerate(ids, 1)}
    for p in esc.membros:
        p.antiguidade = pos[p.militar_id]


def mover_na_escala(ctx: Contexto, escala_id: str, mid: str, posicao: int) -> None:
    """Muda a antiguidade do militar NESTA escala (as outras escalas não são afetadas)."""
    esc = ctx.escala(escala_id)
    ctx.numerar_escala(esc)
    ordem = ctx.ordem_na_escala(esc)
    if mid not in ordem:
        raise ValueError("o militar não está nesta escala")
    ordem.remove(mid)
    ordem.insert(max(1, min(int(posicao), len(ordem) + 1)) - 1, mid)
    for k, i in enumerate(ordem, 1):
        for p in esc.membros:
            if p.militar_id == i:
                p.antiguidade = k


def remover_da_escala(ctx: Contexto, escala_id: str, ids: list[str], a_partir_de: date | None = None) -> int:
    """Com data: encerra a participação nessa data (mudou de escala). Sem data: remove de vez."""
    esc = ctx.escala(escala_id)
    n = 0
    for i in ids:
        if a_partir_de is None:
            for fila, ult in list(esc.ultimo_servico.items()):      # a fila segue de onde estava
                if ult == i:
                    ant = _anterior_na_escala(ctx, esc, i)
                    if ant:
                        esc.ultimo_servico[fila] = ant
                    else:
                        del esc.ultimo_servico[fila]
            antes = len(esc.membros)
            esc.membros = [p for p in esc.membros if p.militar_id != i]
            n += antes != len(esc.membros)
        else:
            for p in esc.membros:
                if p.militar_id == i and p.fim is None:
                    p.fim = a_partir_de
                    n += 1
    ctx.numerar_escala(esc)
    return n

"""Central de avisos dentro do sistema (sem e-mail): quem precisa saber, sabe."""
from __future__ import annotations

from datetime import datetime, timedelta

from .modelos import Contexto, Notificacao

MAX_POR_USUARIO = 300
DIAS_LIDAS = 30


def _prox_id(ctx: Contexto) -> int:
    return max([int(n.id[1:]) for n in ctx.notificacoes if n.id[1:].isdigit()] + [0]) + 1


def notificar(ctx: Contexto, usuarios, tipo: str, texto: str, escala_id: str = "",
              agora: datetime | None = None, excluir=()) -> int:
    """Cria um aviso para cada usuário ativo (sem repetir, sem avisar quem está em `excluir`)."""
    agora = agora or datetime.now()
    alvo = [u for u in dict.fromkeys(usuarios) if u and u not in set(excluir)]
    n = _prox_id(ctx)
    criados = 0
    for uid in alvo:
        u = ctx.usuario(uid)
        if u is None or not u.ativo:
            continue
        ctx.notificacoes.append(Notificacao(f"n{n}", uid, tipo, texto, agora, False, escala_id))
        n += 1
        criados += 1
    return criados


def usuarios_do_militar(ctx: Contexto, militar_id: str) -> list[str]:
    return [u.id for u in ctx.usuarios if u.militar_id == militar_id and u.ativo]


def editores_da_escala(ctx: Contexto, escala_id: str) -> list[str]:
    esc = ctx.escala(escala_id)
    ids = [esc.dono_id] + [u for u, n in esc.compartilhado_com.items() if n == "edicao"]
    ids = [i for i in ids if i]
    if esc.auxiliares:                        # os auxiliares do detalhista também decidem
        ids += [u.id for u in ctx.usuarios if u.militar_id in esc.auxiliares and u.ativo]
    return ids


def usuarios_da_escala(ctx: Contexto, escala_id: str) -> list[str]:
    """Editores e as contas dos militares que estão na escala."""
    esc = ctx.escala(escala_id)
    membros = {p.militar_id for p in esc.membros}
    return editores_da_escala(ctx, escala_id) + [u.id for u in ctx.usuarios if u.militar_id in membros and u.ativo]


def do_usuario(ctx: Contexto, usuario_id: str, so_nao_lidas: bool = False) -> list[Notificacao]:
    lista = [n for n in ctx.notificacoes if n.usuario_id == usuario_id and not (so_nao_lidas and n.lida)]
    return sorted(lista, key=lambda n: n.criado_em, reverse=True)


def nao_lidas(ctx: Contexto, usuario_id: str) -> int:
    return sum(1 for n in ctx.notificacoes if n.usuario_id == usuario_id and not n.lida)


def marcar_lidas(ctx: Contexto, usuario_id: str, ids: list[str] | None = None) -> int:
    n = 0
    for x in ctx.notificacoes:
        if x.usuario_id == usuario_id and not x.lida and (ids is None or x.id in ids):
            x.lida = True
            n += 1
    return n


def podar(ctx: Contexto, agora: datetime | None = None) -> int:
    """Remove avisos lidos com mais de 30 dias e limita a 300 por usuário (mantém os mais novos)."""
    agora = agora or datetime.now()
    antes = len(ctx.notificacoes)
    corte = agora - timedelta(days=DIAS_LIDAS)
    ctx.notificacoes = [n for n in ctx.notificacoes if not (n.lida and n.criado_em < corte)]
    por_usuario: dict[str, list[Notificacao]] = {}
    for n in ctx.notificacoes:
        por_usuario.setdefault(n.usuario_id, []).append(n)
    descartar = set()
    for lista in por_usuario.values():
        for n in sorted(lista, key=lambda n: n.criado_em, reverse=True)[MAX_POR_USUARIO:]:
            descartar.add(n.id)
    ctx.notificacoes = [n for n in ctx.notificacoes if n.id not in descartar]
    return antes - len(ctx.notificacoes)

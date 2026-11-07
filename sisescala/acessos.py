"""Busca de escalas e pedidos de acesso.

Qualquer usuário aprovado pode pesquisar as escalas existentes (só dados gerais: nome, tipo, OM e detalhista; nunca
os militares) e pedir acesso ao detalhista. O detalhista aprova (a pessoa passa a ver a escala, em leitura) ou
rejeita. Depois do acesso, o militar pede o vínculo ao seu nome na escala (que o detalhista também autoriza).
"""
from __future__ import annotations

import unicodedata
from datetime import datetime

from . import notificacoes as nt
from .modelos import Contexto, Escala, PedidoAcesso
from .permissoes import PermissaoNegada, eh_detalhista, pode_ver


def _norm(txt: str) -> str:
    return unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower().strip()


def nome_do_detalhista(ctx: Contexto, esc: Escala) -> str:
    u = ctx.usuario(esc.dono_id)
    return u.nome if u else "—"


def buscar(ctx: Contexto, usuario_id: str, termo: str = "") -> list[Escala]:
    """Escalas que o usuário AINDA NÃO enxerga, filtradas por nome, tipo, OM ou nome do detalhista."""
    t = _norm(termo)
    achadas = []
    for e in ctx.escalas:
        if pode_ver(ctx, usuario_id, e):
            continue
        alvo = " ".join([_norm(e.nome), _norm(e.tipo), _norm(e.om), _norm(nome_do_detalhista(ctx, e))])
        if not t or t in alvo:
            achadas.append(e)
    return sorted(achadas, key=lambda e: (_norm(e.om), _norm(e.nome)))


def pedido_pendente(ctx: Contexto, usuario_id: str, escala_id: str) -> PedidoAcesso | None:
    return next((p for p in ctx.pedidos_acesso
                 if p.usuario_id == usuario_id and p.escala_id == escala_id and p.status == "pendente"), None)


def meus_pedidos(ctx: Contexto, usuario_id: str) -> list[PedidoAcesso]:
    return sorted((p for p in ctx.pedidos_acesso if p.usuario_id == usuario_id), key=lambda p: p.criado_em, reverse=True)


def pedir_acesso(ctx: Contexto, usuario_id: str, escala_id: str, mensagem: str = "",
                 agora: datetime | None = None) -> PedidoAcesso:
    agora = agora or datetime.now()
    u = ctx.usuario(usuario_id)
    esc = ctx.escala(escala_id)
    if not (u and u.ativo):
        raise PermissaoNegada("conta inválida")
    if pode_ver(ctx, usuario_id, esc):
        raise ValueError("você já tem acesso a esta escala")
    if pedido_pendente(ctx, usuario_id, escala_id):
        raise ValueError("você já pediu acesso a esta escala; aguarde o detalhista")
    n = max([int(p.id[1:]) for p in ctx.pedidos_acesso if p.id[1:].isdigit()] + [0]) + 1
    p = PedidoAcesso(f"a{n}", usuario_id, escala_id, agora, mensagem.strip())
    ctx.pedidos_acesso.append(p)
    nt.notificar(ctx, [esc.dono_id], "acesso",
                 f"{u.nome} (NIP {u.nip}, OM {u.om}) pediu acesso à escala {esc.nome}."
                 + (f" Mensagem: {p.mensagem}" if p.mensagem else ""), esc.id, agora)
    return p


def _obter(ctx: Contexto, pid: str) -> PedidoAcesso:
    p = next((x for x in ctx.pedidos_acesso if x.id == pid), None)
    if p is None:
        raise ValueError("pedido de acesso não encontrado")
    return p


def _exigir_detalhista(ctx: Contexto, usuario_id: str, p: PedidoAcesso) -> Escala:
    esc = ctx.escala(p.escala_id)
    if not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada("só o detalhista da escala decide pedidos de acesso")
    return esc


def aprovar(ctx: Contexto, usuario_id: str, pid: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = _exigir_detalhista(ctx, usuario_id, p)
    if p.status != "pendente":
        raise ValueError(f"pedido {p.status}")
    if ctx.usuario(p.usuario_id) is None:
        raise ValueError("a conta que pediu não existe mais")
    esc.compartilhado_com.setdefault(p.usuario_id, "leitura")
    p.status, p.decidido_por, p.decidido_em = "aprovado", usuario_id, agora
    nt.notificar(ctx, [p.usuario_id], "acesso", f"Seu acesso à escala {esc.nome} foi APROVADO. Agora você pode pedir o "
                 f"vínculo ao seu nome nela (página Vínculos).", esc.id, agora)


def rejeitar(ctx: Contexto, usuario_id: str, pid: str, motivo: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = _exigir_detalhista(ctx, usuario_id, p)
    if p.status != "pendente":
        raise ValueError(f"pedido {p.status}")
    if not motivo.strip():
        raise ValueError("informe o motivo da rejeição")
    p.status, p.decidido_por, p.decidido_em, p.motivo_rejeicao = "rejeitado", usuario_id, agora, motivo.strip()
    nt.notificar(ctx, [p.usuario_id], "acesso", f"Seu pedido de acesso à escala {esc.nome} foi REJEITADO: {motivo.strip()}",
                 esc.id, agora)


def cancelar(ctx: Contexto, usuario_id: str, pid: str) -> None:
    p = _obter(ctx, pid)
    if p.usuario_id != usuario_id:
        raise PermissaoNegada("só quem pediu cancela o próprio pedido")
    if p.status != "pendente":
        raise ValueError(f"pedido {p.status}")
    p.status = "cancelado"


def pendentes_para(ctx: Contexto, usuario_id: str) -> list[PedidoAcesso]:
    """Pedidos de acesso às escalas em que o usuário é o detalhista."""
    return [p for p in ctx.pedidos_acesso if p.status == "pendente"
            and any(e.id == p.escala_id and eh_detalhista(ctx, usuario_id, e) for e in ctx.escalas)]

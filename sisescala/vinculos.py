"""Vínculo da conta de um militar com a sua "persona" (o militar citado na escala).

Fluxo: o militar cria a conta, recebe acesso (leitura) a uma escala e pede para se vincular ao militar
dele nessa escala, criando um PIN. O detalhista (quem edita a escala) aprova ou rejeita. Aprovado, a conta
passa a ser daquele militar: enxerga as escalas em que ele está, pede troca para si, assina com o PIN e
pode abrir disponibilidade de troca. Se o militar já tem NIP no cadastro, o NIP informado precisa conferir.
"""
from __future__ import annotations

from datetime import datetime

from .auth import hash_pin
from .modelos import Contexto, Vinculo
from .permissoes import PermissaoNegada, pode_editar, pode_ver


def _obter(ctx: Contexto, vid: str) -> Vinculo:
    v = next((x for x in ctx.vinculos if x.id == vid), None)
    if v is None:
        raise ValueError("pedido de vínculo não encontrado")
    return v


def militares_livres(ctx: Contexto, escala_id: str) -> list[str]:
    """Militares da escala que ainda não têm conta nem pedido de vínculo pendente."""
    esc = ctx.escala(escala_id)
    ocupados = {u.militar_id for u in ctx.usuarios if u.militar_id}
    ocupados |= {v.militar_id for v in ctx.vinculos if v.status == "pendente"}
    ids = {p.militar_id for p in esc.membros}
    return sorted((m for m in ids if m not in ocupados), key=lambda i: ctx.militar(i).antiguidade)


def pendente_do_usuario(ctx: Contexto, usuario_id: str) -> Vinculo | None:
    return next((v for v in ctx.vinculos if v.usuario_id == usuario_id and v.status == "pendente"), None)


def solicitar(ctx: Contexto, usuario_id: str, escala_id: str, militar_id: str, nip: str, pin: str,
              agora: datetime | None = None) -> Vinculo:
    agora = agora or datetime.now()
    u = ctx.usuario(usuario_id)
    esc = ctx.escala(escala_id)
    if u is None or not u.ativo:
        raise PermissaoNegada("conta inválida")
    if u.militar_id:
        raise ValueError("sua conta já está vinculada a um militar")
    if pendente_do_usuario(ctx, usuario_id):
        raise ValueError("você já tem um pedido de vínculo aguardando decisão")
    if not pode_ver(ctx, usuario_id, esc):
        raise PermissaoNegada("você ainda não recebeu acesso a esta escala; peça ao detalhista")
    if militar_id not in militares_livres(ctx, escala_id):
        raise ValueError("esse militar não está disponível para vínculo (já vinculado ou com pedido pendente)")
    m = ctx.militar(militar_id)
    if m.nip and nip.strip() != m.nip:
        raise ValueError("NIP não confere com o cadastro do militar")
    v = Vinculo(f"v{max([int(x.id[1:]) for x in ctx.vinculos] + [0]) + 1}", usuario_id, militar_id, escala_id,
                agora, hash_pin(pin))
    ctx.vinculos.append(v)
    return v


def _exigir_editor(ctx: Contexto, usuario_id: str, v: Vinculo) -> None:
    if not pode_editar(ctx, usuario_id, ctx.escala(v.escala_id)):
        raise PermissaoNegada("somente o detalhista e os editores da escala decidem o vínculo")


def aprovar(ctx: Contexto, usuario_id: str, vid: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    v = _obter(ctx, vid)
    _exigir_editor(ctx, usuario_id, v)
    if v.status != "pendente":
        raise ValueError(f"pedido {v.status}")
    u = ctx.usuario(v.usuario_id)
    if u is None or u.militar_id:
        raise ValueError("a conta já está vinculada ou não existe mais")
    if any(x.militar_id == v.militar_id for x in ctx.usuarios):
        raise ValueError("esse militar já foi vinculado a outra conta")
    m = ctx.militar(v.militar_id)
    u.militar_id, u.pin_hash = m.id, v.pin_hash
    for campo in ("email", "ramal", "celular"):          # contato da conta completa o cadastro do militar
        if not getattr(m, campo) and getattr(u, campo):
            setattr(m, campo, getattr(u, campo))
    v.status, v.decidido_por, v.decidido_em = "aprovado", usuario_id, agora


def rejeitar(ctx: Contexto, usuario_id: str, vid: str, motivo: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    v = _obter(ctx, vid)
    _exigir_editor(ctx, usuario_id, v)
    if v.status != "pendente":
        raise ValueError(f"pedido {v.status}")
    if not motivo.strip():
        raise ValueError("informe o motivo da rejeição")
    v.status, v.decidido_por, v.decidido_em, v.motivo_rejeicao = "rejeitado", usuario_id, agora, motivo.strip()


def cancelar(ctx: Contexto, usuario_id: str, vid: str) -> None:
    v = _obter(ctx, vid)
    if v.usuario_id != usuario_id:
        raise PermissaoNegada("só quem pediu cancela o próprio pedido")
    if v.status != "pendente":
        raise ValueError(f"pedido {v.status}")
    v.status = "cancelado"


def pendentes_para(ctx: Contexto, usuario_id: str) -> list[Vinculo]:
    return [v for v in ctx.vinculos if v.status == "pendente"
            and pode_editar(ctx, usuario_id, ctx.escala(v.escala_id))]

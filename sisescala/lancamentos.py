"""Lançamentos que mudam a escala: impedimentos e dispensas, dispensa no dia do serviço, dias especiais,
guarnecimento e eventos.

Quem lança: o detalhista e o auxiliar dele. O auxiliar lança só nas escalas em que é auxiliar e só para os
militares dessas escalas. Ninguém lança (nem remove) dispensa ou impedimento para si mesmo: isso cabe a outro
responsável.
"""
from __future__ import annotations

from . import notificacoes as nt
from .modelos import Contexto, DiaEspecial, Escala, Evento, Guarnecimento, Impedimento, Ocorrencia
from .permissoes import PermissaoNegada, eh_auxiliar, pode_decidir

PROPRIO = "ninguém lança dispensa ou impedimento para si mesmo: peça a outro responsável (detalhista ou auxiliar)"


def _meu_militar(ctx: Contexto, usuario_id: str) -> str:
    u = ctx.usuario(usuario_id)
    return u.militar_id if u else ""


def escalas_lancaveis(ctx: Contexto, usuario_id: str) -> list[Escala]:
    """Escalas em que o usuário pode lançar (é o detalhista ou o auxiliar)."""
    return [e for e in ctx.escalas if pode_decidir(ctx, usuario_id, e)]


def militares_lancaveis(ctx: Contexto, usuario_id: str) -> list[str]:
    """Militares para quem o usuário pode lançar impedimentos: os das escalas em que ele é o detalhista ou auxiliar.
    Nunca ele mesmo."""
    u = ctx.usuario(usuario_id)
    if not u or not u.ativo:
        return []
    base = {p.militar_id for e in ctx.escalas if pode_decidir(ctx, usuario_id, e) for p in e.membros}
    ordem = {m.id: m.antiguidade for m in ctx.militares}
    return sorted((m for m in base if m != u.militar_id and m in ordem), key=lambda m: ordem[m])


def _exigir_militar(ctx: Contexto, usuario_id: str, militar_id: str) -> None:
    if militar_id and militar_id == _meu_militar(ctx, usuario_id):
        raise PermissaoNegada(PROPRIO)
    if militar_id not in militares_lancaveis(ctx, usuario_id):
        raise PermissaoNegada("você só lança para militares das escalas em que é detalhista ou auxiliar")


def _exigir_escala(ctx: Contexto, usuario_id: str, escala_id: str) -> Escala:
    esc = ctx.escala(escala_id)
    if not pode_decidir(ctx, usuario_id, esc):
        raise PermissaoNegada("você só lança nas escalas em que é detalhista ou auxiliar")
    return esc


def _exigir_alguma_escala(ctx: Contexto, usuario_id: str) -> None:
    if not escalas_lancaveis(ctx, usuario_id):
        raise PermissaoNegada("somente o detalhista e o auxiliar lançam")


def lancar_impedimento(ctx: Contexto, usuario_id: str, imp: Impedimento) -> None:
    _exigir_militar(ctx, usuario_id, imp.militar_id)
    if erros := imp.validar():
        raise ValueError("; ".join(erros))
    ctx.impedimentos.append(imp)


def lancar_dispensa_no_dia(ctx: Contexto, usuario_id: str, oc: Ocorrencia) -> None:
    """Dispensa o militar do serviço em que estava escalado: Disp com justificativa, retém avança, devolução."""
    esc = _exigir_escala(ctx, usuario_id, oc.escala_id)
    if oc.militar_id == _meu_militar(ctx, usuario_id):
        raise PermissaoNegada(PROPRIO)
    if not any(p.militar_id == oc.militar_id for p in esc.membros):
        raise ValueError("o militar não faz parte desta escala")
    if erros := oc.validar():
        raise ValueError("; ".join(erros))
    ctx.ocorrencias.append(oc)
    nt.notificar(ctx, nt.usuarios_do_militar(ctx, oc.militar_id), "devolucao",
                 f"Você foi dispensado do serviço de {oc.data:%d/%m/%Y} ({esc.nome}): {oc.motivo}. "
                 f"Você tem um serviço a devolver em até {ctx.janela_devolucao_dias} dias (página Devoluções).", esc.id)


def _eh_admin(ctx: Contexto, usuario_id: str) -> bool:
    u = ctx.usuario(usuario_id)
    return bool(u and u.ativo and u.admin)


def _exigir_dia(ctx: Contexto, usuario_id: str, de: DiaEspecial) -> None:
    """Dia especial vale para UMA escala (detalhista ou auxiliar dela) ou, sem escala, para todas (só o administrador)."""
    if de.escala_id:
        _exigir_escala(ctx, usuario_id, de.escala_id)
    elif not _eh_admin(ctx, usuario_id):
        raise PermissaoNegada("dia especial para todas as escalas só o administrador lança; escolha uma escala sua")


def lancar_dia_especial(ctx: Contexto, usuario_id: str, de: DiaEspecial) -> None:
    _exigir_dia(ctx, usuario_id, de)
    ctx.dias_especiais.append(de)


def lancar_guarnecimento(ctx: Contexto, usuario_id: str, g: Guarnecimento) -> None:
    _exigir_escala(ctx, usuario_id, g.escala_id)
    ctx.guarnecimentos.append(g)


def lancar_evento(ctx: Contexto, usuario_id: str, ev: Evento) -> None:
    esc = _exigir_escala(ctx, usuario_id, ev.escala_id)
    if esc.modo != "eventos":
        raise ValueError("esta escala não é do modo “Por evento”")
    ctx.eventos.append(ev)


def _lista_do(ctx: Contexto, item) -> list:
    return {Impedimento: ctx.impedimentos, Ocorrencia: ctx.ocorrencias, Guarnecimento: ctx.guarnecimentos,
            Evento: ctx.eventos, DiaEspecial: ctx.dias_especiais}[type(item)]


def remover(ctx: Contexto, usuario_id: str, item) -> None:
    """Remove um lançamento, com as mesmas regras de quem pode lançá-lo (e nunca o que é dele mesmo)."""
    if isinstance(item, Impedimento):
        _exigir_militar(ctx, usuario_id, item.militar_id)
    elif isinstance(item, Ocorrencia):
        _exigir_escala(ctx, usuario_id, item.escala_id)
        if item.militar_id == _meu_militar(ctx, usuario_id):
            raise PermissaoNegada(PROPRIO)
    elif isinstance(item, (Guarnecimento, Evento)):
        _exigir_escala(ctx, usuario_id, item.escala_id)
    else:
        _exigir_dia(ctx, usuario_id, item)
    _lista_do(ctx, item).remove(item)


def pode_remover(ctx: Contexto, usuario_id: str, item) -> bool:
    try:
        if isinstance(item, Impedimento):
            _exigir_militar(ctx, usuario_id, item.militar_id)
        elif isinstance(item, Ocorrencia):
            _exigir_escala(ctx, usuario_id, item.escala_id)
            return item.militar_id != _meu_militar(ctx, usuario_id)
        elif isinstance(item, (Guarnecimento, Evento)):
            _exigir_escala(ctx, usuario_id, item.escala_id)
        else:
            _exigir_dia(ctx, usuario_id, item)
        return True
    except PermissaoNegada:
        return False

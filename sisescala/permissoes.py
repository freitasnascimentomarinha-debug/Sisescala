"""Compartilhamento de escalas entre usuários (leitura | edição) e referências entre escalas."""
from __future__ import annotations

from .modelos import NIVEIS, Contexto, Escala
from .motor import _ancestrais

ORDEM = {None: 0, "leitura": 1, "edicao": 2, "dono": 3}


class PermissaoNegada(Exception):
    pass


def nivel(ctx: Contexto, usuario_id: str, esc: Escala) -> str | None:
    if esc.dono_id == usuario_id:
        return "dono"
    explicito = esc.compartilhado_com.get(usuario_id)
    if explicito:
        return explicito
    u = ctx.usuario(usuario_id)
    if u and u.militar_id and any(p.militar_id == u.militar_id for p in esc.membros):
        return "leitura"   # o militar sempre enxerga (somente leitura) as escalas em que está
    return None


def pode_ver(ctx: Contexto, usuario_id: str, esc: Escala) -> bool:
    return ORDEM[nivel(ctx, usuario_id, esc)] >= ORDEM["leitura"]


def pode_editar(ctx: Contexto, usuario_id: str, esc: Escala) -> bool:
    return ORDEM[nivel(ctx, usuario_id, esc)] >= ORDEM["edicao"]


def escalas_visiveis(ctx: Contexto, usuario_id: str) -> list[Escala]:
    return [e for e in ctx.escalas if pode_ver(ctx, usuario_id, e)]


def compartilhar(ctx: Contexto, quem_id: str, escala_id: str, com_id: str, novo_nivel: str | None) -> None:
    """Só o dono compartilha. `novo_nivel=None` revoga o acesso."""
    esc = ctx.escala(escala_id)
    if nivel(ctx, quem_id, esc) != "dono":
        raise PermissaoNegada("somente o dono da escala pode compartilhar o acesso")
    if com_id == esc.dono_id:
        raise ValueError("o dono já tem acesso total")
    if novo_nivel is None:
        esc.compartilhado_com.pop(com_id, None)
    elif novo_nivel in NIVEIS:
        esc.compartilhado_com[com_id] = novo_nivel
    else:
        raise ValueError(f"nível inválido: {novo_nivel}")


def referenciar(ctx: Contexto, usuario_id: str, escala_id: str, referencia_id: str) -> None:
    """A escala `referencia_id` (que o usuário só precisa poder ler) passa a prevalecer sobre
    `escala_id` (que o usuário precisa poder editar): quem estiver de serviço nela é considerado
    ao formar a outra, como se fossem escalas do próprio usuário."""
    esc, ref = ctx.escala(escala_id), ctx.escala(referencia_id)
    if not pode_editar(ctx, usuario_id, esc):
        raise PermissaoNegada("sem permissão de edição na escala")
    if not pode_ver(ctx, usuario_id, ref):
        raise PermissaoNegada("a escala de referência não foi compartilhada com você")
    if esc.id == ref.id or esc.id in _ancestrais(ctx, ref):
        raise ValueError("referência circular")
    if ref.id not in esc.referencias:
        esc.referencias.append(ref.id)


def remover_referencia(ctx: Contexto, usuario_id: str, escala_id: str, referencia_id: str) -> None:
    esc = ctx.escala(escala_id)
    if not pode_editar(ctx, usuario_id, esc):
        raise PermissaoNegada("sem permissão de edição na escala")
    if referencia_id in esc.referencias:
        esc.referencias.remove(referencia_id)

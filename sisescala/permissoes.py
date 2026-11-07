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
    if u and u.militar_id and (any(p.militar_id == u.militar_id for p in esc.membros) or u.militar_id in esc.auxiliares):
        return "leitura"   # o militar enxerga (somente leitura) as escalas em que está e as que ele auxilia
    return None


def pode_ver(ctx: Contexto, usuario_id: str, esc: Escala) -> bool:
    return ORDEM[nivel(ctx, usuario_id, esc)] >= ORDEM["leitura"]


def pode_editar(ctx: Contexto, usuario_id: str, esc: Escala) -> bool:
    return ORDEM[nivel(ctx, usuario_id, esc)] >= ORDEM["edicao"]


def eh_detalhista(ctx: Contexto, usuario_id: str, esc: Escala) -> bool:
    """Detalhista da escala: conta de perfil detalhista com poder de edição (dono ou editor).

    É quem decide papeletas e vínculos, pede troca por qualquer militar e vê todos os pedidos. Conta de
    militar nunca decide, mesmo que alguém lhe tenha dado "edição" por engano."""
    u = ctx.usuario(usuario_id)
    return bool(u and u.ativo and u.perfil == "detalhista" and pode_editar(ctx, usuario_id, esc))


def eh_auxiliar(ctx: Contexto, usuario_id: str, esc: Escala) -> bool:
    """Conta ligada ao militar que é o auxiliar do detalhista nesta escala."""
    u = ctx.usuario(usuario_id)
    return bool(u and u.ativo and u.militar_id and u.militar_id in esc.auxiliares)


def pode_decidir(ctx: Contexto, usuario_id: str, esc: Escala) -> bool:
    """Quem decide papeletas e vínculos da escala: o detalhista e o auxiliar dele. O auxiliar concorre à escala
    normalmente e decide só nesta escala (sem acesso às páginas de gestão). Ninguém decide o que é seu
    (ver `papeletas._exigir_editor`)."""
    return eh_detalhista(ctx, usuario_id, esc) or eh_auxiliar(ctx, usuario_id, esc)


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
        alvo = ctx.usuario(com_id)
        if novo_nivel == "edicao" and alvo is not None and alvo.perfil != "detalhista":
            raise ValueError("só contas de detalhista podem ter acesso de edição; a conta de militar fica em leitura")
        esc.compartilhado_com[com_id] = novo_nivel
    else:
        raise ValueError(f"nível inválido: {novo_nivel}")


def referenciar(ctx: Contexto, usuario_id: str, escala_id: str, referencia_id: str) -> None:
    """A escala `referencia_id` (que o usuário só precisa poder ler) passa a prevalecer sobre
    `escala_id` (que o usuário precisa poder editar): quem estiver de serviço nela é considerado
    ao formar a outra, como se fossem escalas do próprio usuário."""
    esc, ref = ctx.escala(escala_id), ctx.escala(referencia_id)
    if not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada("sem permissão de edição na escala")
    if not pode_ver(ctx, usuario_id, ref):
        raise PermissaoNegada("a escala de referência não foi compartilhada com você")
    if esc.id == ref.id or esc.id in _ancestrais(ctx, ref):
        raise ValueError("referência circular")
    if ref.id not in esc.referencias:
        esc.referencias.append(ref.id)


def remover_referencia(ctx: Contexto, usuario_id: str, escala_id: str, referencia_id: str) -> None:
    esc = ctx.escala(escala_id)
    if not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada("sem permissão de edição na escala")
    if referencia_id in esc.referencias:
        esc.referencias.remove(referencia_id)

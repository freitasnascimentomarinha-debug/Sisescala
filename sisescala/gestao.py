"""Gestão das escalas (regras, membros e exclusão): só o detalhista.

O auxiliar do detalhista concorre à escala, decide papeletas e vínculos e faz lançamentos, mas NÃO edita as
regras da escala (descanso, quartos, quantidade por dia, prioridade, quem é o detalhista/auxiliar, membros...).
"""
from __future__ import annotations

import dataclasses

from . import cadastro as cd
from .modelos import Contexto, Escala, Pertinencia
from .motor import validar_escala
from .permissoes import PermissaoNegada, eh_detalhista, referenciar

# o que NÃO se altera por aqui: identidade, dono, vínculos entre escalas, compartilhamento, membros e fila
PROTEGIDOS = {"id", "dono_id", "membros", "compartilhado_com", "referencias", "ultimo_servico"}
NEGADO = "só o detalhista da escala edita as regras da escala (o auxiliar não)"


def _exigir_detalhista(ctx: Contexto, usuario_id: str, esc: Escala) -> None:
    if not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada(NEGADO)


def militar_do_detalhista(ctx: Contexto, u) -> str:
    """Militar do cadastro que é essa pessoa: o vinculado à conta ou, na falta, o de mesmo NIP."""
    if u.militar_id:
        return u.militar_id
    from .auth import normalizar_nip
    return next((m.id for m in ctx.militares if m.nip and normalizar_nip(m.nip) == u.login), "")


def criar_escala(ctx: Contexto, usuario_id: str, escala: Escala, referencias=()) -> Escala:
    u = ctx.usuario(usuario_id)
    if not (u and u.ativo):
        raise PermissaoNegada("só usuário com cadastro aprovado cria escalas")
    if not escala.nome.strip():
        raise ValueError("informe o nome da escala")
    if any(e.id == escala.id for e in ctx.escalas):
        raise ValueError("já existe uma escala com esse identificador")
    escala.dono_id = usuario_id                       # quem cria vira automaticamente o detalhista da escala
    if not escala.detalhista_id:                      # e o militar dele (pelo vínculo ou pelo NIP) fica fora da escala
        escala.detalhista_id = militar_do_detalhista(ctx, u)
    ctx.numerar_escala(escala)
    if erros := validar_escala(ctx, escala):
        raise ValueError(" ".join(erros))
    ctx.escalas.append(escala)
    try:
        for r in referencias:
            referenciar(ctx, usuario_id, escala.id, r)
    except Exception:
        ctx.escalas.remove(escala)
        raise
    return escala


def editar_escala(ctx: Contexto, usuario_id: str, escala_id: str, **campos) -> Escala:
    """Altera as regras e a configuração da escala (nome, modo, quartos, descanso, detalhista, auxiliar...)."""
    esc = ctx.escala(escala_id)
    _exigir_detalhista(ctx, usuario_id, esc)
    if invalidos := PROTEGIDOS & campos.keys():
        raise ValueError("campo não editável por aqui: " + ", ".join(sorted(invalidos)))
    novo = dataclasses.replace(esc, **campos)
    if erros := validar_escala(ctx, novo):
        raise ValueError(" ".join(erros))
    ctx.escalas[ctx.escalas.index(esc)] = novo
    return novo


def excluir_escala(ctx: Contexto, usuario_id: str, escala_id: str) -> None:
    esc = ctx.escala(escala_id)
    if esc.dono_id != usuario_id:
        raise PermissaoNegada("somente o dono (detalhista) da escala a exclui")
    _exigir_detalhista(ctx, usuario_id, esc)
    ctx.escalas.remove(esc)
    for o in ctx.escalas:
        o.referencias = [r for r in o.referencias if r != esc.id]


def adicionar_militares(ctx: Contexto, usuario_id: str, escala_id: str, ids: list[str], desde=None,
                        posicao: int | None = None) -> int:
    _exigir_detalhista(ctx, usuario_id, ctx.escala(escala_id))
    return cd.adicionar_a_escala(ctx, escala_id, ids, desde, posicao)


def mudar_antiguidade(ctx: Contexto, usuario_id: str, escala_id: str, militar_id: str, posicao: int) -> None:
    """A antiguidade vale só dentro da escala; quem muda é o detalhista dela."""
    _exigir_detalhista(ctx, usuario_id, ctx.escala(escala_id))
    cd.mover_na_escala(ctx, escala_id, militar_id, posicao)


def remover_militares(ctx: Contexto, usuario_id: str, escala_id: str, ids: list[str], a_partir_de=None) -> int:
    """Com data, encerra a participação nessa data; sem data, remove de vez."""
    _exigir_detalhista(ctx, usuario_id, ctx.escala(escala_id))
    return cd.remover_da_escala(ctx, escala_id, ids, a_partir_de)


PAPEIS = {"escalado": "militar escalado (concorre à escala)", "auxiliar": "auxiliar do detalhista",
          "nenhum": "nenhum papel nesta escala"}


def transferir_detalhe(ctx: Contexto, usuario_id: str, escala_id: str, novo_usuario_id: str, papel: str = "nenhum",
                       militar_anterior: str = "", concorre: bool = False) -> Escala:
    """O detalhista entrega o detalhe da escala a outra pessoa. Quem entrega nunca fica sem designar o novo
    detalhista e escolhe o que passa a ser nesta escala:
    - "escalado": vira militar escalado (entra como membro e concorre);
    - "auxiliar": vira auxiliar (por padrão sem concorrer; `concorre=True` mantém ele como membro);
    - "nenhum": deixa de ter qualquer papel (sai dos auxiliares, dos membros e do acesso).
    `militar_anterior` indica o militar de quem entrega, se a conta dele não estiver ligada a um."""
    esc = ctx.escala(escala_id)
    if esc.dono_id != usuario_id or not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada("só o detalhista atual entrega o detalhe da escala")
    novo = ctx.usuario(novo_usuario_id)
    if novo is None or not novo.ativo or novo.id == usuario_id:
        raise ValueError("designe OUTRO detalhista (um usuário ativo) para receber o detalhe")
    if papel not in PAPEIS:
        raise ValueError("escolha o que você será nesta escala: militar escalado, auxiliar ou nenhum papel")
    velho = ctx.usuario(usuario_id)
    meu = militar_anterior or esc.detalhista_id or militar_do_detalhista(ctx, velho)
    if meu and not any(m.id == meu for m in ctx.militares):
        raise ValueError("militar não encontrado no cadastro")
    if papel in ("escalado", "auxiliar") and not meu:
        raise ValueError("indique o seu militar no cadastro para continuar nesta escala como "
                         + ("militar escalado" if papel == "escalado" else "auxiliar"))
    if militar_do_detalhista(ctx, novo) and militar_do_detalhista(ctx, novo) == meu:
        raise ValueError("o novo detalhista e quem entrega não podem ser o mesmo militar")

    # --- o novo detalhista: assume, fica fora da escala por padrão e deixa de ser auxiliar/convidado
    esc.dono_id = novo.id
    esc.detalhista_id = militar_do_detalhista(ctx, novo)
    esc.detalhista_escalavel = False
    esc.auxiliares = [a for a in esc.auxiliares if a != esc.detalhista_id]
    esc.compartilhado_com.pop(novo.id, None)
    # --- quem entregou
    esc.compartilhado_com.pop(velho.id, None)
    if papel != "nenhum":                              # continua vendo a escala (a conta pode não estar ligada a um militar)
        esc.compartilhado_com[velho.id] = "leitura"
    esc.auxiliares = [a for a in esc.auxiliares if a != meu] if meu else esc.auxiliares
    esta_na_escala = lambda: any(p.militar_id == meu and p.fim is None for p in esc.membros)  # noqa: E731
    if papel == "escalado":
        if not esta_na_escala():
            esc.membros.append(Pertinencia(meu, None, None, 10 ** 6))
    elif papel == "auxiliar":
        esc.auxiliares.append(meu)
        if concorre and not esta_na_escala():
            esc.membros.append(Pertinencia(meu, None, None, 10 ** 6))
        if not concorre:
            esc.membros = [p for p in esc.membros if p.militar_id != meu]
    else:                                              # nenhum papel
        esc.membros = [p for p in esc.membros if p.militar_id != meu]
    ctx.numerar_escala(esc)
    from . import notificacoes as nt
    nt.notificar(ctx, [novo.id], "papeleta", f"Você agora é o detalhista da escala {esc.nome} (entregue por {velho.nome}).", esc.id)
    nt.notificar(ctx, [velho.id], "papeleta", f"Você entregou o detalhe da escala {esc.nome} a {novo.nome} "
                                             f"e ficou como: {PAPEIS[papel]}.", esc.id)
    return esc

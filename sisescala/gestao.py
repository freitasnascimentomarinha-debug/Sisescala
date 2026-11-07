"""Gestão das escalas (regras, membros e exclusão): só o detalhista.

O auxiliar do detalhista concorre à escala, decide papeletas e vínculos e faz lançamentos, mas NÃO edita as
regras da escala (descanso, quartos, quantidade por dia, prioridade, quem é o detalhista/auxiliar, membros...).
"""
from __future__ import annotations

import dataclasses

from . import cadastro as cd
from .modelos import Contexto, Escala
from .motor import validar_escala
from .permissoes import PermissaoNegada, eh_detalhista, referenciar

# o que NÃO se altera por aqui: identidade, dono, vínculos entre escalas, compartilhamento, membros e fila
PROTEGIDOS = {"id", "dono_id", "membros", "compartilhado_com", "referencias", "ultimo_servico"}
NEGADO = "só o detalhista da escala edita as regras da escala (o auxiliar não)"


def _exigir_detalhista(ctx: Contexto, usuario_id: str, esc: Escala) -> None:
    if not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada(NEGADO)


def criar_escala(ctx: Contexto, usuario_id: str, escala: Escala, referencias=()) -> Escala:
    u = ctx.usuario(usuario_id)
    if not (u and u.ativo and u.perfil == "detalhista"):
        raise PermissaoNegada("somente o detalhista cria escalas")
    if not escala.nome.strip():
        raise ValueError("informe o nome da escala")
    if any(e.id == escala.id for e in ctx.escalas):
        raise ValueError("já existe uma escala com esse identificador")
    escala.dono_id = usuario_id                       # quem cria é o detalhista (dono) da escala
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


def adicionar_militares(ctx: Contexto, usuario_id: str, escala_id: str, ids: list[str], desde=None) -> int:
    _exigir_detalhista(ctx, usuario_id, ctx.escala(escala_id))
    return cd.adicionar_a_escala(ctx, escala_id, ids, desde)


def remover_militares(ctx: Contexto, usuario_id: str, escala_id: str, ids: list[str], a_partir_de=None) -> int:
    """Com data, encerra a participação nessa data; sem data, remove de vez."""
    _exigir_detalhista(ctx, usuario_id, ctx.escala(escala_id))
    return cd.remover_da_escala(ctx, escala_id, ids, a_partir_de)

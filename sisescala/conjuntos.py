"""Documento unificado: reúne várias escalas (fiscal, sentinela, contramestre...) num só detalhe de serviço, com instruções,
recomendações e regras gerais, e segue o mesmo fluxo de envio e assinatura das quatro autoridades.

Quem cria é o detalhista (ou o auxiliar) e vira o responsável (`dono_id`). Só se juntam escalas em que o responsável decide
(detalhista ou auxiliar)."""
from __future__ import annotations

from .modelos import Contexto, DetalheConjunto
from .permissoes import PermissaoNegada, pode_decidir

PROTEGIDOS = {"id", "dono_id"}


def elegiveis(ctx: Contexto, usuario_id: str) -> list:
    """Escalas que esta conta pode juntar num documento unificado."""
    return [e for e in ctx.escalas if pode_decidir(ctx, usuario_id, e)]


def criar(ctx: Contexto, usuario_id: str, nome: str, escala_ids=()) -> DetalheConjunto:
    u = ctx.usuario(usuario_id)
    if not (u and u.ativo):
        raise PermissaoNegada("só usuário com cadastro aprovado cria documentos")
    if not nome.strip():
        raise ValueError("informe o nome do documento (ex.: Escala de Serviço do Dia)")
    if not elegiveis(ctx, usuario_id):
        raise PermissaoNegada("você não é detalhista nem auxiliar de nenhuma escala")
    n = max([int(c.id[1:]) for c in ctx.conjuntos if c.id[1:].isdigit()] + [0]) + 1
    cj = DetalheConjunto(f"c{n}", nome.strip(), usuario_id)
    ctx.conjuntos.append(cj)
    if escala_ids:
        editar(ctx, usuario_id, cj.id, escala_ids=list(escala_ids))
    return cj


def obter(ctx: Contexto, cid: str) -> DetalheConjunto:
    cj = ctx.conjunto(cid)
    if cj is None:
        raise ValueError("documento não encontrado")
    return cj


def editar(ctx: Contexto, usuario_id: str, cid: str, **campos) -> DetalheConjunto:
    cj = obter(ctx, cid)
    if cj.dono_id != usuario_id:
        raise PermissaoNegada("só o responsável pelo documento o edita")
    if inv := PROTEGIDOS & campos.keys():
        raise ValueError("campo não editável por aqui: " + ", ".join(sorted(inv)))
    if "nome" in campos and not str(campos["nome"]).strip():
        raise ValueError("informe o nome do documento")
    if "escala_ids" in campos:
        ids = list(dict.fromkeys(campos["escala_ids"]))
        ok = {e.id for e in elegiveis(ctx, usuario_id)}
        if invalidas := [i for i in ids if i not in ok]:
            raise PermissaoNegada("você só junta escalas em que é detalhista ou auxiliar: " + ", ".join(invalidas))
        if not ids:
            raise ValueError("escolha ao menos uma escala")
        campos["escala_ids"] = ids
    for k, v in campos.items():                          # no próprio objeto: quem o segura continua com a versão atual
        if not hasattr(cj, k):
            raise ValueError(f"campo desconhecido: {k}")
        setattr(cj, k, v)
    return cj


def excluir(ctx: Contexto, usuario_id: str, cid: str) -> None:
    cj = obter(ctx, cid)
    if cj.dono_id != usuario_id:
        raise PermissaoNegada("só o responsável pelo documento o exclui")
    for d in ctx.detalhes_docs:
        if d.conjunto_id == cid and d.status == "aberto":
            d.status = "cancelado"                       # o que está para assinar deixa de valer
    ctx.conjuntos.remove(cj)

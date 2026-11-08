"""Lançamentos que mudam a escala: impedimentos e dispensas, dispensa no dia do serviço, dias especiais,
guarnecimento e eventos.

Quem lança: o detalhista e o auxiliar dele. O auxiliar lança só nas escalas em que é auxiliar e só para os
militares dessas escalas. Ninguém lança (nem remove) dispensa ou impedimento para si mesmo: isso cabe a outro
responsável.
"""
from __future__ import annotations

from datetime import datetime

from . import notificacoes as nt
from .modelos import (Contexto, DiaEspecial, Escala, Evento, Guarnecimento, Impedimento, Ocorrencia, PeriodoRoxa)
from .permissoes import PermissaoNegada, eh_auxiliar, eh_detalhista, pode_decidir

PROPRIO = "ninguém lança dispensa ou impedimento para si mesmo: peça a outro responsável (detalhista ou auxiliar)"


def _meu_militar(ctx: Contexto, usuario_id: str) -> str:
    u = ctx.usuario(usuario_id)
    return u.militar_id if u else ""


def _carimbo(item, usuario_id: str, agora: datetime | None):
    """Registra quem lançou e quando (o que já vem com carimbo, de importação ou dado antigo, não muda)."""
    if not item.criado_por:
        item.criado_por = usuario_id
    if item.criado_em is None:
        item.criado_em = agora or datetime.now()
    return item


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
    nomes = {m.id: m.nome for m in ctx.militares}
    return sorted((m for m in base if m != u.militar_id and m in nomes), key=lambda m: nomes[m])


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


def lancar_impedimento(ctx: Contexto, usuario_id: str, imp: Impedimento, agora: datetime | None = None) -> None:
    _exigir_militar(ctx, usuario_id, imp.militar_id)
    if erros := imp.validar():
        raise ValueError("; ".join(erros))
    ctx.impedimentos.append(_carimbo(imp, usuario_id, agora))


def lancar_dispensa_no_dia(ctx: Contexto, usuario_id: str, oc: Ocorrencia, agora: datetime | None = None) -> None:
    """Dispensa o militar do serviço em que estava escalado: Disp com justificativa, retém avança, devolução."""
    esc = _exigir_escala(ctx, usuario_id, oc.escala_id)
    if oc.militar_id == _meu_militar(ctx, usuario_id):
        raise PermissaoNegada(PROPRIO)
    if not any(p.militar_id == oc.militar_id for p in esc.membros):
        raise ValueError("o militar não faz parte desta escala")
    if erros := oc.validar():
        raise ValueError("; ".join(erros))
    ctx.ocorrencias.append(_carimbo(oc, usuario_id, agora))
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


def lancar_dia_especial(ctx: Contexto, usuario_id: str, de: DiaEspecial, agora: datetime | None = None) -> None:
    """Feriado, licença administrativa ou outro dia/período sem expediente. `conta_como` força preta ou vermelha."""
    _exigir_dia(ctx, usuario_id, de)
    if de.tipo not in ("feriado", "sem_expediente"):
        raise ValueError("tipo inválido: use feriado ou sem expediente")
    if de.conta_como not in ("", "preta", "vermelha"):
        raise ValueError("conta como inválido: use automático, preta ou vermelha (roxa é um período roxo)")
    if de.data_fim is not None and de.data_fim < de.data:
        raise ValueError("a data final não pode ser anterior à inicial")
    ctx.dias_especiais.append(_carimbo(de, usuario_id, agora))


def _em_varias(ctx: Contexto, usuario_id: str, modelo, escala_ids: list[str], lancar, agora) -> list[str]:
    """Lança o mesmo item em várias escalas de uma vez. Tudo ou nada: se uma falhar (permissão ou regra), nenhuma fica.
    Quem já tem item idêntico na escala é pulado. Devolve os nomes das escalas em que realmente lançou."""
    import copy
    ids = [i for i in dict.fromkeys(escala_ids) if i]
    if not ids:
        raise ValueError("escolha pelo menos uma escala")
    feitos: list[tuple[list, object]] = []
    nomes: list[str] = []
    try:
        for eid in ids:
            esc = ctx.escala(eid)
            if not eh_detalhista(ctx, usuario_id, esc) and len(ids) > 1:
                raise PermissaoNegada(f"para lançar em várias escalas você precisa ser o detalhista de cada uma ({esc.nome})")
            item = copy.copy(modelo)
            item.escala_id = eid
            igual = [x for x in (ctx.dias_especiais if isinstance(item, DiaEspecial) else ctx.roxas)
                     if x.escala_id == eid and all(getattr(x, c) == getattr(item, c)
                                                   for c in ("data", "data_fim", "tipo", "conta_como", "descricao")
                                                   if hasattr(item, c))
                     and (isinstance(item, DiaEspecial) or (x.inicio, x.fim, x.nome) == (item.inicio, item.fim, item.nome))]
            if igual:
                continue
            lista = ctx.dias_especiais if isinstance(item, DiaEspecial) else ctx.roxas
            lancar(ctx, usuario_id, item, agora)
            feitos.append((lista, item))
            nomes.append(esc.nome)
    except Exception:
        for lista, item in feitos:
            lista.remove(item)
        raise
    return nomes


def lancar_dia_especial_em(ctx: Contexto, usuario_id: str, de: DiaEspecial, escala_ids: list[str],
                           agora: datetime | None = None) -> list[str]:
    """Mesmo feriado/licença/ponto facultativo em várias escalas (só nas que o usuário é detalhista)."""
    return _em_varias(ctx, usuario_id, de, escala_ids, lancar_dia_especial, agora)


def lancar_periodo_roxo_em(ctx: Contexto, usuario_id: str, r: PeriodoRoxa, escala_ids: list[str],
                           agora: datetime | None = None) -> list[str]:
    """Mesmo período roxo em várias escalas (cada uma precisa participar da roxa)."""
    return _em_varias(ctx, usuario_id, r, escala_ids, lancar_periodo_roxo, agora)


def _exigir_roxo(ctx: Contexto, usuario_id: str, r: PeriodoRoxa) -> None:
    """Período roxo é regra da escala: só o detalhista (ou o administrador, para todas as escalas)."""
    if r.escala_id:
        if not eh_detalhista(ctx, usuario_id, ctx.escala(r.escala_id)):
            raise PermissaoNegada("só o detalhista da escala cria ou remove período roxo")
    elif not _eh_admin(ctx, usuario_id):
        raise PermissaoNegada("período roxo para todas as escalas só o administrador lança; escolha uma escala sua")


def lancar_periodo_roxo(ctx: Contexto, usuario_id: str, r: PeriodoRoxa, agora: datetime | None = None) -> None:
    """Período em que o dia conta como roxa para a escala (fila própria, funciona todos os dias)."""
    _exigir_roxo(ctx, usuario_id, r)
    if not r.nome.strip():
        raise ValueError("informe o nome do período roxo")
    if r.fim < r.inicio:
        raise ValueError("a data final não pode ser anterior à inicial")
    if r.escala_id and not ctx.escala(r.escala_id).participa_roxa:
        raise ValueError("esta escala não participa da roxa: ative em Escalas → Editar (\"Participa da escala roxa\")")
    if any(o.inicio <= r.fim and r.inicio <= o.fim and (not o.escala_id or not r.escala_id or o.escala_id == r.escala_id)
           for o in ctx.roxas):
        raise ValueError("já existe um período roxo que coincide com essas datas nesta escala")
    if not r.id:
        r.id = f"r{max([int(o.id[1:]) for o in ctx.roxas if o.id[1:].isdigit()] + [0]) + 1}"
    ctx.roxas.append(_carimbo(r, usuario_id, agora))


def lancar_guarnecimento(ctx: Contexto, usuario_id: str, g: Guarnecimento, agora: datetime | None = None) -> None:
    _exigir_escala(ctx, usuario_id, g.escala_id)
    ctx.guarnecimentos.append(_carimbo(g, usuario_id, agora))


def lancar_evento(ctx: Contexto, usuario_id: str, ev: Evento, agora: datetime | None = None) -> None:
    esc = _exigir_escala(ctx, usuario_id, ev.escala_id)
    if esc.modo != "eventos":
        raise ValueError("esta escala não é do modo “Por evento”")
    ctx.eventos.append(_carimbo(ev, usuario_id, agora))


def _lista_do(ctx: Contexto, item) -> list:
    return {Impedimento: ctx.impedimentos, Ocorrencia: ctx.ocorrencias, Guarnecimento: ctx.guarnecimentos,
            Evento: ctx.eventos, DiaEspecial: ctx.dias_especiais, PeriodoRoxa: ctx.roxas}[type(item)]


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
    elif isinstance(item, PeriodoRoxa):
        _exigir_roxo(ctx, usuario_id, item)
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
        elif isinstance(item, PeriodoRoxa):
            _exigir_roxo(ctx, usuario_id, item)
        else:
            _exigir_dia(ctx, usuario_id, item)
        return True
    except PermissaoNegada:
        return False

"""Papeleta de troca (e de devolução) de serviço.

Fluxo
 1. Quem pede confirma o pedido com o PRÓPRIO PIN (cadastrado no perfil). O militar pede para si, mesmo
    com acesso só de leitura; detalhista/editores pedem por qualquer militar da escala. Respeita a
    antecedência mínima da escala (24h por padrão, ajustável).
 2. O pedido chega ao detalhista e aos editores daquela escala: aprovar ou rejeitar.
 3. Aprovando, a prévia muda automaticamente (SVÇ (T) nos dois dias).
 4. Cada parte assina com o PIN (data, hora e hash do documento ficam registrados). O detalhista
    confirma quando as duas assinaram, ou cancela (inclusive depois de aprovar; a troca é desfeita).

Um pedido ativo (pendente ou aprovado) trava os dois militares: não entram em outro pedido. As partes
cancelam enquanto não aprovado.

Devolução: quem não deu um serviço (e fez o retém avançar) devolve em outro dia dentro do prazo,
assumindo o serviço de um colega (papeleta tipo "devolucao", mesmo fluxo).

Assinatura eletrônica simples (conta + PIN); não substitui certificado ICP-Brasil. O detalhista pode
registrar documento assinado fora do sistema (gov.br/ICP/papel).
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta

from . import auth
from . import notificacoes as nt
from .modelos import Assinatura, Contexto, Escala, Militar, Papeleta, Troca
from .motor import Devolucao, Resultado, _achar, _descansado, _impedido, gerar
from .permissoes import PermissaoNegada, eh_detalhista, pode_ver

ABERTAS = ("pendente", "aprovada")
TIPOS = {"troca": "troca de serviço", "devolucao": "devolução de serviço"}


def _log(p: Papeleta, quem: str, texto: str, agora: datetime) -> None:
    p.historico.append((agora, quem, texto))


def inicio_do_servico(d: date) -> datetime:
    return datetime.combine(d, time.min)


def antecedencia_ok(esc: Escala, d1: date, d2: date, agora: datetime) -> bool:
    primeiro = min(inicio_do_servico(d1), inicio_do_servico(d2))
    return agora + timedelta(hours=esc.antecedencia_horas) <= primeiro


def _datas_servico(p: Papeleta) -> tuple[date, date]:
    """Datas cujo início conta para a antecedência (na devolução, só o dia assumido)."""
    return (p.data_outro, p.data_outro) if p.tipo == "devolucao" else (p.data_solicitante, p.data_outro)


# ------------------------------------------------------------------ validações
def validar_troca(ctx: Contexto, esc: Escala, x: str, dx: date, y: str, dy: date) -> tuple[list[str], list[str], Resultado | None]:
    """Valida a troca X(dx) <-> Y(dy). Retorna (erros, avisos, resultado)."""
    erros: list[str] = []
    avisos: list[str] = []
    nome = lambda m: ctx.militar(m).nome  # noqa: E731
    if x == y:
        erros.append("escolha outro militar para a troca")
    if dx == dy:
        erros.append("as duas datas devem ser diferentes")
    if min(dx, dy) < ctx.data_base:
        erros.append("data anterior ao início da escala no sistema")
    if erros:
        return erros, avisos, None
    res = gerar(ctx, max(dx, dy))
    ax, ay = _achar(res, dx, esc.id, x), _achar(res, dy, esc.id, y)
    for a, m, d in ((ax, x, dx), (ay, y, dy)):
        if a is None:
            erros.append(f"{nome(m)} não está escalado em {d:%d/%m/%Y}")
        elif a.origem != "normal":
            erros.append(f"o serviço de {nome(m)} em {d:%d/%m/%Y} já veio de uma troca e não pode ser trocado de novo")
    if erros:
        return erros, avisos, res
    for m, d, d_orig in ((x, dy, dx), (y, dx, dy)):
        if not any(p.militar_id == m and p.ativo(d) for p in esc.membros):
            erros.append(f"{nome(m)} não faz parte da escala em {d:%d/%m/%Y}")
        if _impedido(ctx, m, d):
            erros.append(f"{nome(m)} está impedido (férias, curso, destaque etc.) em {d:%d/%m/%Y}")
        if any(a.militar_id == m for a in res.alocacoes_do_dia(d)):
            erros.append(f"{nome(m)} já está escalado em {d:%d/%m/%Y}")
        elif not _descansado(res, esc, m, d, ignorar=d_orig):
            avisos.append(f"{nome(m)} ficará com menos de {esc.folgas_minimas} folga(s) em torno de {d:%d/%m/%Y}")
    return erros, avisos, res


def _devolucao(res: Resultado, esc: Escala, x: str, d_origem: date) -> Devolucao | None:
    return next((d for d in res.devolucoes if d.militar_id == x and d.escala_id == esc.id
                 and d.data_origem == d_origem), None)


def validar_devolucao(ctx: Contexto, esc: Escala, x: str, d_origem: date, c: str, d2: date,
                      ignorar_pid: str = "") -> tuple[list[str], list[str], Resultado | None]:
    """X devolve o serviço que deixou de dar em `d_origem` assumindo o serviço de C em `d2`."""
    erros: list[str] = []
    avisos: list[str] = []
    nome = lambda m: ctx.militar(m).nome  # noqa: E731
    if x == c:
        erros.append("escolha outro militar")
    if d2 <= d_origem:
        erros.append("a devolução deve ser em data posterior ao serviço não dado")
    if d2 < ctx.data_base:
        erros.append("data anterior ao início da escala no sistema")
    if erros:
        return erros, avisos, None
    res = gerar(ctx, d2)
    dev = _devolucao(res, esc, x, d_origem)
    if dev is None:
        return ["não há serviço a devolver desse militar nessa data"], avisos, res
    if d2 > dev.prazo:
        erros.append(f"fora do prazo de devolução (até {dev.prazo:%d/%m/%Y})")
    for q in ctx.papeletas:
        if (q.tipo == "devolucao" and q.escala_id == esc.id and q.solicitante_id == x
                and q.data_solicitante == d_origem and q.status in (*ABERTAS, "confirmada") and q.id != ignorar_pid):
            erros.append(f"essa devolução já tem a papeleta {q.numero:04d} ({q.status})")
    a = _achar(res, d2, esc.id, c)
    if a is None or a.papel != "efetivo":
        erros.append(f"{nome(c)} não está escalado como efetivo em {d2:%d/%m/%Y}")
    elif a.origem != "normal":
        erros.append(f"o serviço de {nome(c)} em {d2:%d/%m/%Y} já veio de uma troca")
    if not any(p.militar_id == x and p.ativo(d2) for p in esc.membros):
        erros.append(f"{nome(x)} não faz parte da escala em {d2:%d/%m/%Y}")
    if _impedido(ctx, x, d2):
        erros.append(f"{nome(x)} está impedido em {d2:%d/%m/%Y}")
    if any(al.militar_id == x for al in res.alocacoes_do_dia(d2)):
        erros.append(f"{nome(x)} já está escalado em {d2:%d/%m/%Y}")
    elif not _descansado(res, esc, x, d2):
        avisos.append(f"{nome(x)} ficará com menos de {esc.folgas_minimas} folga(s) em torno de {d2:%d/%m/%Y}")
    return erros, avisos, res


def validar(ctx: Contexto, p: Papeleta, ignorar_pid: str = ""):
    esc = ctx.escala(p.escala_id)
    if p.tipo == "devolucao":
        return validar_devolucao(ctx, esc, p.solicitante_id, p.data_solicitante, p.outro_id, p.data_outro, ignorar_pid)
    return validar_troca(ctx, esc, p.solicitante_id, p.data_solicitante, p.outro_id, p.data_outro)


# ------------------------------------------------------------------ documento
def texto_canonico(ctx: Contexto, p: Papeleta) -> str:
    esc = ctx.escala(p.escala_id)
    x, y = ctx.militar(p.solicitante_id), ctx.militar(p.outro_id)
    if p.tipo == "devolucao":
        corpo = [f"DEVOLUCAO DE SERVICO DE {x.nome} ({x.nip}) DISPENSADO EM {p.data_solicitante:%d/%m/%Y}",
                 f"ASSUME O SERVICO DE {y.nome} ({y.nip}) EM {p.data_outro:%d/%m/%Y}"]
    else:
        corpo = [f"SOLICITANTE {x.nome} ({x.nip}) DIA {p.data_solicitante:%d/%m/%Y}",
                 f"TROCA COM {y.nome} ({y.nip}) DIA {p.data_outro:%d/%m/%Y}"]
    return "\n".join([f"PAPELETA {p.numero:04d}", f"ESCALA {esc.nome}", *corpo,
                      f"PEDIDO EM {p.criado_em:%d/%m/%Y %H:%M}", f"MOTIVO {p.motivo}"])


def hash_documento(ctx: Contexto, p: Papeleta) -> str:
    return hashlib.sha256(texto_canonico(ctx, p).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ pessoas e travas
def militar_do_usuario(ctx: Contexto, usuario_id: str) -> str:
    u = ctx.usuario(usuario_id)
    return u.militar_id if u else ""


def militares_em_pedido_ativo(ctx: Contexto) -> dict[str, Papeleta]:
    """Quem já está numa papeleta ativa (pendente ou aprovada) -> a papeleta. Não pode entrar em outra."""
    ativos: dict[str, Papeleta] = {}
    for q in ctx.papeletas:
        if q.status in ABERTAS:
            ativos.setdefault(q.solicitante_id, q)
            ativos.setdefault(q.outro_id, q)
    return ativos


def pode_pedir_por(ctx: Contexto, usuario_id: str, escala_id: str, solicitante_id: str) -> bool:
    """Editores pedem por qualquer militar da escala; o militar pede só para si (mesmo em leitura)."""
    esc = ctx.escala(escala_id)
    if eh_detalhista(ctx, usuario_id, esc):
        return True
    return pode_ver(ctx, usuario_id, esc) and militar_do_usuario(ctx, usuario_id) == solicitante_id


def _exigir_pode_pedir(ctx: Contexto, usuario_id: str, escala_id: str, solicitante_id: str) -> None:
    """Só militar vinculado pede para si; só o detalhista da escala pede por qualquer militar."""
    if pode_pedir_por(ctx, usuario_id, escala_id, solicitante_id):
        return
    esc = ctx.escala(escala_id)
    if not militar_do_usuario(ctx, usuario_id) and not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada("só militar vinculado pode pedir troca: peça o vínculo ao detalhista "
                              "(a vinculação precisa da autorização dele)")
    raise PermissaoNegada("você só pode pedir troca para o seu próprio serviço; só o detalhista pede por outro militar")


def e_parte(ctx: Contexto, usuario_id: str, p: Papeleta) -> bool:
    return militar_do_usuario(ctx, usuario_id) in (p.solicitante_id, p.outro_id)


def _interessados(ctx: Contexto, p: Papeleta) -> list[str]:
    """Contas das duas partes e de quem lançou o pedido."""
    return [*nt.usuarios_do_militar(ctx, p.solicitante_id), *nt.usuarios_do_militar(ctx, p.outro_id), p.criado_por]


def _exigir_pin(ctx: Contexto, usuario_id: str, pin: str | None, agora: datetime) -> None:
    u = ctx.usuario(usuario_id)
    if u is None or not u.pin_hash:
        raise PermissaoNegada("cadastre o seu PIN no perfil (Minha conta) antes de pedir ou assinar")
    if not pin or not auth.confirmar_assinatura(ctx, usuario_id, pin, agora):
        raise PermissaoNegada("PIN incorreto")


# ------------------------------------------------------------------ ciclo de vida
def _nova(ctx: Contexto, usuario_id: str, esc: Escala, tipo: str, x: str, dx: date, y: str, dy: date,
          motivo: str, agora: datetime, pin: str | None) -> Papeleta:
    _exigir_pin(ctx, usuario_id, pin, agora)
    numero = max((q.numero for q in ctx.papeletas), default=0) + 1
    p = Papeleta(f"pp{numero}", numero, esc.id, x, dx, y, dy, agora, usuario_id, motivo.strip(), tipo=tipo)
    nome_u = ctx.usuario(usuario_id).nome
    _log(p, usuario_id, f"Pedido criado por {nome_u} com PIN", agora)
    ctx.papeletas.append(p)
    cx, cy = ctx.militar(x).nome, ctx.militar(y).nome
    quando = f"{agora:%d/%m %H:%M}"
    if tipo == "devolucao":
        txt = f"Pedido {numero:04d} ({esc.nome}): {cx} quer devolver o serviço de {dx:%d/%m} assumindo o de {cy} em {dy:%d/%m}."
    else:
        txt = f"Pedido {numero:04d} ({esc.nome}): {cx} quer trocar o serviço de {dx:%d/%m} com {cy} ({dy:%d/%m})."
    nt.notificar(ctx, nt.usuarios_do_militar(ctx, y), "papeleta", txt + " Aguardando a decisão do detalhista.",
                 esc.id, agora, excluir=[usuario_id])
    nt.notificar(ctx, nt.editores_da_escala(ctx, esc.id), "papeleta", txt + " Aguardando a sua decisão.",
                 esc.id, agora, excluir=[usuario_id])
    return p


def _erros_de_pedido(ctx, esc, x, y, antecedencia_datas, agora, motivo, erros) -> list[str]:
    if not erros and not antecedencia_ok(esc, *antecedencia_datas, agora):
        erros.append(f"a papeleta precisa de pelo menos {esc.antecedencia_horas}h de antecedência do primeiro serviço")
    for m in (x, y):
        q = militares_em_pedido_ativo(ctx).get(m)
        if q:
            erros.append(f"{ctx.militar(m).nome} já está na papeleta {q.numero:04d} em andamento")
    if not motivo.strip():
        erros.append("informe o motivo")
    return erros


def criar(ctx: Contexto, usuario_id: str, escala_id: str, solicitante_id: str, data_solicitante: date,
          outro_id: str, data_outro: date, motivo: str = "", agora: datetime | None = None,
          pin: str | None = None) -> Papeleta:
    """Pedido de troca. Exige o PIN de quem está pedindo."""
    agora = agora or datetime.now()
    esc = ctx.escala(escala_id)
    _exigir_pode_pedir(ctx, usuario_id, escala_id, solicitante_id)
    erros, _, _ = validar_troca(ctx, esc, solicitante_id, data_solicitante, outro_id, data_outro)
    _erros_de_pedido(ctx, esc, solicitante_id, outro_id, (data_solicitante, data_outro), agora, motivo, erros)
    if erros:
        raise ValueError("; ".join(erros))
    return _nova(ctx, usuario_id, esc, "troca", solicitante_id, data_solicitante, outro_id, data_outro,
                 motivo, agora, pin)


def criar_devolucao(ctx: Contexto, usuario_id: str, escala_id: str, militar_id: str, data_origem: date,
                    colega_id: str, data_devolucao: date, motivo: str = "", agora: datetime | None = None,
                    pin: str | None = None) -> Papeleta:
    """Pedido de devolução: `militar_id` assume o serviço de `colega_id` em `data_devolucao`."""
    agora = agora or datetime.now()
    esc = ctx.escala(escala_id)
    _exigir_pode_pedir(ctx, usuario_id, escala_id, militar_id)
    erros, _, _ = validar_devolucao(ctx, esc, militar_id, data_origem, colega_id, data_devolucao)
    motivo = motivo.strip() or f"Devolução do serviço de {data_origem:%d/%m/%Y}"
    _erros_de_pedido(ctx, esc, militar_id, colega_id, (data_devolucao, data_devolucao), agora, motivo, erros)
    if erros:
        raise ValueError("; ".join(erros))
    return _nova(ctx, usuario_id, esc, "devolucao", militar_id, data_origem, colega_id, data_devolucao,
                 motivo, agora, pin)


def _obter(ctx: Contexto, pid: str) -> Papeleta:
    p = next((q for q in ctx.papeletas if q.id == pid), None)
    if p is None:
        raise ValueError("papeleta não encontrada")
    return p


def _exigir_editor(ctx: Contexto, usuario_id: str, p: Papeleta) -> Escala:
    esc = ctx.escala(p.escala_id)
    if not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada("somente o detalhista e os editores da escala decidem papeletas")
    return esc


def aprovar(ctx: Contexto, usuario_id: str, pid: str, agora: datetime | None = None) -> list[str]:
    """Aprova e muda a prévia automaticamente. Retorna avisos (ex.: descanso curto)."""
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = _exigir_editor(ctx, usuario_id, p)
    if p.status != "pendente":
        raise ValueError(f"papeleta {p.status}: só pedidos pendentes podem ser aprovados")
    erros, avisos, _ = validar(ctx, p, ignorar_pid=p.id)
    if not erros and min(inicio_do_servico(d) for d in _datas_servico(p)) <= agora:
        erros.append("o serviço já começou")
    if erros:
        raise ValueError("; ".join(erros))
    obs = f"Papeleta {p.numero:04d}" + (" (devolução)" if p.tipo == "devolucao" else "")
    if p.tipo == "devolucao":
        ctx.trocas.append(Troca(p.data_outro, esc.id, p.outro_id, p.solicitante_id, True, True, obs, p.id))
    else:
        ctx.trocas += [
            Troca(p.data_solicitante, esc.id, p.solicitante_id, p.outro_id, True, True, obs, p.id),
            Troca(p.data_outro, esc.id, p.outro_id, p.solicitante_id, True, True, obs, p.id)]
    p.status, p.decidido_por, p.decidido_em = "aprovada", usuario_id, agora
    _log(p, usuario_id, "Aprovada; troca aplicada na escala (aguardando assinaturas)", agora)
    nt.notificar(ctx, _interessados(ctx, p), "papeleta",
                 f"Papeleta {p.numero:04d} ({esc.nome}) APROVADA e aplicada na escala. Assine com o seu PIN.",
                 esc.id, agora, excluir=[usuario_id])
    return avisos


def rejeitar(ctx: Contexto, usuario_id: str, pid: str, motivo: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = _exigir_editor(ctx, usuario_id, p)
    if p.status != "pendente":
        raise ValueError(f"papeleta {p.status}: só pedidos pendentes podem ser rejeitados")
    if not motivo.strip():
        raise ValueError("informe o motivo da rejeição")
    p.status, p.decidido_por, p.decidido_em, p.motivo_rejeicao = "rejeitada", usuario_id, agora, motivo.strip()
    _log(p, usuario_id, f"Rejeitada: {motivo.strip()}", agora)
    nt.notificar(ctx, _interessados(ctx, p), "papeleta",
                 f"Papeleta {p.numero:04d} ({esc.nome}) REJEITADA: {motivo.strip()}", esc.id, agora, excluir=[usuario_id])


def cancelar(ctx: Contexto, usuario_id: str, pid: str, motivo: str = "", agora: datetime | None = None) -> None:
    """Pendente: quem criou, qualquer das partes ou um editor. Aprovada/confirmada: só o detalhista
    (editor), com motivo na confirmada, e a troca é desfeita."""
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = ctx.escala(p.escala_id)
    desfeita = False
    if p.status == "pendente":
        if not (usuario_id == p.criado_por or e_parte(ctx, usuario_id, p) or eh_detalhista(ctx, usuario_id, esc)):
            raise PermissaoNegada("sem permissão para cancelar")
    elif p.status in ("aprovada", "confirmada"):
        _exigir_editor(ctx, usuario_id, p)
        if p.status == "confirmada" and not motivo.strip():
            raise ValueError("informe o motivo para cancelar uma papeleta já confirmada")
        ctx.trocas = [t for t in ctx.trocas if t.papeleta_id != p.id]
        desfeita = True
    else:
        raise ValueError(f"papeleta {p.status} não pode ser cancelada")
    p.status = "cancelada"
    _log(p, usuario_id, "Cancelada" + (" (troca desfeita)" if desfeita else "")
         + (f": {motivo.strip()}" if motivo.strip() else ""), agora)
    nt.notificar(ctx, [*_interessados(ctx, p), *nt.editores_da_escala(ctx, esc.id)], "papeleta",
                 f"Papeleta {p.numero:04d} ({esc.nome}) CANCELADA" + (" e a troca foi desfeita." if desfeita else "."),
                 esc.id, agora, excluir=[usuario_id])


# ------------------------------------------------------------------ assinaturas
def assinar(ctx: Contexto, pid: str, usuario_id: str, pin: str, agora: datetime | None = None) -> Assinatura:
    """O militar assina logado na própria conta, com o PIN. Fica registrado com data, hora e hash."""
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    if p.status not in ABERTAS:
        raise ValueError(f"papeleta {p.status}: não aceita assinaturas")
    mid = militar_do_usuario(ctx, usuario_id)
    if mid not in (p.solicitante_id, p.outro_id):
        raise PermissaoNegada("somente os dois militares da troca assinam, com a própria conta")
    if mid in p.assinaturas:
        raise ValueError("já assinou")
    _exigir_pin(ctx, usuario_id, pin, agora)
    a = Assinatura(mid, agora, hash_documento(ctx, p), "conta")
    p.assinaturas[mid] = a
    m = ctx.militar(mid)
    _log(p, usuario_id, f"{m.nome} assinou pelo sistema com PIN em {agora:%d/%m/%Y às %H:%M:%S}", agora)
    esc = ctx.escala(p.escala_id)
    nt.notificar(ctx, [*nt.editores_da_escala(ctx, esc.id), *_interessados(ctx, p)], "papeleta",
                 f"{m.nome} assinou a papeleta {p.numero:04d} ({esc.nome}) em {agora:%d/%m %H:%M}.",
                 esc.id, agora, excluir=[usuario_id])
    return a


def registrar_assinatura_externa(ctx: Contexto, usuario_id: str, pid: str, militar_id: str, referencia: str,
                                 agora: datetime | None = None) -> None:
    """O detalhista registra que recebeu o documento assinado por fora (gov.br, ICP, papel)."""
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    _exigir_editor(ctx, usuario_id, p)
    if p.status not in ABERTAS:
        raise ValueError(f"papeleta {p.status}: não aceita assinaturas")
    if militar_id not in (p.solicitante_id, p.outro_id):
        raise ValueError("somente os militares da troca assinam")
    if not referencia.strip():
        raise ValueError("informe o link ou número do documento assinado")
    p.assinaturas[militar_id] = Assinatura(militar_id, agora, hash_documento(ctx, p), "externo", referencia.strip())
    _log(p, usuario_id, f"Registrou assinatura externa de {ctx.militar(militar_id).nome}", agora)


def situacao_partes(ctx: Contexto, p: Papeleta) -> list[dict]:
    """Para o detalhista: cada parte tem conta no sistema e PIN? assinou? quando e como?"""
    out = []
    for mid in (p.solicitante_id, p.outro_id):
        m: Militar = ctx.militar(mid)
        conta = next((u for u in ctx.usuarios if u.militar_id == mid and u.ativo), None)
        a = p.assinaturas.get(mid)
        out.append({"militar": m, "papel": "solicitante" if mid == p.solicitante_id else "troca com",
                    "tem_conta": conta is not None, "login": conta.login if conta else "",
                    "tem_pin": bool(conta and conta.pin_hash),
                    "assinou": a is not None, "metodo": a.metodo if a else "", "em": a.em if a else None,
                    "referencia": a.referencia if a else ""})
    return out


def papeletas_visiveis(ctx: Contexto, usuario_id: str, escala_id: str) -> list[Papeleta]:
    """Editores veem todas da escala; os demais, só as que os envolvem (parte ou quem criou)."""
    esc = ctx.escala(escala_id)
    editor = eh_detalhista(ctx, usuario_id, esc)
    return sorted((p for p in ctx.papeletas if p.escala_id == escala_id
                   and (editor or e_parte(ctx, usuario_id, p) or p.criado_por == usuario_id)),
                  key=lambda p: -p.numero)


def faltam_assinar(ctx: Contexto, p: Papeleta) -> list[str]:
    return [ctx.militar(m).nome for m in (p.solicitante_id, p.outro_id) if m not in p.assinaturas]


def confirmar(ctx: Contexto, usuario_id: str, pid: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = _exigir_editor(ctx, usuario_id, p)
    if p.status != "aprovada":
        raise ValueError("só papeletas aprovadas podem ser confirmadas")
    if falta := faltam_assinar(ctx, p):
        raise ValueError("aguardando assinatura de: " + ", ".join(falta))
    p.status, p.confirmada_por, p.confirmada_em = "confirmada", usuario_id, agora
    _log(p, usuario_id, "Confirmada com as assinaturas das partes", agora)
    nt.notificar(ctx, _interessados(ctx, p), "papeleta", f"Papeleta {p.numero:04d} ({esc.nome}) CONFIRMADA.",
                 esc.id, agora, excluir=[usuario_id])


# ------------------------------------------------------------------ caixa de pedidos
def pedidos_pendentes(ctx: Contexto, usuario_id: str) -> list[Papeleta]:
    """Pedidos aguardando decisão nas escalas em que o usuário é dono ou editor."""
    editaveis = {e.id for e in ctx.escalas if eh_detalhista(ctx, usuario_id, e)}
    return [p for p in ctx.papeletas if p.status == "pendente" and p.escala_id in editaveis]


# ------------------------------------------------------------------ devoluções em aberto
def devolucoes_em_aberto(ctx: Contexto, res: Resultado, escala_ids: set[str] | None = None,
                         hoje: date | None = None) -> list[dict]:
    """Serviços a devolver (da geração `res`), com situação: aberta | em_andamento | vencida.
    Exclui os já quitados (papeleta de devolução confirmada)."""
    hoje = hoje or date.today()
    out = []
    for dv in res.devolucoes:
        if escala_ids is not None and dv.escala_id not in escala_ids:
            continue
        pap = [q for q in ctx.papeletas if q.tipo == "devolucao" and q.escala_id == dv.escala_id
               and q.solicitante_id == dv.militar_id and q.data_solicitante == dv.data_origem]
        if any(q.status == "confirmada" for q in pap):
            continue
        andamento = next((q for q in pap if q.status in ABERTAS), None)
        estado = "em_andamento" if andamento else ("vencida" if dv.prazo < hoje else "aberta")
        out.append({"devolucao": dv, "estado": estado, "papeleta": andamento,
                    "dias_restantes": (dv.prazo - hoje).days})
    return sorted(out, key=lambda x: x["devolucao"].prazo)

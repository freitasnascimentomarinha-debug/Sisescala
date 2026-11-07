"""Papeleta de troca de serviço.

Fluxo
 1. Alguém com acesso à escala escolhe, na prévia, o dia de serviço de um militar e o dia/militar
    com quem trocar. Respeita a antecedência mínima da escala (24h por padrão, ajustável).
    O sistema gera o documento para assinatura dos dois militares e para o detalhista.
 2. O pedido chega ao detalhista e aos editores daquela escala: aprovar ou rejeitar.
 3. Aprovando, o sistema troca automaticamente as datas (SVÇ (T) nos dois dias).
 4. O detalhista aguarda o documento assinado pelas duas partes e então confirma.
    Se não for assinado, pode cancelar e a troca é desfeita.

Quem pode pedir: detalhista/editores (em nome de qualquer militar da escala) e o próprio militar
(mesmo com acesso só de leitura), sempre para si. Um pedido ativo (pendente ou aprovado) trava os dois
militares: não podem entrar em outro pedido. As partes cancelam enquanto não aprovado; o detalhista
cancela também depois de aprovado.

Assinatura: o militar assina logado na própria conta, reconfirmando a senha (com data/hora e hash do
documento), ou o detalhista registra documento assinado fora do sistema (gov.br/ICP/papel).
Não substitui certificado ICP-Brasil.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta


from . import auth
from .modelos import Assinatura, Contexto, Escala, Militar, Papeleta, Troca
from .motor import Resultado, _achar, _descansado, _impedido, gerar
from .permissoes import PermissaoNegada, pode_editar, pode_ver

ABERTAS = ("pendente", "aprovada")


def _log(p: Papeleta, quem: str, texto: str, agora: datetime) -> None:
    p.historico.append((agora, quem, texto))


def inicio_do_servico(d: date) -> datetime:
    return datetime.combine(d, time.min)


def antecedencia_ok(esc: Escala, d1: date, d2: date, agora: datetime) -> bool:
    primeiro = min(inicio_do_servico(d1), inicio_do_servico(d2))
    return agora + timedelta(hours=esc.antecedencia_horas) <= primeiro


def validar_troca(ctx: Contexto, esc: Escala, x: str, dx: date, y: str, dy: date) -> tuple[list[str], list[str], Resultado | None]:
    """Valida a troca X(dx) <-> Y(dy). Retorna (erros, avisos)."""
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


# ------------------------------------------------------------------ documento
def texto_canonico(ctx: Contexto, p: Papeleta) -> str:
    esc = ctx.escala(p.escala_id)
    return "\n".join([
        f"PAPELETA {p.numero:04d}", f"ESCALA {esc.nome}",
        f"SOLICITANTE {ctx.militar(p.solicitante_id).nome} ({ctx.militar(p.solicitante_id).nip}) DIA {p.data_solicitante:%d/%m/%Y}",
        f"TROCA COM {ctx.militar(p.outro_id).nome} ({ctx.militar(p.outro_id).nip}) DIA {p.data_outro:%d/%m/%Y}",
        f"PEDIDO EM {p.criado_em:%d/%m/%Y %H:%M}", f"MOTIVO {p.motivo}"])


def hash_documento(ctx: Contexto, p: Papeleta) -> str:
    return hashlib.sha256(texto_canonico(ctx, p).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ ciclo de vida
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
    if pode_editar(ctx, usuario_id, esc):
        return True
    return pode_ver(ctx, usuario_id, esc) and militar_do_usuario(ctx, usuario_id) == solicitante_id


def criar(ctx: Contexto, usuario_id: str, escala_id: str, solicitante_id: str, data_solicitante: date,
          outro_id: str, data_outro: date, motivo: str = "", agora: datetime | None = None) -> Papeleta:
    agora = agora or datetime.now()
    esc = ctx.escala(escala_id)
    if not pode_pedir_por(ctx, usuario_id, escala_id, solicitante_id):
        raise PermissaoNegada("você só pode pedir troca para o seu próprio serviço, em uma escala em que está")
    erros, _, _ = validar_troca(ctx, esc, solicitante_id, data_solicitante, outro_id, data_outro)
    if not erros and not antecedencia_ok(esc, data_solicitante, data_outro, agora):
        erros.append(f"a papeleta precisa de pelo menos {esc.antecedencia_horas}h de antecedência "
                     f"do primeiro serviço")
    for m in (solicitante_id, outro_id):
        q = militares_em_pedido_ativo(ctx).get(m)
        if q:
            erros.append(f"{ctx.militar(m).nome} já está na papeleta {q.numero:04d} em andamento")
    if not motivo.strip():
        erros.append("informe o motivo da troca")
    if erros:
        raise ValueError("; ".join(erros))
    numero = max((q.numero for q in ctx.papeletas), default=0) + 1
    p = Papeleta(f"pp{numero}", numero, esc.id, solicitante_id, data_solicitante, outro_id, data_outro,
                 agora, usuario_id, motivo.strip())
    _log(p, usuario_id, "Pedido criado", agora)
    ctx.papeletas.append(p)
    return p


def _obter(ctx: Contexto, pid: str) -> Papeleta:
    p = next((q for q in ctx.papeletas if q.id == pid), None)
    if p is None:
        raise ValueError("papeleta não encontrada")
    return p


def _exigir_editor(ctx: Contexto, usuario_id: str, p: Papeleta) -> Escala:
    esc = ctx.escala(p.escala_id)
    if not pode_editar(ctx, usuario_id, esc):
        raise PermissaoNegada("somente o detalhista e os editores da escala decidem papeletas")
    return esc


def aprovar(ctx: Contexto, usuario_id: str, pid: str, agora: datetime | None = None) -> list[str]:
    """Aprova e faz a troca automaticamente. Retorna avisos (ex.: descanso curto)."""
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = _exigir_editor(ctx, usuario_id, p)
    if p.status != "pendente":
        raise ValueError(f"papeleta {p.status}: só pedidos pendentes podem ser aprovados")
    erros, avisos, _ = validar_troca(ctx, esc, p.solicitante_id, p.data_solicitante, p.outro_id, p.data_outro)
    if not erros and min(inicio_do_servico(p.data_solicitante), inicio_do_servico(p.data_outro)) <= agora:
        erros.append("o serviço já começou")
    if erros:
        raise ValueError("; ".join(erros))
    obs = f"Papeleta {p.numero:04d}"
    ctx.trocas += [
        Troca(p.data_solicitante, esc.id, p.solicitante_id, p.outro_id, True, True, obs, p.id),
        Troca(p.data_outro, esc.id, p.outro_id, p.solicitante_id, True, True, obs, p.id)]
    p.status, p.decidido_por, p.decidido_em = "aprovada", usuario_id, agora
    _log(p, usuario_id, "Aprovada; troca aplicada na escala (aguardando assinaturas)", agora)
    return avisos


def rejeitar(ctx: Contexto, usuario_id: str, pid: str, motivo: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    _exigir_editor(ctx, usuario_id, p)
    if p.status != "pendente":
        raise ValueError(f"papeleta {p.status}: só pedidos pendentes podem ser rejeitados")
    if not motivo.strip():
        raise ValueError("informe o motivo da rejeição")
    p.status, p.decidido_por, p.decidido_em, p.motivo_rejeicao = "rejeitada", usuario_id, agora, motivo.strip()
    _log(p, usuario_id, f"Rejeitada: {motivo.strip()}", agora)


def e_parte(ctx: Contexto, usuario_id: str, p: Papeleta) -> bool:
    return militar_do_usuario(ctx, usuario_id) in (p.solicitante_id, p.outro_id)


def cancelar(ctx: Contexto, usuario_id: str, pid: str, motivo: str = "", agora: datetime | None = None) -> None:
    """Pendente: quem criou, qualquer das partes ou um editor. Aprovada/confirmada: só o detalhista
    (editor), com motivo na confirmada, e a troca é desfeita."""
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = ctx.escala(p.escala_id)
    desfeita = False
    if p.status == "pendente":
        if not (usuario_id == p.criado_por or e_parte(ctx, usuario_id, p) or pode_editar(ctx, usuario_id, esc)):
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


# ------------------------------------------------------------------ assinaturas
def assinar(ctx: Contexto, pid: str, usuario_id: str, senha: str, agora: datetime | None = None) -> Assinatura:
    """O militar assina logado na própria conta, confirmando com o PIN (ou a senha, se ainda não tiver PIN)."""
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    if p.status not in ABERTAS:
        raise ValueError(f"papeleta {p.status}: não aceita assinaturas")
    mid = militar_do_usuario(ctx, usuario_id)
    if mid not in (p.solicitante_id, p.outro_id):
        raise PermissaoNegada("somente os dois militares da troca assinam, com a própria conta")
    if mid in p.assinaturas:
        raise ValueError("já assinou")
    if not auth.confirmar_assinatura(ctx, usuario_id, senha, agora):
        raise PermissaoNegada("PIN/senha incorreto")
    a = Assinatura(mid, agora, hash_documento(ctx, p), "conta")
    p.assinaturas[mid] = a
    _log(p, usuario_id, f"{ctx.militar(mid).nome} assinou pelo sistema", agora)
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
    """Para o detalhista: cada parte tem conta no sistema? assinou? como?"""
    out = []
    for mid in (p.solicitante_id, p.outro_id):
        m: Militar = ctx.militar(mid)
        conta = next((u for u in ctx.usuarios if u.militar_id == mid and u.ativo), None)
        a = p.assinaturas.get(mid)
        out.append({"militar": m, "papel": "solicitante" if mid == p.solicitante_id else "troca com",
                    "tem_conta": conta is not None, "login": conta.login if conta else "",
                    "assinou": a is not None, "metodo": a.metodo if a else "", "em": a.em if a else None,
                    "referencia": a.referencia if a else ""})
    return out


def papeletas_visiveis(ctx: Contexto, usuario_id: str, escala_id: str) -> list[Papeleta]:
    """Editores veem todas da escala; os demais, só as que os envolvem (parte ou quem criou)."""
    esc = ctx.escala(escala_id)
    editor = pode_editar(ctx, usuario_id, esc)
    return sorted((p for p in ctx.papeletas if p.escala_id == escala_id
                   and (editor or e_parte(ctx, usuario_id, p) or p.criado_por == usuario_id)),
                  key=lambda p: -p.numero)


def faltam_assinar(ctx: Contexto, p: Papeleta) -> list[str]:
    return [ctx.militar(m).nome for m in (p.solicitante_id, p.outro_id) if m not in p.assinaturas]


def confirmar(ctx: Contexto, usuario_id: str, pid: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    _exigir_editor(ctx, usuario_id, p)
    if p.status != "aprovada":
        raise ValueError("só papeletas aprovadas podem ser confirmadas")
    if falta := faltam_assinar(ctx, p):
        raise ValueError("aguardando assinatura de: " + ", ".join(falta))
    p.status, p.confirmada_por, p.confirmada_em = "confirmada", usuario_id, agora
    _log(p, usuario_id, "Confirmada com as assinaturas das partes", agora)


# ------------------------------------------------------------------ caixa de pedidos
def pedidos_pendentes(ctx: Contexto, usuario_id: str) -> list[Papeleta]:
    """Pedidos aguardando decisão nas escalas em que o usuário é dono ou editor."""
    editaveis = {e.id for e in ctx.escalas if pode_editar(ctx, usuario_id, e)}
    return [p for p in ctx.papeletas if p.status == "pendente" and p.escala_id in editaveis]

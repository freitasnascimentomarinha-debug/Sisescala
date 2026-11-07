"""Papeleta de troca de serviço.

Fluxo
 1. Alguém com acesso à escala escolhe, na prévia, o dia de serviço de um militar e o dia/militar
    com quem trocar. Respeita a antecedência mínima da escala (24h por padrão, ajustável).
    O sistema gera o documento para assinatura dos dois militares e para o detalhista.
 2. O pedido chega ao detalhista e aos editores daquela escala: aprovar ou rejeitar.
 3. Aprovando, o sistema troca automaticamente as datas (SVÇ (T) nos dois dias).
 4. O detalhista aguarda o documento assinado pelas duas partes e então confirma.
    Se não for assinado, pode cancelar e a troca é desfeita.

Assinatura: eletrônica simples (NIP + PIN do militar, com data/hora e hash do documento) ou
registro de documento assinado fora do sistema (gov.br/ICP/papel). Não substitui certificado ICP-Brasil.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta

import bcrypt

from .calendario import dia_util  # noqa: F401  (reservado para regras futuras)
from .modelos import Assinatura, Contexto, Escala, Papeleta, Troca
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
def criar(ctx: Contexto, usuario_id: str, escala_id: str, solicitante_id: str, data_solicitante: date,
          outro_id: str, data_outro: date, motivo: str = "", agora: datetime | None = None) -> Papeleta:
    agora = agora or datetime.now()
    esc = ctx.escala(escala_id)
    if not pode_ver(ctx, usuario_id, esc):
        raise PermissaoNegada("sem acesso a esta escala")
    erros, _, _ = validar_troca(ctx, esc, solicitante_id, data_solicitante, outro_id, data_outro)
    if not erros and not antecedencia_ok(esc, data_solicitante, data_outro, agora):
        erros.append(f"a papeleta precisa de pelo menos {esc.antecedencia_horas}h de antecedência "
                     f"do primeiro serviço")
    for q in ctx.papeletas:
        if q.escala_id == esc.id and q.status in ABERTAS and (
                {(q.solicitante_id, q.data_solicitante), (q.outro_id, q.data_outro)}
                & {(solicitante_id, data_solicitante), (outro_id, data_outro)}):
            erros.append(f"já existe a papeleta {q.numero:04d} em andamento para um desses serviços")
            break
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


def cancelar(ctx: Contexto, usuario_id: str, pid: str, motivo: str = "", agora: datetime | None = None) -> None:
    """Pendente: quem criou ou um editor. Aprovada: só editor, e a troca é desfeita."""
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    esc = ctx.escala(p.escala_id)
    desfeita = False
    if p.status == "pendente":
        if usuario_id != p.criado_por and not pode_editar(ctx, usuario_id, esc):
            raise PermissaoNegada("sem permissão para cancelar")
    elif p.status == "aprovada":
        _exigir_editor(ctx, usuario_id, p)
        ctx.trocas = [t for t in ctx.trocas if t.papeleta_id != p.id]
        desfeita = True
    else:
        raise ValueError(f"papeleta {p.status} não pode ser cancelada")
    p.status = "cancelada"
    _log(p, usuario_id, "Cancelada" + (" (troca desfeita)" if desfeita else "")
         + (f": {motivo.strip()}" if motivo.strip() else ""), agora)


# ------------------------------------------------------------------ assinaturas
def definir_pin(ctx: Contexto, militar_id: str, nip: str, pin: str, pin_atual: str | None = None) -> None:
    m = ctx.militar(militar_id)
    if not m.nip:
        raise ValueError("militar sem NIP cadastrado: cadastre o NIP antes de assinar")
    if nip.strip() != m.nip:
        raise ValueError("NIP não confere")
    if len(pin) < 4 or not pin.isdigit():
        raise ValueError("o PIN deve ter pelo menos 4 dígitos numéricos")
    if m.pin_hash and not (pin_atual and bcrypt.checkpw(pin_atual.encode(), m.pin_hash.encode())):
        raise ValueError("PIN atual incorreto")
    m.pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=10)).decode()


def assinar(ctx: Contexto, pid: str, militar_id: str, nip: str, pin: str, agora: datetime | None = None) -> Assinatura:
    agora = agora or datetime.now()
    p = _obter(ctx, pid)
    if p.status not in ABERTAS:
        raise ValueError(f"papeleta {p.status}: não aceita assinaturas")
    if militar_id not in (p.solicitante_id, p.outro_id):
        raise PermissaoNegada("somente os militares da troca assinam")
    if militar_id in p.assinaturas:
        raise ValueError("já assinou")
    m = ctx.militar(militar_id)
    if not m.pin_hash:
        raise ValueError("defina seu PIN antes de assinar")
    if nip.strip() != m.nip or not bcrypt.checkpw(pin.encode(), m.pin_hash.encode()):
        raise PermissaoNegada("NIP ou PIN incorretos")
    a = Assinatura(militar_id, agora, hash_documento(ctx, p), "pin")
    p.assinaturas[militar_id] = a
    _log(p, m.nome, "Assinou eletronicamente", agora)
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

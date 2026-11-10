"""Vínculo da conta de um militar com a sua "persona" (o militar citado na escala).

Fluxo: o militar cria a conta, recebe acesso (leitura) a uma escala e pede para se vincular ao militar
dele nessa escala, criando um PIN. O detalhista (quem edita a escala) aprova ou rejeita. Aprovado, a conta
passa a ser daquele militar: enxerga as escalas em que ele está, pede troca para si, assina com o PIN e
pode abrir disponibilidade de troca. Se o militar já tem NIP no cadastro, o NIP informado precisa conferir.
"""
from __future__ import annotations

from datetime import datetime

from . import notificacoes as nt
from .auth import hash_pin
from .modelos import ConviteVinculo, Contexto, Usuario, Vinculo
from .permissoes import PermissaoNegada, eh_detalhista, pode_decidir, pode_ver


def _obter(ctx: Contexto, vid: str) -> Vinculo:
    v = next((x for x in ctx.vinculos if x.id == vid), None)
    if v is None:
        raise ValueError("pedido de vínculo não encontrado")
    return v


def militares_livres(ctx: Contexto, escala_id: str, para_usuario_id: str = "") -> list[str]:
    """Militares da escala que ainda não têm conta nem pedido de vínculo pendente.

    O militar do detalhista (fora da escala) só é oferecido ao próprio detalhista, para ele ligar a sua conta."""
    esc = ctx.escala(escala_id)
    ocupados = {u.militar_id for u in ctx.usuarios if u.militar_id}
    ocupados |= {v.militar_id for v in ctx.vinculos if v.status == "pendente"}
    ocupados |= {c.militar_id for c in ctx.convites_vinculo if c.status == "pendente"}
    ids = set(ctx.escalaveis(esc))
    if esc.detalhista_id and para_usuario_id and eh_detalhista(ctx, para_usuario_id, esc):
        ids.add(esc.detalhista_id)
    return sorted((m for m in ids if m not in ocupados), key=lambda i: ctx.antig(esc, i))


def _completar_cadastro(m, u) -> None:
    """Contato, posto e especialidade informados na conta completam os campos VAZIOS do militar (nunca sobrescrevem)."""
    for campo in ("email", "ramal", "celular", "posto", "especialidade"):
        if not getattr(m, campo) and getattr(u, campo):
            setattr(m, campo, getattr(u, campo))


def pendente_do_usuario(ctx: Contexto, usuario_id: str) -> Vinculo | None:
    return next((v for v in ctx.vinculos if v.usuario_id == usuario_id and v.status == "pendente"), None)


def solicitar(ctx: Contexto, usuario_id: str, escala_id: str, militar_id: str, nip: str, pin: str = "",
              agora: datetime | None = None) -> Vinculo:
    """`pin` em branco reaproveita o PIN que a conta já tem (só é exigido de quem ainda não cadastrou um).
    Se quem pede é o próprio detalhista da escala, não há quem aprove: o vínculo já nasce aprovado."""
    agora = agora or datetime.now()
    u = ctx.usuario(usuario_id)
    esc = ctx.escala(escala_id)
    if u is None or not u.ativo:
        raise PermissaoNegada("conta inválida")
    if u.militar_id:
        raise ValueError("sua conta já está vinculada a um militar")
    if pendente_do_usuario(ctx, usuario_id):
        raise ValueError("você já tem um pedido de vínculo aguardando decisão")
    if not pode_ver(ctx, usuario_id, esc):
        raise PermissaoNegada("você ainda não recebeu acesso a esta escala; peça ao detalhista")
    if militar_id not in militares_livres(ctx, escala_id, usuario_id):
        raise ValueError("esse militar não está disponível para vínculo (já vinculado ou com pedido pendente)")
    m = ctx.militar(militar_id)
    if m.nip and nip.strip() != m.nip:
        raise ValueError("NIP não confere com o cadastro do militar")
    if not pin and not u.pin_hash:
        raise ValueError("crie um PIN (4 a 6 dígitos) para assinar e pedir trocas")
    v = Vinculo(f"v{max([int(x.id[1:]) for x in ctx.vinculos] + [0]) + 1}", usuario_id, militar_id, escala_id,
                agora, hash_pin(pin) if pin else u.pin_hash)
    ctx.vinculos.append(v)
    if eh_detalhista(ctx, usuario_id, esc):
        _efetivar(ctx, u, m, v, usuario_id, agora)
        return v
    nt.notificar(ctx, nt.editores_da_escala(ctx, escala_id), "vinculo",
                 f"{u.nome} pediu para ser vinculado(a) a {m.nome} na escala {esc.nome}.", escala_id, agora)
    return v


def _exigir_editor(ctx: Contexto, usuario_id: str, v: Vinculo) -> None:
    if not pode_decidir(ctx, usuario_id, ctx.escala(v.escala_id)):
        raise PermissaoNegada("somente o detalhista e o auxiliar da escala decidem o vínculo")
    if v.usuario_id == usuario_id:
        raise PermissaoNegada("ninguém decide o próprio vínculo")


def _efetivar(ctx: Contexto, u: Usuario, m, v: Vinculo, decidido_por: str, agora: datetime) -> None:
    u.militar_id, u.pin_hash = m.id, (v.pin_hash or u.pin_hash)
    _completar_cadastro(m, u)
    v.status, v.decidido_por, v.decidido_em = "aprovado", decidido_por, agora


def aprovar(ctx: Contexto, usuario_id: str, vid: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    v = _obter(ctx, vid)
    _exigir_editor(ctx, usuario_id, v)
    if v.status != "pendente":
        raise ValueError(f"pedido {v.status}")
    u = ctx.usuario(v.usuario_id)
    if u is None or u.militar_id:
        raise ValueError("a conta já está vinculada ou não existe mais")
    if any(x.militar_id == v.militar_id for x in ctx.usuarios):
        raise ValueError("esse militar já foi vinculado a outra conta")
    m = ctx.militar(v.militar_id)
    _efetivar(ctx, u, m, v, usuario_id, agora)
    nt.notificar(ctx, [u.id], "vinculo", f"Seu vínculo com {m.nome} foi APROVADO. Você já pode pedir trocas e assinar com o PIN.",
                 v.escala_id, agora)


def rejeitar(ctx: Contexto, usuario_id: str, vid: str, motivo: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    v = _obter(ctx, vid)
    _exigir_editor(ctx, usuario_id, v)
    if v.status != "pendente":
        raise ValueError(f"pedido {v.status}")
    if not motivo.strip():
        raise ValueError("informe o motivo da rejeição")
    v.status, v.decidido_por, v.decidido_em, v.motivo_rejeicao = "rejeitado", usuario_id, agora, motivo.strip()
    nt.notificar(ctx, [v.usuario_id], "vinculo", f"Seu pedido de vínculo foi REJEITADO: {motivo.strip()}", v.escala_id, agora)


def cancelar(ctx: Contexto, usuario_id: str, vid: str) -> None:
    v = _obter(ctx, vid)
    if v.usuario_id != usuario_id:
        raise PermissaoNegada("só quem pediu cancela o próprio pedido")
    if v.status != "pendente":
        raise ValueError(f"pedido {v.status}")
    v.status = "cancelado"


def pendentes_para(ctx: Contexto, usuario_id: str) -> list[Vinculo]:
    return [v for v in ctx.vinculos if v.status == "pendente"
            and pode_decidir(ctx, usuario_id, ctx.escala(v.escala_id)) and v.usuario_id != usuario_id]


# ---------------------------------------------------------------- convite do detalhista
def _norm(txt: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower().strip()


def buscar_usuarios(ctx: Contexto, quem_id: str, escala_id: str, termo: str) -> list[Usuario]:
    """Usuários ativos, ainda sem vínculo e sem convite pendente, que combinam com o termo (nome, NIP ou OM).

    Só quem decide a escala busca, e o termo tem de ter ao menos 3 caracteres (não dá para listar todo mundo).
    A tela mostra apenas nome e OM: e-mail e telefone não saem daqui."""
    if not pode_decidir(ctx, quem_id, ctx.escala(escala_id)):
        raise PermissaoNegada("somente o detalhista e o auxiliar da escala convidam para o vínculo")
    t = _norm(termo)
    if len(t) < 3:
        return []
    com_convite = {c.usuario_id for c in ctx.convites_vinculo if c.status == "pendente"}
    achados = [u for u in ctx.usuarios
               if u.ativo and not u.militar_id and u.id != quem_id and u.id not in com_convite
               and t in " ".join([_norm(u.nome), _norm(u.login), _norm(u.om)])]
    return sorted(achados, key=lambda u: _norm(u.nome))


def convidar(ctx: Contexto, quem_id: str, usuario_id: str, militar_id: str, escala_id: str,
             agora: datetime | None = None) -> ConviteVinculo:
    agora = agora or datetime.now()
    esc = ctx.escala(escala_id)
    if not pode_decidir(ctx, quem_id, esc):
        raise PermissaoNegada("somente o detalhista e o auxiliar da escala convidam para o vínculo")
    u = ctx.usuario(usuario_id)
    if u is None or not u.ativo:
        raise ValueError("usuário não encontrado ou inativo")
    if u.id == quem_id:
        raise PermissaoNegada("ninguém convida a si mesmo")
    if u.militar_id:
        raise ValueError("essa conta já está vinculada a um militar")
    if any(c.usuario_id == u.id and c.status == "pendente" for c in ctx.convites_vinculo):
        raise ValueError("essa conta já tem um convite de vínculo aguardando resposta")
    if militar_id not in militares_livres(ctx, escala_id):
        raise ValueError("esse militar não está disponível (já vinculado, com pedido ou convite pendente)")
    m = ctx.militar(militar_id)
    if m.id == (ctx.usuario(quem_id).militar_id if ctx.usuario(quem_id) else ""):
        raise PermissaoNegada("ninguém convida a si mesmo")
    n = max([int(c.id[1:]) for c in ctx.convites_vinculo if c.id[1:].isdigit()] + [0]) + 1
    c = ConviteVinculo(f"c{n}", u.id, m.id, escala_id, agora, quem_id)
    ctx.convites_vinculo.append(c)
    quem = ctx.usuario(quem_id)
    nt.notificar(ctx, [u.id], "vinculo", f"{quem.nome} convidou você para ser {m.nome} na escala {esc.nome}. Abra Vínculos "
                 f"para aceitar (você confirma o NIP e cria o seu PIN) ou recusar.", escala_id, agora)
    return c


def convites_do_usuario(ctx: Contexto, usuario_id: str) -> list[ConviteVinculo]:
    return [c for c in ctx.convites_vinculo if c.usuario_id == usuario_id and c.status == "pendente"]


def convites_enviados(ctx: Contexto, quem_id: str) -> list[ConviteVinculo]:
    """Convites pendentes das escalas em que o usuário decide."""
    return [c for c in ctx.convites_vinculo if c.status == "pendente"
            and pode_decidir(ctx, quem_id, ctx.escala(c.escala_id))]


def _convite(ctx: Contexto, cid: str) -> ConviteVinculo:
    c = next((x for x in ctx.convites_vinculo if x.id == cid), None)
    if c is None:
        raise ValueError("convite não encontrado")
    return c


def aceitar_convite(ctx: Contexto, usuario_id: str, cid: str, nip: str, pin: str = "",
                    agora: datetime | None = None) -> None:
    """O convidado confirma o NIP e cria o PIN. A aprovação do detalhista já está no convite: o vínculo vale na hora."""
    agora = agora or datetime.now()
    c = _convite(ctx, cid)
    if c.usuario_id != usuario_id:
        raise PermissaoNegada("esse convite é de outra conta")
    if c.status != "pendente":
        raise ValueError(f"convite {c.status}")
    u = ctx.usuario(usuario_id)
    if u is None or u.militar_id:
        raise ValueError("sua conta já está vinculada ou não existe mais")
    if any(x.militar_id == c.militar_id for x in ctx.usuarios):
        raise ValueError("esse militar já foi vinculado a outra conta")
    m = ctx.militar(c.militar_id)
    if m.nip and nip.strip() != m.nip:
        raise ValueError("NIP não confere com o cadastro do militar")
    if not pin and not u.pin_hash:
        raise ValueError("crie um PIN (4 a 6 dígitos) para assinar e pedir trocas")
    v = Vinculo(f"v{max([int(x.id[1:]) for x in ctx.vinculos] + [0]) + 1}", usuario_id, m.id, c.escala_id, agora,
                hash_pin(pin) if pin else u.pin_hash, "aprovado", c.convidado_por, agora)
    ctx.vinculos.append(v)
    u.militar_id, u.pin_hash = m.id, v.pin_hash
    _completar_cadastro(m, u)
    for x in ctx.vinculos:                                   # um pedido que ele tivesse feito deixa de valer
        if x is not v and x.usuario_id == usuario_id and x.status == "pendente":
            x.status = "cancelado"
    for x in ctx.convites_vinculo:
        if x.usuario_id == usuario_id and x.status == "pendente":
            x.status, x.decidido_em = ("aceito" if x is c else "cancelado"), agora
    nt.notificar(ctx, [c.convidado_por], "vinculo", f"{u.nome} aceitou o convite e agora é {m.nome} na escala "
                 f"{ctx.escala(c.escala_id).nome}.", c.escala_id, agora)


def recusar_convite(ctx: Contexto, usuario_id: str, cid: str, agora: datetime | None = None) -> None:
    agora = agora or datetime.now()
    c = _convite(ctx, cid)
    if c.usuario_id != usuario_id:
        raise PermissaoNegada("esse convite é de outra conta")
    if c.status != "pendente":
        raise ValueError(f"convite {c.status}")
    c.status, c.decidido_em = "recusado", agora
    u = ctx.usuario(usuario_id)
    nt.notificar(ctx, [c.convidado_por], "vinculo", f"{u.nome} recusou o convite para ser {ctx.militar(c.militar_id).nome}.",
                 c.escala_id, agora)


def cancelar_convite(ctx: Contexto, quem_id: str, cid: str) -> None:
    c = _convite(ctx, cid)
    if not pode_decidir(ctx, quem_id, ctx.escala(c.escala_id)):
        raise PermissaoNegada("somente o detalhista e o auxiliar da escala cancelam o convite")
    if c.status != "pendente":
        raise ValueError(f"convite {c.status}")
    c.status = "cancelado"

"""Contas e login por NIP.

- O acesso é por **NIP e senha** (senha só como hash bcrypt; bloqueio temporário após falhas seguidas).
- Quem se cadastra (NIP, OM, contato) fica **pendente** até o administrador aprovar.
- O administrador é criado **automaticamente** pelo sistema (`garantir_admin`) e aprova, rejeita, edita,
  bloqueia, desbloqueia e exclui contas.
- Não existe "perfil": todo usuário aprovado pode criar ou importar escalas e vira o detalhista delas; os papéis
  (detalhista, auxiliar, militar) são por escala.
"""
from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timedelta

import bcrypt

from .contatos import normalizar_contato
from .modelos import Contexto, Usuario

ROUNDS = 12   # custo do bcrypt (os testes usam menos)
MAX_TENTATIVAS = 5
BLOQUEIO_MIN = 5
SITUACOES = ("pendente", "ativo", "bloqueado", "rejeitado")
PERFIS = ("usuario", "detalhista", "militar")      # legado: não influencia mais as permissões


class AutenticacaoErro(Exception):
    pass


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt(rounds=ROUNDS)).decode()


def _checar(senha: str, h: str) -> bool:
    try:
        return bool(h) and bcrypt.checkpw(senha.encode(), h.encode())
    except ValueError:
        return False


def _validar_senha(senha: str) -> None:
    if len(senha) < 8:
        raise ValueError("a senha deve ter pelo menos 8 caracteres")


def normalizar_nip(txt: str) -> str:
    """NIP sem pontos, traços ou espaços (é o login): '12.3456.78' -> '12345678'."""
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def validar_nip(nip: str) -> str:
    """NIP de militar: 6 a 10 dígitos (aceita pontos e traços). Retorna o NIP normalizado."""
    n = normalizar_nip(nip)
    if not (n.isdigit() and 6 <= len(n) <= 10):
        raise ValueError("NIP inválido: informe de 6 a 10 dígitos (ex.: 12.3456.78)")
    return n


def tem_usuarios(ctx: Contexto) -> bool:
    return bool(ctx.usuarios)


def _admins_ativos(ctx: Contexto) -> list[Usuario]:
    return [u for u in ctx.usuarios if u.admin and u.ativo]


def _novo_id(ctx: Contexto) -> str:
    return f"u{max([int(u.id[1:]) for u in ctx.usuarios if u.id[1:].isdigit()] + [0]) + 1}"


def _registrar(ctx, login, nome, senha, perfil, militar_id, admin, email, ramal, celular, nip="", om="",
               situacao="ativo", trocar_senha=False) -> Usuario:
    u = Usuario(_novo_id(ctx), nome.strip() or login, login, hash_senha(senha), militar_id, perfil, admin,
                ativo=situacao == "ativo", email=email, ramal=ramal, celular=celular, nip=nip or login,
                om=om.strip(), situacao=situacao, trocar_senha=trocar_senha)
    ctx.usuarios.append(u)
    return u


def criar_usuario(ctx: Contexto, quem_id: str | None, login: str, nome: str, senha: str, *,
                  perfil: str = "usuario", militar_id: str = "", admin: bool = False,
                  email: str = "", ramal: str = "", celular: str = "", exigir_contato: bool = False,
                  om: str = "") -> Usuario:
    """Cria uma conta já ATIVA. Só o administrador cria assim; a primeira conta do sistema nasce administradora.

    O cadastro normal é `cadastrar_se` (pendente de aprovação). `militar_id` existe só para migração e testes: o
    vínculo da conta com um militar exige a autorização do detalhista (ver `vinculos.py`)."""
    primeiro = not ctx.usuarios
    if not primeiro:
        quem = ctx.usuario(quem_id or "")
        if not (quem and quem.admin and quem.ativo):
            raise PermissionError("somente o administrador cria contas")
    login_n = normalizar_nip(login)
    if not login_n:
        raise ValueError("informe o NIP")
    if any(u.login == login_n for u in ctx.usuarios):
        raise ValueError(f"o NIP '{login}' já está cadastrado")
    if perfil not in PERFIS:
        raise ValueError("perfil inválido")
    if militar_id:
        if not any(m.id == militar_id for m in ctx.militares):
            raise ValueError("militar não encontrado no cadastro")
        if any(u.militar_id == militar_id for u in ctx.usuarios):
            raise ValueError("esse militar já tem conta")
    if exigir_contato or email or ramal or celular:
        email, ramal, celular = normalizar_contato(email, ramal, celular, obrigatorio=exigir_contato)
    _validar_senha(senha)
    return _registrar(ctx, login_n, nome, senha, perfil, militar_id, admin or primeiro, email, ramal, celular,
                      nip=login.strip(), om=om)


def cadastrar_se(ctx: Contexto, nip: str, nome: str, senha: str, email: str, ramal: str, celular: str,
                 om: str = "") -> Usuario:
    """O próprio militar pede o cadastro com NIP, OM e contato. A conta fica PENDENTE: só entra depois que o
    administrador aprovar. Os administradores são avisados."""
    if not ctx.cadastro_aberto:
        raise PermissionError("o cadastro de novas contas está fechado; fale com o administrador")
    login = validar_nip(nip)
    if any(u.login == login for u in ctx.usuarios):
        raise ValueError("já existe um cadastro com esse NIP")
    if not nome.strip():
        raise ValueError("informe o nome")
    if not om.strip():
        raise ValueError("informe a sua OM")
    email, ramal, celular = normalizar_contato(email, ramal, celular, obrigatorio=True)
    _validar_senha(senha)
    u = _registrar(ctx, login, nome, senha, "usuario", "", False, email, ramal, celular, nip=nip.strip(), om=om,
                   situacao="pendente")
    from . import notificacoes as nt
    nt.notificar(ctx, [a.id for a in _admins_ativos(ctx)], "cadastro",
                 f"Novo cadastro aguardando aprovação: {u.nome} (NIP {u.nip}, OM {u.om}).")
    return u


def garantir_admin(ctx: Contexto, nip: str = "admin", senha: str | None = None) -> tuple[Usuario | None, str | None]:
    """Cria o administrador automaticamente se ainda não houver nenhum.

    Com `senha` (vinda dos segredos/ambiente do deploy), a conta já nasce pronta. Sem `senha`, gera uma senha
    provisória forte (devolvida para ser gravada no log do servidor) e exige a troca no primeiro acesso.
    Retorna (usuario, senha_gerada) ou (None, None) se já existe administrador."""
    if any(u.admin for u in ctx.usuarios):
        return None, None
    gerada = None
    if not senha:
        gerada = senha = secrets.token_urlsafe(12)
    login = normalizar_nip(nip) or "admin"
    existente = next((u for u in ctx.usuarios if u.login == login), None)
    if existente is not None:                                   # promove a conta que já usa esse NIP
        existente.admin, existente.ativo, existente.situacao = True, True, "ativo"
        return existente, None
    u = _registrar(ctx, login, "Administrador", senha, "usuario", "", True, "", "", "", nip=nip.strip() or login,
                   trocar_senha=gerada is not None)
    return u, gerada


def sincronizar_admin(ctx: Contexto, nip: str, senha: str) -> bool:
    """Aplica ao administrador o NIP e a senha dos segredos/ambiente do deploy, quando eles MUDAM (ou ainda não foram
    aplicados): cria ou promove a conta, define a senha, ativa e zera bloqueio e tentativas. Se os segredos não mudaram,
    não mexe (a senha que o administrador trocou depois continua valendo). Retorna True se aplicou."""
    import hashlib
    login = normalizar_nip(nip) or "admin"
    sig = hashlib.sha256(f"{login}\n{senha}".encode()).hexdigest()
    if ctx.admin_cfg_sig == sig:
        return False
    _validar_senha(senha)
    u = next((x for x in ctx.usuarios if x.login == login), None)
    if u is None:
        _registrar(ctx, login, "Administrador", senha, "usuario", "", True, "", "", "", nip=nip.strip() or login)
    else:
        u.admin, u.ativo, u.situacao = True, True, "ativo"
        u.senha_hash, u.trocar_senha = hash_senha(senha), False
        u.tentativas, u.bloqueado_ate = 0, None
    ctx.admin_cfg_sig = sig
    return True


def atualizar_contato(ctx: Contexto, usuario_id: str, email: str, ramal: str, celular: str) -> None:
    u = ctx.usuario(usuario_id)
    if u is None:
        raise ValueError("usuário não encontrado")
    u.email, u.ramal, u.celular = normalizar_contato(email, ramal, celular, obrigatorio=True)
    m = next((x for x in ctx.militares if x.id == u.militar_id), None)
    if m:
        m.email, m.ramal, m.celular = u.email, u.ramal, u.celular


# ---------------------------------------------------------------- PIN de assinatura
def validar_pin(pin: str) -> None:
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        raise ValueError("o PIN deve ter de 4 a 6 dígitos numéricos")


def hash_pin(pin: str) -> str:
    validar_pin(pin)
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=ROUNDS)).decode()


def alterar_pin(ctx: Contexto, usuario_id: str, senha: str, novo_pin: str) -> None:
    u = ctx.usuario(usuario_id)
    if not u or not _checar(senha, u.senha_hash):
        raise AutenticacaoErro("senha incorreta")
    u.pin_hash = hash_pin(novo_pin)


def confirmar_assinatura(ctx: Contexto, usuario_id: str, pin: str, agora: datetime | None = None) -> bool:
    """Confirma com o PIN da conta (obrigatório para pedir troca e assinar). Erros seguidos bloqueiam a conta."""
    agora = agora or datetime.now()
    u = ctx.usuario(usuario_id)
    if not u or not u.ativo:
        return False
    if not u.pin_hash:
        raise AutenticacaoErro("cadastre o seu PIN no perfil (Minha conta)")
    if u.bloqueado_ate and u.bloqueado_ate > agora:
        raise AutenticacaoErro(f"conta bloqueada por excesso de tentativas até {u.bloqueado_ate:%H:%M}")
    if _checar(pin, u.pin_hash):
        u.tentativas = 0
        return True
    u.tentativas += 1
    if u.tentativas >= MAX_TENTATIVAS:
        u.bloqueado_ate, u.tentativas = agora + timedelta(minutes=BLOQUEIO_MIN), 0
    return False


# ---------------------------------------------------------------- login
def entrar(ctx: Contexto, nip: str, senha: str, agora: datetime | None = None) -> Usuario:
    """Entra com NIP e senha. A mensagem de erro é genérica (sem revelar o que falhou), exceto quando a senha está
    certa mas a conta ainda não pode entrar (pendente, rejeitada ou bloqueada)."""
    agora = agora or datetime.now()
    u = next((x for x in ctx.usuarios if x.login == normalizar_nip(nip)), None)
    if u is None:
        bcrypt.checkpw(b"x", bcrypt.hashpw(b"y", bcrypt.gensalt(rounds=ROUNDS)))   # custo parecido
        raise AutenticacaoErro("NIP ou senha incorretos")
    if u.bloqueado_ate and u.bloqueado_ate > agora:
        raise AutenticacaoErro(f"conta bloqueada por excesso de tentativas até {u.bloqueado_ate:%H:%M}")
    if not _checar(senha, u.senha_hash):
        if u.ativo:
            u.tentativas += 1
            if u.tentativas >= MAX_TENTATIVAS:
                u.bloqueado_ate, u.tentativas = agora + timedelta(minutes=BLOQUEIO_MIN), 0
        raise AutenticacaoErro("NIP ou senha incorretos")
    if u.situacao == "pendente":
        raise AutenticacaoErro("seu cadastro está aguardando a aprovação do administrador")
    if u.situacao == "rejeitado":
        raise AutenticacaoErro("seu cadastro não foi aprovado: fale com o administrador")
    if not u.ativo or u.situacao == "bloqueado":
        raise AutenticacaoErro("conta bloqueada pelo administrador")
    u.tentativas, u.bloqueado_ate = 0, None
    return u


def confirmar_senha(ctx: Contexto, usuario_id: str, senha: str) -> bool:
    """Reconfirmação de senha."""
    u = ctx.usuario(usuario_id)
    return bool(u and u.ativo and _checar(senha, u.senha_hash))


def trocar_senha(ctx: Contexto, usuario_id: str, atual: str, nova: str) -> None:
    u = ctx.usuario(usuario_id)
    if not u or not _checar(atual, u.senha_hash):
        raise AutenticacaoErro("senha atual incorreta")
    _validar_senha(nova)
    if _checar(nova, u.senha_hash):
        raise ValueError("a nova senha deve ser diferente da atual")
    u.senha_hash = hash_senha(nova)
    u.trocar_senha = False


# ---------------------------------------------------------------- administração de contas
def _exigir_admin(ctx: Contexto, quem_id: str) -> None:
    quem = ctx.usuario(quem_id)
    if not (quem and quem.admin and quem.ativo):
        raise PermissionError("somente o administrador gerencia contas")


def _alvo(ctx: Contexto, alvo_id: str) -> Usuario:
    alvo = ctx.usuario(alvo_id)
    if alvo is None:
        raise ValueError("usuário não encontrado")
    return alvo


def pendentes(ctx: Contexto) -> list[Usuario]:
    return [u for u in ctx.usuarios if u.situacao == "pendente"]


def aprovar_usuario(ctx: Contexto, admin_id: str, alvo_id: str) -> None:
    _exigir_admin(ctx, admin_id)
    alvo = _alvo(ctx, alvo_id)
    if alvo.situacao != "pendente":
        raise ValueError(f"o cadastro não está pendente (situação: {alvo.situacao})")
    alvo.situacao, alvo.ativo = "ativo", True


def rejeitar_usuario(ctx: Contexto, admin_id: str, alvo_id: str) -> None:
    _exigir_admin(ctx, admin_id)
    alvo = _alvo(ctx, alvo_id)
    if alvo.situacao != "pendente":
        raise ValueError(f"o cadastro não está pendente (situação: {alvo.situacao})")
    alvo.situacao, alvo.ativo = "rejeitado", False


def bloquear_usuario(ctx: Contexto, admin_id: str, alvo_id: str) -> None:
    _exigir_admin(ctx, admin_id)
    alvo = _alvo(ctx, alvo_id)
    if alvo.admin and len(_admins_ativos(ctx)) <= 1:
        raise ValueError("não é possível bloquear o único administrador")
    if alvo.id == admin_id:
        raise ValueError("você não pode bloquear a própria conta")
    alvo.situacao, alvo.ativo = "bloqueado", False


def desbloquear_usuario(ctx: Contexto, admin_id: str, alvo_id: str) -> None:
    """Libera a conta bloqueada (pelo administrador ou por excesso de tentativas) e zera as tentativas."""
    _exigir_admin(ctx, admin_id)
    alvo = _alvo(ctx, alvo_id)
    if alvo.situacao == "pendente":
        raise ValueError("o cadastro ainda está pendente: aprove-o em vez de desbloquear")
    alvo.situacao, alvo.ativo, alvo.tentativas, alvo.bloqueado_ate = "ativo", True, 0, None


def definir_ativo(ctx: Contexto, admin_id: str, alvo_id: str, ativo: bool) -> None:
    (desbloquear_usuario if ativo else bloquear_usuario)(ctx, admin_id, alvo_id)


def papeletas_abertas_do_militar(ctx: Contexto, militar_id: str) -> int:
    """Papeletas ainda em andamento em que o militar é parte (para avisar antes de desvincular)."""
    return sum(1 for p in ctx.papeletas if p.status in ("pendente", "aprovada")
               and militar_id in (p.solicitante_id, p.outro_id))


def desvincular_usuario(ctx: Contexto, admin_id: str, alvo_id: str) -> None:
    """O administrador desfaz o vínculo da conta com o militar. A conta continua existindo (sem vínculo, sem PIN: o
    próprio usuário pede outro vínculo ou recebe um convite); o militar continua cadastrado e nas escalas, e as
    assinaturas já registradas ficam como estão."""
    _exigir_admin(ctx, admin_id)
    alvo = _alvo(ctx, alvo_id)
    if not alvo.militar_id:
        raise ValueError("essa conta não está vinculada a nenhum militar")
    m = next((x for x in ctx.militares if x.id == alvo.militar_id), None)
    for v in ctx.vinculos:
        if v.usuario_id == alvo.id and v.status == "aprovado":
            v.status = "desfeito"
    alvo.militar_id, alvo.pin_hash = "", ""
    from . import notificacoes as nt
    nt.notificar(ctx, [alvo.id], "vinculo",
                 f"O administrador desfez o vínculo da sua conta com {m.nome if m else 'o militar'}. Peça um novo vínculo "
                 f"(ou aguarde um convite) em Vínculos.")


def redefinir_senha(ctx: Contexto, admin_id: str, alvo_id: str, nova: str) -> None:
    """Senha provisória: o usuário será obrigado a trocá-la no próximo acesso."""
    _exigir_admin(ctx, admin_id)
    _validar_senha(nova)
    alvo = _alvo(ctx, alvo_id)
    alvo.senha_hash, alvo.tentativas, alvo.bloqueado_ate = hash_senha(nova), 0, None
    alvo.trocar_senha = alvo.id != admin_id


def editar_usuario(ctx: Contexto, admin_id: str, alvo_id: str, *, nome: str | None = None, nip: str | None = None,
                   om: str | None = None, email: str | None = None, ramal: str | None = None,
                   celular: str | None = None, admin: bool | None = None) -> Usuario:
    """O administrador corrige nome, NIP, OM, contato e o papel de administrador de uma conta."""
    _exigir_admin(ctx, admin_id)
    alvo = _alvo(ctx, alvo_id)
    if nip is not None and normalizar_nip(nip) != alvo.login:
        novo = validar_nip(nip) if not alvo.admin else (normalizar_nip(nip) or alvo.login)
        if any(u.login == novo and u.id != alvo.id for u in ctx.usuarios):
            raise ValueError("já existe uma conta com esse NIP")
        alvo.login, alvo.nip = novo, nip.strip()
    if nome is not None:
        if not nome.strip():
            raise ValueError("informe o nome")
        alvo.nome = nome.strip()
    if om is not None:
        alvo.om = om.strip()
    if any(v is not None for v in (email, ramal, celular)):
        alvo.email, alvo.ramal, alvo.celular = normalizar_contato(
            alvo.email if email is None else email, alvo.ramal if ramal is None else ramal,
            alvo.celular if celular is None else celular, obrigatorio=False)
    if admin is not None and admin != alvo.admin:
        if not admin and len(_admins_ativos(ctx)) <= 1 and alvo.admin:
            raise ValueError("não é possível tirar o papel do único administrador")
        alvo.admin = admin
    return alvo


def excluir_usuario(ctx: Contexto, admin_id: str, alvo_id: str) -> None:
    """Exclui a conta. Não exclui a si mesmo, o único administrador, nem quem ainda é detalhista de escalas
    (reatribua as escalas antes). Limpa acessos, pedidos, vínculos e avisos dessa conta."""
    _exigir_admin(ctx, admin_id)
    alvo = _alvo(ctx, alvo_id)
    if alvo.id == admin_id:
        raise ValueError("você não pode excluir a própria conta")
    if alvo.admin and len(_admins_ativos(ctx)) <= 1:
        raise ValueError("não é possível excluir o único administrador")
    donas = [e.nome for e in ctx.escalas if e.dono_id == alvo.id]
    if donas:
        raise ValueError("esta conta é o detalhista de: " + ", ".join(donas) + ". Passe as escalas a outro usuário antes.")
    for e in ctx.escalas:
        e.compartilhado_com.pop(alvo.id, None)
    ctx.vinculos = [v for v in ctx.vinculos if v.usuario_id != alvo.id]
    ctx.pedidos_acesso = [p for p in ctx.pedidos_acesso if p.usuario_id != alvo.id]
    ctx.convites_vinculo = [c for c in ctx.convites_vinculo if c.usuario_id != alvo.id]
    ctx.notificacoes = [n for n in ctx.notificacoes if n.usuario_id != alvo.id]
    ctx.usuarios = [u for u in ctx.usuarios if u.id != alvo.id]


def reatribuir_escalas(ctx: Contexto, admin_id: str, de_id: str, para_id: str) -> int:
    """Passa as escalas de um detalhista para outro usuário (ex.: antes de excluir a conta de quem saiu)."""
    _exigir_admin(ctx, admin_id)
    de, para = _alvo(ctx, de_id), _alvo(ctx, para_id)
    if para.id == de.id or not para.ativo:
        raise ValueError("escolha outro usuário ativo para receber as escalas")
    n = 0
    for e in ctx.escalas:
        if e.dono_id == de.id:
            e.dono_id, e.detalhista_id, e.detalhista_escalavel = para.id, para.militar_id, False
            e.compartilhado_com.pop(para.id, None)
            e.auxiliares = [a for a in e.auxiliares if a != para.militar_id]
            n += 1
    return n

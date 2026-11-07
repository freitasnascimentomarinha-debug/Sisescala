"""Contas e login. Senhas só como hash bcrypt; bloqueio temporário após falhas seguidas."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

import bcrypt

from .contatos import normalizar_contato
from .modelos import Contexto, Usuario

ROUNDS = 12   # custo do bcrypt (os testes usam menos)
MAX_TENTATIVAS = 5
BLOQUEIO_MIN = 5
PERFIS = ("detalhista", "militar")


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


def _slug_login(txt: str) -> str:
    t = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[^a-z0-9._-]+", "", t)


def tem_usuarios(ctx: Contexto) -> bool:
    return bool(ctx.usuarios)


def criar_usuario(ctx: Contexto, quem_id: str | None, login: str, nome: str, senha: str, *,
                  perfil: str = "detalhista", militar_id: str = "", admin: bool = False,
                  email: str = "", ramal: str = "", celular: str = "", exigir_contato: bool = False) -> Usuario:
    """Só administrador cria contas; a primeira conta do sistema nasce administradora.

    `militar_id` existe só para migração e testes: o app NÃO o expõe, porque o vínculo da conta com um militar
    exige a autorização do detalhista (ver `vinculos.py`)."""
    primeiro = not ctx.usuarios
    if not primeiro:
        quem = ctx.usuario(quem_id or "")
        if not (quem and quem.admin and quem.ativo):
            raise PermissionError("somente o administrador cria contas")
    login = _slug_login(login)
    if not login:
        raise ValueError("informe o login")
    if any(u.login == login for u in ctx.usuarios):
        raise ValueError(f"login '{login}' já existe")
    if perfil not in PERFIS:
        raise ValueError("perfil inválido")
    if perfil == "militar" and militar_id:
        if not any(m.id == militar_id for m in ctx.militares):
            raise ValueError("militar não encontrado no cadastro")
        if any(u.militar_id == militar_id for u in ctx.usuarios):
            raise ValueError("esse militar já tem conta")
    if exigir_contato or email or ramal or celular:
        email, ramal, celular = normalizar_contato(email, ramal, celular, obrigatorio=exigir_contato)
    _validar_senha(senha)
    return _registrar(ctx, login, nome, senha, perfil, militar_id, admin or primeiro, email, ramal, celular)


def _registrar(ctx, login, nome, senha, perfil, militar_id, admin, email, ramal, celular) -> Usuario:
    uid = f"u{max([int(u.id[1:]) for u in ctx.usuarios if u.id[1:].isdigit()] + [0]) + 1}"
    u = Usuario(uid, nome.strip() or login, login, hash_senha(senha), militar_id, perfil, admin,
                email=email, ramal=ramal, celular=celular)
    ctx.usuarios.append(u)
    return u


def cadastrar_se(ctx: Contexto, login: str, nome: str, senha: str, email: str, ramal: str, celular: str) -> Usuario:
    """O próprio militar cria a conta (perfil militar, sem acesso a nada até receber uma escala e ser
    vinculado). Contato obrigatório. O administrador pode fechar o cadastro."""
    if not ctx.cadastro_aberto:
        raise PermissionError("o cadastro de novas contas está fechado; fale com o administrador")
    login = _slug_login(login)
    if not login:
        raise ValueError("informe o login")
    if any(u.login == login for u in ctx.usuarios):
        raise ValueError(f"login '{login}' já existe")
    if not nome.strip():
        raise ValueError("informe o nome")
    email, ramal, celular = normalizar_contato(email, ramal, celular, obrigatorio=True)
    _validar_senha(senha)
    return _registrar(ctx, login, nome, senha, "militar", "", False, email, ramal, celular)


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


def entrar(ctx: Contexto, login: str, senha: str, agora: datetime | None = None) -> Usuario:
    """Retorna o usuário ou levanta AutenticacaoErro (mensagem genérica, sem revelar o que falhou)."""
    agora = agora or datetime.now()
    u = next((x for x in ctx.usuarios if x.login == _slug_login(login)), None)
    if u is None:
        bcrypt.checkpw(b"x", bcrypt.hashpw(b"y", bcrypt.gensalt(rounds=ROUNDS)))   # custo parecido
        raise AutenticacaoErro("login ou senha incorretos")
    if u.bloqueado_ate and u.bloqueado_ate > agora:
        raise AutenticacaoErro(f"conta bloqueada por excesso de tentativas até {u.bloqueado_ate:%H:%M}")
    if not u.ativo or not _checar(senha, u.senha_hash):
        if u.ativo:
            u.tentativas += 1
            if u.tentativas >= MAX_TENTATIVAS:
                u.bloqueado_ate, u.tentativas = agora + timedelta(minutes=BLOQUEIO_MIN), 0
        raise AutenticacaoErro("login ou senha incorretos")
    u.tentativas, u.bloqueado_ate = 0, None
    return u


def confirmar_senha(ctx: Contexto, usuario_id: str, senha: str) -> bool:
    """Reconfirmação de senha (ex.: para assinar uma papeleta)."""
    u = ctx.usuario(usuario_id)
    return bool(u and u.ativo and _checar(senha, u.senha_hash))


def trocar_senha(ctx: Contexto, usuario_id: str, atual: str, nova: str) -> None:
    u = ctx.usuario(usuario_id)
    if not u or not _checar(atual, u.senha_hash):
        raise AutenticacaoErro("senha atual incorreta")
    _validar_senha(nova)
    u.senha_hash = hash_senha(nova)


def _exigir_admin(ctx: Contexto, quem_id: str) -> None:
    quem = ctx.usuario(quem_id)
    if not (quem and quem.admin and quem.ativo):
        raise PermissionError("somente o administrador gerencia contas")


def redefinir_senha(ctx: Contexto, admin_id: str, alvo_id: str, nova: str) -> None:
    _exigir_admin(ctx, admin_id)
    _validar_senha(nova)
    alvo = ctx.usuario(alvo_id)
    if alvo is None:
        raise ValueError("usuário não encontrado")
    alvo.senha_hash, alvo.tentativas, alvo.bloqueado_ate = hash_senha(nova), 0, None


def definir_ativo(ctx: Contexto, admin_id: str, alvo_id: str, ativo: bool) -> None:
    _exigir_admin(ctx, admin_id)
    alvo = ctx.usuario(alvo_id)
    if alvo is None:
        raise ValueError("usuário não encontrado")
    if not ativo and alvo.admin and sum(1 for u in ctx.usuarios if u.admin and u.ativo) <= 1:
        raise ValueError("não é possível desativar o único administrador")
    alvo.ativo = ativo

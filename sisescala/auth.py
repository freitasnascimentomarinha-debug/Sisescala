"""Contas e login. Senhas só como hash bcrypt; bloqueio temporário após falhas seguidas."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

import bcrypt

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
                  perfil: str = "detalhista", militar_id: str = "", admin: bool = False) -> Usuario:
    """Só administrador cria contas; a primeira conta do sistema nasce administradora."""
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
    if perfil == "militar":
        if not militar_id or not any(m.id == militar_id for m in ctx.militares):
            raise ValueError("conta de militar precisa estar vinculada a um militar do cadastro")
        if any(u.militar_id == militar_id for u in ctx.usuarios):
            raise ValueError("esse militar já tem conta")
    _validar_senha(senha)
    uid = f"u{max([int(u.id[1:]) for u in ctx.usuarios if u.id[1:].isdigit()] + [0]) + 1}"
    u = Usuario(uid, nome.strip() or login, login, hash_senha(senha), militar_id, perfil, admin or primeiro)
    ctx.usuarios.append(u)
    return u


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

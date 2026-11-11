"""Trecho de referência (SisEscala, sisescala/auth.py): ciclo de vida do PIN — validar, guardar só o hash (bcrypt), confirmar na hora de assinar com bloqueio por tentativas, alterar com a senha da conta e redefinir pelo administrador (que só APAGA)."""
from datetime import datetime, timedelta
import bcrypt
ROUNDS, MAX_TENTATIVAS, BLOQUEIO_MIN = 12, 5, 5   # ajuste ao seu servidor


class AutenticacaoErro(Exception):
    pass


def _checar(texto: str, hash_: str) -> bool:
    return bcrypt.checkpw(texto.encode(), hash_.encode())


# `ctx` é o contexto/repositório do seu sistema; `_exigir_admin`, `_alvo` e `nt.notificar` são os equivalentes locais de
# "só o administrador", "buscar o usuário" e "criar aviso para o usuário". Aqui só o miolo do ciclo de vida do PIN:

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
def redefinir_pin(ctx: Contexto, admin_id: str, alvo_id: str, agora: datetime | None = None) -> None:
    """Esqueceu o PIN? O administrador APAGA o PIN da conta (e zera as tentativas/bloqueio). Ele nunca define um PIN: quem escolhe
    o novo é a própria pessoa, em Minha conta, confirmando com a senha. Até lá a conta não assina nem pede trocas."""
    from . import notificacoes as nt
    _exigir_admin(ctx, admin_id)
    alvo = _alvo(ctx, alvo_id)
    if not alvo.pin_hash:
        raise ValueError("esta conta não tem PIN cadastrado")
    alvo.pin_hash, alvo.tentativas, alvo.bloqueado_ate = "", 0, None
    nt.notificar(ctx, [alvo.id], "conta", "O administrador apagou o seu PIN. Cadastre um novo em Minha conta (você confirma com a "
                 "sua senha). Enquanto isso você não consegue assinar documentos nem pedir trocas.", "", agora, excluir=[admin_id])



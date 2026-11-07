"""Disponibilidade de troca: o militar sinaliza, no dia em que está escalado, que aceita trocar.

Na prévia aparece uma bolinha piscando na célula. Só vale para serviço futuro, dentro da antecedência
mínima da escala, que ainda seja dele (se o serviço mudar de mãos, o sinal some) e enquanto ele não
estiver num pedido de troca ativo.
"""
from __future__ import annotations

from datetime import date, datetime

from . import notificacoes as nt
from .modelos import Contexto, Disponibilidade
from .motor import Resultado
from .papeletas import antecedencia_ok, militar_do_usuario, militares_em_pedido_ativo
from .permissoes import PermissaoNegada, pode_editar


def _alocacao(res: Resultado, d: date, escala_id: str, mid: str):
    dia = res.dia(d, escala_id)
    return next((a for a in (dia.alocacoes if dia else []) if a.militar_id == mid and a.origem == "normal"), None)


def abertas(ctx: Contexto, res: Resultado, escala_id: str) -> dict[tuple[date, str], Disponibilidade]:
    """Sinais válidos agora: (data, militar) -> disponibilidade."""
    ativos = militares_em_pedido_ativo(ctx)
    return {(x.data, x.militar_id): x for x in ctx.disponibilidades
            if x.escala_id == escala_id and x.militar_id not in ativos
            and _alocacao(res, x.data, escala_id, x.militar_id) is not None}


def alternar(ctx: Contexto, usuario_id: str, escala_id: str, militar_id: str, data: date, res: Resultado,
             agora: datetime | None = None) -> bool:
    """Abre ou fecha a disponibilidade. Retorna True se ficou aberta."""
    agora = agora or datetime.now()
    esc = ctx.escala(escala_id)
    if not (pode_editar(ctx, usuario_id, esc) or militar_do_usuario(ctx, usuario_id) == militar_id):
        raise PermissaoNegada("você só pode sinalizar disponibilidade para o seu próprio serviço")
    atual = next((x for x in ctx.disponibilidades
                  if (x.escala_id, x.militar_id, x.data) == (escala_id, militar_id, data)), None)
    if atual:
        ctx.disponibilidades.remove(atual)
        return False
    if _alocacao(res, data, escala_id, militar_id) is None:
        raise ValueError("o militar não está escalado (ou o serviço dele veio de uma troca) nesse dia")
    if militar_id in militares_em_pedido_ativo(ctx):
        raise ValueError("o militar já está em um pedido de troca ativo")
    if not antecedencia_ok(esc, data, data, agora):
        raise ValueError(f"a troca exige pelo menos {esc.antecedencia_horas}h de antecedência do serviço")
    ctx.disponibilidades.append(Disponibilidade(escala_id, militar_id, data, agora, usuario_id))
    m = ctx.militar(militar_id)
    nt.notificar(ctx, nt.usuarios_da_escala(ctx, escala_id), "disponibilidade",
                 f"{m.nome} está aberto(a) a trocar o serviço de {data:%d/%m} ({esc.nome}).", escala_id, agora,
                 excluir=[usuario_id, *nt.usuarios_do_militar(ctx, militar_id)])
    return True


def podar(ctx: Contexto, hoje: date | None = None) -> int:
    """Remove sinais de dias que já passaram."""
    hoje = hoje or date.today()
    antes = len(ctx.disponibilidades)
    ctx.disponibilidades = [x for x in ctx.disponibilidades if x.data >= hoje]
    return antes - len(ctx.disponibilidades)

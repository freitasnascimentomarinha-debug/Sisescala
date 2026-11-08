"""Dias e períodos especiais por escala, "conta como" preta/vermelha/roxa e carimbo de quem lançou."""
from datetime import date, datetime, timedelta

import pytest

from sisescala import auth, gestao
from sisescala import lancamentos as lc
from sisescala.calendario import conta_como, dia_util
from sisescala.modelos import *
from sisescala.motor import fila_do_dia, funciona, gerar
from sisescala.permissoes import PermissaoNegada
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)            # segunda-feira
SENHA = "senha-forte-1"
AGORA = datetime(2027, 2, 20, 10, 30)


def mundo():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"1000000{i}") for i in range(1, 8)]
    c = Contexto(ms, [], D)
    adm, _ = auth.garantir_admin(c, "admin", SENHA)
    det = auth.criar_usuario(c, adm.id, "20000001", "Detalhista", SENHA)
    aux_u = auth.criar_usuario(c, adm.id, "20000002", "Auxiliar", SENHA, militar_id="m2")
    gestao.criar_escala(c, det.id, Escala("e1", "Um", modo="preta_vermelha", data_base=D, auxiliares=["m2"],
                                           membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    return c, adm, det, aux_u


def test_periodo_licenca_conta_como_preta_vermelha_e_automatico():
    c, adm, det, _ = mundo()
    e = c.escala("e1")
    ter, qua = D + timedelta(days=1), D + timedelta(days=2)
    assert dia_util(ter, c, e) and conta_como(ter, c, e) == "preta"
    lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "sem_expediente", "Licença", "e1", qua), AGORA)   # período de 2 dias
    assert not dia_util(ter, c, e) and not dia_util(qua, c, e) and dia_util(D + timedelta(days=3), c, e)
    assert fila_do_dia(c, e, ter) == "vermelha"                                                          # automático
    # sábado forçado a preta (compensação) e dia útil forçado a vermelha
    sab = D + timedelta(days=5)
    lc.lancar_dia_especial(c, det.id, DiaEspecial(sab, "sem_expediente", "Expediente extra", "e1", None, "preta"))
    assert dia_util(sab, c, e) and fila_do_dia(c, e, sab) == "preta"
    qui = D + timedelta(days=3)
    lc.lancar_dia_especial(c, det.id, DiaEspecial(qui, "feriado", "Feriado trabalhado", "e1", None, "vermelha"))
    assert fila_do_dia(c, e, qui) == "vermelha"
    lc.lancar_dia_especial(c, det.id, DiaEspecial(qui + timedelta(days=1), "feriado", "Feriado preta", "e1", None, "preta"))
    assert fila_do_dia(c, e, qui + timedelta(days=1)) == "preta"                                         # feriado contado como preta


def test_dia_especial_so_vale_na_escala_e_validacoes():
    c, adm, det, _ = mundo()
    gestao.criar_escala(c, det.id, Escala("e2", "Dois", modo="preta_vermelha", data_base=D,
                                           membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    ter = D + timedelta(days=1)
    lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "sem_expediente", "x", "e1"))
    assert not dia_util(ter, c, c.escala("e1")) and dia_util(ter, c, c.escala("e2"))
    with pytest.raises(ValueError, match="anterior"):
        lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "feriado", "x", "e1", ter - timedelta(days=1)))
    with pytest.raises(ValueError, match="conta como"):
        lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "feriado", "x", "e1", None, "roxa"))
    with pytest.raises(ValueError, match="tipo"):
        lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "outro", "x", "e1"))


def test_periodo_roxo_por_escala_so_detalhista_e_participa_roxa():
    c, adm, det, aux_u = mundo()
    e = c.escala("e1")
    d1, d2 = D + timedelta(days=7), D + timedelta(days=9)
    with pytest.raises(ValueError, match="não participa da roxa"):
        e.participa_roxa = False
        lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Recesso", d1, d2, "e1"))
    e.participa_roxa = True
    with pytest.raises(PermissaoNegada, match="detalhista"):
        lc.lancar_periodo_roxo(c, aux_u.id, PeriodoRoxa("", "Recesso", d1, d2, "e1"))            # auxiliar não
    with pytest.raises(PermissaoNegada, match="administrador"):
        lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Recesso", d1, d2, ""))                # geral só admin
    lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Recesso", d1, d2, "e1"), AGORA)
    assert c.roxas[0].id == "r1" and c.roxas[0].criado_por == det.id
    assert fila_do_dia(c, e, d1) == "roxa:r1" and conta_como(d1, c, e) == "roxa" and funciona(c, e, d1)
    with pytest.raises(ValueError, match="coincide"):
        lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Outro", d2, d2 + timedelta(days=2), "e1"))
    assert not lc.pode_remover(c, aux_u.id, c.roxas[0]) and lc.pode_remover(c, det.id, c.roxas[0])
    lc.remover(c, det.id, c.roxas[0])
    assert c.roxas == []


def test_roxo_de_uma_escala_nao_vale_em_outra():
    c, adm, det, _ = mundo()
    gestao.criar_escala(c, det.id, Escala("e2", "Dois", modo="preta_vermelha", data_base=D,
                                           membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    d1 = D + timedelta(days=7)
    lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Só da e1", d1, d1, "e1"))
    assert fila_do_dia(c, c.escala("e1"), d1).startswith("roxa:") and not fila_do_dia(c, c.escala("e2"), d1).startswith("roxa:")
    gerar(c, D + timedelta(days=10))                                                              # não quebra


def test_quem_lancou_e_quando_em_todos_os_lancamentos_e_persiste():
    c, adm, det, aux_u = mundo()
    lc.lancar_impedimento(c, det.id, Impedimento("m3", "ferias", D, D + timedelta(days=5)), AGORA)
    lc.lancar_dispensa_no_dia(c, aux_u.id, Ocorrencia(D, "e1", "m4", "baixa médica"), AGORA)
    lc.lancar_guarnecimento(c, det.id, Guarnecimento(D, "e1", True), AGORA)
    lc.lancar_dia_especial(c, det.id, DiaEspecial(D + timedelta(days=1), "feriado", "x", "e1"), AGORA)
    itens = [*c.impedimentos, *c.ocorrencias, *c.guarnecimentos, *c.dias_especiais]
    assert all(i.criado_em == AGORA and i.criado_por for i in itens)
    assert c.ocorrencias[0].criado_por == aux_u.id and c.impedimentos[0].criado_por == det.id
    c2 = de_tabelas(para_tabelas(c))
    assert [(i.criado_por, i.criado_em) for i in c2.impedimentos] == [(det.id, AGORA)]
    assert c2.dias_especiais[0].data_fim is None and c2.dias_especiais[0].criado_em == AGORA
    # planilha antiga (sem as colunas novas) carrega com carimbo vazio
    T = {k: [list(r) for r in v] for k, v in para_tabelas(c).items()}
    cab = T["Impedimentos"][0]
    for nome in ("criado_por", "criado_em"):
        j = T["Impedimentos"][0].index(nome)
        T["Impedimentos"] = [[x for k, x in enumerate(r) if k != j] for r in T["Impedimentos"]]
    c3 = de_tabelas(T)
    assert c3.impedimentos[0].criado_por == "" and c3.impedimentos[0].criado_em is None


def test_roxo_antigo_sem_escala_continua_valendo_para_todas():
    c, adm, det, _ = mundo()
    d1 = D + timedelta(days=7)
    c.roxas.append(PeriodoRoxa("fa", "Recesso antigo", d1, d1))                                   # dado de antes (sem escala)
    assert fila_do_dia(c, c.escala("e1"), d1) == "roxa:fa"
    with pytest.raises(PermissaoNegada):
        lc.remover(c, det.id, c.roxas[0])                                                         # geral só o administrador
    lc.remover(c, adm.id, c.roxas[0])

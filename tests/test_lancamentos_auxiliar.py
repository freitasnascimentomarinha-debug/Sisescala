"""O auxiliar também lança dispensas e demais lançamentos nas escalas dele, exceto para ele mesmo."""
from datetime import date, timedelta

import pytest

from sisescala import auth
from sisescala import lancamentos as lc
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.permissoes import PermissaoNegada

D = date(2027, 3, 1)
SENHA = "senha-forte-1"
CONTATO = dict(email="a@b.com", ramal="2345", celular="21987654321")
AUX, M3 = "u2", "u3"


def mk():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, 11)]
    a = Escala("A", "Portaria", dono_id="u1", detalhista_id="m1", auxiliares=["m2"],
               membros=[Pertinencia(f"m{i}") for i in range(1, 7)])                      # m1..m6
    b = Escala("B", "Outra", dono_id="u1", detalhista_id="m1", auxiliares=["m9"],
               membros=[Pertinencia(f"m{i}") for i in (1, 7, 8, 9, 10)], modo="eventos", categoria="palestra",
               retem_qtd=0)
    c = Contexto(ms, [a, b], D)
    auth.criar_usuario(c, None, "det", "Detalhista", SENHA, admin=True)                  # u1
    auth.criar_usuario(c, "u1", "aux", "Auxiliar", SENHA, perfil="militar", militar_id="m2", **CONTATO)   # u2
    auth.criar_usuario(c, "u1", "mil3", "Mil 3", SENHA, perfil="militar", militar_id="m3", **CONTATO)     # u3
    return c


def imp(mid, tipo="dispensa_justificada", motivo="Baixa médica"):
    return Impedimento(mid, tipo, D, D + timedelta(days=2), motivo)


def test_auxiliar_lanca_dispensa_para_militar_da_escala_dele():
    c = mk()
    lc.lancar_impedimento(c, AUX, imp("m4"))
    assert [i.militar_id for i in c.impedimentos] == ["m4"]
    r = gerar(c, D + timedelta(days=6))
    assert all(a.militar_id != "m4" for d in range(3) for a in r.dia(D + timedelta(days=d), "A").efetivos)


def test_auxiliar_nao_lanca_para_si_mesmo():
    c = mk()
    with pytest.raises(PermissaoNegada, match="para si mesmo"):
        lc.lancar_impedimento(c, AUX, imp("m2"))
    with pytest.raises(PermissaoNegada, match="para si mesmo"):
        lc.lancar_dispensa_no_dia(c, AUX, Ocorrencia(D, "A", "m2", "passei mal"))
    assert c.impedimentos == [] and c.ocorrencias == []
    assert "m2" not in lc.militares_lancaveis(c, AUX)                              # nem aparece na lista da tela


def test_auxiliar_so_lanca_para_militares_das_escalas_dele():
    c = mk()
    assert set(lc.militares_lancaveis(c, AUX)) == {"m1", "m3", "m4", "m5", "m6"}
    with pytest.raises(PermissaoNegada, match="escalas em que é"):
        lc.lancar_impedimento(c, AUX, imp("m8"))                                   # m8 só está na escala B


def test_auxiliar_lanca_dispensa_no_dia_com_justificativa_e_o_retem_avanca():
    c = mk()
    lc.lancar_dispensa_no_dia(c, AUX, Ocorrencia(D + timedelta(days=1), "A", "m3", "Falta justificada"))
    assert c.ocorrencias[0].militar_id == "m3"
    assert any(n.usuario_id == M3 and "dispensado do serviço" in n.texto and "Falta justificada" in n.texto
               for n in c.notificacoes)                                           # o militar é avisado
    with pytest.raises(ValueError, match="justificativa"):
        lc.lancar_dispensa_no_dia(c, AUX, Ocorrencia(D, "A", "m4", ""))
    with pytest.raises(ValueError, match="não faz parte"):
        lc.lancar_dispensa_no_dia(c, AUX, Ocorrencia(D, "A", "m8", "x"))


def test_auxiliar_nao_lanca_em_escala_de_que_nao_e_auxiliar():
    c = mk()
    with pytest.raises(PermissaoNegada, match="escalas em que é"):
        lc.lancar_dispensa_no_dia(c, AUX, Ocorrencia(D, "B", "m7", "x"))
    with pytest.raises(PermissaoNegada):
        lc.lancar_guarnecimento(c, AUX, Guarnecimento(D, "B", True))
    with pytest.raises(PermissaoNegada):
        lc.lancar_evento(c, AUX, Evento("B", D, "Palestra"))


def test_auxiliar_lanca_dia_especial_guarnecimento_e_evento_nas_escalas_dele():
    c = mk()
    c.escalas[0].funciona_em = "uteis"
    lc.lancar_dia_especial(c, AUX, DiaEspecial(D + timedelta(days=1), "sem_expediente", "Licença administrativa"))
    lc.lancar_guarnecimento(c, AUX, Guarnecimento(D + timedelta(days=1), "A", True))
    assert len(c.dias_especiais) == 1 and len(c.guarnecimentos) == 1
    c.escalas[1].auxiliares = ["m9", "m2"]                                                # agora também auxiliar da escala por evento
    lc.lancar_evento(c, AUX, Evento("B", D, "Palestra"))
    assert len(c.eventos) == 1
    with pytest.raises(ValueError, match="Por evento"):
        lc.lancar_evento(c, AUX, Evento("A", D, "x"))                              # A não é por evento


def test_militar_comum_nao_lanca_nada():
    c = mk()
    assert lc.escalas_lancaveis(c, M3) == [] and lc.militares_lancaveis(c, M3) == []
    for acao in (lambda: lc.lancar_impedimento(c, M3, imp("m4")),
                 lambda: lc.lancar_dispensa_no_dia(c, M3, Ocorrencia(D, "A", "m4", "x")),
                 lambda: lc.lancar_dia_especial(c, M3, DiaEspecial(D, "feriado", "x")),
                 lambda: lc.lancar_guarnecimento(c, M3, Guarnecimento(D, "A", True))):
        with pytest.raises(PermissaoNegada):
            acao()


def test_detalhista_lanca_para_qualquer_militar_e_tambem_nao_para_si_se_estiver_ligado_a_um():
    c = mk()
    lc.lancar_impedimento(c, "u1", imp("m8"))                                      # qualquer militar, mesmo de outra escala
    assert len(c.impedimentos) == 1
    c.usuario("u1").militar_id = "m1"                                              # detalhista ligado ao militar m1
    with pytest.raises(PermissaoNegada, match="para si mesmo"):
        lc.lancar_impedimento(c, "u1", imp("m1"))
    assert "m1" not in lc.militares_lancaveis(c, "u1")


def test_auxiliar_remove_lancamentos_dos_outros_mas_nao_os_proprios():
    c = mk()
    lc.lancar_impedimento(c, "u1", imp("m2"))                                      # o detalhista lança para o auxiliar
    lc.lancar_impedimento(c, AUX, imp("m4"))
    proprio, alheio = c.impedimentos[0], c.impedimentos[1]
    assert not lc.pode_remover(c, AUX, proprio) and lc.pode_remover(c, AUX, alheio)
    with pytest.raises(PermissaoNegada, match="para si mesmo"):
        lc.remover(c, AUX, proprio)
    lc.remover(c, AUX, alheio)
    assert c.impedimentos == [proprio]
    lc.lancar_dispensa_no_dia(c, "u1", Ocorrencia(D, "A", "m2", "x"))              # dispensa do próprio auxiliar
    assert not lc.pode_remover(c, AUX, c.ocorrencias[0])
    lc.lancar_dia_especial(c, AUX, DiaEspecial(D, "feriado", "x"))
    lc.remover(c, AUX, c.dias_especiais[0])
    assert c.dias_especiais == []

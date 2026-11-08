"""Só o detalhista edita as regras da escala; o auxiliar não (nem criar, excluir, compartilhar ou mexer nos membros)."""
from datetime import date

import pytest

from sisescala import auth, gestao
from sisescala.modelos import *
from sisescala.motor import avisos_escala
from sisescala.permissoes import PermissaoNegada, compartilhar, eh_detalhista, referenciar

D = date(2027, 3, 1)
SENHA = "senha-forte-1"
CONTATO = dict(email="a@b.com", ramal="2345", celular="21987654321")
AUX, M3, DET2 = "u2", "u3", "u4"


def mk():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, 9)]
    e = Escala("e1", "Portaria", dono_id="u1", detalhista_id="m1", auxiliares=["m2"],
               membros=[Pertinencia(f"m{i}") for i in range(1, 9)])
    c = Contexto(ms, [e], D)
    auth.criar_usuario(c, None, "det", "Detalhista", SENHA, admin=True)                                  # u1 (dono)
    auth.criar_usuario(c, "u1", "aux", "Auxiliar", SENHA, perfil="militar", militar_id="m2", **CONTATO)  # u2
    auth.criar_usuario(c, "u1", "mil3", "Mil 3", SENHA, perfil="militar", militar_id="m3", **CONTATO)    # u3
    auth.criar_usuario(c, "u1", "det2", "Detalhista 2", SENHA)                                           # u4 (editor)
    compartilhar(c, "u1", "e1", DET2, "edicao")
    return c


def test_auxiliar_nao_edita_nenhuma_regra_da_escala():
    c = mk()
    for campos in ({"folgas_minimas": 1}, {"militares_dia": 2}, {"quartos": []}, {"prioridade": 9},
                   {"auxiliares": []}, {"detalhista_id": "m2"}, {"detalhista_escalavel": True}, {"nome": "Outra"}):
        with pytest.raises(PermissaoNegada, match="só o detalhista"):
            gestao.editar_escala(c, AUX, "e1", **campos)
    e = c.escala("e1")
    assert (e.folgas_minimas, e.militares_dia, e.prioridade, e.auxiliares, e.detalhista_id, e.nome) == \
           (2, 1, 1, ["m2"], "m1", "Portaria")                                      # nada mudou


def test_auxiliar_nao_cria_nem_exclui_nem_compartilha_nem_mexe_nos_membros_nem_referencia():
    c = mk()
    # qualquer usuário aprovado cria a sua escala (e vira detalhista dela), mas isso não dá poder sobre a e1
    nova = gestao.criar_escala(c, AUX, Escala("e2", "Nova", membros=[Pertinencia(m) for m in ("m3", "m4", "m5")]))
    assert nova.dono_id == AUX and not eh_detalhista(c, AUX, c.escala("e1"))
    with pytest.raises(PermissaoNegada):
        gestao.excluir_escala(c, AUX, "e1")
    with pytest.raises(PermissaoNegada, match="dono"):
        compartilhar(c, AUX, "e1", M3, "leitura")
    with pytest.raises(PermissaoNegada, match="só o detalhista"):
        gestao.adicionar_militares(c, AUX, "e1", ["m3"])
    with pytest.raises(PermissaoNegada, match="só o detalhista"):
        gestao.remover_militares(c, AUX, "e1", ["m3"])
    with pytest.raises(PermissaoNegada):
        referenciar(c, AUX, "e1", "e1")
    assert [e.id for e in c.escalas] == ["e1", "e2"] and len(c.escala("e1").membros) == 8


def test_conta_de_militar_comum_tambem_nao_edita():
    c = mk()
    with pytest.raises(PermissaoNegada):
        gestao.editar_escala(c, M3, "e1", folgas_minimas=0)


def test_detalhista_dono_edita_as_regras_e_o_auxiliar_ve_o_resultado():
    c = mk()
    novo = gestao.editar_escala(c, "u1", "e1", folgas_minimas=2, militares_dia=2, antecedencia_horas=48,
                                auxiliares=["m4"], om="Centro de Operações")
    assert (novo.folgas_minimas, novo.militares_dia, novo.antecedencia_horas, novo.auxiliares) == (2, 2, 48, ["m4"])
    assert c.escala("e1").om == "Centro de Operações" and c.escala("e1").membros == novo.membros


def test_outro_detalhista_com_edicao_edita_mas_nao_exclui_nem_compartilha():
    c = mk()
    gestao.editar_escala(c, DET2, "e1", prioridade=5)
    assert c.escala("e1").prioridade == 5
    with pytest.raises(PermissaoNegada, match="dono"):
        gestao.excluir_escala(c, DET2, "e1")
    with pytest.raises(PermissaoNegada):
        compartilhar(c, DET2, "e1", M3, "leitura")


def test_edicao_e_validada_e_campos_protegidos_nao_passam():
    c = mk()
    gestao.editar_escala(c, "u1", "e1", militares_dia=8)                          # 8 por dia com 2x1: só avisa
    assert avisos_escala(c, c.escala("e1"))
    gestao.editar_escala(c, "u1", "e1", militares_dia=1)
    with pytest.raises(ValueError, match="auxiliar não pode ser o próprio detalhista"):
        gestao.editar_escala(c, "u1", "e1", auxiliares=["m1"])
    for campo in ("dono_id", "membros", "compartilhado_com", "referencias", "id"):
        with pytest.raises(ValueError, match="não editável"):
            gestao.editar_escala(c, "u1", "e1", **{campo: "x"})
    assert c.escala("e1").militares_dia == 1


def test_detalhista_cria_escala_vira_dono_e_exclui():
    c = mk()
    nova = gestao.criar_escala(c, DET2, Escala("e2", "Nova", dono_id="u9", membros=[Pertinencia(f"m{i}") for i in range(1, 6)]))
    assert nova.dono_id == DET2                                                    # dono é quem criou, não o que veio no objeto
    with pytest.raises(ValueError, match="já existe"):
        gestao.criar_escala(c, DET2, Escala("e2", "Outra", membros=[]))
    with pytest.raises(ValueError, match="nome"):
        gestao.criar_escala(c, DET2, Escala("e3", "  "))
    gestao.excluir_escala(c, DET2, "e2")
    assert [e.id for e in c.escalas] == ["e1"]


def test_detalhista_gerencia_membros():
    c = mk()
    assert gestao.remover_militares(c, "u1", "e1", ["m8"]) == 1
    assert gestao.adicionar_militares(c, "u1", "e1", ["m8"]) == 1

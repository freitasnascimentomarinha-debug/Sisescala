"""Cada escala tem a sua numeração de antiguidade; mexer numa não desloca a outra."""
from datetime import date

import pytest

from sisescala import auth, cadastro as cd, gestao
from sisescala import importacao as imp
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.permissoes import PermissaoNegada
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)
SENHA = "senha-forte-1"


def mundo():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"1000000{i}") for i in range(1, 9)]
    c = Contexto(ms, [], D)
    adm, _ = auth.garantir_admin(c, "admin", SENHA)
    a = auth.criar_usuario(c, adm.id, "20000001", "A", SENHA)
    b = auth.criar_usuario(c, adm.id, "20000002", "B", SENHA)
    gestao.criar_escala(c, a.id, Escala("e1", "Um", membros=[Pertinencia(f"m{i}") for i in (1, 2, 3, 4)], data_base=D))
    gestao.criar_escala(c, b.id, Escala("e2", "Dois", membros=[Pertinencia(f"m{i}") for i in (3, 4, 5, 6)], data_base=D))
    return c, a, b


def ordem(c, eid):
    return c.ordem_na_escala(c.escala(eid))


def test_numeracao_nasce_sequencial_em_cada_escala():
    c, a, b = mundo()
    assert ordem(c, "e1") == ["m1", "m2", "m3", "m4"] and ordem(c, "e2") == ["m3", "m4", "m5", "m6"]
    assert [c.antig(c.escala("e2"), i) for i in ordem(c, "e2")] == [1, 2, 3, 4]


def test_mudar_antiguidade_numa_escala_nao_mexe_na_outra_e_so_o_detalhista_muda():
    c, a, b = mundo()
    gestao.mudar_antiguidade(c, a.id, "e1", "m4", 1)
    assert ordem(c, "e1") == ["m4", "m1", "m2", "m3"]
    assert ordem(c, "e2") == ["m3", "m4", "m5", "m6"]                 # a outra ficou igual
    with pytest.raises(PermissaoNegada):
        gestao.mudar_antiguidade(c, b.id, "e1", "m1", 2)
    with pytest.raises(ValueError):
        gestao.mudar_antiguidade(c, a.id, "e1", "m8", 1)               # não está na escala


def test_alterar_o_cadastro_global_nao_reordena_as_escalas():
    c, a, b = mundo()
    cd.editar_militar(c, "m6", antiguidade=1)                          # reordena só o cadastro (legado)
    assert ordem(c, "e1") == ["m1", "m2", "m3", "m4"] and ordem(c, "e2") == ["m3", "m4", "m5", "m6"]


def test_entra_no_fim_ou_na_posicao_pedida_e_sair_renumera():
    c, a, b = mundo()
    gestao.adicionar_militares(c, a.id, "e1", ["m8"])
    assert ordem(c, "e1")[-1] == "m8"
    gestao.adicionar_militares(c, a.id, "e1", ["m7"], posicao=1)
    assert ordem(c, "e1")[0] == "m7"
    gestao.remover_militares(c, a.id, "e1", ["m1"])
    assert [c.antig(c.escala("e1"), i) for i in ordem(c, "e1")] == list(range(1, 6))
    assert ordem(c, "e2") == ["m3", "m4", "m5", "m6"]


def test_a_fila_do_servico_segue_a_antiguidade_da_escala():
    c, a, b = mundo()
    gestao.mudar_antiguidade(c, a.id, "e1", "m4", 1)
    r = gerar(c, D + __import__("datetime").timedelta(days=4))
    quem = [r.dia(D + __import__("datetime").timedelta(days=i), "e1").efetivos[0].militar_id for i in range(4)]
    assert quem == ["m4", "m1", "m2", "m3"]


def test_persistencia_guarda_a_numeracao_e_planilha_antiga_herda_a_do_cadastro():
    c, a, b = mundo()
    gestao.mudar_antiguidade(c, a.id, "e1", "m4", 1)
    assert ordem(de_tabelas(para_tabelas(c)), "e1") == ["m4", "m1", "m2", "m3"]
    T = {k: [list(r) for r in v] for k, v in para_tabelas(c).items()}
    cab = T["EscalaMembros"][0]
    i = cab.index("antiguidade")
    T["EscalaMembros"] = [[x for k, x in enumerate(r) if k != i] for r in T["EscalaMembros"]]   # sem a coluna nova
    assert ordem(de_tabelas(T), "e1") == ["m1", "m2", "m3", "m4"]


def test_importacao_ordena_so_as_escalas_citadas():
    c, a, b = mundo()
    linhas = [{"Nome de guerra": f"M{i}", "NIP": f"1000000{i}", "Escala": "Um", "Ordem": str(o)}
              for i, o in ((2, 1), (1, 2), (3, 3), (4, 4))]
    novo, _ = imp.importar(c, linhas, usuario_id=a.id, dono_id=a.id, sobrescrever=False)
    assert ordem(novo, "e1") == ["m1", "m2", "m3", "m4"]               # escala existente: quem já estava mantém o lugar
    assert ordem(novo, "e2") == ["m3", "m4", "m5", "m6"]
    linhas2 = [{"Nome de guerra": n, "NIP": nip, "Escala": "Nova"} for n, nip in
               (("Zeta", "30000003"), ("Alfa", "30000001"))]
    novo2, rel = imp.importar(c, linhas2, usuario_id=a.id, dono_id=a.id, sobrescrever=False)
    nid = next(e.id for e in novo2.escalas if e.nome == "Nova")
    assert [novo2.militar(i).nome for i in ordem(novo2, nid)] == ["Zeta", "Alfa"]     # escala criada: ordem da planilha
    assert ordem(novo2, "e1") == ["m1", "m2", "m3", "m4"]

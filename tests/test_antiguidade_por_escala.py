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


def test_definir_ordem_da_escala_inteira_e_validacoes():
    c, a, b = mundo()
    gestao.definir_ordem_da_escala(c, a.id, "e1", ["m3", "m1", "m4", "m2"])
    assert ordem(c, "e1") == ["m3", "m1", "m4", "m2"] and ordem(c, "e2") == ["m3", "m4", "m5", "m6"]
    with pytest.raises(PermissaoNegada):
        gestao.definir_ordem_da_escala(c, b.id, "e1", ["m1", "m2", "m3", "m4"])
    with pytest.raises(ValueError, match="não confere"):
        gestao.definir_ordem_da_escala(c, a.id, "e1", ["m1", "m2"])


def test_componente_ignora_valor_velho(monkeypatch):
    from sisescala import componente
    itens = [{"id": i, "nome": i, "posto": ""} for i in ("a", "b", "c")]
    monkeypatch.setattr(componente, "_ordem", lambda **kw: {"base": ["a", "b", "c"], "ordem": ["b", "a", "c"]})
    assert componente.ordem_interativa(itens, "k") == ["b", "a", "c"]
    monkeypatch.setattr(componente, "_ordem", lambda **kw: {"base": ["c", "a", "b"], "ordem": ["b", "a", "c"]})
    assert componente.ordem_interativa(itens, "k") is None            # a ordem já mudou por outro caminho
    monkeypatch.setattr(componente, "_ordem", lambda **kw: None)
    assert componente.ordem_interativa(itens, "k") is None


def test_escala_nasce_vazia_gera_sem_erro_e_recebe_militares_por_importacao():
    from datetime import timedelta
    from sisescala.motor import avisos_escala
    c = Contexto([], [], D)
    adm, _ = auth.garantir_admin(c, "admin", SENHA)
    e = gestao.criar_escala(c, adm.id, Escala("e1", "Portaria", data_base=D))      # sem nenhum militar
    assert e.membros == [] and "ainda não tem militares" in avisos_escala(c, e)[0]
    r = gerar(c, D + timedelta(days=5))                                              # não quebra
    assert not r.dia(D, "e1").efetivos
    linhas = [{"Nome de guerra": f"M{i}", "NIP": f"1000000{i}", "Escala": "Portaria"} for i in range(1, 5)]
    novo, rel = imp.importar(c, linhas, usuario_id=adm.id, dono_id=adm.id, sobrescrever=False)
    assert not rel.erros and [m.nome for m in novo.militares] == ["M1", "M2", "M3", "M4"]
    assert len(novo.escala("e1").membros) == 4 and len(novo.escalas) == 1             # entrou na escala criada
    assert not avisos_escala(novo, novo.escala("e1"))
    assert gerar(novo, D + timedelta(days=2)).dia(D, "e1").efetivos


def test_importar_em_escala_existente_acrescenta_ou_substitui_com_protecao():
    c, a, b = mundo()
    # e1 = m1..m4 (detalhista a); e2 = m3..m6 (detalhista b). m3 e m4 são das duas.
    linhas = [{"Nome de guerra": "Novo Nome", "NIP": "10000001", "OM": "XYZ", "Posto": "1T"},
              {"Nome de guerra": "Outro Nome", "NIP": "10000003", "OM": "XYZ"},
              {"Nome de guerra": "Zé", "NIP": "10000008", "OM": "XYZ"}]
    # acrescentar: ninguém sai e dados existentes não mudam
    n1, r1 = imp.importar(c, linhas, usuario_id=a.id, dono_id=a.id, sobrescrever=False, escala_destino="e1")
    assert not r1.erros and ordem(n1, "e1")[:4] == ["m1", "m2", "m3", "m4"] and len(ordem(n1, "e1")) == 5
    assert n1.militar("m1").nome == "M1" and r1.removidos == []
    # substituir: a escala fica exatamente como a planilha; m1 (só da e1) tem os dados trocados; m3 (também da e2) é protegido
    n2, r2 = imp.importar(c, linhas, usuario_id=a.id, dono_id=a.id, sobrescrever=True, substituir_membros=True,
                          escala_destino="e1")
    assert [n2.militar(i).nip for i in ordem(n2, "e1")] == ["10000001", "10000003", "10000008"]
    assert n2.militar("m1").nome == "Novo Nome" and n2.militar("m1").om == "XYZ"
    assert n2.militar("m3").nome == "M3" and r2.protegidos == 2                       # m3 (de outra escala) e m8 (sem escala) não são trocados
    assert sorted(r2.removidos) == ["M2 (Um)", "M4 (Um)"]
    assert ordem(n2, "e2") == ["m3", "m4", "m5", "m6"]                                # a escala do outro intacta
    # escala de destino que não é sua
    n3, r3 = imp.importar(c, linhas, usuario_id=a.id, dono_id=a.id, escala_destino="e2")
    assert r3.erros


def test_posicao_ao_cadastrar_1_e_o_mais_antigo_0_e_no_fim():
    c, a, b = mundo()                                    # e1 = m1..m4
    gestao.adicionar_militares(c, a.id, "e1", ["m5"], None, 1)
    assert ordem(c, "e1") == ["m5", "m1", "m2", "m3", "m4"]          # 1 = o mais antigo
    gestao.adicionar_militares(c, a.id, "e1", ["m6"], None, 3)
    assert ordem(c, "e1") == ["m5", "m1", "m6", "m2", "m3", "m4"]    # 3 = terceiro da fila
    gestao.adicionar_militares(c, a.id, "e1", ["m7"], None, None)
    assert ordem(c, "e1")[-1] == "m7"                                # sem posição (0): no fim, o mais moderno
    gestao.adicionar_militares(c, a.id, "e1", ["m8"], None, 99)
    assert ordem(c, "e1")[-1] == "m8"                                # posição além do fim: no fim

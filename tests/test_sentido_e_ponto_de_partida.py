"""A fila gira do mais moderno para o mais antigo (padrão) e o detalhista informa onde a escala está hoje."""
from datetime import date, timedelta

import pytest

from sisescala import auth, cadastro as cd, gestao
from sisescala import importacao as imp
from sisescala.modelos import *
from sisescala.motor import filas_da_escala, gerar, proximo_da_fila
from sisescala.permissoes import PermissaoNegada
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)           # segunda-feira (preta)
SENHA = "senha-forte-1"


def mundo(sentido="moderno_antigo", modo="corrida", n=7):
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"1000000{i}") for i in range(1, n + 1)]
    c = Contexto(ms, [], D)
    adm, _ = auth.garantir_admin(c, "admin", SENHA)
    outro = auth.criar_usuario(c, adm.id, "20000002", "Outro", SENHA)
    gestao.criar_escala(c, adm.id, Escala("e1", "Portaria", modo=modo, data_base=D, sentido_fila=sentido, folgas_minimas=2,
                                           membros=[Pertinencia(m.id) for m in ms]))
    return c, adm, outro


def quem(c, i, eid="e1"):
    r = gerar(c, D + timedelta(days=30))
    return [a.militar_id for a in r.dia(D + timedelta(days=i), eid).efetivos]


def test_padrao_comeca_no_mais_moderno_e_sobe_ate_o_mais_antigo():
    c, adm, _ = mundo()                                                   # moderno_antigo (padrão)
    assert [quem(c, i)[0] for i in range(9)] == ["m7", "m6", "m5", "m4", "m3", "m2", "m1", "m7", "m6"]
    assert c.escala("e1").sentido_fila == "moderno_antigo"
    inverso, *_ = mundo("antigo_moderno")
    assert [quem(inverso, i)[0] for i in range(4)] == ["m1", "m2", "m3", "m4"]       # opção de inverter


def test_escala_antiga_sem_a_coluna_carrega_com_o_padrao_novo():
    c, *_ = mundo("antigo_moderno")
    T = {k: [list(r) for r in v] for k, v in para_tabelas(c).items()}
    j = T["Escalas"][0].index("sentido_fila")
    T["Escalas"] = [[x for k, x in enumerate(r) if k != j] for r in T["Escalas"]]
    assert de_tabelas(T).escala("e1").sentido_fila == "moderno_antigo"
    assert de_tabelas(para_tabelas(c)).escala("e1").sentido_fila == "antigo_moderno"   # e guarda o que foi escolhido


def test_ponto_de_partida_continua_a_escala_de_quem_esta_de_servico():
    c, adm, outro = mundo()
    assert proximo_da_fila(c, c.escala("e1"), "corrida", D) == "m7"                    # início da fila
    e = c.escala("e1")
    gestao.definir_ponto_de_partida(c, adm.id, "e1", D + timedelta(days=10), {"corrida": "m4"})
    assert e.data_base == D + timedelta(days=10) and e.ultimo_servico["corrida"] == "m5"
    r = gerar(c, D + timedelta(days=20))
    assert r.dia(D, "e1") is None and r.dia(D + timedelta(days=9), "e1") is None               # antes da data: nada
    seq = [r.dia(D + timedelta(days=10 + i), "e1").efetivos[0].militar_id for i in range(5)]
    assert seq == ["m4", "m3", "m2", "m1", "m7"]                                      # m4 está de serviço e a fila segue
    gestao.definir_ponto_de_partida(c, adm.id, "e1", D, {"corrida": ""})               # volta ao início da fila
    assert "corrida" not in e.ultimo_servico and quem(c, 0)[0] == "m7"
    gestao.definir_ponto_de_partida(c, adm.id, "e1", D, {"corrida": "m7"})              # escolher o 1º da fila = início
    assert "corrida" not in e.ultimo_servico


def test_ponto_de_partida_em_escala_preta_e_vermelha_e_validacoes():
    c, adm, outro = mundo(modo="preta_vermelha")
    e = c.escala("e1")
    assert filas_da_escala(e) == ["preta", "vermelha"]
    gestao.definir_ponto_de_partida(c, adm.id, "e1", D, {"preta": "m5", "vermelha": "m2"})
    r = gerar(c, D + timedelta(days=8))
    assert r.dia(D, "e1").efetivos[0].militar_id == "m5"                               # segunda: fila preta começa em m5
    sab = D + timedelta(days=5)
    gestao.definir_ponto_de_partida(c, adm.id, "e1", sab, {"preta": "m5", "vermelha": "m2"})
    assert gerar(c, sab + timedelta(days=3)).dia(sab, "e1").efetivos[0].militar_id == "m2"   # sábado: vermelha começa em m2
    with pytest.raises(PermissaoNegada):
        gestao.definir_ponto_de_partida(c, outro.id, "e1", D, {"preta": "m5"})          # só o detalhista
    with pytest.raises(ValueError, match="fila inválida"):
        gestao.definir_ponto_de_partida(c, adm.id, "e1", D, {"roxa:x": "m5"})
    with pytest.raises(ValueError, match="não pode ser escalado"):
        gestao.definir_ponto_de_partida(c, adm.id, "e1", D, {"preta": "inexistente"})
    e.detalhista_id = "m3"                                                              # o detalhista fica fora da escala
    with pytest.raises(ValueError, match="não pode ser escalado"):
        gestao.definir_ponto_de_partida(c, adm.id, "e1", D, {"preta": "m3"})


def test_retirar_quem_deu_o_ultimo_servico_mantem_a_fila_no_sentido_novo():
    c, adm, _ = mundo()
    e = c.escala("e1")
    e.ultimo_servico = {"corrida": "m5"}                 # no sentido moderno→antigo, quem serviu antes de m5 foi m6
    gestao.remover_militares(c, adm.id, "e1", ["m5"])
    assert e.ultimo_servico["corrida"] == "m6"
    assert proximo_da_fila(c, e, "corrida", D) == "m4"                                  # a fila segue de onde estava


def test_importacao_com_historico_continua_no_sentido_moderno_antigo():
    c, adm, _ = mundo()
    c.escalas.clear()
    gestao.criar_escala(c, adm.id, Escala("e1", "Portaria", data_base=D, sentido_fila="moderno_antigo", folgas_minimas=2))
    linhas = [{"Nome de guerra": f"M{i}", "NIP": f"1000000{i}", "Escala": "Portaria", "Ordem": str(i), "Data": ""}
              for i in range(1, 8)]
    linhas[2]["Data"] = (D - timedelta(days=1)).strftime("%d/%m/%Y")                     # M3 deu o último serviço
    linhas[3]["Data"] = (D - timedelta(days=2)).strftime("%d/%m/%Y")                     # M4 antes dele
    novo, rel = imp.importar(c, linhas, usuario_id=adm.id, dono_id=adm.id)
    assert novo.escala("e1").ultimo_servico["corrida"] == "m3"
    r = gerar(novo, D + timedelta(days=3))
    assert r.dia(D, "e1").efetivos[0].militar_id == "m2"                                # depois de M3 vem M2 (mais antigo)

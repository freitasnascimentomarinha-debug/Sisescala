"""O detalhista é dispensado de serviço: não dá nenhum serviço e não é escalado para nada."""
from datetime import date, timedelta

from sisescala import auth, cadastro as cd, vinculos as vc
from sisescala import papeletas as pp
from sisescala.importacao import importar, ler_tabela
from sisescala.modelos import *
from sisescala.motor import gerar, validar_escala
from sisescala.persistencia import de_tabelas, para_tabelas
from sisescala.previa import html_previa, periodo
from sisescala.relatorio import situacao_atual

D = date(2027, 3, 1)


def mk(n=5, **kw):
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, n + 1)]
    ms[0].detalhista = True                                   # m1 é o detalhista
    e = Escala("A", "Portaria", dono_id="u1", membros=[Pertinencia(m.id) for m in ms], **kw)
    return Contexto(ms, [e], D)


def todos(res, escala="A", dias=12):
    efet, ret = [], []
    for i in range(dias):
        dia = res.dia(D + timedelta(days=i), escala)
        efet += [a.militar_id for a in dia.efetivos]
        ret += [a.militar_id for a in dia.retens]
    return efet, ret


def test_detalhista_nunca_e_escalado_nem_efetivo_nem_retem():
    c = mk(retem_qtd=2, militares_dia=1)
    efet, ret = todos(gerar(c, D + timedelta(days=12)))
    assert "m1" not in efet and "m1" not in ret
    assert set(efet) == {"m2", "m3", "m4", "m5"}                  # os demais se revezam normalmente


def test_detalhista_nao_consome_vez_na_fila():
    c = mk()
    r = gerar(c, D + timedelta(days=7))
    assert [r.dia(D + timedelta(days=i), "A").efetivos[0].militar_id for i in range(8)] == \
           ["m2", "m3", "m4", "m5", "m2", "m3", "m4", "m5"]


def test_detalhista_vem_tambem_da_conta_de_perfil_detalhista():
    c = mk()
    c.militares[0].detalhista = False
    c.militares[1].detalhista = False
    auth.criar_usuario(c, None, "det", "Detalhista", "senha-forte-1", admin=True)
    c.usuario("u1").militar_id = "m2"                              # conta de detalhista ligada ao militar m2
    assert c.dispensado_de_servico("m2") and not c.dispensado_de_servico("m3")
    efet, ret = todos(gerar(c, D + timedelta(days=12)))
    assert "m2" not in efet and "m2" not in ret and "m1" in efet


def test_detalhista_fora_das_escalacoes_que_nao_sao_servico():
    pal = Escala("P", "Palestras", dono_id="u1", categoria="palestra", modo="eventos", militares_dia=2, retem_qtd=0,
                 membros=[Pertinencia(f"m{i}") for i in range(1, 6)])
    c = mk()
    c.escalas.append(pal)
    c.eventos += [Evento("P", D + timedelta(days=i), f"Palestra {i}") for i in range(1, 8)]
    efet, _ = todos(gerar(c, D + timedelta(days=10)), "P", 10)
    assert efet and "m1" not in efet


def test_detalhista_nao_conta_para_o_minimo_de_militares():
    c = mk(n=4)                                                   # m1 detalhista + 3 escaláveis, 1 por dia, 2x1
    assert validar_escala(c, c.escala("A")) == []
    c.escala("A").militares_dia = 2                              # precisaria de 6; só há 3 escaláveis
    assert validar_escala(c, c.escala("A"))
    c2 = mk(n=3)                                                  # 1 detalhista + 2: não respeita 2x1 (precisa de 3)
    assert validar_escala(c2, c2.escala("A"))


def test_previa_nao_mostra_o_detalhista_e_a_contagem_o_ignora():
    c = mk()
    r = gerar(c, D + timedelta(days=6))
    html = html_previa(c, r, periodo(D, 7), "A")
    assert "CB M1<" not in html and "CB M2<" in html
    assert ("Militares na escala</span><b>4</b>" in html)


def test_troca_com_detalhista_nao_e_possivel():
    c = mk()
    c.escala("A").militares_dia = 1
    r = gerar(c, D + timedelta(days=5))
    erros, _, _ = pp.validar_troca(c, c.escala("A"), "m2", D, "m1", D + timedelta(days=1))
    assert erros and any("M1 não está escalado" in e for e in erros)


def test_detalhista_nao_e_persona_para_vinculo_nem_aparece_no_relatorio_como_escalado():
    c = mk()
    assert "m1" not in vc.militares_livres(c, "A")
    sit = dict(situacao_atual(c, c.escala("A")))
    assert "Detalhistas (dispensados de serviço)" in sit and sit["Detalhistas (dispensados de serviço)"] == "M1"
    assert "M1" not in next(v for k, v in sit.items() if k.startswith("Militares na escala"))


def test_cadastro_marca_detalhista_e_persiste():
    c = Contexto([], [], D)
    m = cd.adicionar_militar(c, "Silva", "1SG", detalhista=True)
    n = cd.adicionar_militar(c, "Souza", "CB")
    assert m.detalhista and not n.detalhista
    cd.editar_militar(c, n.id, detalhista=True)
    assert c.dispensado_de_servico(n.id)
    cd.editar_militar(c, n.id, detalhista=False)
    assert not c.dispensado_de_servico(n.id)
    c2 = de_tabelas(para_tabelas(c))
    assert [x.detalhista for x in c2.militares] == [True, False]


def test_importacao_com_coluna_detalhista():
    csv = ("Nome de guerra;Posto;NIP;Escala;Detalhista\n"
           "SILVA;1SG;1.1;Portaria;sim\nSOUZA;CB;2.2;Portaria;\nLIMA;CB;3.3;Portaria;não\n")
    novo, rel = importar(Contexto([], [], D), ler_tabela(csv.encode(), "x.csv"))
    por_nome = {m.nome: m.detalhista for m in novo.militares}
    assert por_nome == {"SILVA": True, "SOUZA": False, "LIMA": False}


def test_conta_de_detalhista_aponta_o_militar_dela_e_ele_fica_dispensado():
    c = Contexto([Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, 5)], [], D)
    adm = auth.criar_usuario(c, None, "adm", "Adm", "senha-forte-1")
    u = auth.criar_usuario(c, adm.id, "det", "Detalhista", "senha-forte-1", militar_id="m3")   # perfil detalhista
    assert u.perfil == "detalhista" and c.dispensado_de_servico("m3") and not c.dispensado_de_servico("m4")
    with __import__("pytest").raises(ValueError, match="já tem conta"):
        auth.criar_usuario(c, adm.id, "det2", "Outro", "senha-forte-1", militar_id="m3")

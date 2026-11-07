"""Detalhista por escala: um só em cada escala, pode ser o mesmo em várias, fica fora por padrão (opção de
concorrer) e o auxiliar concorre normalmente."""
from datetime import date, timedelta

from sisescala import vinculos as vc
from sisescala import papeletas as pp
from sisescala.importacao import importar, ler_tabela
from sisescala.modelos import *
from sisescala.motor import gerar, validar_escala
from sisescala.persistencia import de_tabelas, para_tabelas
from sisescala.previa import html_previa, periodo
from sisescala.relatorio import itens_configuracao, situacao_atual, texto_funcionamento

D = date(2027, 3, 1)


def escala(eid="A", ids=("m1", "m2", "m3", "m4", "m5"), **kw):
    return Escala(eid, f"Escala {eid}", dono_id="u1", membros=[Pertinencia(i) for i in ids], **kw)


def mk(n=5, **kw):
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, n + 1)]
    return Contexto(ms, [escala(ids=tuple(m.id for m in ms), detalhista_id="m1", **kw)], D)


def todos(res, escala_id="A", dias=12):
    efet, ret = [], []
    for i in range(dias):
        dia = res.dia(D + timedelta(days=i), escala_id)
        efet += [a.militar_id for a in dia.efetivos]
        ret += [a.militar_id for a in dia.retens]
    return efet, ret


def test_por_padrao_o_detalhista_fica_fora_da_escala():
    assert Escala("x", "x").detalhista_escalavel is False
    c = mk(retem_qtd=2)
    efet, ret = todos(gerar(c, D + timedelta(days=12)))
    assert "m1" not in efet and "m1" not in ret
    assert set(efet) == {"m2", "m3", "m4", "m5"}


def test_nao_consome_vez_na_fila():
    r = gerar(mk(), D + timedelta(days=7))
    assert [r.dia(D + timedelta(days=i), "A").efetivos[0].militar_id for i in range(8)] == \
           ["m2", "m3", "m4", "m5", "m2", "m3", "m4", "m5"]


def test_opcao_rara_detalhista_concorre_como_qualquer_militar():
    c = mk(detalhista_escalavel=True)
    efet, _ = todos(gerar(c, D + timedelta(days=12)))
    assert "m1" in efet and efet[:5] == ["m1", "m2", "m3", "m4", "m5"]
    assert "m1" in c.escalaveis(c.escala("A"))


def test_mesmo_detalhista_de_varias_escalas_fora_de_todas_elas():
    c = mk()
    c.escalas.append(escala("B", ids=("m1", "m2", "m3", "m4", "m5"), detalhista_id="m1"))
    r = gerar(c, D + timedelta(days=12))
    assert "m1" not in todos(r, "A")[0] + todos(r, "B")[0]


def test_em_escala_onde_nao_e_detalhista_ele_e_um_militar_como_os_outros():
    c = mk()
    c.escalas.append(escala("B", detalhista_id="m2"))                 # m1 é só membro de B; o detalhista de B é m2
    r = gerar(c, D + timedelta(days=12))
    efet_b, _ = todos(r, "B")
    assert "m1" in efet_b and "m2" not in efet_b
    assert "m1" not in todos(r, "A")[0]


def test_auxiliar_concorre_normalmente():
    c = mk(auxiliar_id="m2")
    efet, _ = todos(gerar(c, D + timedelta(days=12)))
    assert "m2" in efet and "m1" not in efet
    assert validar_escala(c, c.escala("A")) == []
    c.escala("A").auxiliar_id = "m1"                                  # auxiliar não pode ser o próprio detalhista
    assert any("auxiliar não pode ser o próprio detalhista" in e for e in validar_escala(c, c.escala("A")))
    c.escala("A").auxiliar_id = "inexistente"
    assert any("auxiliar não encontrado" in e for e in validar_escala(c, c.escala("A")))


def test_detalhista_fora_tambem_das_escalacoes_que_nao_sao_servico():
    pal = Escala("P", "Palestras", dono_id="u1", categoria="palestra", modo="eventos", militares_dia=2, retem_qtd=0,
                 detalhista_id="m1", membros=[Pertinencia(f"m{i}") for i in range(1, 6)])
    c = mk()
    c.escalas.append(pal)
    c.eventos += [Evento("P", D + timedelta(days=i), f"Palestra {i}") for i in range(1, 8)]
    efet, _ = todos(gerar(c, D + timedelta(days=10)), "P", 10)
    assert efet and "m1" not in efet


def test_detalhista_fora_nao_conta_para_o_minimo_de_militares():
    c = mk(n=4)                                                       # m1 fora + 3 escaláveis, 1 por dia, 2x1
    assert validar_escala(c, c.escala("A")) == []
    c.escala("A").militares_dia = 2                                   # precisaria de 6
    assert validar_escala(c, c.escala("A"))
    c.escala("A").detalhista_escalavel = True                         # concorrendo, conta: 4 militares ainda < 6
    assert validar_escala(c, c.escala("A"))
    c3 = mk(n=3)                                                      # m1 fora + 2: não respeita 2x1 (precisa de 3)
    assert validar_escala(c3, c3.escala("A"))
    c3.escala("A").detalhista_escalavel = True                        # concorrendo: 3 militares, passa
    assert validar_escala(c3, c3.escala("A")) == []


def test_previa_mostra_o_detalhista_so_se_ele_concorre():
    c = mk()
    r = gerar(c, D + timedelta(days=6))
    html = html_previa(c, r, periodo(D, 7), "A")
    assert "CB M1<" not in html and "CB M2<" in html
    assert "Detalhista</span><b>M1 (fora da escala)</b>" in html
    c.escala("A").detalhista_escalavel = True
    assert "CB M1<" in html_previa(c, gerar(c, D + timedelta(days=6)), periodo(D, 7), "A")


def test_troca_com_o_detalhista_fora_da_escala_nao_e_possivel():
    c = mk()
    r = gerar(c, D + timedelta(days=5))
    erros, _, _ = pp.validar_troca(c, c.escala("A"), "m2", D, "m1", D + timedelta(days=1))
    assert erros and any("M1 não está escalado" in e for e in erros)


def test_detalhista_fora_nao_e_persona_para_vinculo():
    c = mk()
    assert "m1" not in vc.militares_livres(c, "A")
    c.escala("A").detalhista_escalavel = True
    assert "m1" in vc.militares_livres(c, "A")


def test_relatorio_informa_detalhista_auxiliar_e_a_opcao():
    c = mk(auxiliar_id="m2")
    sit = dict(situacao_atual(c, c.escala("A")))
    assert sit["Detalhista da escala"] == "M1 (fora da escala, dispensado de serviço)"
    assert sit["Auxiliar do detalhista"].startswith("M2 (concorre normalmente, decide papeletas e vínculos e faz lançamentos")
    assert "M1" not in next(v for k, v in sit.items() if k.startswith("Militares na escala"))
    assert any("M1" in t and "fica fora da escala" in t for t in texto_funcionamento(c, c.escala("A")))
    item = next(i for _, its in itens_configuracao(c, c.escala("A")) for i in its if i.rotulo == "Detalhista concorre à escala")
    assert item.valor == "não" and not item.alterado
    c.escala("A").detalhista_escalavel = True
    item = next(i for _, its in itens_configuracao(c, c.escala("A")) for i in its if i.rotulo == "Detalhista concorre à escala")
    assert item.valor == "sim" and item.alterado


def test_campos_persistem():
    c = mk(auxiliar_id="m2", detalhista_escalavel=True)
    e = de_tabelas(para_tabelas(c)).escala("A")
    assert (e.detalhista_id, e.detalhista_escalavel, e.auxiliar_id) == ("m1", True, "m2")


def test_importacao_coluna_detalhista_marca_o_detalhista_da_escala_um_so():
    csv = ("Nome de guerra;Posto;NIP;Escala;Detalhista\n"
           "SILVA;1SG;1.1;Portaria;sim\nSOUZA;CB;2.2;Portaria;\nLIMA;CB;3.3;Portaria;sim\n")
    novo, _ = importar(Contexto([], [], D), ler_tabela(csv.encode(), "x.csv"))
    esc = novo.escalas[0]
    assert novo.militar(esc.detalhista_id).nome == "SILVA"            # um só por escala: o primeiro marcado
    assert esc.detalhista_escalavel is False

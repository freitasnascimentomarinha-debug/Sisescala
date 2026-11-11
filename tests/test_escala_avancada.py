"""Personalização avançada da escala: dias da semana, quantidade por dia da semana, turnos livres (inclusive no dia seguinte),
distribuição (intercalado, um por turno, todos), rodízio de turnos e validação. Sem a opção ligada nada muda."""
import json
from datetime import date, timedelta

import pytest

from sisescala.modelos import Contexto, Escala, Impedimento, Militar, Pertinencia, Quarto, quartos_padrao
from sisescala.motor import exemplo_do_dia, gerar, validar_escala
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)          # segunda-feira
T3 = [Quarto("06:00", "08:00", "1º"), Quarto("12:00", "16:00", "2º"), Quarto("16:00", "18:00", "3º")]


def mk(n=10, **kw):
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, n + 1)]
    kw.setdefault("folgas_minimas", 0)
    e = Escala("A", "Diário", membros=[Pertinencia(m.id) for m in ms], **kw)
    return Contexto(ms, [e], D)


def dia(c, d, eid="A"):
    return gerar(c, d).dia(d, eid)


def hs(a):
    return a.horarios


def test_sem_personalizacao_tudo_continua_igual():
    c = mk(militares_dia=3, quartos=quartos_padrao(4), folgas_minimas=2)
    d = dia(c, D)
    assert [hs(a) for a in d.efetivos] == [["00:00-04:00", "12:00-16:00"], ["04:00-08:00", "16:00-20:00"], ["08:00-12:00", "20:00-00:00"]]
    # chaves avançadas ligadas mas "avancada" desligada: nada vale
    c2 = mk(militares_dia=3, quartos=quartos_padrao(4), folgas_minimas=2, adv_dias_semana=True, dias_semana="0", adv_qtd_semana=True,
            qtd_semana="9,9,9,9,9,9,9", adv_turnos=True, distribuicao="um_por_turno", rodizio_turnos=True)
    assert [hs(a) for a in dia(c2, D).efetivos] == [hs(a) for a in d.efetivos]
    assert dia(c2, D + timedelta(days=2)).funciona


def test_dias_da_semana_escolhidos():
    c = mk(avancada=True, adv_dias_semana=True, dias_semana="0,2,4")            # seg, qua, sex
    r = gerar(c, D + timedelta(days=6))
    assert [r.dia(D + timedelta(days=i), "A").funciona for i in range(7)] == [True, False, True, False, True, False, False]


def test_quantidade_por_dia_da_semana_inclusive_zero():
    c = mk(n=12, avancada=True, adv_qtd_semana=True, qtd_semana="5,5,5,5,5,3,0")
    r = gerar(c, D + timedelta(days=6))
    q = [len(r.dia(D + timedelta(days=i), "A").efetivos) for i in range(7)]
    assert q == [5, 5, 5, 5, 5, 3, 0]
    assert not r.dia(D + timedelta(days=6), "A").funciona                       # zero = não guarnece


def test_turnos_livres_um_militar_por_turno_com_reteins_por_turno():
    qs = [Quarto("06:00", "08:00", "1º", 1, 1), Quarto("12:00", "16:00", "2º", 2, 0), Quarto("16:00", "18:00", "3º", 1, 1)]
    c = mk(avancada=True, adv_turnos=True, quartos=qs, distribuicao="um_por_turno")
    d = dia(c, D)
    ef = [hs(a) for a in d.efetivos]
    assert ef == [["06:00-08:00"], ["12:00-16:00"], ["12:00-16:00"], ["16:00-18:00"]]       # 1 + 2 + 1 militares
    assert [hs(a) for a in d.retens] == [["06:00-08:00"], ["16:00-18:00"]]                  # retém só onde foi pedido
    assert len({a.militar_id for a in d.alocacoes}) == 6                                    # ninguém repetido


def test_distribuicoes_intercalado_e_todos():
    c = mk(avancada=True, adv_turnos=True, quartos=T3, distribuicao="intercalado", militares_dia=2)
    assert [hs(a) for a in dia(c, D).efetivos] == [["06:00-08:00", "16:00-18:00"], ["12:00-16:00"]]
    c = mk(avancada=True, adv_turnos=True, quartos=T3, distribuicao="todos", militares_dia=1)
    assert [hs(a) for a in dia(c, D).efetivos] == [["06:00-08:00", "12:00-16:00", "16:00-18:00"]]


def test_turno_no_dia_seguinte_marca_mais_um_e_bloqueia_quem_esta_impedido_amanha():
    qs = [Quarto("12:00", "16:00", "1º"), Quarto("06:00", "08:00", "2º", 1, 0, True)]
    c = mk(n=6, avancada=True, adv_turnos=True, quartos=qs, distribuicao="todos", militares_dia=1)
    d = dia(c, D)
    assert hs(d.efetivos[0]) == ["12:00-16:00", "06:00-08:00+1"]
    escalado = d.efetivos[0].militar_id
    c.impedimentos.append(Impedimento(escalado, "ferias", D + timedelta(days=1), D + timedelta(days=5)))   # impedido AMANHÃ
    assert dia(c, D).efetivos[0].militar_id != escalado                         # não escala quem não pode cumprir o turno de amanhã
    # com o turno no dia seguinte, o descanso nunca é menor que 1 folga: o mesmo militar não serve em dois dias seguidos
    c2 = mk(n=6, avancada=True, adv_turnos=True, quartos=qs, distribuicao="todos", militares_dia=1, folgas_minimas=0)
    r = gerar(c2, D + timedelta(days=3))
    assert len({r.dia(D + timedelta(days=i), "A").efetivos[0].militar_id for i in range(3)}) == 3


def test_rodizio_de_turnos_o_militar_passa_para_o_turno_seguinte():
    qs = [Quarto("06:00", "08:00"), Quarto("12:00", "16:00"), Quarto("16:00", "18:00")]
    c = mk(n=4, avancada=True, adv_turnos=True, quartos=qs, distribuicao="um_por_turno", rodizio_turnos=True)   # 3 por dia, 4 militares
    r = gerar(c, D + timedelta(days=8))
    turno = {}                                                                  # militar -> turnos, em ordem
    for i in range(9):
        for a in r.dia(D + timedelta(days=i), "A").efetivos:
            turno.setdefault(a.militar_id, []).append(qs.index(next(q for q in qs if str(q) == a.horarios[0])))
    for seq in turno.values():
        assert all((b - a) % 3 == 1 for a, b in zip(seq, seq[1:])), seq         # cada vez o turno seguinte (ciclo de 3)


def test_validacao_avancada():
    base = dict(avancada=True)
    assert validar_escala(mk(**base, adv_turnos=True, quartos=T3), mk(**base, adv_turnos=True, quartos=T3).escalas[0]) == []
    e = lambda **kw: validar_escala(mk(**base, **kw), mk(**base, **kw).escalas[0])        # noqa: E731
    assert any("sobrepõem" in x for x in e(adv_turnos=True, quartos=[Quarto("06:00", "10:00"), Quarto("09:00", "12:00")]))
    assert any("inválido" in x for x in e(adv_turnos=True, quartos=[Quarto("25:00", "10:00")]))
    assert any("ao menos 1 pessoa" in x for x in e(adv_turnos=True, quartos=[Quarto("06:00", "10:00", "", 0)]))
    assert any("pelo menos" in x or "ao menos um turno" in x for x in e(adv_turnos=True, quartos=[]))
    assert any("dia da semana" in x for x in e(adv_dias_semana=True, dias_semana=""))
    assert any("sete dias" in x for x in e(adv_qtd_semana=True, qtd_semana="1,2,3"))
    assert any("distribuir" in x for x in e(distribuicao="x"))
    # turno do dia seguinte não conflita com o do mesmo dia no mesmo horário
    assert e(adv_turnos=True, quartos=[Quarto("06:00", "08:00"), Quarto("06:00", "08:00", "", 1, 0, True)]) == []


def test_persistencia_dos_campos_novos_e_leitura_do_formato_antigo_dos_quartos():
    c = mk(avancada=True, adv_turnos=True, quartos=[Quarto("06:00", "08:00", "1º", 2, 1, False), Quarto("06:00", "08:00", "2º", 1, 0, True)],
           distribuicao="um_por_turno", rodizio_turnos=True, adv_dias_semana=True, dias_semana="0,1,2", adv_qtd_semana=True,
           qtd_semana="5,5,5,5,5,3,3")
    e = de_tabelas(para_tabelas(c)).escala("A")
    assert (e.avancada, e.adv_turnos, e.distribuicao, e.rodizio_turnos, e.dias_semana, e.qtd_semana) == (
        True, True, "um_por_turno", True, "0,1,2", "5,5,5,5,5,3,3")
    assert [(q.inicio, q.fim, q.nome, q.pessoas, q.retem, q.proximo_dia) for q in e.quartos] == [
        ("06:00", "08:00", "1º", 2, 1, False), ("06:00", "08:00", "2º", 1, 0, True)]
    T = para_tabelas(c)                                                         # planilha antiga: quartos só com início e fim
    cab = T["Escalas"][0]
    T["Escalas"][1][cab.index("quartos")] = json.dumps([["00:00", "04:00"], ["04:00", "08:00"]])
    ant = de_tabelas(T).escala("A")
    assert [(q.inicio, q.fim, q.pessoas, q.proximo_dia) for q in ant.quartos] == [("00:00", "04:00", 1, False), ("04:00", "08:00", 1, False)]


def test_exemplo_do_dia_para_a_tela():
    e = Escala("A", "A", avancada=True, adv_turnos=True, quartos=T3, distribuicao="um_por_turno")
    ex = exemplo_do_dia(e)
    assert [h for _, h in ex["efetivos"]] == [["06:00-08:00"], ["12:00-16:00"], ["16:00-18:00"]]
    e2 = Escala("A", "A", avancada=True, adv_turnos=True, quartos=T3, distribuicao="intercalado", militares_dia=2)
    assert [h for _, h in exemplo_do_dia(e2)["efetivos"]] == [["06:00-08:00", "16:00-18:00"], ["12:00-16:00"]]


def test_criar_e_editar_escala_recusam_configuracao_avancada_invalida_e_aceitam_a_valida():
    from sisescala import auth, gestao
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, 6)]
    c = Contexto(ms, [], D)
    auth.criar_usuario(c, None, "adm", "Administrador", "senha-forte-1", admin=True)
    e = Escala("e1", "Portaria", membros=[Pertinencia(m.id) for m in ms])
    gestao.criar_escala(c, "u1", e)
    with pytest.raises(ValueError, match="sobrepõem"):
        gestao.editar_escala(c, "u1", "e1", avancada=True, adv_turnos=True, quartos=[Quarto("06:00", "10:00"), Quarto("09:00", "12:00")])
    n = gestao.editar_escala(c, "u1", "e1", avancada=True, adv_turnos=True, quartos=T3, distribuicao="um_por_turno", rodizio_turnos=True,
                             adv_dias_semana=True, dias_semana="0,1,2,3,4")
    assert [str(q) for q in n.quartos] == ["06:00-08:00", "12:00-16:00", "16:00-18:00"] and n.turnos_livres()
    r = gerar(c, D + timedelta(days=6))
    assert [r.dia(D + timedelta(days=i), "e1").funciona for i in range(7)] == [True] * 5 + [False, False]
    assert len(r.dia(D, "e1").efetivos) == 3 and all(len(a.horarios) == 1 for a in r.dia(D, "e1").efetivos)


def test_orientacao_do_documento_unificado_persiste_e_papeleta_leva_o_turno():
    from sisescala.modelos import DetalheConjunto
    c = mk()
    c.conjuntos.append(DetalheConjunto("c1", "Dia", "u1", escala_ids=["A"], orientacao="paisagem"))
    assert de_tabelas(para_tabelas(c)).conjunto("c1").orientacao == "paisagem"
    T = para_tabelas(c)                                                         # planilha anterior à coluna: padrão "auto"
    cab = T["DetalhesConjuntos"][0]
    T["DetalhesConjuntos"][1][cab.index("orientacao")] = ""
    assert de_tabelas(T).conjunto("c1").orientacao == "auto"

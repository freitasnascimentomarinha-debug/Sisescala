from datetime import date, timedelta

import pytest

from sisescala.calendario import dia_util
from sisescala.modelos import *
from sisescala.motor import fila_do_dia, gerar, sugerir_devolucao, validar_escala, avisos_escala


def mil(n):
    return [Militar(f"m{i}", f"M{i}", "", i) for i in range(1, n + 1)]


def esc(id, ids, **kw):
    kw.setdefault("dono_id", "u1")
    return Escala(id, id, id[:3].upper(), membros=[Pertinencia(i) for i in ids], **kw)


def ctx(escalas, n=6, base=date(2027, 3, 1), **kw):  # 01/03/2027 = segunda
    return Contexto(mil(n), escalas, base, **kw)


def quem(res, d, eid, papel="efetivo"):
    dia = res.dia(d, eid)
    return [a.militar_id for a in dia.alocacoes if a.papel == papel and a.origem != "falta"]


D = date(2027, 3, 1)


def test_sequencia_antiguo_para_moderno_e_circular():
    c = ctx([esc("A", ["m1", "m2", "m3"])])
    r = gerar(c, D + timedelta(days=4))
    assert [quem(r, D + timedelta(days=i), "A")[0] for i in range(5)] == ["m1", "m2", "m3", "m1", "m2"]
    assert quem(r, D, "A", "retem") == ["m2"]


def test_ponto_de_partida():
    c = ctx([esc("A", ["m1", "m2", "m3"], ultimo_servico={"corrida": "m2"})])
    assert quem(gerar(c, D), D, "A") == ["m3"]


def test_impedimento_pula_e_nao_consome():
    c = ctx([esc("A", ["m1", "m2", "m3"])],
            impedimentos=[Impedimento("m2", "ferias", D, D + timedelta(days=1))])
    r = gerar(c, D + timedelta(days=3))
    # m2 de férias; m1 ainda descansa no dia 3 (2x1) -> m2 volta e m1 não perde a vez (dia 4)
    assert [quem(r, D + timedelta(days=i), "A")[0] for i in range(4)] == ["m1", "m3", "m2", "m1"]


def test_desembarque_sai_da_fila():
    c = ctx([esc("A", ["m1", "m2", "m3"])], impedimentos=[Impedimento("m2", "desembarque", D)])
    r = gerar(c, D + timedelta(days=3))
    assert all("m2" not in quem(r, D + timedelta(days=i), "A") + quem(r, D + timedelta(days=i), "A", "retem")
               for i in range(4))


def test_dispensa_exige_motivo_e_arquivo():
    assert Impedimento("m1", "dispensa", D, D).validar()
    assert not Impedimento("m1", "dispensa", D, D, "luto", "arq.pdf").validar()


def test_preta_vermelha_filas_independentes_e_descanso_entre_filas():
    # sex 05/03 (preta), sáb 06 e dom 07 (vermelha), seg 08 (preta)
    c = ctx([esc("A", ["m1", "m2", "m3", "m4"], modo="preta_vermelha")], base=date(2027, 3, 5))
    r = gerar(c, date(2027, 3, 10))
    f = lambda d: (quem(r, date(2027, 3, d), "A")[0], r.dia(date(2027, 3, d), "A").fila)  # noqa: E731
    assert f(5) == ("m1", "preta")
    assert f(6) == ("m2", "vermelha")   # m1 deu sexta: não pode dar sábado (1x1 proibido)
    assert f(7) == ("m3", "vermelha")
    assert f(8) == ("m4", "preta")      # m2 e m3 ainda descansam
    # nunca dois serviços do mesmo militar com menos de 2 folgas entre eles
    dias = sorted(d for (d, e), de in r.dias.items() for a in de.efetivos if a.militar_id == "m2")
    assert all((b - a).days >= 3 for a, b in zip(dias, dias[1:]))


def test_servico_so_dias_uteis_para_no_fim_de_semana():
    c = ctx([esc("A", ["m1", "m2", "m3"], funciona_em="uteis")], base=date(2027, 3, 5))
    r = gerar(c, date(2027, 3, 8))
    assert not r.dia(date(2027, 3, 6), "A").funciona
    assert quem(r, date(2027, 3, 8), "A") == ["m2"]  # fila congelada no fim de semana


def test_comando_guarnece_dia_sem_expediente():
    c = ctx([esc("A", ["m1", "m2", "m3"], funciona_em="uteis")], base=date(2027, 3, 5),
            guarnecimentos=[Guarnecimento(date(2027, 3, 6), "A")])
    r = gerar(c, date(2027, 3, 8))
    assert quem(r, date(2027, 3, 6), "A") == ["m2"] and quem(r, date(2027, 3, 8), "A") == ["m3"]


def test_licenca_administrativa_manual_e_feriado_manual():
    c = ctx([esc("A", ["m1", "m2"], funciona_em="uteis")],
            dias_especiais=[DiaEspecial(D + timedelta(days=1), "sem_expediente", "Licença adm.")])
    assert not dia_util(D + timedelta(days=1), c)
    assert not gerar(c, D + timedelta(days=2)).dia(D + timedelta(days=1), "A").funciona


def test_feriado_nacional_automatico():
    c = ctx([esc("A", ["m1"])])
    assert not dia_util(date(2027, 4, 21), c)  # Tiradentes (quarta)
    assert not dia_util(date(2027, 4, 23), c)  # São Jorge (RJ)
    c.uf = "SP"
    assert dia_util(date(2027, 4, 23), c)


def test_roxa_comeca_do_zero_e_congela_as_outras():
    roxa = PeriodoRoxa("c", "Carnaval", date(2027, 3, 3), date(2027, 3, 5))
    c = ctx([esc("A", ["m1", "m2", "m3"])], roxas=[roxa])
    r = gerar(c, date(2027, 3, 8))
    a = [quem(r, date(2027, 3, d), "A")[0] for d in range(1, 9)]
    # 1,2 corrida (m1,m2); roxa do zero: m1/m2 ainda descansam (2x1) -> m3, depois m1, m2;
    # corrida retoma depois de m2 -> m3
    assert a == ["m1", "m2", "m3", "m1", "m2", "m3", "m1", "m2"]
    assert r.dia(date(2027, 3, 4), "A").fila == "roxa:c"


def test_quartos_intercalam_militares():
    c = ctx([esc("A", ["m1", "m2", "m3", "m4"], militares_dia=3, quartos=quartos_padrao(4))])
    ef = gerar(c, D).dia(D, "A").efetivos
    assert {a.militar_id: a.horarios for a in ef} == {
        "m1": ["00:00-04:00", "12:00-16:00"], "m2": ["04:00-08:00", "16:00-20:00"],
        "m3": ["08:00-12:00", "20:00-00:00"]}


def test_doze_quartos_de_2h():
    assert len(quartos_padrao(2)) == 12


def test_ocorrencia_avanca_retem_e_gera_devolucao():
    c = ctx([esc("A", ["m1", "m2", "m3", "m4", "m5", "m6", "m7"])], n=7,
            ocorrencias=[Ocorrencia(D, "A", "m1", "passou mal")])
    r = gerar(c, D + timedelta(days=2))
    assert quem(r, D, "A") == ["m2"]
    assert quem(r, D + timedelta(days=1), "A") == ["m3"]  # retéms avançam
    assert r.devolucoes[0].militar_id == "m1"
    assert r.devolucoes[0].prazo == D + timedelta(days=30)
    sug = sugerir_devolucao(c, r, r.devolucoes[0])
    assert sug                                              # há dias que respeitam o 2x1
    datas_m1 = [d for (d, e), de in r.dias.items() for a in de.efetivos if a.militar_id == "m1"]
    assert all(abs((d - x).days) >= 3 for d, _ in sug for x in datas_m1)


def test_troca_consensual_so_com_dois_aceites():
    t = Troca(D, "A", "m1", "m3", True, False)
    r = gerar(ctx([esc("A", ["m1", "m2", "m3"])], trocas=[t]), D)
    assert quem(r, D, "A") == ["m1"] and r.avisos
    t.aceite_entrando = True
    r = gerar(ctx([esc("A", ["m1", "m2", "m3"])], trocas=[t]), D)
    assert quem(r, D, "A") == ["m3"]
    assert r.dia(D, "A").efetivos[0].sigla == SVC_T


def test_troca_forcada_pernoite_prevalece_e_nao_perde_a_vez():
    per = esc("P", ["m1", "m2", "m3", "m4"], prioridade=5)           # m1 no dia D
    dia = esc("D", ["m1", "m5", "m6", "m7", "m8", "m9"], prioridade=1)  # m1 também em D
    c = ctx([per, dia], n=9)
    r = gerar(c, D + timedelta(days=5))
    assert quem(r, D, "P") == ["m1"]
    ef = r.dia(D, "D").efetivos[0]
    assert ef.sigla == SVC_TF and ef.militar_id != "m1" and "TF" in ef.obs
    # m1 passou a dar o serviço diário em outra data (realocado para dar ambos)
    datas_m1 = [d for (d, e), de in r.dias.items() if e == "D"
                for a in de.efetivos if a.militar_id == "m1"]
    assert datas_m1 and all(a.sigla == SVC_TF for (d, e), de in r.dias.items() if e == "D"
                            for a in de.efetivos if a.militar_id == "m1" and d > D and a.sigla != SVC)


def test_troca_forcada_de_retem():
    per = esc("P", ["m1", "m2", "m3"], prioridade=5)
    # diária: depois de m7 vem m8 (efetivo) e o retém seria m1, que está de pernoite
    dia = esc("D", ["m1", "m6", "m7", "m8"], prioridade=1, ultimo_servico={"corrida": "m7"})
    r = gerar(ctx([per, dia], n=8), D)
    assert quem(r, D, "P") == ["m1"]
    assert quem(r, D, "D") == ["m8"]
    ret = r.dia(D, "D").retens[0]
    assert ret.militar_id != "m1" and ret.sigla == RT_TF and "TF" in ret.obs


def test_resultado_independe_do_tamanho_da_previa():
    per = esc("P", ["m1", "m2", "m3", "m4"], prioridade=5)
    dia = esc("D", ["m1", "m5", "m6", "m7", "m8", "m9"], prioridade=1)
    c = ctx([per, dia], n=9)
    r7, r30 = gerar(c, D + timedelta(days=6)), gerar(c, D + timedelta(days=29))
    for i in range(7):
        d = D + timedelta(days=i)
        for e in ("P", "D"):
            assert quem(r7, d, e) == quem(r30, d, e) and quem(r7, d, e, "retem") == quem(r30, d, e, "retem")


def test_minimo_2x1_validacao_e_configuravel():
    c = ctx([esc("A", ["m1", "m2"])])
    assert avisos_escala(c, c.escala("A"))              # 1x1 não é recomendado por padrão (só avisa)
    assert not validar_escala(c, c.escala("A"))        # não é erro: dá para criar e completar depois
    c.escala("A").folgas_minimas = 1                      # configurável
    assert not avisos_escala(c, c.escala("A"))
    c.escala("A").membros.append(Pertinencia("m3"))
    c.escala("A").folgas_minimas = 2
    assert not avisos_escala(c, c.escala("A"))


def test_dtq_destaque_nao_concorre():
    c = ctx([esc("A", ["m1", "m2", "m3", "m4"])],
            impedimentos=[Impedimento("m2", "destaque", D, D + timedelta(days=20), "Destacado na OM X")])
    r = gerar(c, D + timedelta(days=8))
    todos = [m for i in range(9) for m in quem(r, D + timedelta(days=i), "A")]
    assert "m2" not in todos
    assert TIPOS_IMPEDIMENTO["destaque"] == "DTQ"


def test_palestra_so_nos_dias_de_evento():
    e = esc("PAL", ["m1", "m2", "m3", "m4"], categoria="palestra", modo="eventos", militares_dia=2,
            retem_qtd=0)
    c = ctx([e], eventos=[Evento("PAL", D + timedelta(days=2), "Palestra de segurança", "10h"),
                          Evento("PAL", D + timedelta(days=5), "Cerimônia", vagas=1)])
    r = gerar(c, D + timedelta(days=6))
    assert not r.dia(D, "PAL").funciona
    d2 = r.dia(D + timedelta(days=2), "PAL")
    assert [a.militar_id for a in d2.efetivos] == ["m1", "m2"] and d2.efetivos[0].sigla == "PAL"
    assert d2.descricao == "Palestra de segurança"
    assert quem(r, D + timedelta(days=5), "PAL") == ["m3"]   # fila segue de onde parou


def test_horario_compacto():
    assert horarios_curtos(["04:00-08:00", "16:00-20:00"]) == "4h/16h"
    assert horarios_curtos(["00:00-04:00", "12:00-16:00"]) == "0h/12h"


def test_referencia_escala_do_outro_usuario_prevalece():
    # u1 é dono da Pernoite (m1 de serviço em D). u2 faz a Diária referenciando a Pernoite.
    per = esc("P", ["m1", "m2", "m3", "m4"], dono_id="u1", prioridade=1)
    dia = esc("D", ["m1", "m5", "m6", "m7", "m8", "m9"], dono_id="u2", prioridade=9,
              referencias=["P"])
    r = gerar(ctx([per, dia], n=9), D + timedelta(days=5))
    assert quem(r, D, "P") == ["m1"]                 # referenciada prevalece (apesar da prioridade 9)
    assert r.dia(D, "D").efetivos[0].sigla == SVC_TF and r.dia(D, "D").efetivos[0].militar_id != "m1"


def test_escalas_de_donos_sem_referencia_nao_interferem():
    per = esc("P", ["m1", "m2", "m3", "m4"], dono_id="u1")
    dia = esc("D", ["m1", "m5", "m6", "m7", "m8", "m9"], dono_id="u2")
    r = gerar(ctx([per, dia], n=9), D)
    assert quem(r, D, "P") == ["m1"] and quem(r, D, "D") == ["m1"]
    assert r.dia(D, "D").efetivos[0].origem == "normal"


def test_compartilhamento_leitura_e_edicao():
    from sisescala import permissoes as pm
    per = esc("P", ["m1", "m2", "m3"], dono_id="u1")
    dia = esc("D", ["m4", "m5", "m6"], dono_id="u2")
    c = ctx([per, dia])
    from sisescala import auth                      # contas reais de detalhista: u1, u2 e u3
    auth.criar_usuario(c, None, "d1", "D1", "senha-forte-1")
    for lg in ("d2", "d3"):
        auth.criar_usuario(c, "u1", lg, lg.upper(), "senha-forte-1")
    assert not pm.pode_ver(c, "u2", per)
    with pytest.raises(pm.PermissaoNegada):
        pm.referenciar(c, "u2", "D", "P")                  # ainda não compartilhada
    with pytest.raises(pm.PermissaoNegada):
        pm.compartilhar(c, "u2", "P", "u3", "leitura")     # só o dono compartilha
    pm.compartilhar(c, "u1", "P", "u2", "leitura")
    assert pm.pode_ver(c, "u2", per) and not pm.pode_editar(c, "u2", per)
    pm.referenciar(c, "u2", "D", "P")                      # leitura basta para referenciar
    assert dia.referencias == ["P"]
    with pytest.raises(pm.PermissaoNegada):
        pm.referenciar(c, "u1", "P", "D")                  # u1 não vê a escala D
    pm.compartilhar(c, "u2", "D", "u1", "leitura")
    with pytest.raises(ValueError):
        pm.referenciar(c, "u1", "P", "D")                  # P→D e D→P seria circular
    pm.compartilhar(c, "u1", "P", "u2", "edicao")
    assert pm.pode_editar(c, "u2", per)
    pm.compartilhar(c, "u1", "P", "u2", None)              # revoga
    assert not pm.pode_ver(c, "u2", per)
    assert [e.id for e in pm.escalas_visiveis(c, "u2")] == ["D"]


def test_palestra_nunca_tem_prioridade_sobre_servico():
    per = esc("P", ["m1", "m2", "m3", "m4"], prioridade=1)
    pal = esc("PAL", ["m1", "m2", "m3", "m4", "m5", "m6"], categoria="palestra", modo="eventos",
              militares_dia=1, retem_qtd=0, prioridade=99)         # prioridade alta não adianta
    c = ctx([per, pal], n=6, eventos=[Evento("PAL", D, "Palestra 1"),
                                      Evento("PAL", D + timedelta(days=7), "Palestra 2")])
    r = gerar(c, D + timedelta(days=8))
    assert quem(r, D, "P") == ["m1"]
    a = r.dia(D, "PAL").efetivos[0]
    assert a.militar_id == "m2" and a.origem == "normal"       # pulou m1 (de serviço), sem TF
    # m1 foi pulado por estar de serviço: não perde a vez e entra na palestra seguinte
    assert quem(r, D + timedelta(days=7), "PAL") == ["m1"]


def test_palestra_pode_escalar_quem_esta_de_reten():
    per = esc("P", ["m1", "m2", "m3", "m4"])
    pal = esc("PAL", ["m2", "m3", "m4", "m5"], categoria="palestra", modo="eventos",
              militares_dia=1, retem_qtd=0)
    c = ctx([per, pal], n=6, eventos=[Evento("PAL", D, "Palestra")])
    r = gerar(c, D)
    assert quem(r, D, "P", "retem") == ["m2"] and quem(r, D, "PAL") == ["m2"]  # retém não bloqueia


def test_servico_prevalece_mesmo_com_dono_diferente_sem_referencia():
    per = esc("P", ["m1", "m2", "m3", "m4"], dono_id="u1")
    pal = esc("PAL", ["m1", "m2", "m3"], dono_id="u2", categoria="palestra", modo="eventos",
              militares_dia=1, retem_qtd=0)
    r = gerar(ctx([per, pal], n=6, eventos=[Evento("PAL", D, "x")]), D)
    assert quem(r, D, "PAL") != ["m1"]

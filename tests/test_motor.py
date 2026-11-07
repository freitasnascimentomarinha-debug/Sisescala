from datetime import date, timedelta

from sisescala.calendario import dia_util
from sisescala.modelos import *
from sisescala.motor import fila_do_dia, gerar, sugerir_devolucao


def mil(n):
    return [Militar(f"m{i}", f"M{i}", "", i) for i in range(1, n + 1)]


def esc(id, ids, **kw):
    return Escala(id, id, id[:3].upper(), membros=[Pertinencia(i) for i in ids], **kw)


def ctx(escalas, n=6, base=date(2027, 3, 1), **kw):  # 01/03/2027 = segunda
    return Contexto(mil(n), escalas, base, **kw)


def quem(res, d, eid, papel="efetivo"):
    dia = res.dia(d, eid)
    return [a.militar_id for a in dia.alocacoes if a.papel == papel and a.sigla != "Falta"]


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
    assert [quem(r, D + timedelta(days=i), "A")[0] for i in range(4)] == ["m1", "m3", "m1", "m2"]


def test_desembarque_sai_da_fila():
    c = ctx([esc("A", ["m1", "m2", "m3"])], impedimentos=[Impedimento("m2", "desembarque", D)])
    r = gerar(c, D + timedelta(days=3))
    assert all("m2" not in quem(r, D + timedelta(days=i), "A") + quem(r, D + timedelta(days=i), "A", "retem")
               for i in range(4))


def test_dispensa_exige_motivo_e_arquivo():
    assert Impedimento("m1", "dispensa", D, D).validar()
    assert not Impedimento("m1", "dispensa", D, D, "luto", "arq.pdf").validar()


def test_preta_vermelha_filas_independentes_congeladas():
    # sex 05/03, sáb 06, dom 07, seg 08
    c = ctx([esc("A", ["m1", "m2", "m3", "m4"], modo="preta_vermelha")], base=date(2027, 3, 5))
    r = gerar(c, date(2027, 3, 8))
    sex, sab, dom, seg = (date(2027, 3, d) for d in (5, 6, 7, 8))
    assert [quem(r, x, "A")[0] for x in (sex, sab, dom, seg)] == ["m1", "m1", "m2", "m2"]
    assert r.dia(sab, "A").fila == "vermelha" and r.dia(seg, "A").fila == "preta"


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
    # 1,2 corrida (m1,m2); 3-5 roxa do zero (m1,m2,m3); 6.. corrida retoma depois de m2 -> m3,m1,m2
    assert a == ["m1", "m2", "m1", "m2", "m3", "m3", "m1", "m2"]
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
    c = ctx([esc("A", ["m1", "m2", "m3", "m4"])],
            ocorrencias=[Ocorrencia(D, "A", "m1", "passou mal")])
    r = gerar(c, D + timedelta(days=2))
    assert quem(r, D, "A") == ["m2"]
    assert quem(r, D + timedelta(days=1), "A") == ["m3"]  # retéms avançam
    assert r.devolucoes[0].militar_id == "m1"
    assert r.devolucoes[0].prazo == D + timedelta(days=30)
    sug = sugerir_devolucao(c, r, r.devolucoes[0])
    assert sug and sug[0][0] == D + timedelta(days=1)


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

"""Dias e períodos especiais por escala, "conta como" preta/vermelha/roxa e carimbo de quem lançou."""
from datetime import date, datetime, timedelta

import pytest

from sisescala import auth, gestao
from sisescala import lancamentos as lc
from sisescala.calendario import conta_como, dia_util
from sisescala.modelos import *
from sisescala.motor import fila_do_dia, funciona, gerar
from sisescala.permissoes import PermissaoNegada
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)            # segunda-feira
SENHA = "senha-forte-1"
AGORA = datetime(2027, 2, 20, 10, 30)


def mundo():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"1000000{i}") for i in range(1, 8)]
    c = Contexto(ms, [], D)
    adm, _ = auth.garantir_admin(c, "admin", SENHA)
    det = auth.criar_usuario(c, adm.id, "20000001", "Detalhista", SENHA)
    aux_u = auth.criar_usuario(c, adm.id, "20000002", "Auxiliar", SENHA, militar_id="m2")
    gestao.criar_escala(c, det.id, Escala("e1", "Um", modo="preta_vermelha", data_base=D, auxiliares=["m2"],
                                           membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    return c, adm, det, aux_u


def test_periodo_licenca_conta_como_preta_vermelha_e_automatico():
    c, adm, det, _ = mundo()
    e = c.escala("e1")
    ter, qua = D + timedelta(days=1), D + timedelta(days=2)
    assert dia_util(ter, c, e) and conta_como(ter, c, e) == "preta"
    lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "sem_expediente", "Licença", "e1", qua), AGORA)   # período de 2 dias
    assert not dia_util(ter, c, e) and not dia_util(qua, c, e) and dia_util(D + timedelta(days=3), c, e)
    assert fila_do_dia(c, e, ter) == "vermelha"                                                          # automático
    # sábado forçado a preta (compensação) e dia útil forçado a vermelha
    sab = D + timedelta(days=5)
    lc.lancar_dia_especial(c, det.id, DiaEspecial(sab, "sem_expediente", "Expediente extra", "e1", None, "preta"))
    assert dia_util(sab, c, e) and fila_do_dia(c, e, sab) == "preta"
    qui = D + timedelta(days=3)
    lc.lancar_dia_especial(c, det.id, DiaEspecial(qui, "feriado", "Feriado trabalhado", "e1", None, "vermelha"))
    assert fila_do_dia(c, e, qui) == "vermelha"
    lc.lancar_dia_especial(c, det.id, DiaEspecial(qui + timedelta(days=1), "feriado", "Feriado preta", "e1", None, "preta"))
    assert fila_do_dia(c, e, qui + timedelta(days=1)) == "preta"                                         # feriado contado como preta


def test_dia_especial_so_vale_na_escala_e_validacoes():
    c, adm, det, _ = mundo()
    gestao.criar_escala(c, det.id, Escala("e2", "Dois", modo="preta_vermelha", data_base=D,
                                           membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    ter = D + timedelta(days=1)
    lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "sem_expediente", "x", "e1"))
    assert not dia_util(ter, c, c.escala("e1")) and dia_util(ter, c, c.escala("e2"))
    with pytest.raises(ValueError, match="anterior"):
        lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "feriado", "x", "e1", ter - timedelta(days=1)))
    with pytest.raises(ValueError, match="conta como"):
        lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "feriado", "x", "e1", None, "roxa"))
    with pytest.raises(ValueError, match="tipo"):
        lc.lancar_dia_especial(c, det.id, DiaEspecial(ter, "outro", "x", "e1"))


def test_periodo_roxo_por_escala_so_detalhista_e_participa_roxa():
    c, adm, det, aux_u = mundo()
    e = c.escala("e1")
    d1, d2 = D + timedelta(days=7), D + timedelta(days=9)
    with pytest.raises(ValueError, match="não participa da roxa"):
        e.participa_roxa = False
        lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Recesso", d1, d2, "e1"))
    e.participa_roxa = True
    with pytest.raises(PermissaoNegada, match="detalhista"):
        lc.lancar_periodo_roxo(c, aux_u.id, PeriodoRoxa("", "Recesso", d1, d2, "e1"))            # auxiliar não
    with pytest.raises(PermissaoNegada, match="administrador"):
        lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Recesso", d1, d2, ""))                # geral só admin
    lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Recesso", d1, d2, "e1"), AGORA)
    assert c.roxas[0].id == "r1" and c.roxas[0].criado_por == det.id
    assert fila_do_dia(c, e, d1) == "roxa:r1" and conta_como(d1, c, e) == "roxa" and funciona(c, e, d1)
    with pytest.raises(ValueError, match="coincide"):
        lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Outro", d2, d2 + timedelta(days=2), "e1"))
    assert not lc.pode_remover(c, aux_u.id, c.roxas[0]) and lc.pode_remover(c, det.id, c.roxas[0])
    lc.remover(c, det.id, c.roxas[0])
    assert c.roxas == []


def test_roxo_de_uma_escala_nao_vale_em_outra():
    c, adm, det, _ = mundo()
    gestao.criar_escala(c, det.id, Escala("e2", "Dois", modo="preta_vermelha", data_base=D,
                                           membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    d1 = D + timedelta(days=7)
    lc.lancar_periodo_roxo(c, det.id, PeriodoRoxa("", "Só da e1", d1, d1, "e1"))
    assert fila_do_dia(c, c.escala("e1"), d1).startswith("roxa:") and not fila_do_dia(c, c.escala("e2"), d1).startswith("roxa:")
    gerar(c, D + timedelta(days=10))                                                              # não quebra


def test_quem_lancou_e_quando_em_todos_os_lancamentos_e_persiste():
    c, adm, det, aux_u = mundo()
    lc.lancar_impedimento(c, det.id, Impedimento("m3", "ferias", D, D + timedelta(days=5)), AGORA)
    lc.lancar_dispensa_no_dia(c, aux_u.id, Ocorrencia(D, "e1", "m4", "baixa médica"), AGORA)
    lc.lancar_guarnecimento(c, det.id, Guarnecimento(D, "e1", True), AGORA)
    lc.lancar_dia_especial(c, det.id, DiaEspecial(D + timedelta(days=1), "feriado", "x", "e1"), AGORA)
    itens = [*c.impedimentos, *c.ocorrencias, *c.guarnecimentos, *c.dias_especiais]
    assert all(i.criado_em == AGORA and i.criado_por for i in itens)
    assert c.ocorrencias[0].criado_por == aux_u.id and c.impedimentos[0].criado_por == det.id
    c2 = de_tabelas(para_tabelas(c))
    assert [(i.criado_por, i.criado_em) for i in c2.impedimentos] == [(det.id, AGORA)]
    assert c2.dias_especiais[0].data_fim is None and c2.dias_especiais[0].criado_em == AGORA
    # planilha antiga (sem as colunas novas) carrega com carimbo vazio
    T = {k: [list(r) for r in v] for k, v in para_tabelas(c).items()}
    cab = T["Impedimentos"][0]
    for nome in ("criado_por", "criado_em"):
        j = T["Impedimentos"][0].index(nome)
        T["Impedimentos"] = [[x for k, x in enumerate(r) if k != j] for r in T["Impedimentos"]]
    c3 = de_tabelas(T)
    assert c3.impedimentos[0].criado_por == "" and c3.impedimentos[0].criado_em is None


def test_roxo_antigo_sem_escala_continua_valendo_para_todas():
    c, adm, det, _ = mundo()
    d1 = D + timedelta(days=7)
    c.roxas.append(PeriodoRoxa("fa", "Recesso antigo", d1, d1))                                   # dado de antes (sem escala)
    assert fila_do_dia(c, c.escala("e1"), d1) == "roxa:fa"
    with pytest.raises(PermissaoNegada):
        lc.remover(c, det.id, c.roxas[0])                                                         # geral só o administrador
    lc.remover(c, adm.id, c.roxas[0])


def test_mesmo_lancamento_em_varias_escalas_so_onde_e_detalhista_tudo_ou_nada():
    c, adm, det, aux_u = mundo()
    outro = auth.criar_usuario(c, adm.id, "20000003", "Outro Detalhista", SENHA)
    for eid in ("e2", "e3"):
        gestao.criar_escala(c, det.id, Escala(eid, eid, modo="preta_vermelha", data_base=D,
                                               membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    gestao.criar_escala(c, outro.id, Escala("x1", "Do outro", modo="preta_vermelha", data_base=D,
                                             membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    ter = D + timedelta(days=1)
    nomes = lc.lancar_dia_especial_em(c, det.id, DiaEspecial(ter, "sem_expediente", "Licença adm.", "", ter + timedelta(days=1)),
                                      ["e1", "e2", "e3"], AGORA)
    assert nomes == ["Um", "e2", "e3"]
    assert sorted(x.escala_id for x in c.dias_especiais) == ["e1", "e2", "e3"]
    assert all(not dia_util(ter, c, c.escala(e)) for e in ("e1", "e2", "e3")) and dia_util(ter, c, c.escala("x1"))
    assert all(x.criado_por == det.id and x.criado_em == AGORA for x in c.dias_especiais)
    # repetir é seguro: escalas que já têm o mesmo lançamento são puladas
    assert lc.lancar_dia_especial_em(c, det.id, DiaEspecial(ter, "sem_expediente", "Licença adm.", "", ter + timedelta(days=1)),
                                     ["e1", "e2"]) == []
    assert len(c.dias_especiais) == 3
    # escala de outro detalhista na lista: nada é lançado (tudo ou nada)
    antes = len(c.dias_especiais)
    with pytest.raises(PermissaoNegada, match="detalhista de cada uma"):
        lc.lancar_dia_especial_em(c, det.id, DiaEspecial(D + timedelta(days=9), "feriado", "x", ""), ["e1", "e2", "x1"])
    assert len(c.dias_especiais) == antes
    with pytest.raises(PermissaoNegada, match="detalhista de cada uma"):
        lc.lancar_dia_especial_em(c, aux_u.id, DiaEspecial(D + timedelta(days=9), "feriado", "x", ""), ["e1", "e2"])  # auxiliar
    with pytest.raises(ValueError, match="pelo menos uma"):
        lc.lancar_dia_especial_em(c, det.id, DiaEspecial(ter, "feriado", "x", ""), [])


def test_periodo_roxo_em_varias_escalas_exige_participar_da_roxa_em_todas():
    c, adm, det, _ = mundo()
    gestao.criar_escala(c, det.id, Escala("e2", "Dois", modo="preta_vermelha", data_base=D, participa_roxa=False,
                                           membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    d1 = D + timedelta(days=7)
    with pytest.raises(ValueError, match="não participa da roxa"):
        lc.lancar_periodo_roxo_em(c, det.id, PeriodoRoxa("", "Recesso", d1, d1 + timedelta(days=2)), ["e1", "e2"])
    assert c.roxas == []                                                    # nada ficou pela metade
    c.escala("e2").participa_roxa = True
    assert lc.lancar_periodo_roxo_em(c, det.id, PeriodoRoxa("", "Recesso", d1, d1 + timedelta(days=2)), ["e1", "e2"]) == ["Um", "Dois"]
    assert sorted(r.id for r in c.roxas) == ["r1", "r2"]                    # ids próprios, uma fila por período/escala
    assert fila_do_dia(c, c.escala("e1"), d1) == "roxa:r1" and fila_do_dia(c, c.escala("e2"), d1) == "roxa:r2"


def test_guarnecimento_em_varias_escalas_substitui_decisao_e_e_tudo_ou_nada():
    c, adm, det, aux_u = mundo()
    outro = auth.criar_usuario(c, adm.id, "20000003", "Outro Detalhista", SENHA)
    for eid in ("e2", "e3"):
        gestao.criar_escala(c, det.id, Escala(eid, eid, modo="preta_vermelha", data_base=D,
                                               membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    gestao.criar_escala(c, outro.id, Escala("x1", "Do outro", modo="preta_vermelha", data_base=D,
                                             membros=[Pertinencia(f"m{i}") for i in range(1, 8)]))
    dia = D + timedelta(days=1)
    assert lc.lancar_guarnecimento_em(c, det.id, Guarnecimento(dia, "", False), ["e1", "e2", "e3"], AGORA) == ["Um", "e2", "e3"]
    assert all(not funciona(c, c.escala(e), dia) for e in ("e1", "e2", "e3")) and funciona(c, c.escala("x1"), dia)
    assert all(g.criado_por == det.id and g.criado_em == AGORA for g in c.guarnecimentos)
    # repetir a mesma decisão não duplica; decisão oposta SUBSTITUI a anterior (antes a primeira ficava valendo)
    assert lc.lancar_guarnecimento_em(c, det.id, Guarnecimento(dia, "", False), ["e1", "e2"]) == []
    assert len(c.guarnecimentos) == 3
    assert lc.lancar_guarnecimento_em(c, det.id, Guarnecimento(dia, "", True), ["e1", "e2"]) == ["Um", "e2"]
    assert len(c.guarnecimentos) == 3 and funciona(c, c.escala("e1"), dia) and not funciona(c, c.escala("e3"), dia)
    # escala de outro detalhista na lista: nada muda
    antes = [(g.escala_id, g.data, g.guarnece) for g in c.guarnecimentos]
    with pytest.raises(PermissaoNegada, match="detalhista de cada uma"):
        lc.lancar_guarnecimento_em(c, det.id, Guarnecimento(dia, "", False), ["e1", "e2", "x1"])
    assert [(g.escala_id, g.data, g.guarnece) for g in c.guarnecimentos] == antes
    with pytest.raises(PermissaoNegada):
        lc.lancar_guarnecimento_em(c, aux_u.id, Guarnecimento(dia, "", False), ["e1", "e2"])


def test_obice_do_militar_vale_sozinho_em_escala_nova_e_em_palestra():
    """Impedimento é do militar: qualquer escala ou escalação criada depois já o respeita e o mostra."""
    from sisescala.previa import html_previa, periodo
    c, adm, det, _ = mundo()
    lc.lancar_impedimento(c, det.id, Impedimento("m5", "ferias", D, D + timedelta(days=20)), AGORA)
    gestao.criar_escala(c, det.id, Escala("nova", "Escala nova", data_base=D, militares_dia=2,
                                           membros=[Pertinencia(f"m{i}") for i in range(3, 8)]))
    gestao.criar_escala(c, det.id, Escala("pal", "Palestra", modo="eventos", categoria="palestra", data_base=D,
                                           militares_dia=2, membros=[Pertinencia(f"m{i}") for i in range(3, 8)]))
    c.eventos.append(Evento("pal", D + timedelta(days=2), "Palestra de segurança"))
    r = gerar(c, D + timedelta(days=15))
    for eid in ("nova", "pal"):
        for i in range(16):
            assert all(a.militar_id != "m5" for a in r.dia(D + timedelta(days=i), eid).efetivos)    # ninguém de férias é escalado
    dias = periodo(D, 7)
    html = html_previa(c, r, dias, "nova")
    assert "Férias" in html                                                                           # e a prévia mostra o óbice
    assert "Férias" in html_previa(c, r, dias, "pal")
    # depois das férias, ele volta à fila da escala nova
    r2 = gerar(c, D + timedelta(days=60))
    assert any(a.militar_id == "m5" for i in range(21, 60) for a in r2.dia(D + timedelta(days=i), "nova").efetivos)


def test_previa_ocupa_a_largura_e_ajusta_as_colunas_por_periodo_e_pdf_gera():
    from sisescala.pdf import gerar_pdf
    from sisescala.previa import html_previa, periodo
    c, adm, det, _ = mundo()
    for n, denso in ((7, False), (15, True), (30, True)):
        dias = periodo(D, n)
        html = html_previa(c, gerar(c, dias[-1]), dias, "e1", com_card=False)
        assert "table-layout:fixed" in html and html.count("<col ") == n + 1       # uma coluna de nomes + n dias iguais
        assert ('class="prev dens"' in html) == denso
        assert f"min-width:{128 + (96 if n == 7 else 48 if n == 15 else 52) * n}px" in html
    dias = periodo(D, 15)
    pdf = gerar_pdf(c, gerar(c, dias[-1]), dias, "e1", "OM Teste", "Instruções", "Recomendações", "Regras", ("A", "B", "C"))
    assert pdf.startswith(b"%PDF")

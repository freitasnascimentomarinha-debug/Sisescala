"""Cadastro com nome de guerra, posto/graduação e especialidade: `2ºSG-PL Freitas (11.0316.11)`."""
from datetime import date, datetime, timedelta

import pytest
from pypdf import PdfReader

from io import BytesIO

from sisescala import auth, cadastro as cd, gestao
from sisescala import importacao as imp
from sisescala import vinculos as vc
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.pdf import gerar_pdf, pdf_papeleta
from sisescala.previa import html_previa, periodo

D = date(2027, 3, 1)
SENHA = "senha-forte-1"


def test_rotulo_grad_especialidade_nome_e_nip():
    m = Militar("m1", "Freitas", "2ºSG", 1, "11.0316.11", especialidade="PL")
    assert m.rotulo == "2ºSG-PL Freitas (11.0316.11)"
    assert Militar("m2", "Silva", "CB", 2, "12345678").rotulo == "CB Silva (12.3456.78)"        # NIP de 8 dígitos formatado
    assert Militar("m3", "Souza", "1ºSG", 3, especialidade="MO").rotulo == "1ºSG-MO Souza"      # sem NIP
    assert Militar("m4", "Lima", "", 4, "11.0316.11", especialidade="CL").rotulo == "CL Lima (11.0316.11)"
    assert Militar("m5", "Rocha", "CT", 5).rotulo == "CT Rocha"
    assert formatar_nip("1234567") == "1234567" and formatar_nip("") == ""                      # tamanho estranho fica como está
    assert rotulo_militar(m, com_nip=False) == "2ºSG-PL Freitas"


def mundo():
    ms = [Militar("m1", "Freitas", "2ºSG", 1, "11.0316.11", especialidade="PL"),
          Militar("m2", "Souza", "CB", 2, "22.0000.22", especialidade="MO"),
          Militar("m3", "Lima", "1ºSG", 3, "33.0000.33"), Militar("m4", "Rocha", "CT", 4)]
    c = Contexto(ms, [], D)
    adm, _ = auth.garantir_admin(c, "admin", SENHA)
    gestao.criar_escala(c, adm.id, Escala("e1", "Portaria", om="CAAML", data_base=D, militares_dia=1, folgas_minimas=2,
                                           membros=[Pertinencia(m.id) for m in ms]))
    return c, adm


def test_previa_e_pdf_mostram_o_rotulo_completo():
    c, adm = mundo()
    dias = periodo(D, 7)
    res = gerar(c, dias[-1])
    html = html_previa(c, res, dias, "e1", com_card=False)
    assert "2ºSG-PL Freitas" in html and "(11.0316.11)" in html and "1ºSG Lima" in html
    texto = "\n".join(p.extract_text() for p in PdfReader(BytesIO(gerar_pdf(c, res, dias, "e1", "OM"))).pages)
    assert "2ºSG-PL Freitas (11.0316.11)" in texto.replace("\n", " ") or "2ºSG-PL Freitas" in texto
    assert "(11.0316.11)" in texto


def test_cadastro_de_militar_com_especialidade_e_edicao():
    c, adm = mundo()
    m = cd.adicionar_militar(c, "Novo", "3ºSG", "44.0000.44", "COPAB", None, "", "", "", "ET")
    assert m.especialidade == "ET" and m.rotulo == "3ºSG-ET Novo (44.0000.44)"
    cd.editar_militar(c, m.id, especialidade="PL")
    assert c.militar(m.id).especialidade == "PL"


def test_importacao_le_a_coluna_especialidade():
    c, adm = mundo()
    linhas = [{"Nome de guerra": "Zé", "Posto/Graduação": "2ºSG", "Especialidade": "PL", "NIP": "55.0000.55", "Escala": "Portaria"},
              {"Nome de guerra": "Mario", "Posto/Graduação": "CB", "Especialidade": "MO", "NIP": "66.0000.66", "Escala": "Portaria"}]
    novo, rel = imp.importar(c, linhas, usuario_id=adm.id, dono_id=adm.id, sobrescrever=False)
    por_nome = {m.nome: m for m in novo.militares}
    assert por_nome["Zé"].rotulo == "2ºSG-PL Zé (55.0000.55)" and por_nome["Mario"].especialidade == "MO"
    ler = imp.ler_tabela(imp.MODELO_CSV.encode("utf-8-sig"), "modelo.csv")
    assert "Especialidade" in ler[0] and ler[0]["Especialidade"] == "PL"


def test_cadastro_da_conta_exige_nome_de_guerra_e_posto_e_completa_o_militar_ao_vincular():
    c, adm = mundo()
    args = dict(email="a@b.com", ramal="2345", celular="21987654321")
    with pytest.raises(ValueError, match="nome de guerra"):
        auth.cadastrar_se(c, "77000077", "Beltrano Silva", SENHA, om="CAAML", posto="CB", **args)
    with pytest.raises(ValueError, match="posto"):
        auth.cadastrar_se(c, "77000077", "Beltrano Silva", SENHA, om="CAAML", nome_guerra="Beltrano", **args)
    u = auth.cadastrar_se(c, "77000077", "Beltrano Silva", SENHA, om="CAAML", nome_guerra="Beltrano", posto="1ºSG",
                          especialidade="CL", **args)
    assert (u.nome_guerra, u.posto, u.especialidade) == ("Beltrano", "1ºSG", "CL")
    auth.aprovar_usuario(c, adm.id, u.id)
    # militar do cadastro sem posto nem especialidade: a conta vinculada completa o que está vazio
    c.militar("m3").posto = ""
    ana = auth.criar_usuario(c, adm.id, "33000033", "Ana", SENHA, nome_guerra="Lima", posto="1ºSG", especialidade="CL")
    cv = vc.convidar(c, adm.id, ana.id, "m3", "e1", datetime(2027, 2, 1))
    vc.aceitar_convite(c, ana.id, cv.id, "33.0000.33", "1234")
    assert c.militar("m3").especialidade == "CL" and c.militar("m3").posto == "1ºSG"
    ana2 = auth.criar_usuario(c, adm.id, "99000099", "Outra", SENHA, nome_guerra="X", posto="CMG", especialidade="ZZ")
    cv2 = vc.convidar(c, adm.id, ana2.id, "m1", "e1", datetime(2027, 2, 1))
    vc.aceitar_convite(c, ana2.id, cv2.id, "11.0316.11", "1234")
    assert c.militar("m1").especialidade == "PL" and c.militar("m1").posto == "2ºSG"            # dados do cadastro não mudam


def test_persistencia_guarda_especialidade_e_dados_da_conta():
    from sisescala.persistencia import de_tabelas, para_tabelas
    c, adm = mundo()
    u = auth.cadastrar_se(c, "77000077", "Beltrano Silva", SENHA, "a@b.com", "2345", "21987654321", om="CAAML",
                          nome_guerra="Beltrano", posto="1ºSG", especialidade="CL")
    c2 = de_tabelas(para_tabelas(c))
    assert c2.militar("m1").especialidade == "PL"
    u2 = c2.usuario(u.id)
    assert (u2.nome_guerra, u2.posto, u2.especialidade) == ("Beltrano", "1ºSG", "CL")


def test_papeleta_pdf_usa_o_rotulo_completo():
    from sisescala import papeletas as pp
    c, adm = mundo()
    p = Papeleta("pp1", 1, "e1", "m1", D, "m2", D + timedelta(days=1), datetime(2027, 2, 20, 9, 0), adm.id, "teste")
    texto = " ".join(pg.extract_text() for pg in PdfReader(BytesIO(pdf_papeleta(c, p))).pages).replace("\n", " ")
    assert "2ºSG-PL Freitas" in texto and "(11.0316.11)" in texto and "CB-MO Souza" in texto


def test_rotulo_da_conta_responsavel_e_opcoes_de_detalhista_sem_vazar_outros_cadastros():
    c, adm = mundo()
    # conta com posto/guerra/especialidade: aparece como o militar
    u = auth.criar_usuario(c, adm.id, "88000088", "Beltrano da Silva", SENHA, nome_guerra="Beltrano", posto="1ºSG",
                           especialidade="CL")
    assert c.rotulo_do_usuario(u) == "1ºSG-CL Beltrano (88.0000.88)"
    u.militar_id = "m2"                                               # vinculada: vale o cadastro do militar
    assert c.rotulo_do_usuario(u) == c.militar("m2").rotulo
    assert c.rotulo_do_usuario(adm) == "Administrador (admin)"        # conta sem dados de militar: nome e NIP/login


def test_a_pessoa_atualiza_os_proprios_dados_e_o_militar_vinculado_acompanha():
    c, adm = mundo()
    u = auth.criar_usuario(c, adm.id, "88000088", "Beltrano", SENHA, nome_guerra="", posto="", militar_id="m4")  # conta antiga, sem dados
    with pytest.raises(ValueError, match="nome de guerra"):
        auth.atualizar_dados(c, u.id, "Beltrano da Silva", "", "CT", "", "CAAML")
    with pytest.raises(ValueError, match="posto"):
        auth.atualizar_dados(c, u.id, "Beltrano da Silva", "Beltrano", "", "", "CAAML")
    with pytest.raises(ValueError, match="OM"):
        auth.atualizar_dados(c, u.id, "Beltrano da Silva", "Beltrano", "CT", "", "")
    auth.atualizar_dados(c, u.id, "Beltrano da Silva", "Beltrano", "1ºTEN", "ET", "COPAB")
    assert (u.nome, u.nome_guerra, u.posto, u.especialidade, u.om) == ("Beltrano da Silva", "Beltrano", "1ºTEN", "ET", "COPAB")
    m = c.militar("m4")                                     # vinculado: o cadastro do militar acompanha (promoção etc.)
    assert (m.nome, m.posto, m.especialidade, m.om) == ("Beltrano", "1ºTEN", "ET", "COPAB")
    assert m.rotulo == "1ºTEN-ET Beltrano"
    auth.atualizar_dados(c, u.id, "Beltrano da Silva", "Beltrano", "CC", "", "COPAB")        # promoção: atualiza de novo
    assert c.militar("m4").posto == "CC" and c.militar("m4").especialidade == ""
    adm.nome_guerra = ""                                    # o administrador não precisa de OM
    auth.atualizar_dados(c, adm.id, "Administrador", "Admin", "CMG", "", "")
    assert adm.posto == "CMG"

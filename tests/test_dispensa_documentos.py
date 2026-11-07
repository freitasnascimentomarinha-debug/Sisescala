from datetime import date, datetime, timedelta
from io import BytesIO

import pytest

from sisescala import auth
from sisescala import papeletas as pp
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.pdf import gerar_pdf, pdf_papeleta
from sisescala.persistencia import de_tabelas, para_tabelas
from sisescala.previa import html_previa, periodo
from sisescala.relatorio import pdf_regras

D = date(2027, 3, 1)
OM = "Centro de Operações do Abastecimento"


def mk():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"{i}.000") for i in range(1, 8)]
    e = Escala("A", "Portaria", dono_id="u1", om=OM, membros=[Pertinencia(m.id) for m in ms])
    c = Contexto(ms, [e], D)
    auth.criar_usuario(c, None, "det", "Detalhista", "senha-forte-1", admin=True)
    c.usuario("u1").pin_hash = auth.hash_pin("1234")
    return c


def texto_pdf(dados: bytes) -> str:
    pypdf = pytest.importorskip("pypdf")
    return " ".join(pg.extract_text() for pg in pypdf.PdfReader(BytesIO(dados)).pages)


# ------------------------------------------------------------- baixa e falta viram Dispensado
def test_dispensado_no_dia_aparece_como_disp_com_justificativa_e_reconfigura():
    c = mk()
    c.ocorrencias.append(Ocorrencia(D, "A", "m1", "Baixa médica – atestado 3 dias"))
    r = gerar(c, D + timedelta(days=3))
    dia = r.dia(D, "A")
    disp = [a for a in dia.alocacoes if a.origem == "falta"]
    assert [(a.militar_id, a.sigla) for a in disp] == [("m1", "Disp")]
    assert "Baixa médica – atestado 3 dias" in disp[0].obs and "retém avançou" in disp[0].obs.lower()
    assert [a.militar_id for a in dia.efetivos] == ["m2"]                    # o retém avançou: escala reconfigurada
    assert [a.militar_id for a in r.dia(D + timedelta(days=1), "A").efetivos] == ["m3"]


def test_previa_nao_tem_status_baixa_nem_falta_e_mostra_disp_e_justificativa():
    c = mk()
    c.ocorrencias.append(Ocorrencia(D, "A", "m1", "Passou mal no expediente"))
    c.impedimentos.append(Impedimento("m4", "dispensa_justificada", D, D + timedelta(days=2), "Baixa hospitalar"))
    r = gerar(c, D + timedelta(days=6))
    html = html_previa(c, r, periodo(D, 7), "A")
    assert "Baixa</span>" not in html and ">Falta<" not in html and "Não deu o serviço" not in html
    assert ">Disp<" in html or "Disp</span>" in html
    assert "Dispensado (baixa, falta ou dispensa)" in html                     # legenda única
    assert "Passou mal no expediente" in html                                  # justificativa nas observações
    assert "Baixa hospitalar" in html


def test_justificativa_do_detalhista_e_obrigatoria():
    assert Ocorrencia(D, "A", "m1", "").validar() and Ocorrencia(D, "A", "m1", "  ").validar()
    assert not Ocorrencia(D, "A", "m1", "Falta justificada").validar()
    assert Impedimento("m1", "dispensa_justificada", D, D).validar()
    assert not Impedimento("m1", "dispensa_justificada", D, D, "Baixa médica").validar()
    assert Impedimento("m1", "dispensa", D, D, "luto").validar()                # com documento exige arquivo
    assert not Impedimento("m1", "dispensa", D, D, "luto", "doc.pdf").validar()


def test_tipos_da_tela_nao_incluem_baixa_mas_dados_antigos_continuam_valendo():
    assert "baixa" not in TIPOS_VISIVEIS and "dispensa_justificada" in TIPOS_VISIVEIS
    assert all(t in ROTULO_IMPEDIMENTO for t in TIPOS_IMPEDIMENTO)
    c = mk()
    c.impedimentos.append(Impedimento("m1", "baixa", D, D + timedelta(days=1), "legado"))   # dado antigo
    r = gerar(c, D + timedelta(days=2))
    assert "m1" not in [a.militar_id for a in r.dia(D, "A").efetivos]
    assert TIPOS_IMPEDIMENTO["baixa"] == "Disp"


def test_dispensa_por_periodo_tira_da_fila_sem_perder_a_vez():
    c = mk()
    c.impedimentos.append(Impedimento("m2", "dispensa_justificada", D, D + timedelta(days=1), "Baixa"))
    r = gerar(c, D + timedelta(days=4))
    assert [r.dia(D + timedelta(days=i), "A").efetivos[0].militar_id for i in range(4)] == ["m1", "m3", "m4", "m5"]


# ------------------------------------------------------------- cabeçalho dos documentos
def test_detalhe_tem_cabecalho_marinha_e_om_e_lista_dispensados():
    c = mk()
    c.ocorrencias.append(Ocorrencia(D, "A", "m1", "Baixa médica"))
    r = gerar(c, D + timedelta(days=4))
    t = texto_pdf(gerar_pdf(c, r, periodo(D, 5), "A"))
    assert t.index("MARINHA DO BRASIL") < t.index(OM.upper()) < t.index("DETALHE DE SERVIÇO")
    assert "M1 [Disp]" in t and "Baixa médica" in t                                    # dispensado + justificativa
    assert "Falta" not in t.replace("faltam", "")


def test_om_do_formulario_prevalece_sobre_a_da_escala():
    c = mk()
    r = gerar(c, D + timedelta(days=2))
    t = texto_pdf(gerar_pdf(c, r, periodo(D, 3), "A", om="Outra OM Qualquer"))
    assert "OUTRA OM QUALQUER" in t and OM.upper() not in t


def test_papeleta_e_regras_tambem_tem_cabecalho_oficial():
    c = mk()
    for u in c.usuarios:
        u.pin_hash = auth.hash_pin("1234")
    res = gerar(c, D + timedelta(days=10))
    d = lambda m: sorted(dd for (dd, e), de in res.dias.items() for a in de.efetivos if a.militar_id == m)  # noqa: E731
    par = next((x, dx, y, dy) for x in ("m1", "m2") for y in ("m4", "m5") for dx in d(x) for dy in d(y)
               if dx != dy and not pp.validar_troca(c, c.escala("A"), x, dx, y, dy)[0])
    p = pp.criar(c, "u1", "A", par[0], par[1], par[2], par[3], "motivo", datetime(2027, 2, 20), pin="1234")
    for dados in (pdf_papeleta(c, p), pdf_regras(c, c.escala("A"))):
        t = texto_pdf(dados)
        assert t.index("MARINHA DO BRASIL") < t.index(OM.upper())


def test_om_persiste():
    c = mk()
    c2 = de_tabelas(para_tabelas(c))
    assert c2.escala("A").om == OM

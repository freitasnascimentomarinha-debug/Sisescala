"""Assinatura do detalhista: registro, conferência pelo código (inteiro, começo ou lido do QR) e adulteração."""
import io
from datetime import date, datetime, timedelta

from pypdf import PdfReader

from sisescala import verificacao as vf
from sisescala.modelos import Contexto, Escala, Militar, Pertinencia
from sisescala.motor import gerar
from sisescala.pdf import codigo_do_corpo, corpo_detalhe, gerar_pdf
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)


def mk():
    c = Contexto([Militar(f"m{i}", f"Fulano{i}", "CB", i) for i in range(1, 5)],
                 [Escala("A", "Portaria", membros=[Pertinencia(f"m{i}") for i in range(1, 5)])], D)
    dias = [D + timedelta(days=i) for i in range(3)]
    return c, gerar(c, dias[-1]), dias


def test_registro_se_confere_pelo_codigo_e_sobrevive_a_gravacao():
    c, r, dias = mk()
    corpo = corpo_detalhe(c, r, dias, "A", "OM", "<b>X</b>", "", "", ("Det", "", ""))
    cod = codigo_do_corpo(corpo)
    a = vf.registrar(c, "u1", "A", dias, corpo, cod, "CT Fulano", "11.0316.11", "OM", datetime(2027, 3, 1, 8))
    assert vf.registrar(c, "u1", "A", dias, corpo, cod, "CT Fulano", "11.0316.11", "OM") is a      # não duplica
    assert len(c.assinaturas_detalhe) == 1
    url = vf.url_de_verificacao("https://app.exemplo.br/escala?x=1", cod)
    assert url == f"https://app.exemplo.br/verificar?codigo={cod}"
    for entrada in (cod, cod[:12].upper(), f" {cod[:20]}\n", f"SISESCALA-VERIFICAR:{cod}", url):
        assert vf.buscar(c, entrada) is a, entrada
    assert vf.buscar(c, cod[:8]) is None and vf.buscar(c, "0" * 64) is None and vf.buscar(c, "") is None
    assert vf.integra(a)
    d = vf.descrever(c, a)
    assert d["escala"] == "Portaria" and len(d["dias"]) == 3 and d["textos"][0] == "<b>X</b>"
    c2 = de_tabelas(para_tabelas(c))
    b = vf.buscar(c2, cod)
    assert b and (b.nome, b.nip, b.inicio, b.fim, b.em) == ("CT Fulano", "11.0316.11", D, dias[-1], datetime(2027, 3, 1, 8)) and vf.integra(b)
    from sisescala.assinaturas import desempacotar, empacotar
    b.conteudo = empacotar(desempacotar(b.conteudo).replace("Portaria", "Outra"))
    assert not vf.integra(b)                                            # registro adulterado deixa de conferir


def test_pdf_assinado_tem_qr_codigo_e_cabecalho_na_ordem_pedida():
    c, r, dias = mk()
    corpo = corpo_detalhe(c, r, dias, "A", "Centro de Operações", "", "", "", ("", "", ""))
    cod = codigo_do_corpo(corpo)
    ass = {"detalhista": {"nome": "CT Fulano", "nip": "1", "em": datetime(2027, 3, 1, 8)},
           "auxiliar": {"nome": "1T Auxiliar", "nip": "2", "em": datetime(2027, 3, 1, 9)},
           "hash": cod, "url": vf.url_de_verificacao("https://x.br", cod)}
    pdf = gerar_pdf(c, r, dias, "A", "Centro de Operações", "", "", "", ("", "", "", ""), ass)
    txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert cod in txt and "Verificar documento" in txt and "CT Fulano" in txt and "1T Auxiliar" in txt
    assert "Auxiliar do Detalhista" in txt and txt.count("Assinado eletronicamente") == 2
    assert txt.index("MARINHA DO BRASIL") < txt.index("CENTRO DE OPERAÇÕES") < txt.index("DETALHE DE SERVIÇO DE PORTARIA")


def test_titulo_nao_repete_detalhe_de_servico_e_brasao_enviado_sai_no_pdf():
    import base64
    from PIL import Image
    from sisescala import brasao as bs
    from sisescala.pdf import titulo_detalhe
    assert titulo_detalhe("Pernoite") == "DETALHE DE SERVIÇO DE PERNOITE"
    assert titulo_detalhe("Detalhe de Serviço do COpAb") == "DETALHE DE SERVIÇO DO COPAB"
    assert titulo_detalhe("DETALHE DE SERVICO – Diária") == "DETALHE DE SERVICO – DIÁRIA"
    c, r, dias = mk()
    buf = io.BytesIO()
    Image.new("RGBA", (800, 900), (10, 35, 66, 255)).save(buf, "PNG")
    c.brasao_b64 = bs.preparar(buf.getvalue())
    assert 0 < len(c.brasao_b64) <= bs.LIMITE and base64.b64decode(c.brasao_b64)[:4] == b"\x89PNG"
    c2 = de_tabelas(para_tabelas(c))
    assert c2.brasao_b64 == c.brasao_b64                                  # sobrevive à gravação (Config)
    from pathlib import Path
    from sisescala import pdf as pdfmod
    pdfmod.BRASAO, original = Path("/nao/existe.png"), pdfmod.BRASAO     # sem o arquivo padrão, só vale o enviado
    try:
        com, sem = gerar_pdf(c2, r, dias, "A", "OM"), gerar_pdf(mk()[0], r, dias, "A", "OM")
    finally:
        pdfmod.BRASAO = original
    assert len(com) > len(sem) + 1000                                    # a imagem entrou no PDF
    assert len(gerar_pdf(mk()[0], r, dias, "A", "OM")) > len(sem) + 1000  # e o brasão padrão (assets/brasao.png) também
    try:
        bs.preparar(b"nao e imagem")
        raise AssertionError("deveria recusar")
    except ValueError:
        pass


def test_auxiliar_tambem_assina_o_mesmo_conteudo_e_as_duas_assinaturas_se_conferem_pelo_codigo():
    c, r, dias = mk()
    nomes = ("", "Aux", "", "")
    corpo = corpo_detalhe(c, r, dias, "A", "OM", "", "", "", nomes)
    cod = codigo_do_corpo(corpo)
    a = vf.registrar(c, "u1", "A", dias, corpo, cod, "CT Det", "1", "OM", datetime(2027, 3, 1, 8), "detalhista")
    b = vf.registrar(c, "u2", "A", dias, corpo, cod, "1T Aux", "2", "OM", datetime(2027, 3, 1, 9), "auxiliar")
    assert [x.papel for x in vf.do_codigo(c, cod)] == ["detalhista", "auxiliar"]
    assert vf.buscar(c, cod[:16]) in (a, b) and vf.integra(a) and vf.integra(b)
    c2 = de_tabelas(para_tabelas(c))
    assert [(x.papel, x.nome) for x in vf.do_codigo(c2, cod)] == [("detalhista", "CT Det"), ("auxiliar", "1T Aux")]
    # mudar um nome de assinante muda o código: as assinaturas antigas não valem para o conteúdo novo
    assert codigo_do_corpo(corpo_detalhe(c, r, dias, "A", "OM", "", "", "", ("", "Outro", "", ""))) != cod

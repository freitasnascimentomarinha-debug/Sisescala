"""Documento unificado: várias escalas num só detalhe, com regras gerais, enviado e assinado pelas quatro autoridades."""
import io
from datetime import date, datetime, timedelta

import pytest
from pypdf import PdfReader

from sisescala import assinaturas as asn
from sisescala import auth, gestao
from sisescala import conjuntos as cjs
from sisescala import verificacao as vf
from sisescala.modelos import Contexto, Escala, Militar, Pertinencia
from sisescala.motor import gerar
from sisescala.pdf import codigo_do_corpo, corpo_conjunto, gerar_pdf_conjunto, renderizar_pdf
from sisescala.permissoes import PermissaoNegada
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 0)
SENHA = "senha-forte-1"


def mk():
    ms = [Militar(f"m{i}", f"Mil{i}", "CB", i) for i in range(1, 13)]
    c = Contexto(ms, [], D)
    auth.criar_usuario(c, None, "adm", "Administrador", SENHA, admin=True)                          # u1
    for login, nome in (("det", "Detalhista"), ("aux", "Auxiliar"), ("enc", "Encarregado"), ("vice", "Vice"),
                        ("outro", "Outro Detalhista")):                                             # u2..u6
        u = auth.criar_usuario(c, "u1", login, nome, SENHA, perfil="militar")
        u.pin_hash = auth.hash_pin("1234")
    for eid, nome, mem in (("e1", "Fiscal", range(1, 5)), ("e2", "Sentinela", range(3, 9)), ("e3", "Contramestre", range(5, 9))):
        gestao.criar_escala(c, "u2", Escala(eid, nome, membros=[Pertinencia(f"m{i}") for i in mem]))
    gestao.criar_escala(c, "u6", Escala("e4", "De outro", membros=[Pertinencia(f"m{i}") for i in range(9, 13)]))
    dias = [D]
    return c, dias


def test_so_junta_escalas_em_que_decide_e_so_o_responsavel_edita():
    c, dias = mk()
    assert [e.id for e in cjs.elegiveis(c, "u2")] == ["e1", "e2", "e3"]
    cj = cjs.criar(c, "u2", "Escala de Serviço do Dia", ["e1", "e2", "e3"])
    assert cj.escala_ids == ["e1", "e2", "e3"] and cj.dono_id == "u2"
    with pytest.raises(PermissaoNegada):
        cjs.editar(c, "u2", cj.id, escala_ids=["e1", "e4"])                       # e4 é de outro detalhista
    with pytest.raises(PermissaoNegada):
        cjs.editar(c, "u6", cj.id, om="X")                                        # só o dono edita
    with pytest.raises(PermissaoNegada):
        cjs.criar(c, "u3", "Meu")                                                 # u3 não decide nenhuma escala
    with pytest.raises(ValueError):
        cjs.editar(c, "u2", cj.id, dono_id="u3")
    cjs.editar(c, "u2", cj.id, om="COpAb", det_regras="<b>Regra geral</b>", ass_vice_diretor="CMG Fulano")
    c2 = de_tabelas(para_tabelas(c))
    x = c2.conjunto(cj.id)
    assert (x.nome, x.om, x.escala_ids, x.det_regras, x.ass_vice_diretor) == (
        "Escala de Serviço do Dia", "COpAb", ["e1", "e2", "e3"], "<b>Regra geral</b>", "CMG Fulano")


def test_pdf_de_um_dia_tem_uma_linha_por_escala_e_as_regras_gerais():
    c, dias = mk()
    cj = cjs.criar(c, "u2", "Escala de Serviço do Dia", ["e1", "e2", "e3"])
    cjs.editar(c, "u2", cj.id, om="Centro de Operações", det_instrucoes="Apresentar-se fardado", det_regras="Parada às 17h")
    r = gerar(c, dias[-1])
    txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(gerar_pdf_conjunto(c, r, dias, cj))).pages)
    for t in ("ESCALA DE SERVIÇO DO DIA", "Fiscal", "Sentinela", "Contramestre", "Apresentar-se fardado", "Parada às 17h",
              "CENTRO DE OPERAÇÕES", "Serviço", "Escalados"):
        assert t in txt, t
    assert txt.index("MARINHA DO BRASIL") < txt.index("CENTRO DE OPERAÇÕES") < txt.index("ESCALA DE SERVIÇO DO DIA")
    assert PdfReader(io.BytesIO(gerar_pdf_conjunto(c, r, dias, cj))).pages[0].mediabox.width < 600          # um dia: retrato
    # vários dias (automático): paisagem, serviços nas linhas e dias nas colunas
    dias3 = [D + timedelta(days=i) for i in range(3)]
    pdf3 = gerar_pdf_conjunto(c, gerar(c, dias3[-1]), dias3, cj)
    pag = PdfReader(io.BytesIO(pdf3)).pages[0]
    txt3 = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf3)).pages)
    assert pag.mediabox.width > pag.mediabox.height
    assert "Fiscal" in txt3 and "Sentinela" in txt3 and "01/03/2027" in txt3 and "03/03/2027" in txt3
    assert txt3.index("SEG") < txt3.index("TER") < txt3.index("QUA")                                         # dias em colunas
    # forçando retrato volta ao formato de uma tabela por escala
    cjs.editar(c, "u2", cj.id, orientacao="retrato")
    pdf4 = gerar_pdf_conjunto(c, gerar(c, dias3[-1]), dias3, cj)
    assert PdfReader(io.BytesIO(pdf4)).pages[0].mediabox.width < 600 and "FISCAL" in "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf4)).pages)
    cjs.editar(c, "u2", cj.id, orientacao="paisagem")                                                      # paisagem mesmo com um dia
    assert PdfReader(io.BytesIO(gerar_pdf_conjunto(c, r, dias, cj))).pages[0].mediabox.width > 800


def test_fluxo_completo_do_documento_unificado_assinado_pelas_quatro_autoridades():
    c, dias = mk()
    cj = cjs.criar(c, "u2", "Escala de Serviço do Dia", ["e1", "e2", "e3"])
    with pytest.raises(PermissaoNegada):
        asn.designar_conjunto(c, "u3", cj, "u3", "u4", "u5")
    asn.designar_conjunto(c, "u2", cj, "u3", "u4", "u5")
    r = gerar(c, dias[-1])
    corpo = corpo_conjunto(c, r, dias, cj)
    cod = codigo_do_corpo(corpo)
    assert asn.papeis_do_usuario(c, "u2", cj) == ["detalhista"] and asn.papeis_do_usuario(c, "u3", cj) == ["auxiliar"]
    assert asn.papeis_do_usuario(c, "u6", cj) == []
    with pytest.raises(PermissaoNegada):
        asn.enviar(c, "u3", cj, dias, corpo, cod, AGORA)                           # só o dono envia
    d, novo = asn.enviar(c, "u2", cj, dias, corpo, cod, AGORA)
    assert novo and d.conjunto_id == cj.id and d.escala_id == "" and asn.nome_do_doc(c, d) == "Escala de Serviço do Dia"
    assert asn.enviar(c, "u2", cj, dias, corpo, cod, AGORA)[1] is False
    assert {n.usuario_id for n in c.notificacoes if n.tipo == "assinatura"} == {"u3", "u4", "u5"}
    for u, p in (("u3", "auxiliar"), ("u4", "encarregado"), ("u2", "detalhista")):
        asn.assinar(c, u, d.id, p, "1234", agora=AGORA)
    assert [x.id for x, _ in asn.para_assinar(c, "u5")] == [d.id] and asn.faltam(c, d) == ["vice_diretor"]
    asn.assinar(c, "u5", d.id, "vice_diretor", "1234", agora=AGORA)
    assert asn.faltam(c, d) == []
    txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(renderizar_pdf(asn.conteudo(d), asn.carimbos(c, d, ""), c))).pages)
    assert txt.count("Assinado eletronicamente") == 4 and "Fiscal" in txt and "Contramestre" in txt
    c2 = de_tabelas(para_tabelas(c))                                               # tudo sobrevive à gravação
    d2 = c2.detalhes_docs[0]
    assert d2.conjunto_id == cj.id and all(vf.integra(a) for a in vf.do_codigo(c2, cod)) and len(vf.do_codigo(c2, cod)) == 4
    desc = vf.descrever(c2, vf.buscar(c2, cod))
    assert [n for n, _ in desc["secoes"]] == ["Fiscal", "Sentinela", "Contramestre"] and desc["escala"] == "Escala de Serviço do Dia"
    # mudou algo (nova regra): nova versão substitui a aberta; assinatura antiga não vale para ela
    cjs.editar(c, "u2", cj.id, det_regras="Nova regra")
    corpo2 = corpo_conjunto(c, r, dias, cj)
    d3, novo3 = asn.enviar(c, "u2", cj, dias, corpo2, codigo_do_corpo(corpo2), AGORA)
    assert novo3 and d.status == "substituido" and asn.faltam(c, d3) == list(asn.PAPEIS)


def test_excluir_o_documento_cancela_o_que_aguarda_assinatura():
    c, dias = mk()
    cj = cjs.criar(c, "u2", "Dia", ["e1"])
    corpo = corpo_conjunto(c, gerar(c, dias[-1]), dias, cj)
    d, _ = asn.enviar(c, "u2", cj, dias, corpo, codigo_do_corpo(corpo), AGORA)
    cjs.excluir(c, "u2", cj.id)
    assert d.status == "cancelado" and c.conjuntos == [] and asn.para_assinar(c, "u2") == []

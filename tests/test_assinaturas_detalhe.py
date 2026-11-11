"""Fluxo de assinatura do detalhe pelas quatro autoridades: designação, envio, aviso, assinatura por papel e PDF parcial."""
import io
from datetime import date, datetime, timedelta

import pytest
from pypdf import PdfReader

from sisescala import assinaturas as asn
from sisescala import auth, gestao
from sisescala import verificacao as vf
from sisescala.modelos import Contexto, Escala, Militar, Pertinencia
from sisescala.motor import gerar
from sisescala.pdf import codigo_do_corpo, corpo_detalhe, renderizar_pdf
from sisescala.permissoes import PermissaoNegada
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 0)
SENHA = "senha-forte-1"


def mk():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, 9)]
    c = Contexto(ms, [], D)
    auth.criar_usuario(c, None, "adm", "Administrador", SENHA, admin=True)                      # u1
    for login, nome, mid in (("det", "Detalhista", "m1"), ("aux", "Auxiliar", "m2"), ("enc", "Encarregado", ""),
                             ("vice", "Vice", ""), ("outro", "Outro", "m5")):                   # u2..u6
        u = auth.criar_usuario(c, "u1", login, nome, SENHA, perfil="militar", militar_id=mid)
        u.pin_hash = auth.hash_pin("1234")
    e = gestao.criar_escala(c, "u2", Escala("e1", "Portaria", membros=[Pertinencia(f"m{i}") for i in range(2, 9)]))
    gestao.editar_escala(c, "u2", "e1", auxiliares=["m2"])
    asn.designar(c, "u2", "e1", "u4", "u5")
    dias = [D + timedelta(days=i) for i in range(3)]
    corpo = corpo_detalhe(c, gerar(c, dias[-1]), dias, "e1", "OM", "<b>X</b>", "", "", ("", "", "", ""))
    return c, dias, corpo, codigo_do_corpo(corpo)


def test_papeis_de_cada_conta_e_so_o_detalhista_designa():
    c, *_ = mk()
    esc = c.escala("e1")
    assert [asn.papeis_do_usuario(c, u, esc) for u in ("u2", "u3", "u4", "u5", "u6")] == \
        [["detalhista"], ["auxiliar"], ["encarregado"], ["vice_diretor"], []]
    with pytest.raises(PermissaoNegada):
        asn.designar(c, "u3", "e1", "u4", "u5")                                  # o auxiliar não designa
    c.usuario("u4").pin_hash = ""
    with pytest.raises(ValueError, match="PIN"):
        asn.designar(c, "u2", "e1", "u4", "u5")                                  # quem assina precisa do PIN


def test_envio_avisa_as_autoridades_nao_duplica_e_nova_versao_substitui():
    c, dias, corpo, cod = mk()
    d, novo = asn.enviar(c, "u2", "e1", dias, corpo, cod, AGORA)
    assert novo and d.status == "aberto"
    avisados = {n.usuario_id for n in c.notificacoes if n.tipo == "assinatura"}
    assert avisados == {"u3", "u4", "u5"}                                        # quem envia não se avisa
    assert asn.enviar(c, "u2", "e1", dias, corpo, cod, AGORA)[1] is False       # mesmo conteúdo: não duplica
    corpo2 = corpo.replace("Portaria", "Portaria X")
    d2, novo2 = asn.enviar(c, "u2", "e1", dias, corpo2, codigo_do_corpo(corpo2), AGORA)
    assert novo2 and d.status == "substituido" and d2.status == "aberto"
    with pytest.raises(PermissaoNegada):
        asn.enviar(c, "u4", "e1", dias, corpo, cod)                              # só o detalhista envia


def test_cada_autoridade_ve_o_que_falta_assina_uma_vez_e_o_pdf_sai_com_as_que_ja_assinaram():
    c, dias, corpo, cod = mk()
    d, _ = asn.enviar(c, "u2", "e1", dias, corpo, cod, AGORA)
    assert [(x.id, p) for x, p in asn.para_assinar(c, "u4")] == [(d.id, ["encarregado"])] and asn.para_assinar(c, "u6") == []
    with pytest.raises(auth.AutenticacaoErro):
        asn.assinar(c, "u4", d.id, "encarregado", "0000", agora=AGORA)           # PIN errado
    with pytest.raises(PermissaoNegada):
        asn.assinar(c, "u4", d.id, "vice_diretor", "1234", agora=AGORA)          # não é o papel dele
    asn.assinar(c, "u4", d.id, "encarregado", "1234", agora=AGORA)
    assert asn.para_assinar(c, "u4") == [] and asn.faltam(c, d) == ["detalhista", "auxiliar", "vice_diretor"]
    with pytest.raises(ValueError, match="já assinou"):
        asn.assinar(c, "u4", d.id, "encarregado", "1234", agora=AGORA)
    txt = lambda cs: "".join(p.extract_text() for p in PdfReader(io.BytesIO(renderizar_pdf(asn.conteudo(d), cs, c))).pages)  # noqa: E731
    parcial = txt(asn.carimbos(c, d, "https://x.br/verificar?codigo=" + cod))
    assert "Encarregado" in parcial and parcial.count("Assinado eletronicamente") == 1 and cod in parcial
    for u, p in (("u2", "detalhista"), ("u3", "auxiliar"), ("u5", "vice_diretor")):
        asn.assinar(c, u, d.id, p, "1234", agora=AGORA)
    assert asn.faltam(c, d) == [] and txt(asn.carimbos(c, d)).count("Assinado eletronicamente") == 4
    assert [n.texto for n in c.notificacoes if n.usuario_id == "u2" and "assinou" in n.texto]    # o detalhista é avisado
    # tudo sobrevive à gravação e cada assinatura se confere pelo código
    c2 = de_tabelas(para_tabelas(c))
    assert len(c2.detalhes_docs) == 1 and [a.papel for a in vf.do_codigo(c2, cod)] == ["encarregado", "detalhista", "auxiliar", "vice_diretor"]
    assert all(vf.integra(a) for a in vf.do_codigo(c2, cod))
    assert asn.conteudo(c2.detalhes_docs[0])["escala_nome"] == "Portaria"


def test_documento_substituido_ou_cancelado_nao_aceita_assinatura():
    c, dias, corpo, cod = mk()
    d, _ = asn.enviar(c, "u2", "e1", dias, corpo, cod, AGORA)
    asn.cancelar(c, "u2", d.id)
    with pytest.raises(ValueError, match="não está mais aberto"):
        asn.assinar(c, "u4", d.id, "encarregado", "1234", agora=AGORA)
    assert asn.para_assinar(c, "u4") == []


def test_vice_diretor_aparece_centralizado_abaixo_das_outras_assinaturas():
    c, dias, corpo, cod = mk()
    d, _ = asn.enviar(c, "u2", "e1", dias, corpo, cod, AGORA)
    pdf = renderizar_pdf(asn.conteudo(d), {"vice_diretor": {"nome": "CMG Vice", "nip": "9", "em": AGORA}, "hash": cod}, c)
    txt = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert txt.index("Detalhista") < txt.index("Encarregado do Detalhe") < txt.index("Vice-Diretor")   # o vice vem depois (abaixo)
    assert "CMG VICE" in txt and "Assinado eletronicamente" in txt


def test_administrador_apaga_o_pin_esquecido_e_a_pessoa_cadastra_outro_com_a_senha():
    c, dias, corpo, cod = mk()
    u = c.usuario("u4")
    u.tentativas = 3
    with pytest.raises(PermissionError):
        auth.redefinir_pin(c, "u2", "u4")                                          # só o administrador
    auth.redefinir_pin(c, "u1", "u4", AGORA)
    assert u.pin_hash == "" and u.tentativas == 0 and u.bloqueado_ate is None
    assert any(n.usuario_id == "u4" and "apagou o seu PIN" in n.texto for n in c.notificacoes)
    with pytest.raises(ValueError, match="não tem PIN"):
        auth.redefinir_pin(c, "u1", "u4")
    d, _ = asn.enviar(c, "u2", "e1", dias, corpo, cod, AGORA)
    with pytest.raises(auth.AutenticacaoErro, match="cadastre"):
        asn.assinar(c, "u4", d.id, "encarregado", "1234", agora=AGORA)             # sem PIN não assina
    with pytest.raises(auth.AutenticacaoErro):
        auth.alterar_pin(c, "u4", "senha-errada", "5678")                          # novo PIN exige a senha da conta
    auth.alterar_pin(c, "u4", SENHA, "5678")
    assert asn.assinar(c, "u4", d.id, "encarregado", "5678", agora=AGORA).papel == "encarregado"


def test_consulta_publica_exige_codigo_mais_longo_e_nao_mostra_nip():
    from sisescala import tela_verificacao as tv
    c, dias, corpo, cod = mk()
    d, _ = asn.enviar(c, "u2", "e1", dias, corpo, cod, AGORA)
    asn.assinar(c, "u2", d.id, "detalhista", "1234", agora=AGORA)
    assert vf.buscar(c, cod[:12]) is not None and vf.buscar(c, cod[:12], tv.MIN_PUBLICO) is None
    assert vf.buscar(c, cod[:16], tv.MIN_PUBLICO) is not None


def test_assinatura_leva_o_nome_completo_da_conta_e_nao_o_rotulo_militar():
    c, dias, corpo, cod = mk()
    c.usuario("u2").nome = "Beltrano de Tal Souza"
    c.usuario("u2").nome_guerra, c.usuario("u2").posto, c.usuario("u2").especialidade = "Beltrano", "1ºTEN", "ET"
    d, _ = asn.enviar(c, "u2", "e1", dias, corpo, cod, AGORA)
    a = asn.assinar(c, "u2", d.id, "detalhista", "1234", agora=AGORA)
    assert a.nome == "Beltrano de Tal Souza"
    txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(renderizar_pdf(asn.conteudo(d), asn.carimbos(c, d), c))).pages)
    assert "BELTRANO DE TAL SOUZA" in txt and "(Brasília)" in txt and "1ºTEN" not in txt

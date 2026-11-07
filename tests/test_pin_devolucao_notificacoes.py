from datetime import date, datetime, timedelta

import pytest

from sisescala import auth
from sisescala import disponibilidade as dp
from sisescala import notificacoes as nt
from sisescala import papeletas as pp
from sisescala import vinculos as vc
from sisescala.modelos import *
from sisescala.motor import gerar, sugerir_devolucao
from sisescala.pdf import pdf_papeleta
from sisescala.permissoes import PermissaoNegada, compartilhar

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 15, 42)
SENHA, PIN = "senha-forte-1", "1234"
CONTATO = dict(email="a@b.com", ramal="2345", celular="21987654321")


def mk(com_pin=True):
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"{i}.000") for i in range(1, 9)]
    e = Escala("A", "Diária", dono_id="u1", membros=[Pertinencia(m.id) for m in ms])
    c = Contexto(ms, [e], D)
    auth.criar_usuario(c, None, "det", "Detalhista", SENHA, admin=True)           # u1
    for i in (1, 3, 5):                                                            # u2, u3, u4
        auth.criar_usuario(c, "u1", f"mil{i}", f"Mil {i}", SENHA, perfil="militar", militar_id=f"m{i}", **CONTATO)
    if com_pin:
        for u in c.usuarios:
            u.pin_hash = auth.hash_pin(PIN)
    return c


M1, M3, M5 = "u2", "u3", "u4"


def pedido(c, **kw):
    a = dict(usuario_id=M1, escala_id="A", solicitante_id="m1", data_solicitante=D, outro_id="m3",
             data_outro=D + timedelta(days=2), motivo="consulta", agora=AGORA, pin=PIN)
    a.update(kw)
    return pp.criar(c, **a)


# ---------------------------------------------------------------- pedido só pelo PIN
def test_pedido_exige_pin_cadastrado_no_perfil():
    c = mk(com_pin=False)
    with pytest.raises(PermissaoNegada, match="cadastre o seu PIN"):
        pedido(c, pin="1234")
    auth.alterar_pin(c, M1, SENHA, PIN)                       # cadastra no perfil (exige a senha)
    assert pedido(c).status == "pendente"


def test_pedido_com_pin_errado_ou_ausente_nao_cria():
    c = mk()
    with pytest.raises(PermissaoNegada, match="PIN incorreto"):
        pedido(c, pin="0000")
    with pytest.raises(PermissaoNegada, match="PIN incorreto"):
        pedido(c, pin=None)
    assert c.papeletas == []


def test_pedido_registra_quem_confirmou_com_pin_e_quando():
    c = mk()
    p = pedido(c)
    quando, quem, texto = p.historico[0]
    assert quando == AGORA and quem == M1 and "com PIN" in texto and "Mil 1" in texto


def test_detalhista_pedindo_por_militar_usa_o_proprio_pin():
    c = mk()
    c.usuario("u1").pin_hash = auth.hash_pin("9999")
    with pytest.raises(PermissaoNegada):
        pedido(c, usuario_id="u1", pin="1234")                 # PIN do militar não vale
    assert pedido(c, usuario_id="u1", pin="9999").criado_por == "u1"


def test_pin_so_com_4_a_6_digitos_e_alterar_exige_senha():
    c = mk(com_pin=False)
    for ruim in ("12", "1234567", "abcd"):
        with pytest.raises(ValueError, match="PIN"):
            auth.alterar_pin(c, M1, SENHA, ruim)
    with pytest.raises(auth.AutenticacaoErro):
        auth.alterar_pin(c, M1, "errada", "1234")
    auth.alterar_pin(c, M1, SENHA, "123456")
    assert auth.confirmar_assinatura(c, M1, "123456")


# ---------------------------------------------------------------- assinatura com data e hora
def test_assinatura_so_com_pin_e_registra_data_hora_completa():
    c = mk()
    p = pedido(c)
    pp.aprovar(c, "u1", p.id, AGORA)
    with pytest.raises(PermissaoNegada):
        pp.assinar(c, p.id, M1, SENHA, AGORA)                  # a senha não assina
    quando = datetime(2027, 2, 27, 14, 32, 5)
    a = pp.assinar(c, p.id, M1, PIN, quando)
    assert a.em == quando and a.metodo == "conta" and a.hash_documento == pp.hash_documento(c, p)
    assert "14:32:05" in p.historico[-1][2]
    sit = pp.situacao_partes(c, p)
    assert sit[0]["em"] == quando and sit[0]["assinou"] and sit[0]["tem_pin"]
    assert not sit[1]["assinou"]


def test_pdf_traz_assinatura_com_hora_e_o_hash():
    pytest.importorskip("pypdf")
    from io import BytesIO
    from pypdf import PdfReader
    c = mk()
    p = pedido(c)
    pp.aprovar(c, "u1", p.id, AGORA)
    pp.assinar(c, p.id, M1, PIN, datetime(2027, 2, 27, 14, 32, 5))
    txt = " ".join(pg.extract_text() for pg in PdfReader(BytesIO(pdf_papeleta(c, p))).pages)
    assert "14:32:05" in txt and "27/02/2027" in txt and "PIN" in txt and pp.hash_documento(c, p) in txt


def test_situacao_avisa_quem_nao_tem_pin_ou_conta():
    c = mk(com_pin=False)
    p = pedido_sem_pin_para_teste(c)
    sit = pp.situacao_partes(c, p)
    assert [s["tem_conta"] for s in sit] == [True, True] and [s["tem_pin"] for s in sit] == [False, False]


def pedido_sem_pin_para_teste(c):
    for u in c.usuarios:
        u.pin_hash = auth.hash_pin(PIN)
    p = pedido(c)
    for u in c.usuarios:
        u.pin_hash = ""
    return p


# ---------------------------------------------------------------- notificações
def test_disponibilidade_avisa_as_pessoas_da_escala():
    c = mk()
    res = gerar(c, D + timedelta(days=10))
    dp.alternar(c, M1, "A", "m1", D, res, AGORA)
    destinos = {n.usuario_id for n in c.notificacoes}
    assert destinos == {"u1", M3, M5}                       # editores e colegas com conta; não o próprio
    n = next(x for x in c.notificacoes if x.usuario_id == M3)
    assert n.tipo == "disponibilidade" and "M1" in n.texto and "01/03" in n.texto and not n.lida
    dp.alternar(c, M1, "A", "m1", D, res, AGORA)             # fechar não avisa de novo
    assert len(c.notificacoes) == 3


def test_pedido_avisa_a_outra_parte_e_aos_editores_depois_as_decisoes():
    c = mk()
    p = pedido(c)
    assert {n.usuario_id for n in c.notificacoes} == {M3, "u1"}        # quem pediu não se avisa
    pp.aprovar(c, "u1", p.id, AGORA)
    novos = [n for n in c.notificacoes if "APROVADA" in n.texto]
    assert {n.usuario_id for n in novos} == {M1, M3}
    pp.assinar(c, p.id, M1, PIN, AGORA)
    assert any("assinou" in n.texto and n.usuario_id == "u1" for n in c.notificacoes)
    pp.cancelar(c, "u1", p.id, "x", AGORA)
    assert any("CANCELADA" in n.texto and n.usuario_id == M1 for n in c.notificacoes)


def test_vinculo_avisa_editores_e_o_solicitante():
    c = mk()
    nova = auth.cadastrar_se(c, "novo", "Novo", SENHA, **CONTATO)
    compartilhar(c, "u1", "A", nova.id, "leitura")
    v = vc.solicitar(c, nova.id, "A", "m2", "2.000", "1234", AGORA)
    assert [n.usuario_id for n in c.notificacoes if n.tipo == "vinculo"] == ["u1"]
    vc.aprovar(c, "u1", v.id, AGORA)
    assert any(n.usuario_id == nova.id and "APROVADO" in n.texto for n in c.notificacoes)


def test_ler_e_podar_notificacoes():
    c = mk()
    nt.notificar(c, [M1, M1, M3, "inexistente"], "x", "texto", agora=AGORA)
    assert nt.nao_lidas(c, M1) == 1 and nt.nao_lidas(c, M3) == 1          # sem duplicar
    assert nt.marcar_lidas(c, M1) == 1 and nt.nao_lidas(c, M1) == 0
    assert nt.podar(c, AGORA + timedelta(days=40)) == 1                     # lida e antiga
    assert nt.nao_lidas(c, M3) == 1                                         # não lida fica


# ---------------------------------------------------------------- devolução
def com_falta():
    c = mk()
    c.ocorrencias.append(Ocorrencia(D, "A", "m1", "passou mal"))
    res = gerar(c, D + timedelta(days=40))
    return c, res


def test_devolucao_em_aberto_e_estados():
    c, res = com_falta()
    lst = pp.devolucoes_em_aberto(c, res, {"A"}, hoje=D)
    assert [(x["devolucao"].militar_id, x["estado"]) for x in lst] == [("m1", "aberta")]
    assert lst[0]["dias_restantes"] == 30
    assert pp.devolucoes_em_aberto(c, res, {"A"}, hoje=D + timedelta(days=31))[0]["estado"] == "vencida"
    assert pp.devolucoes_em_aberto(c, res, {"outra"}, hoje=D) == []


def test_devolucao_fluxo_completo_assume_o_servico_do_colega_e_quita():
    c, res = com_falta()
    dev = res.devolucoes[0]
    d2, colega = sugerir_devolucao(c, res, dev)[0]
    p = pp.criar_devolucao(c, M1, "A", "m1", D, colega, d2, "", AGORA, PIN)
    assert p.tipo == "devolucao" and "Devolução" in p.motivo and p.data_solicitante == D and p.data_outro == d2
    assert pp.devolucoes_em_aberto(c, res, {"A"}, hoje=D)[0]["estado"] == "em_andamento"
    pp.aprovar(c, "u1", p.id, AGORA)
    r2 = gerar(c, d2)
    a = r2.dia(d2, "A").efetivos[0]
    assert (a.militar_id, a.sigla) == ("m1", "SVÇ (T)") and "devolução" in a.obs
    assert colega not in [x.militar_id for x in r2.dia(d2, "A").efetivos]    # o colega foi dispensado
    assert len([t for t in c.trocas if t.papeleta_id == p.id]) == 1          # troca de sentido único
    pp.assinar(c, p.id, M1, PIN, AGORA)
    pp.registrar_assinatura_externa(c, "u1", p.id, colega, "papel 12", AGORA)
    pp.confirmar(c, "u1", p.id, AGORA)
    assert pp.devolucoes_em_aberto(c, res, {"A"}, hoje=D) == []             # quitada


def test_devolucao_cancelada_ou_rejeitada_reabre():
    c, res = com_falta()
    d2, colega = sugerir_devolucao(c, res, res.devolucoes[0])[0]
    p = pp.criar_devolucao(c, M1, "A", "m1", D, colega, d2, "x", AGORA, PIN)
    pp.rejeitar(c, "u1", p.id, "não", AGORA)
    assert pp.devolucoes_em_aberto(c, res, {"A"}, hoje=D)[0]["estado"] == "aberta"


def test_devolucao_valida_prazo_dia_e_colega():
    c, res = com_falta()
    dev = res.devolucoes[0]
    d2, colega = sugerir_devolucao(c, res, dev)[0]
    with pytest.raises(ValueError, match="prazo"):
        pp.criar_devolucao(c, M1, "A", "m1", D, colega, dev.prazo + timedelta(days=1), "", AGORA, PIN)
    with pytest.raises(ValueError, match="posterior"):
        pp.criar_devolucao(c, M1, "A", "m1", D, colega, D, "", AGORA, PIN)
    with pytest.raises(ValueError, match="não há serviço a devolver"):
        pp.criar_devolucao(c, M5, "A", "m5", D, "m6", d2, "", AGORA, PIN)   # m5 não deve nada
    with pytest.raises(ValueError, match="não está escalado como efetivo"):
        pp.criar_devolucao(c, M1, "A", "m1", D, next(m for m in ("m6", "m7", "m8") if m != colega), d2, "", AGORA, PIN)
    with pytest.raises(PermissaoNegada):
        pp.criar_devolucao(c, M3, "A", "m1", D, colega, d2, "", AGORA, PIN)  # militar só devolve o seu
    with pytest.raises(PermissaoNegada, match="PIN"):
        pp.criar_devolucao(c, M1, "A", "m1", D, colega, d2, "", AGORA, "0000")


def test_devolucao_trava_as_partes_e_nao_duplica():
    c, res = com_falta()
    d2, colega = sugerir_devolucao(c, res, res.devolucoes[0])[0]
    p = pp.criar_devolucao(c, M1, "A", "m1", D, colega, d2, "", AGORA, PIN)
    assert {"m1", colega} <= set(pp.militares_em_pedido_ativo(c))
    with pytest.raises(ValueError, match="em andamento|já tem a papeleta"):
        pp.criar_devolucao(c, "u1", "A", "m1", D, colega, d2, "", AGORA, "1234")


def test_persistencia_do_tipo_e_das_notificacoes():
    from sisescala.persistencia import de_tabelas, para_tabelas
    c, res = com_falta()
    d2, colega = sugerir_devolucao(c, res, res.devolucoes[0])[0]
    pp.criar_devolucao(c, M1, "A", "m1", D, colega, d2, "", AGORA, PIN)
    c2 = de_tabelas(para_tabelas(c))
    assert c2.papeletas == c.papeletas and c2.papeletas[0].tipo == "devolucao"
    assert c2.notificacoes == c.notificacoes and c2.notificacoes


def test_sugestao_de_devolucao_inclui_descanso_curto_so_se_pedido():
    c = mk()
    ms = c.militares[:4]                                   # fila apertada: 4 militares, 1 por dia
    c.escala("A").membros = [Pertinencia(m.id) for m in ms]
    c.ocorrencias.append(Ocorrencia(D, "A", "m1", "x"))
    res = gerar(c, D + timedelta(days=40))
    dev = res.devolucoes[0]
    assert sugerir_devolucao(c, res, dev) == []                         # estrito: não há dia com 2 folgas
    flex = sugerir_devolucao(c, res, dev, exigir_descanso=False)
    assert flex                                                          # flexível: oferece, com aviso na tela
    d2, colega = flex[0]
    p = pp.criar_devolucao(c, M1, "A", "m1", D, colega, d2, "", AGORA, PIN)  # o aviso não bloqueia
    assert pp.aprovar(c, "u1", p.id, AGORA)                                  # retorna o aviso de descanso curto

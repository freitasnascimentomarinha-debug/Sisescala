"""O auxiliar do detalhista também aprova (papeletas e vínculos), mas ninguém decide a própria troca."""
from datetime import date, datetime, timedelta

import pytest

from helpers import cad_ativo
from sisescala import auth
from sisescala import papeletas as pp
from sisescala import vinculos as vc
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.permissoes import PermissaoNegada, compartilhar, eh_detalhista, pode_decidir, pode_editar

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 0)
SENHA, PIN = "senha-forte-1", "1234"
CONTATO = dict(email="a@b.com", ramal="2345", celular="21987654321")


def mk():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"{i}.000") for i in range(1, 9)]
    # m1 = detalhista (fora da escala); m2 = auxiliar (concorre normalmente)
    e = Escala("A", "Portaria", dono_id="u1", detalhista_id="m1", auxiliares=["m2"],
               membros=[Pertinencia(m.id) for m in ms])
    c = Contexto(ms, [e], D)
    auth.criar_usuario(c, None, "det", "Detalhista", SENHA, admin=True)                       # u1 detalhista (dono)
    for i in (2, 3, 4, 5):                                                                    # u2..u5 = m2..m5
        auth.criar_usuario(c, "u1", f"mil{i}", f"Mil {i}", SENHA, perfil="militar", militar_id=f"m{i}", **CONTATO)
    for u in c.usuarios:
        u.pin_hash = auth.hash_pin(PIN)
    return c


AUX, M3, M4, M5 = "u2", "u3", "u4", "u5"


def pedir(c, uid, x, dx, y, dy):
    return pp.criar(c, uid, "A", x, D + timedelta(days=dx), y, D + timedelta(days=dy), "motivo", AGORA, pin=PIN)


# Com o detalhista fora, a ordem é m2(D), m3(D+1), m4(D+2), m5(D+3), m6(D+4), m7(D+5), m8(D+6), m2(D+7)...


def test_auxiliar_decide_papeletas_dos_outros_sem_ser_detalhista_nem_editor():
    c = mk()
    esc = c.escala("A")
    assert c.usuario(AUX).perfil == "militar" and not eh_detalhista(c, AUX, esc) and not pode_editar(c, AUX, esc)
    assert pode_decidir(c, AUX, esc)
    p = pedir(c, M3, "m3", 1, "m5", 3)
    assert [x.id for x in pp.pedidos_pendentes(c, AUX)] == [p.id]                     # recebe o pedido
    assert [x.id for x in pp.papeletas_visiveis(c, AUX, "A")] == [p.id]               # vê as papeletas da escala
    pp.aprovar(c, AUX, p.id, AGORA)
    assert p.status == "aprovada" and p.decidido_por == AUX
    pp.assinar(c, p.id, M3, PIN, AGORA); pp.assinar(c, p.id, M5, PIN, AGORA)
    pp.confirmar(c, AUX, p.id, AGORA)
    assert p.status == "confirmada"


def test_auxiliar_rejeita_e_cancela_depois_de_aprovar_pedidos_dos_outros():
    c = mk()
    p = pedir(c, M3, "m3", 1, "m5", 3)
    pp.rejeitar(c, AUX, p.id, "efetivo insuficiente", AGORA)
    assert p.status == "rejeitada"
    p2 = pedir(c, M3, "m3", 1, "m5", 3)
    pp.aprovar(c, AUX, p2.id, AGORA)
    pp.cancelar(c, AUX, p2.id, "não assinaram", AGORA)
    assert p2.status == "cancelada" and c.trocas == []


def test_auxiliar_nao_decide_a_propria_troca():
    c = mk()
    p = pedir(c, AUX, "m2", 0, "m4", 2)                                               # o auxiliar pede a própria troca
    assert pp.pedidos_pendentes(c, AUX) == []                                         # não conta como "aguardando a sua decisão"
    for acao in (lambda: pp.aprovar(c, AUX, p.id, AGORA), lambda: pp.rejeitar(c, AUX, p.id, "x", AGORA)):
        with pytest.raises(PermissaoNegada, match="própria troca"):
            acao()
    assert p.status == "pendente"
    pp.aprovar(c, "u1", p.id, AGORA)                                                  # o detalhista decide
    with pytest.raises(PermissaoNegada, match="própria troca"):
        pp.registrar_assinatura_externa(c, AUX, p.id, "m2", "papel", AGORA)           # nem valida a própria assinatura
    with pytest.raises(PermissaoNegada, match="própria troca"):
        pp.cancelar(c, AUX, p.id, "", AGORA)                                          # nem desfaz depois de aprovada
    pp.assinar(c, p.id, AUX, PIN, AGORA)                                              # mas assina como parte


def test_auxiliar_que_e_a_outra_parte_tambem_nao_decide():
    c = mk()
    p = pedir(c, M4, "m4", 2, "m2", 7)                                                # o auxiliar é "troca com"
    with pytest.raises(PermissaoNegada, match="própria troca"):
        pp.aprovar(c, AUX, p.id, AGORA)
    assert pp.pedidos_pendentes(c, AUX) == []


def test_parte_pode_cancelar_o_proprio_pedido_pendente_mesmo_sendo_auxiliar():
    c = mk()
    p = pedir(c, AUX, "m2", 0, "m4", 2)
    pp.cancelar(c, AUX, p.id, "desisti", AGORA)
    assert p.status == "cancelada"


def test_detalhista_que_concorre_tambem_nao_decide_a_propria_troca():
    c = mk()
    c.escala("A").detalhista_escalavel = True                                         # raro: m1 concorre
    c.usuario("u1").militar_id = "m1"
    p = pp.criar(c, "u1", "A", "m1", D, "m3", D + timedelta(days=2), "motivo", AGORA, pin=PIN)
    with pytest.raises(PermissaoNegada, match="própria troca"):
        pp.aprovar(c, "u1", p.id, AGORA)
    pp.aprovar(c, AUX, p.id, AGORA)                                                   # o auxiliar decide por ele
    assert p.status == "aprovada"


def test_outro_militar_nao_decide_e_auxiliar_so_decide_na_propria_escala():
    c = mk()
    p = pedir(c, M3, "m3", 1, "m5", 3)
    with pytest.raises(PermissaoNegada, match="detalhista e o auxiliar"):
        pp.aprovar(c, M4, p.id, AGORA)
    assert pp.pedidos_pendentes(c, M4) == [] and pp.papeletas_visiveis(c, M4, "A") == []
    c.escalas.append(Escala("B", "Outra", dono_id="u1", detalhista_id="m1", auxiliares=["m6"],
                            membros=[Pertinencia(f"m{i}") for i in range(1, 9)]))
    assert not pode_decidir(c, AUX, c.escala("B"))                                    # m2 é auxiliar só da escala A


def test_auxiliar_nao_pede_troca_pelos_outros():
    c = mk()
    with pytest.raises(PermissaoNegada, match="próprio serviço"):
        pedir(c, AUX, "m3", 1, "m5", 3)


def test_auxiliar_recebe_os_avisos_de_decisao_mas_nao_dos_pedidos_dele():
    c = mk()
    pedir(c, M3, "m3", 1, "m5", 3)
    assert any(n.usuario_id == AUX and "Aguardando a sua decisão" in n.texto for n in c.notificacoes)
    c2 = mk()
    pedir(c2, AUX, "m2", 0, "m4", 2)
    assert not any(n.usuario_id == AUX and "Aguardando a sua decisão" in n.texto for n in c2.notificacoes)


def test_auxiliar_decide_vinculos_mas_nao_o_proprio():
    c = mk()
    nova = cad_ativo(c, "nova", "Nova", SENHA)
    compartilhar(c, "u1", "A", nova.id, "leitura")
    v = vc.solicitar(c, nova.id, "A", "m6", "6.000", PIN, AGORA)
    assert [x.id for x in vc.pendentes_para(c, AUX)] == [v.id]
    vc.aprovar(c, AUX, v.id, AGORA)
    assert c.usuario(nova.id).militar_id == "m6"
    # o auxiliar não decide um vínculo pedido pela própria conta
    c2 = mk()
    c2.usuario(AUX).militar_id = ""                                                   # cenário artificial: auxiliar sem vínculo
    c2.escala("A").auxiliares = ["m6"]
    v2 = Vinculo("v9", AUX, "m7", "A", AGORA, auth.hash_pin(PIN))
    c2.vinculos.append(v2)
    with pytest.raises(PermissaoNegada):
        vc.aprovar(c2, AUX, v2.id, AGORA)


def test_conta_de_militar_comum_nao_ve_pedidos_de_vinculo():
    c = mk()
    nova = cad_ativo(c, "nova", "Nova", SENHA)
    compartilhar(c, "u1", "A", nova.id, "leitura")
    vc.solicitar(c, nova.id, "A", "m6", "6.000", PIN, AGORA)
    assert vc.pendentes_para(c, M3) == []
    with pytest.raises(PermissaoNegada):
        vc.aprovar(c, M3, "v1", AGORA)

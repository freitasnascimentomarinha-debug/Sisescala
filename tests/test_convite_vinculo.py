"""O detalhista pesquisa usuários e convida para o vínculo; o usuário aceita com NIP e PIN (ou o usuário pede)."""
from datetime import date, datetime

import pytest

from sisescala import auth, gestao
from sisescala import vinculos as vc
from sisescala.modelos import *
from sisescala.permissoes import PermissaoNegada
from sisescala.persistencia import de_tabelas, para_tabelas

SENHA = "senha-forte-1"
AGORA = datetime(2027, 2, 27, 9, 0)


def mundo():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"1000000{i}") for i in range(1, 6)]
    c = Contexto(ms, [], date(2027, 3, 1))
    adm, _ = auth.garantir_admin(c, "admin", SENHA)
    det = auth.criar_usuario(c, adm.id, "20000001", "Detalhista", SENHA)
    gestao.criar_escala(c, det.id, Escala("e1", "Um", om="CAAML", data_base=c.data_base,
                                           membros=[Pertinencia(f"m{i}") for i in range(1, 5)]))
    ana = auth.criar_usuario(c, adm.id, "10000002", "Ana Souza", SENHA, om="COPAB", email="ana@x.com",
                             ramal="2345", celular="21988887777")
    return c, det, ana


def test_busca_so_mostra_quem_pode_ser_convidado_e_exige_3_letras():
    c, det, ana = mundo()
    assert vc.buscar_usuarios(c, det.id, "e1", "an") == []                      # termo curto: nada
    assert [u.id for u in vc.buscar_usuarios(c, det.id, "e1", "ana")] == [ana.id]
    assert [u.id for u in vc.buscar_usuarios(c, det.id, "e1", "10000002")] == [ana.id]   # por NIP
    assert [u.id for u in vc.buscar_usuarios(c, det.id, "e1", "copab")] == [ana.id]      # por OM
    assert det.id not in [u.id for u in vc.buscar_usuarios(c, det.id, "e1", "detalh")]    # nunca ele mesmo
    with pytest.raises(PermissaoNegada):
        vc.buscar_usuarios(c, ana.id, "e1", "ana")                                # só quem decide a escala


def test_convite_aceito_vincula_completa_contato_e_avisa():
    c, det, ana = mundo()
    cv = vc.convidar(c, det.id, ana.id, "m2", "e1", AGORA)
    assert ana.militar_id == "" and vc.convites_do_usuario(c, ana.id) == [cv]      # convidar não vincula
    assert any(n.usuario_id == ana.id for n in c.notificacoes)
    assert vc.buscar_usuarios(c, det.id, "e1", "ana") == []                          # já tem convite pendente
    assert "m2" not in vc.militares_livres(c, "e1")
    with pytest.raises(ValueError, match="NIP não confere"):
        vc.aceitar_convite(c, ana.id, cv.id, "99999999", "1234")
    with pytest.raises(ValueError):
        vc.aceitar_convite(c, ana.id, cv.id, "10000002", "12")                     # PIN inválido
    with pytest.raises(PermissaoNegada):
        vc.aceitar_convite(c, det.id, cv.id, "10000002", "1234")                   # só o convidado aceita
    vc.aceitar_convite(c, ana.id, cv.id, "10000002", "1234", AGORA)
    assert ana.militar_id == "m2" and ana.pin_hash and "1234" not in ana.pin_hash
    assert c.militar("m2").email == "ana@x.com" and c.militar("m2").celular            # contato completa o cadastro
    assert cv.status == "aceito" and any(n.usuario_id == det.id and "aceitou" in n.texto for n in c.notificacoes)
    assert auth.confirmar_assinatura(c, ana.id, "1234")


def test_recusar_e_cancelar_convite_liberam_o_militar():
    c, det, ana = mundo()
    cv = vc.convidar(c, det.id, ana.id, "m2", "e1")
    vc.recusar_convite(c, ana.id, cv.id)
    assert cv.status == "recusado" and ana.militar_id == "" and "m2" in vc.militares_livres(c, "e1")
    cv2 = vc.convidar(c, det.id, ana.id, "m3", "e1")
    with pytest.raises(PermissaoNegada):
        vc.cancelar_convite(c, ana.id, cv2.id)                                         # quem recebe só recusa
    vc.cancelar_convite(c, det.id, cv2.id)
    assert cv2.status == "cancelado"


def test_regras_do_convite():
    c, det, ana = mundo()
    outro = auth.criar_usuario(c, "u1", "10000003", "Outro", SENHA)
    with pytest.raises(PermissaoNegada):
        vc.convidar(c, ana.id, outro.id, "m2", "e1")                                 # não decide a escala
    with pytest.raises(ValueError, match="não está disponível"):
        vc.convidar(c, det.id, ana.id, "m5", "e1")                                   # m5 não está na escala
    vc.convidar(c, det.id, ana.id, "m2", "e1")
    with pytest.raises(ValueError, match="já tem um convite"):
        vc.convidar(c, det.id, ana.id, "m3", "e1")
    with pytest.raises(ValueError, match="não está disponível"):
        vc.convidar(c, det.id, outro.id, "m2", "e1")                                 # m2 reservado ao convite


def test_usuario_continua_podendo_pedir_o_vinculo_e_o_pedido_some_ao_aceitar_convite():
    c, det, ana = mundo()
    esc = c.escala("e1")
    esc.compartilhado_com[ana.id] = "leitura"
    v = vc.solicitar(c, ana.id, "e1", "m3", "10000003", "1234", AGORA)             # o usuário pede (fluxo antigo)
    cv = vc.convidar(c, det.id, ana.id, "m2", "e1", AGORA)
    vc.aceitar_convite(c, ana.id, cv.id, "10000002", "4321", AGORA)
    assert ana.militar_id == "m2" and v.status == "cancelado"
    assert vc.pendentes_para(c, det.id) == []


def test_convites_persistem_e_somem_com_a_conta_excluida():
    c, det, ana = mundo()
    vc.convidar(c, det.id, ana.id, "m2", "e1", AGORA)
    c2 = de_tabelas(para_tabelas(c))
    assert [(x.usuario_id, x.militar_id, x.status) for x in c2.convites_vinculo] == [(ana.id, "m2", "pendente")]
    auth.excluir_usuario(c, "u1", ana.id)
    assert c.convites_vinculo == []

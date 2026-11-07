"""Vários auxiliares (concorrendo ou não); o criador vira o detalhista; entrega do detalhe a outra pessoa."""
from datetime import date, datetime, timedelta

import pytest

from sisescala import auth, gestao, lancamentos as lc
from sisescala import papeletas as pp
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.permissoes import PermissaoNegada, eh_detalhista, nivel, pode_decidir, pode_ver
from sisescala.persistencia import de_tabelas, para_tabelas

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 0)
SENHA, PIN = "senha-forte-1", "1234"
CONTATO = dict(email="a@b.com", ramal="2345", celular="21987654321")


def mk():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, 11)]
    c = Contexto(ms, [], D)
    auth.criar_usuario(c, None, "adm", "Administrador", SENHA, admin=True)                                   # u1 (admin)
    auth.criar_usuario(c, "u1", "det1", "Detalhista 1", SENHA, militar_id="m1")                              # u2 -> m1
    auth.criar_usuario(c, "u1", "det2", "Detalhista 2", SENHA, militar_id="m10")                             # u3 -> m10
    auth.criar_usuario(c, "u1", "sem", "Detalhista sem militar", SENHA)                                      # u4
    for i in (2, 3, 4, 5):                                                                                   # u5..u8 = m2..m5
        auth.criar_usuario(c, "u1", f"mil{i}", f"Mil {i}", SENHA, perfil="militar", militar_id=f"m{i}", **CONTATO)
    for u in c.usuarios:
        u.pin_hash = auth.hash_pin(PIN)
    return c


DET1, DET2, SEM, M2, M3, M4, M5 = "u2", "u3", "u4", "u5", "u6", "u7", "u8"


def escala(c, **kw):
    e = Escala("e1", "Portaria", membros=[Pertinencia(f"m{i}") for i in range(2, 10)], **kw)
    return gestao.criar_escala(c, DET1, e)


def efetivos(res, dias=14):
    return {a.militar_id for i in range(dias) for a in res.dia(D + timedelta(days=i), "e1").efetivos}


# ---------------------------------------------------------------- o criador vira o detalhista
def test_criador_vira_o_detalhista_automaticamente_e_fica_fora_da_escala():
    c = mk()
    e = escala(c)
    assert e.dono_id == DET1 and e.detalhista_id == "m1" and eh_detalhista(c, DET1, e)
    assert not e.detalhista_escalavel
    c.escala("e1").membros.append(Pertinencia("m1"))                       # mesmo se constar como membro, não é escalado
    assert "m1" not in efetivos(gerar(c, D + timedelta(days=14)))


def test_criador_sem_militar_ligado_nao_tem_quem_dispensar_mas_continua_sendo_o_detalhista():
    c = mk()
    e = gestao.criar_escala(c, SEM, Escala("e2", "Outra", membros=[Pertinencia("m2"), Pertinencia("m3"), Pertinencia("m4")]))
    assert e.dono_id == SEM and e.detalhista_id == "" and eh_detalhista(c, SEM, e)


# ---------------------------------------------------------------- vários auxiliares
def test_varios_auxiliares_todos_decidem_e_lancam_so_nessa_escala():
    c = mk()
    escala(c)
    gestao.editar_escala(c, DET1, "e1", auxiliares=["m2", "m3"])
    for u in (M2, M3):
        assert pode_decidir(c, u, c.escala("e1")) and not eh_detalhista(c, u, c.escala("e1"))
    assert not pode_decidir(c, M4, c.escala("e1"))
    lc.lancar_impedimento(c, M2, Impedimento("m5", "dispensa_justificada", D, D + timedelta(days=1), "Baixa"))
    lc.lancar_impedimento(c, M3, Impedimento("m4", "dispensa_justificada", D, D + timedelta(days=1), "Baixa"))
    with pytest.raises(PermissaoNegada, match="para si mesmo"):
        lc.lancar_impedimento(c, M3, Impedimento("m3", "dispensa_justificada", D, D, "x"))


def test_auxiliar_que_nao_concorre_na_escala_decide_e_lanca_e_a_enxerga():
    c = mk()
    escala(c)                                                              # membros m2..m9; m10 e m1 fora
    gestao.editar_escala(c, DET1, "e1", auxiliares=["m10"])                # m10 não é membro da escala
    esc = c.escala("e1")
    assert "m10" not in [p.militar_id for p in esc.membros]
    assert not any(p.militar_id == "m10" for p in esc.membros) and pode_decidir(c, DET2, esc)
    assert nivel(c, DET2, esc) == "leitura" and pode_ver(c, DET2, esc)     # enxerga a escala que auxilia
    assert "m10" not in efetivos(gerar(c, D + timedelta(days=14)))         # e não concorre
    p = pp.criar(c, M3, "e1", "m3", D + timedelta(days=1), "m5", D + timedelta(days=3), "motivo", AGORA, pin=PIN)
    assert [x.id for x in pp.pedidos_pendentes(c, DET2)] == [p.id]
    pp.aprovar(c, DET2, p.id, AGORA)
    lc.lancar_dispensa_no_dia(c, DET2, Ocorrencia(D + timedelta(days=4), "e1", "m6", "Falta justificada"))


def test_auxiliar_recebe_os_avisos_e_so_o_detalhista_designa_auxiliares():
    c = mk()
    escala(c)
    with pytest.raises(PermissaoNegada, match="só o detalhista"):
        gestao.editar_escala(c, M2, "e1", auxiliares=["m2"])               # o próprio auxiliar não se designa
    gestao.editar_escala(c, DET1, "e1", auxiliares=["m10", "m2"])
    pp.criar(c, M3, "e1", "m3", D + timedelta(days=1), "m5", D + timedelta(days=3), "motivo", AGORA, pin=PIN)
    avisados = {n.usuario_id for n in c.notificacoes if "Aguardando a sua decisão" in n.texto}
    assert {DET1, DET2, M2} <= avisados


def test_auxiliar_repetido_ou_igual_ao_detalhista_e_recusado():
    c = mk()
    escala(c)
    with pytest.raises(ValueError, match="repetido"):
        gestao.editar_escala(c, DET1, "e1", auxiliares=["m2", "m2"])
    with pytest.raises(ValueError, match="próprio detalhista"):
        gestao.editar_escala(c, DET1, "e1", auxiliares=["m1"])


# ---------------------------------------------------------------- entrega do detalhe
def test_entregar_o_detalhe_exige_designar_outro_detalhista():
    c = mk()
    escala(c)
    for novo in ("inexistente", DET1, M2):                                  # inexistente, a mesma pessoa, conta de militar
        with pytest.raises(ValueError, match="OUTRO detalhista"):
            gestao.transferir_detalhe(c, DET1, "e1", novo, "nenhum")
    assert c.escala("e1").dono_id == DET1


def test_so_o_detalhista_atual_entrega():
    c = mk()
    escala(c)
    gestao.editar_escala(c, DET1, "e1", auxiliares=["m2"])
    for quem in (M2, M3, DET2):
        with pytest.raises(PermissaoNegada, match="detalhista atual"):
            gestao.transferir_detalhe(c, quem, "e1", DET2, "nenhum")


def test_entrega_e_ex_detalhista_vira_militar_escalado():
    c = mk()
    escala(c)
    gestao.transferir_detalhe(c, DET1, "e1", DET2, "escalado")
    e = c.escala("e1")
    assert e.dono_id == DET2 and e.detalhista_id == "m10" and not e.detalhista_escalavel
    assert eh_detalhista(c, DET2, e) and not eh_detalhista(c, DET1, e)
    assert any(p.militar_id == "m1" for p in e.membros)                     # agora é membro e concorre
    r = gerar(c, D + timedelta(days=14))
    assert "m1" in efetivos(r) and "m10" not in efetivos(r)                  # o novo detalhista é que fica fora
    with pytest.raises(PermissaoNegada, match="só o detalhista"):
        gestao.editar_escala(c, DET1, "e1", folgas_minimas=1)                # e o antigo não edita mais as regras
    assert pode_ver(c, DET1, e)                                              # mas vê a escala


def test_entrega_e_ex_detalhista_vira_auxiliar_sem_concorrer_ou_concorrendo():
    c = mk()
    escala(c)
    c.escala("e1").membros.append(Pertinencia("m1"))
    gestao.transferir_detalhe(c, DET1, "e1", DET2, "auxiliar")
    e = c.escala("e1")
    assert "m1" in e.auxiliares and not any(p.militar_id == "m1" for p in e.membros)
    assert pode_decidir(c, DET1, e) and not eh_detalhista(c, DET1, e)         # decide, mas não edita regras
    assert "m1" not in efetivos(gerar(c, D + timedelta(days=14)))
    c2 = mk()
    escala(c2)
    gestao.transferir_detalhe(c2, DET1, "e1", DET2, "auxiliar", concorre=True)
    assert "m1" in c2.escala("e1").auxiliares and "m1" in efetivos(gerar(c2, D + timedelta(days=14)))


def test_entrega_e_ex_detalhista_deixa_de_ter_qualquer_papel():
    c = mk()
    escala(c)
    c.escala("e1").membros.append(Pertinencia("m1"))
    gestao.editar_escala(c, DET1, "e1", auxiliares=["m2"])
    compartilhar_leitura = c.escala("e1").compartilhado_com
    gestao.transferir_detalhe(c, DET1, "e1", DET2, "nenhum")
    e = c.escala("e1")
    assert "m1" not in e.auxiliares and not any(p.militar_id == "m1" for p in e.membros)
    assert DET1 not in e.compartilhado_com and not pode_ver(c, DET1, e) and not pode_decidir(c, DET1, e)
    assert e.auxiliares == ["m2"]                                            # os demais auxiliares ficam


def test_novo_detalhista_que_era_auxiliar_deixa_de_ser_auxiliar():
    c = mk()
    escala(c)
    gestao.editar_escala(c, DET1, "e1", auxiliares=["m10", "m2"])
    gestao.transferir_detalhe(c, DET1, "e1", DET2, "nenhum")                 # DET2 (m10) vira o detalhista
    assert c.escala("e1").auxiliares == ["m2"] and c.escala("e1").detalhista_id == "m10"


def test_ex_detalhista_sem_militar_precisa_indicar_o_dele_para_continuar():
    c = mk()
    gestao.criar_escala(c, SEM, Escala("e2", "Outra", membros=[Pertinencia(f"m{i}") for i in range(2, 8)]))
    with pytest.raises(ValueError, match="indique o seu militar"):
        gestao.transferir_detalhe(c, SEM, "e2", DET2, "escalado")
    gestao.transferir_detalhe(c, SEM, "e2", DET2, "escalado", militar_anterior="m9")
    e = c.escala("e2")
    assert any(p.militar_id == "m9" for p in e.membros) and e.dono_id == DET2
    assert e.compartilhado_com[SEM] == "leitura"                              # continua vendo a escala
    gestao.transferir_detalhe(c, DET2, "e2", SEM, "nenhum")                   # e sair sem papel não exige militar
    assert c.escala("e2").dono_id == SEM


def test_entrega_notifica_os_dois():
    c = mk()
    escala(c)
    gestao.transferir_detalhe(c, DET1, "e1", DET2, "nenhum")
    textos = {n.usuario_id: n.texto for n in c.notificacoes}
    assert "agora é o detalhista" in textos[DET2] and "Você entregou o detalhe" in textos[DET1]


# ---------------------------------------------------------------- ligar a conta do detalhista ao militar (administrador)
def test_so_o_administrador_liga_conta_de_detalhista_a_militar():
    c = mk()
    auth.definir_militar_do_detalhista(c, "u1", SEM, "m9")
    assert c.usuario(SEM).militar_id == "m9"
    with pytest.raises(PermissionError):
        auth.definir_militar_do_detalhista(c, DET1, SEM, "m8")
    with pytest.raises(ValueError, match="só conta de detalhista"):
        auth.definir_militar_do_detalhista(c, "u1", M2, "m8")                 # conta de militar: só pelo vínculo
    with pytest.raises(ValueError, match="já está ligado"):
        auth.definir_militar_do_detalhista(c, "u1", SEM, "m1")
    auth.definir_militar_do_detalhista(c, "u1", SEM, "")
    assert c.usuario(SEM).militar_id == ""


# ---------------------------------------------------------------- persistência
def test_auxiliares_persistem_e_planilha_antiga_com_auxiliar_unico_migra():
    c = mk()
    escala(c)
    gestao.editar_escala(c, DET1, "e1", auxiliares=["m10", "m2"])
    assert de_tabelas(para_tabelas(c)).escala("e1").auxiliares == ["m10", "m2"]
    T = para_tabelas(c)
    T = {k: [list(r) for r in v] for k, v in T.items()}
    T["EscalaAuxiliares"] = [T["EscalaAuxiliares"][0]]                        # sem a tabela nova...
    T["Escalas"][0].append("auxiliar_id")                                     # ...e com o campo antigo
    for r in T["Escalas"][1:]:
        r.append("m4")
    assert de_tabelas(T).escala("e1").auxiliares == ["m4"]

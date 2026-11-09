"""Usuário comum cria/importa escala, busca e pede acesso; admin automático aprova e gerencia contas; NIP e OM."""
from datetime import date, datetime, timedelta

import pytest

from sisescala import acessos as ac
from sisescala import auth, gestao, lancamentos as lc
from sisescala import importacao as imp
from sisescala.calendario import dia_util
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.permissoes import PermissaoNegada, eh_detalhista, pode_ver

D = date(2027, 3, 1)
SENHA = "senha-forte-1"
AGORA = datetime(2027, 2, 27, 9, 0)


def mundo():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"1000000{i}") for i in range(1, 7)]
    c = Contexto(ms, [], D)
    adm, senha = auth.garantir_admin(c, "admin", SENHA)
    return c, adm


def aprovado(c, adm, nip, nome="Fulano", om="CAAML"):
    u = auth.cadastrar_se(c, nip, nome, SENHA, "a@b.com", "2345", "21987654321", om=om)
    auth.aprovar_usuario(c, adm.id, u.id)
    return u


def nova_escala(c, uid, eid="e1", nome="Portaria", n=4, **kw):
    mem = [Pertinencia(f"m{i}") for i in range(1, n + 1)]
    return gestao.criar_escala(c, uid, Escala(eid, nome, om="CAAML", membros=mem, data_base=D, **kw))


# ---------------------------------------------------------------- admin automático
def test_admin_automatico_com_senha_configurada_ou_provisoria():
    c = Contexto([], [], D)
    adm, gerada = auth.garantir_admin(c, "admin", SENHA)
    assert adm.admin and gerada is None and not adm.trocar_senha
    assert auth.garantir_admin(c, "admin", SENHA) == (None, None) or len([u for u in c.usuarios if u.admin]) == 1
    c2 = Contexto([], [], D)
    adm2, gerada2 = auth.garantir_admin(c2)
    assert gerada2 and len(gerada2) >= 12 and adm2.trocar_senha
    assert auth.entrar(c2, "admin", gerada2).id == adm2.id
    auth.trocar_senha(c2, adm2.id, gerada2, "outra-senha-99")
    assert not adm2.trocar_senha
    with pytest.raises(ValueError):
        auth.trocar_senha(c2, adm2.id, "outra-senha-99", "outra-senha-99")


# ---------------------------------------------------------------- cadastro, NIP e login
def test_login_por_nip_com_pontuacao_e_mensagens():
    c, adm = mundo()
    u = auth.cadastrar_se(c, "12.3456.78", "Fulano", SENHA, "a@b.com", "2345", "21987654321", om="CAAML")
    with pytest.raises(auth.AutenticacaoErro, match="aprova"):
        auth.entrar(c, "12345678", SENHA)
    with pytest.raises(auth.AutenticacaoErro, match="NIP ou senha incorretos"):
        auth.entrar(c, "12345678", "errada-errada")
    auth.rejeitar_usuario(c, adm.id, u.id)
    with pytest.raises(auth.AutenticacaoErro, match="não foi aprovado"):
        auth.entrar(c, "12345678", SENHA)


def test_admin_bloqueia_desbloqueia_edita_e_exclui():
    c, adm = mundo()
    u = aprovado(c, adm, "12345678")
    outro = aprovado(c, adm, "87654321", "Outro")
    for f in (auth.bloquear_usuario, auth.aprovar_usuario):
        with pytest.raises(PermissionError):
            f(c, u.id, outro.id)                                   # usuário comum não administra
    auth.bloquear_usuario(c, adm.id, u.id)
    with pytest.raises(auth.AutenticacaoErro, match="bloquead"):
        auth.entrar(c, "12345678", SENHA)
    auth.desbloquear_usuario(c, adm.id, u.id)
    assert auth.entrar(c, "12345678", SENHA).id == u.id
    auth.editar_usuario(c, adm.id, u.id, nome="Novo Nome", om="COPAB", nip="11223344")
    assert (u.nome, u.om, u.login) == ("Novo Nome", "COPAB", "11223344")
    with pytest.raises(ValueError):
        auth.editar_usuario(c, adm.id, u.id, nip="87654321")      # NIP de outro
    with pytest.raises(ValueError):
        auth.bloquear_usuario(c, adm.id, adm.id)                  # nem a si mesmo
    auth.redefinir_senha(c, adm.id, u.id, "provisoria-123")
    assert auth.entrar(c, "11223344", "provisoria-123").trocar_senha
    auth.excluir_usuario(c, adm.id, outro.id)
    assert c.usuario(outro.id) is None
    with pytest.raises(ValueError):
        auth.excluir_usuario(c, adm.id, adm.id)


def test_excluir_conta_dona_de_escala_exige_reatribuir():
    c, adm = mundo()
    u, v = aprovado(c, adm, "12345678"), aprovado(c, adm, "87654321", "Outro")
    nova_escala(c, u.id)
    with pytest.raises(ValueError):
        auth.excluir_usuario(c, adm.id, u.id)
    assert auth.reatribuir_escalas(c, adm.id, u.id, v.id) == 1
    auth.excluir_usuario(c, adm.id, u.id)
    assert c.escala("e1").dono_id == v.id


# ---------------------------------------------------------------- criar escala e virar detalhista
def test_usuario_comum_cria_escala_e_vira_o_detalhista_dela():
    c, adm = mundo()
    u = aprovado(c, adm, "10000001")
    e = nova_escala(c, u.id, n=4)
    assert e.dono_id == u.id and eh_detalhista(c, u.id, e)
    assert e.detalhista_id == "m1"                           # o militar do NIP fica dispensado
    outro = aprovado(c, adm, "87654321", "Outro")
    assert not eh_detalhista(c, outro.id, e) and not pode_ver(c, outro.id, e)
    with pytest.raises(PermissaoNegada):
        gestao.editar_escala(c, outro.id, "e1", nome="X")


# ---------------------------------------------------------------- buscar e pedir acesso
def test_busca_pedido_aprovacao_e_rejeicao():
    c, adm = mundo()
    det, req = aprovado(c, adm, "10000001"), aprovado(c, adm, "87654321", "Beltrano")
    nova_escala(c, det.id)
    assert [e.id for e in ac.buscar(c, req.id, "portaria")] == ["e1"]
    assert [e.id for e in ac.buscar(c, req.id, "caaml")] == ["e1"]
    assert ac.buscar(c, req.id, "inexistente") == [] and ac.buscar(c, det.id) == []   # a própria não aparece
    p = ac.pedir_acesso(c, req.id, "e1", "sou da OM", AGORA)
    with pytest.raises(ValueError):
        ac.pedir_acesso(c, req.id, "e1")                                   # já pendente
    assert [x.id for x in ac.pendentes_para(c, det.id)] == [p.id] and ac.pendentes_para(c, req.id) == []
    assert any(n.usuario_id == det.id for n in c.notificacoes)
    with pytest.raises(PermissaoNegada):
        ac.aprovar(c, req.id, p.id)                                         # só o detalhista decide
    ac.aprovar(c, det.id, p.id, AGORA)
    assert pode_ver(c, req.id, c.escala("e1")) and p.status == "aprovado"
    assert ac.buscar(c, req.id, "portaria") == []                           # agora já enxerga

    outro = aprovado(c, adm, "55555555", "Ciclano")
    p2 = ac.pedir_acesso(c, outro.id, "e1")
    with pytest.raises(ValueError, match="motivo"):
        ac.rejeitar(c, det.id, p2.id, " ")
    ac.rejeitar(c, det.id, p2.id, "não é da OM")
    assert p2.status == "rejeitado" and not pode_ver(c, outro.id, c.escala("e1"))
    ac.pedir_acesso(c, outro.id, "e1")                                      # pode pedir de novo


# ---------------------------------------------------------------- escopo por escala
def test_dia_especial_so_vale_na_escala_dele_e_global_so_admin():
    c, adm = mundo()
    u1, u2 = aprovado(c, adm, "10000001"), aprovado(c, adm, "10000002", "Dois")
    nova_escala(c, u1.id, "e1")
    nova_escala(c, u2.id, "e2", "Outra")
    d = D + timedelta(days=1)
    lc.lancar_dia_especial(c, u1.id, DiaEspecial(d, "sem_expediente", "x", "e1"))
    assert not dia_util(d, c, c.escala("e1")) and dia_util(d, c, c.escala("e2"))
    with pytest.raises(PermissaoNegada):
        lc.lancar_dia_especial(c, u1.id, DiaEspecial(d, "feriado", "x", "e2"))
    with pytest.raises(PermissaoNegada):
        lc.lancar_dia_especial(c, u1.id, DiaEspecial(d, "feriado", "x"))
    lc.lancar_dia_especial(c, adm.id, DiaEspecial(d, "feriado", "todos"))
    assert not dia_util(d, c, c.escala("e2"))


def test_data_base_por_escala_nao_atrapalha_outra():
    c, adm = mundo()
    u1, u2 = aprovado(c, adm, "10000001"), aprovado(c, adm, "10000002", "Dois")
    nova_escala(c, u1.id, "e1")
    e2 = nova_escala(c, u2.id, "e2", "Outra")
    e2.data_base = D + timedelta(days=10)
    r = gerar(c, D + timedelta(days=12))
    assert r.dia(D, "e1").efetivos and not r.dia(D, "e2").efetivos
    assert r.dia(D + timedelta(days=10), "e2").efetivos


def test_excluir_do_cadastro_so_o_admin_e_so_quem_esta_fora_de_escalas_sem_conta_e_sem_papeleta():
    from sisescala import cadastro as cd
    c, adm = mundo()
    u1 = aprovado(c, adm, "10000001")
    nova_escala(c, u1.id, "e1", n=4)                                        # m1..m4; m5 e m6 ficam sem escala
    with pytest.raises(PermissaoNegada, match="administrador"):
        cd.excluir_militares(c, ["m5"], u1.id)                              # detalhista não exclui do cadastro
    with pytest.raises(ValueError, match="ainda está em uma escala"):
        cd.excluir_militares(c, ["m1"], adm.id)                             # quem está em escala: primeiro retira
    gestao.remover_militares(c, u1.id, "e1", ["m1"])                        # retirar da escala NÃO apaga o militar
    assert c.militar("m1") and "m1" not in {p.militar_id for p in c.escala("e1").membros}
    ana = aprovado(c, adm, "10000005", "Ana")
    ana.militar_id = "m5"
    with pytest.raises(ValueError, match="vinculado a uma conta"):
        cd.excluir_militares(c, ["m5"], adm.id)                             # com conta vinculada: recusa
    ana.militar_id = ""
    assert cd.excluir_militares(c, ["m5", "m1"], adm.id) == 2               # fora de escalas, sem conta: admin pode
    assert {m.id for m in c.militares} == {"m2", "m3", "m4", "m6"}


def test_retirar_da_escala_nao_mexe_na_conta_vinculada_nem_em_outras_escalas():
    c, adm = mundo()
    u1, u2 = aprovado(c, adm, "10000001"), aprovado(c, adm, "10000002", "Dois")
    nova_escala(c, u1.id, "e1", n=4)
    gestao.criar_escala(c, u2.id, Escala("e2", "Outra", membros=[Pertinencia(m) for m in ("m3", "m4", "m5", "m6")], data_base=D))
    ana = aprovado(c, adm, "10000009", "Ana")
    ana.militar_id = "m3"
    c.escala("e1").ultimo_servico = {"corrida": "m3"}
    gestao.remover_militares(c, u1.id, "e1", ["m3"])
    assert ana.militar_id == "m3"                                           # a conta continua vinculada
    assert "m3" in {p.militar_id for p in c.escala("e2").membros}           # e a outra escala não muda
    assert c.escala("e1").ultimo_servico["corrida"] == "m2"                 # a fila segue de onde estava


def test_importacao_nao_sobrescreve_dados_de_escala_de_outro_detalhista():
    c, adm = mundo()
    u1, u2 = aprovado(c, adm, "10000001"), aprovado(c, adm, "10000002", "Dois")
    nova_escala(c, u1.id, "e1", n=4)
    c.militar("m2").om = "CAAML"
    linhas = [{"Nome de guerra": "Trocado", "NIP": "10000002", "OM": "XYZ", "Escala": "Portaria", "Ordem": "1"}]
    novo, rel = imp.importar(c, linhas, usuario_id=u2.id, dono_id=u2.id,
                             sobrescrever=False)
    assert novo.militar("m2").nome == "M2" and novo.militar("m2").om == "CAAML"   # só preenche vazios
    assert c.militar("m2").nome == "M2"                                      # original intacto


def test_admin_desvincula_conta_do_militar_e_ela_pode_ser_vinculada_de_novo():
    from sisescala import vinculos as vc
    c, adm = mundo()
    det = aprovado(c, adm, "10000001")
    nova_escala(c, det.id, "e1", n=4)
    ana = aprovado(c, adm, "10000002", "Ana")
    cv = vc.convidar(c, det.id, ana.id, "m2", "e1", AGORA)
    vc.aceitar_convite(c, ana.id, cv.id, "10000002", "1234", AGORA)
    assert ana.militar_id == "m2" and ana.pin_hash
    with pytest.raises(PermissionError):
        auth.desvincular_usuario(c, det.id, ana.id)                        # só o administrador
    auth.desvincular_usuario(c, adm.id, ana.id)
    assert ana.militar_id == "" and ana.pin_hash == "" and c.usuario(ana.id)      # conta continua
    assert c.militar("m2") and "m2" in {p.militar_id for p in c.escala("e1").membros}   # militar e escala intactos
    assert any(n.usuario_id == ana.id and "desfez o vínculo" in n.texto for n in c.notificacoes)
    with pytest.raises(ValueError, match="não está vinculada"):
        auth.desvincular_usuario(c, adm.id, ana.id)
    assert "m2" in vc.militares_livres(c, "e1")                              # liberado para novo vínculo
    vc.convidar(c, det.id, ana.id, "m2", "e1", AGORA)                        # e ela pode ser convidada de novo


def test_desvincular_libera_o_militar_para_o_admin_excluir_do_cadastro_solto():
    from sisescala import cadastro as cd
    c, adm = mundo()
    ana = aprovado(c, adm, "10000005", "Ana")
    ana.militar_id = "m5"                                                    # m5 está fora de escalas
    with pytest.raises(ValueError, match="vinculado a uma conta"):
        cd.excluir_militares(c, ["m5"], adm.id)
    auth.desvincular_usuario(c, adm.id, ana.id)
    assert cd.excluir_militares(c, ["m5"], adm.id) == 1


def test_senha_dos_segredos_vale_para_o_admin_mesmo_que_ele_ja_exista_e_esteja_bloqueado():
    from sisescala.persistencia import de_tabelas, para_tabelas
    c = Contexto([], [], D)
    adm, gerada = auth.garantir_admin(c)                               # primeira execução, ainda sem segredos
    for _ in range(5):                                                 # quem não sabe a senha provisória erra e bloqueia
        with pytest.raises(auth.AutenticacaoErro):
            auth.entrar(c, "admin", "11071989")
    with pytest.raises(auth.AutenticacaoErro, match="bloqueada"):
        auth.entrar(c, "admin", "11071989")
    # o dono configura [admin] nos segredos: a senha deles passa a valer e o bloqueio some
    assert auth.sincronizar_admin(c, "admin", "11071989-ok") is True
    assert auth.entrar(c, "admin", "11071989-ok").id == adm.id and not adm.trocar_senha
    assert auth.sincronizar_admin(c, "admin", "11071989-ok") is False        # mesma configuração: não mexe mais
    # a senha que o admin trocou depois não é desfeita enquanto os segredos não mudarem
    auth.trocar_senha(c, adm.id, "11071989-ok", "senha-nova-do-admin")
    assert auth.sincronizar_admin(c, "admin", "11071989-ok") is False
    assert auth.entrar(c, "admin", "senha-nova-do-admin")
    # recuperar acesso: mudou a senha nos segredos -> vale a nova
    assert auth.sincronizar_admin(c, "admin", "outra-senha-secreta") is True
    assert auth.entrar(c, "admin", "outra-senha-secreta") and c.admin_cfg_sig
    c2 = de_tabelas(para_tabelas(c))                                          # a assinatura persiste entre execuções
    assert c2.admin_cfg_sig == c.admin_cfg_sig and auth.sincronizar_admin(c2, "admin", "outra-senha-secreta") is False


def test_segredos_com_outro_nip_criam_ou_promovem_conta_admin():
    c, adm = mundo()
    comum = aprovado(c, adm, "12345678")
    assert auth.sincronizar_admin(c, "12.3456.78", "senha-segredos-1") is True      # NIP de uma conta comum: é promovida
    assert comum.admin and auth.entrar(c, "12345678", "senha-segredos-1").id == comum.id
    assert auth.sincronizar_admin(c, "99999999", "outra-senha-123") is True          # NIP novo: cria
    assert next(u for u in c.usuarios if u.login == "99999999").admin
    with pytest.raises(ValueError):
        auth.sincronizar_admin(c, "admin", "curta")                                  # senha fraca nos segredos

from datetime import date, datetime, timedelta

import pytest

from sisescala import auth, vinculos as vc
from sisescala import papeletas as pp
from sisescala.contatos import normalizar_contato
from sisescala.disponibilidade import abertas, alternar, podar
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.permissoes import PermissaoNegada, compartilhar, pode_ver
from sisescala.previa import html_previa, periodo
from sisescala.persistencia import MemoriaBackend, Repositorio, de_tabelas, para_tabelas

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 0)
SENHA = "senha-forte-1"
CONTATO = dict(email="fulano@marinha.mil.br", ramal="2345", celular="(21) 98765-4321")


def mk():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"{i}.000", om="COPAB") for i in range(1, 9)]
    e = Escala("A", "Diária", dono_id="u1", membros=[Pertinencia(m.id) for m in ms])
    c = Contexto(ms, [e], D)
    auth.criar_usuario(c, None, "det", "Detalhista", SENHA, admin=True)       # u1
    c.usuario("u1").pin_hash = auth.hash_pin("1234")
    return c


# ---------------------------------------------------------------- contato
def test_contato_valida_e_normaliza():
    assert normalizar_contato(" FULANO@Marinha.MIL.br ", "23-45", "21987654321") == (
        "fulano@marinha.mil.br", "2345", "(21) 98765-4321")
    assert normalizar_contato("a@b.com", "", "", obrigatorio=False)[0] == "a@b.com"
    for args, trecho in [(("x", "2345", "21987654321"), "e-mail"), (("a@b.com", "", "21987654321"), "ramal"),
                         (("a@b.com", "2345", ""), "celular"), (("a@b.com", "2345", "123"), "celular")]:
        with pytest.raises(ValueError, match=trecho):
            normalizar_contato(*args)


def test_autocadastro_exige_contato_e_pode_ser_fechado():
    c = mk()
    u = auth.cadastrar_se(c, "Joao.Silva", "João Silva", SENHA, **CONTATO)
    assert (u.perfil, u.militar_id, u.admin) == ("militar", "", False) and u.celular == "(21) 98765-4321"
    with pytest.raises(ValueError, match="ramal"):
        auth.cadastrar_se(c, "outro", "Outro", SENHA, "a@b.com", "", "21987654321")
    with pytest.raises(ValueError, match="já existe"):
        auth.cadastrar_se(c, "joao.silva", "X", SENHA, **CONTATO)
    c.cadastro_aberto = False
    with pytest.raises(PermissionError, match="fechado"):
        auth.cadastrar_se(c, "novo", "Novo", SENHA, **CONTATO)
    assert not pode_ver(c, u.id, c.escala("A"))              # conta recém-criada não vê nada


# ---------------------------------------------------------------- vínculo
def conta(c, login="mil1"):
    return auth.cadastrar_se(c, login, "Militar", SENHA, **CONTATO)


def test_vinculo_fluxo_completo_com_pin_e_aprovacao():
    c = mk()
    u = conta(c)
    with pytest.raises(PermissaoNegada, match="acesso"):
        vc.solicitar(c, u.id, "A", "m1", "1.000", "1234", AGORA)      # ainda sem acesso à escala
    compartilhar(c, "u1", "A", u.id, "leitura")
    assert pode_ver(c, u.id, c.escala("A"))
    with pytest.raises(ValueError, match="NIP"):
        vc.solicitar(c, u.id, "A", "m1", "9.999", "1234", AGORA)
    with pytest.raises(ValueError, match="PIN"):
        vc.solicitar(c, u.id, "A", "m1", "1.000", "12", AGORA)
    v = vc.solicitar(c, u.id, "A", "m1", "1.000", "1234", AGORA)
    assert v.status == "pendente" and "1234" not in v.pin_hash and u.militar_id == ""
    with pytest.raises(ValueError, match="já tem um pedido"):
        vc.solicitar(c, u.id, "A", "m2", "2.000", "1234", AGORA)
    assert "m1" not in vc.militares_livres(c, "A")                      # persona reservada
    assert [x.id for x in vc.pendentes_para(c, "u1")] == [v.id]
    with pytest.raises(PermissaoNegada):
        vc.aprovar(c, u.id, v.id, AGORA)                                # o próprio não aprova
    vc.aprovar(c, "u1", v.id, AGORA)
    assert u.militar_id == "m1" and u.pin_hash == v.pin_hash and v.status == "aprovado"
    assert c.militar("m1").email == CONTATO["email"]                    # contato completa o cadastro
    assert pp.militar_do_usuario(c, u.id) == "m1"
    assert "m1" not in vc.militares_livres(c, "A")


def test_vinculo_rejeitar_cancelar_e_conflitos():
    c = mk()
    u1, u2 = conta(c, "a1"), conta(c, "a2")
    for u in (u1, u2):
        compartilhar(c, "u1", "A", u.id, "leitura")
    v = vc.solicitar(c, u1.id, "A", "m1", "1.000", "1234", AGORA)
    with pytest.raises(ValueError, match="não está disponível"):
        vc.solicitar(c, u2.id, "A", "m1", "1.000", "4321", AGORA)       # mesma persona
    with pytest.raises(ValueError, match="motivo"):
        vc.rejeitar(c, "u1", v.id, " ")
    vc.rejeitar(c, "u1", v.id, "não é você", AGORA)
    assert v.status == "rejeitado" and "m1" in vc.militares_livres(c, "A")
    v2 = vc.solicitar(c, u2.id, "A", "m1", "1.000", "4321", AGORA)
    with pytest.raises(PermissaoNegada):
        vc.cancelar(c, u1.id, v2.id)                                    # só quem pediu cancela
    vc.cancelar(c, u2.id, v2.id)
    assert v2.status == "cancelado"
    with pytest.raises(ValueError):
        vc.aprovar(c, "u1", v2.id, AGORA)


def test_pin_assina_papeleta_e_bloqueia_apos_erros():
    c = mk()
    u = conta(c)
    compartilhar(c, "u1", "A", u.id, "leitura")
    vc.aprovar(c, "u1", vc.solicitar(c, u.id, "A", "m1", "1.000", "1234", AGORA).id, AGORA)
    p = pp.criar(c, u.id, "A", "m1", D, "m3", D + timedelta(days=2), "consulta", AGORA, pin="1234")
    pp.aprovar(c, "u1", p.id, AGORA)
    with pytest.raises(PermissaoNegada):
        pp.assinar(c, p.id, u.id, SENHA, AGORA)                        # com PIN definido, a senha não vale
    a = pp.assinar(c, p.id, u.id, "1234", AGORA)
    assert a.metodo == "conta"
    c2 = mk(); u2 = conta(c2); compartilhar(c2, "u1", "A", u2.id, "leitura")
    vc.aprovar(c2, "u1", vc.solicitar(c2, u2.id, "A", "m1", "1.000", "1234", AGORA).id, AGORA)
    p2 = pp.criar(c2, u2.id, "A", "m1", D, "m3", D + timedelta(days=2), "x", AGORA, pin="1234")
    pp.aprovar(c2, "u1", p2.id, AGORA)
    for _ in range(auth.MAX_TENTATIVAS):
        with pytest.raises(PermissaoNegada):
            pp.assinar(c2, p2.id, u2.id, "0000", AGORA)
    with pytest.raises(auth.AutenticacaoErro, match="bloqueada"):
        pp.assinar(c2, p2.id, u2.id, "1234", AGORA)                    # bloqueada mesmo com o PIN certo
    assert pp.assinar(c2, p2.id, u2.id, "1234", AGORA + timedelta(minutes=6))


def test_alterar_pin_exige_senha():
    c = mk(); u = conta(c)
    with pytest.raises(auth.AutenticacaoErro):
        auth.alterar_pin(c, u.id, "errada", "5678")
    auth.alterar_pin(c, u.id, SENHA, "5678")
    assert auth.confirmar_assinatura(c, u.id, "5678") and not auth.confirmar_assinatura(c, u.id, SENHA)


# ---------------------------------------------------------------- disponibilidade
def logado(c, mid="m1", login="mil"):
    u = auth.cadastrar_se(c, login, "Mil", SENHA, **CONTATO)
    compartilhar(c, "u1", "A", u.id, "leitura")
    vc.aprovar(c, "u1", vc.solicitar(c, u.id, "A", mid, f"{mid[1:]}.000", "1234", AGORA).id, AGORA)
    return u


def test_disponibilidade_abre_fecha_e_aparece_na_previa():
    c = mk(); u = logado(c)
    res = gerar(c, D + timedelta(days=10))
    assert alternar(c, u.id, "A", "m1", D, res, AGORA) is True
    ab = abertas(c, res, "A")
    assert list(ab) == [(D, "m1")]
    html = html_previa(c, res, periodo(D, 7), "A", ab)
    assert html.count('class="pisca"') == 2 and "aberto a troca de serviço" in html    # 1 na célula + 1 na legenda
    assert 'class="pisca"' not in html_previa(c, res, periodo(D, 7), "A")               # sem sinais, sem bolinha
    assert alternar(c, u.id, "A", "m1", D, res, AGORA) is False                         # alterna (fecha)
    assert abertas(c, res, "A") == {}


def test_disponibilidade_regras():
    c = mk(); u = logado(c)
    res = gerar(c, D + timedelta(days=10))
    with pytest.raises(ValueError, match="não está escalado"):
        alternar(c, u.id, "A", "m1", D + timedelta(days=1), res, AGORA)      # dia de outro militar
    with pytest.raises(ValueError, match="antecedência"):
        alternar(c, u.id, "A", "m1", D, res, datetime(2027, 2, 28, 20, 0))   # 4h antes
    with pytest.raises(PermissaoNegada):
        alternar(c, u.id, "A", "m3", D + timedelta(days=2), res, AGORA)      # não é dele
    alternar(c, "u1", "A", "m3", D + timedelta(days=2), res, AGORA)         # detalhista marca por ele


def test_disponibilidade_some_quando_o_servico_muda_ou_ha_pedido_ativo():
    c = mk(); u = logado(c)
    res = gerar(c, D + timedelta(days=10))
    alternar(c, u.id, "A", "m1", D, res, AGORA)
    p = pp.criar(c, u.id, "A", "m1", D, "m3", D + timedelta(days=2), "x", AGORA, pin="1234")
    assert abertas(c, res, "A") == {}                                         # pedido ativo oculta o sinal
    pp.aprovar(c, "u1", p.id, AGORA)
    res2 = gerar(c, D + timedelta(days=10))
    assert abertas(c, res2, "A") == {}                                         # o serviço mudou de mãos
    assert alternar(c, "u1", "A", "m4", D + timedelta(days=3), res2, AGORA)
    assert podar(c, D + timedelta(days=30)) == 2 and c.disponibilidades == []


# ---------------------------------------------------------------- persistência dos novos dados
def test_novos_dados_persistem_e_voltam_iguais():
    c = mk(); u = logado(c)
    res = gerar(c, D + timedelta(days=10))
    alternar(c, u.id, "A", "m1", D, res, AGORA)
    u2 = conta(c, "pendente"); compartilhar(c, "u1", "A", u2.id, "leitura")
    vc.solicitar(c, u2.id, "A", "m2", "2.000", "9999", AGORA)
    c.cadastro_aberto = False
    T = para_tabelas(c)
    c2 = de_tabelas(T)
    assert c2.vinculos == c.vinculos and c2.disponibilidades == c.disponibilidades
    assert c2.usuarios == c.usuarios and c2.militares == c.militares and c2.cadastro_aberto is False
    assert c2.usuarios[1].pin_hash and c2.usuarios[1].celular == "(21) 98765-4321"
    b = MemoriaBackend(); r = Repositorio(b); r.carregar(); r.salvar(c)
    assert Repositorio(b).carregar().vinculos == c.vinculos

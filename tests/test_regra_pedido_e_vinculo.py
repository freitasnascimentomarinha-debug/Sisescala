"""Só militar vinculado pede troca (para si); o detalhista pede por todos; vínculo exige o detalhista."""
from datetime import date, datetime, timedelta

import pytest

from sisescala import auth
from sisescala import papeletas as pp
from sisescala import vinculos as vc
from sisescala.modelos import *
from sisescala.permissoes import PermissaoNegada, compartilhar, eh_detalhista, pode_editar

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 0)
SENHA, PIN = "senha-forte-1", "1234"
CONTATO = dict(email="a@b.com", ramal="2345", celular="21987654321")


def mk():
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"{i}.000") for i in range(1, 9)]
    e = Escala("A", "Diária", dono_id="u1", membros=[Pertinencia(m.id) for m in ms])
    c = Contexto(ms, [e], D)
    auth.criar_usuario(c, None, "det", "Detalhista", SENHA, admin=True)                         # u1 (dono)
    auth.criar_usuario(c, "u1", "ed", "Outro detalhista", SENHA)                                # u2
    sem = auth.cadastrar_se(c, "sem", "Sem vínculo", SENHA, **CONTATO)                          # u3
    vinc = auth.cadastrar_se(c, "vinc", "Vinculado", SENHA, **CONTATO)                          # u4
    for u in (c.usuario("u1"), c.usuario("u2"), sem, vinc):
        u.pin_hash = auth.hash_pin(PIN)
    for u in (sem, vinc):
        compartilhar(c, "u1", "A", u.id, "leitura")
    vc.aprovar(c, "u1", vc.solicitar(c, vinc.id, "A", "m1", "1.000", PIN, AGORA).id, AGORA)     # u4 = m1
    return c


SEM, VINC = "u3", "u4"


def pedir(c, uid, x="m1", dx=D, y="m3", dy=D + timedelta(days=2)):
    return pp.criar(c, uid, "A", x, dx, y, dy, "motivo", AGORA, pin=PIN)


def test_conta_sem_vinculo_nao_pede_troca_nem_com_acesso_de_leitura():
    c = mk()
    assert not c.usuario(SEM).militar_id
    with pytest.raises(PermissaoNegada, match="só militar vinculado"):
        pedir(c, SEM, x="m2", dy=D + timedelta(days=3), y="m4")
    assert c.papeletas == []


def test_militar_vinculado_pede_so_para_si():
    c = mk()
    assert pedir(c, VINC).solicitante_id == "m1"
    c2 = mk()
    with pytest.raises(PermissaoNegada, match="próprio serviço"):
        pedir(c2, VINC, x="m3", dx=D + timedelta(days=2), y="m5", dy=D + timedelta(days=4))   # por outro militar


def test_detalhista_pede_por_qualquer_militar_com_o_proprio_pin():
    c = mk()
    for u in ("u1", "u2"):
        assert eh_detalhista(c, u, c.escala("A")) == (u == "u1")      # u2 ainda sem poder de edição
    compartilhar(c, "u1", "A", "u2", "edicao")
    assert eh_detalhista(c, "u2", c.escala("A"))
    assert pedir(c, "u2", x="m3", dx=D + timedelta(days=2), y="m5", dy=D + timedelta(days=4)).criado_por == "u2"
    assert pedir(c, "u1", x="m2", dx=D + timedelta(days=1), y="m4", dy=D + timedelta(days=3)).solicitante_id == "m2"


def test_conta_de_militar_nao_recebe_edicao_nem_decide_nem_ve_pedidos_dos_outros():
    c = mk()
    with pytest.raises(ValueError, match="só contas de detalhista"):
        compartilhar(c, "u1", "A", VINC, "edicao")
    c.escala("A").compartilhado_com[VINC] = "edicao"                # mesmo se estivesse gravado assim (dado antigo)
    assert pode_editar(c, VINC, c.escala("A")) and not eh_detalhista(c, VINC, c.escala("A"))
    p = pedir(c, "u1", x="m3", dx=D + timedelta(days=2), y="m5", dy=D + timedelta(days=4))
    with pytest.raises(PermissaoNegada):
        pp.aprovar(c, VINC, p.id, AGORA)
    assert pp.papeletas_visiveis(c, VINC, "A") == [] and pp.pedidos_pendentes(c, VINC) == []
    assert VINC not in {n.usuario_id for n in c.notificacoes if "Aguardando a sua decisão" in n.texto}


def test_o_militar_nao_aprova_o_proprio_pedido():
    c = mk()
    p = pedir(c, VINC)
    with pytest.raises(PermissaoNegada):
        pp.aprovar(c, VINC, p.id, AGORA)
    pp.aprovar(c, "u1", p.id, AGORA)


# ---------------------------------------------------------------- vínculo precisa do detalhista
def test_vinculo_so_vale_com_autorizacao_do_detalhista():
    c = mk()
    v = vc.solicitar(c, SEM, "A", "m2", "2.000", PIN, AGORA)
    assert c.usuario(SEM).militar_id == ""                            # pedir não vincula
    with pytest.raises(PermissaoNegada):
        vc.aprovar(c, SEM, v.id, AGORA)                               # nem o próprio
    with pytest.raises(PermissaoNegada):
        vc.aprovar(c, VINC, v.id, AGORA)                              # nem outro militar
    assert c.usuario(SEM).militar_id == ""
    vc.aprovar(c, "u1", v.id, AGORA)
    assert c.usuario(SEM).militar_id == "m2"


def test_editor_com_conta_de_militar_nao_aprova_vinculo():
    c = mk()
    c.escala("A").compartilhado_com[VINC] = "edicao"                  # dado antigo
    v = vc.solicitar(c, SEM, "A", "m2", "2.000", PIN, AGORA)
    assert vc.pendentes_para(c, VINC) == []
    with pytest.raises(PermissaoNegada):
        vc.aprovar(c, VINC, v.id, AGORA)


def test_tela_de_usuarios_nao_oferece_vinculo_direto():
    """A conta criada pelo administrador nasce sem vínculo (o vínculo é pedido pelo militar e autorizado depois)."""
    from pathlib import Path
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    import os, tempfile
    d = tempfile.mkdtemp()
    os.environ["SISESCALA_ARQUIVO"] = str(Path(d) / "d.json")
    st.cache_resource.clear()
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=120).run()
    for rot, val in (("Login", "admin"), ("Nome", "Adm"), ("Senha (8+ caracteres)", "senha-admin-1"),
                     ("E-mail", "a@b.com"), ("Ramal", "2000"), ("Celular (com DDD)", "21999990000")):
        next(t for t in at.text_input if t.label == rot).input(val)
    next(b for b in at.button if "Criar administrador" in b.label).click().run()
    at.switch_page("paginas/usuarios.py").run()
    assert not at.exception
    assert not any("Militar" in s.label and "vincula" in s.label.lower() for s in at.selectbox)

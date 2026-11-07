"""Fumaça do app: todas as páginas abrem (administrador e militar) sem erro."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from sisescala import auth

RAIZ = Path(__file__).resolve().parent.parent
PAGINAS_GESTAO = ["painel", "escala", "papeletas", "devolucoes", "detalhe", "regras", "escalas", "militares",
                  "lancamentos", "importar", "buscar", "acessos", "vinculos", "usuarios", "conta", "notificacoes"]
PAGINAS_MILITAR = ["painel", "escala", "papeletas", "devolucoes", "detalhe", "regras", "escalas", "importar", "buscar",
                   "vinculos", "conta", "notificacoes"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SISESCALA_ARQUIVO", str(tmp_path / "d.json"))
    monkeypatch.setenv("SISESCALA_DEMO", "1")
    monkeypatch.setenv("SISESCALA_ADMIN_NIP", "admin")
    monkeypatch.setenv("SISESCALA_ADMIN_SENHA", "senha-admin-1")
    st.cache_resource.clear()
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120).run()
    return at


def _texto(at, rotulo):
    return next(t for t in at.text_input if t.label == rotulo)


def _criar_admin(at):
    """O administrador nasce sozinho, com NIP e senha vindos do ambiente; só falta entrar."""
    _entrar(at, "admin", "senha-admin-1")


def _entrar(at, nip, senha):
    _texto(at, "NIP").input(nip)
    next(t for t in at.text_input if t.label == "Senha").input(senha)
    next(b for b in at.button if b.label == "Entrar").click().run()


def test_admin_automatico_entra_e_abre_todas_as_paginas(app):
    assert not app.exception
    _criar_admin(app)
    assert not app.exception and app.session_state["uid"] == "u1"
    for p in PAGINAS_GESTAO:
        app.switch_page(f"paginas/{p}.py").run()
        assert not app.exception, (p, [e.value for e in app.exception])


def test_paginas_do_militar_e_login(app):
    _criar_admin(app)
    ctx = app.session_state["ctx"]
    u = auth.criar_usuario(ctx, "u1", "mil1", "Militar Um", "senha-mil-123", perfil="militar", militar_id="m1",
                           email="m@x.com", ramal="2345", celular="21988887777")
    app.run()                                          # grava
    del app.session_state["uid"]
    app.run()
    _entrar(app, "mil1", "senha-mil-123")
    assert app.session_state["uid"] == u.id and not app.exception
    for p in PAGINAS_MILITAR:
        app.switch_page(f"paginas/{p}.py").run()
        assert not app.exception, (p, [e.value for e in app.exception])


def test_senha_errada_nao_entra(app):
    _criar_admin(app)
    del app.session_state["uid"]
    app.run()
    _entrar(app, "admin", "errada")
    assert "uid" not in app.session_state and any("incorretos" in e.value for e in app.error)


def test_paginas_do_auxiliar_que_decide_papeletas_e_vinculos(app):
    _criar_admin(app)
    ctx = app.session_state["ctx"]
    ctx.escala("per").auxiliares = ["m2"]
    auth.criar_usuario(ctx, "u1", "aux", "Auxiliar", "senha-aux-1234", perfil="militar", militar_id="m2",
                       email="a@x.com", ramal="2345", celular="21988887777")
    app.run()
    del app.session_state["uid"]
    app.run()
    _entrar(app, "aux", "senha-aux-1234")
    assert app.session_state["uid"] == "u2" and not app.exception
    for p in PAGINAS_MILITAR + ["vinculos"]:
        app.switch_page(f"paginas/{p}.py").run()
        assert not app.exception, (p, [e.value for e in app.exception])


def test_auxiliar_abre_a_pagina_de_lancamentos(app):
    _criar_admin(app)
    ctx = app.session_state["ctx"]
    ctx.escala("per").auxiliares = ["m2"]
    auth.criar_usuario(ctx, "u1", "aux", "Auxiliar", "senha-aux-1234", perfil="militar", militar_id="m2",
                       email="a@x.com", ramal="2345", celular="21988887777")
    app.run()
    del app.session_state["uid"]
    app.run()
    _entrar(app, "aux", "senha-aux-1234")
    app.switch_page("paginas/lancamentos.py").run()
    assert not app.exception
    militares = next(s for s in app.selectbox if s.label == "Militar")
    assert "Militar 02" not in militares.options and "Militar 03" in militares.options       # sem ele mesmo


def test_admin_sem_senha_configurada_recebe_senha_provisoria_e_troca(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SISESCALA_ARQUIVO", str(tmp_path / "d.json"))
    monkeypatch.setenv("SISESCALA_DEMO", "1")
    monkeypatch.delenv("SISESCALA_ADMIN_NIP", raising=False)
    monkeypatch.delenv("SISESCALA_ADMIN_SENHA", raising=False)
    st.cache_resource.clear()
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120).run()
    saida = capsys.readouterr().out
    assert "Senha provisória:" in saida
    provisoria = saida.split("Senha provisória:")[1].split()[0]
    _entrar(at, "admin", provisoria)
    assert not at.exception
    assert any(b.label == "Salvar senha" for b in at.button)           # troca obrigatória antes de usar
    next(t for t in at.text_input if t.label == "Senha provisória").input(provisoria)
    next(t for t in at.text_input if t.label == "Nova senha (8+)").input("nova-senha-99")
    next(t for t in at.text_input if t.label == "Repita a nova senha").input("nova-senha-99")
    next(b for b in at.button if b.label == "Salvar senha").click().run()
    assert not at.exception and not any(b.label == "Salvar senha" for b in at.button)


def test_cadastro_pelo_login_fica_pendente_e_admin_aprova(app):
    _texto(app, "NIP (somente números)").input("12345678")
    _texto(app, "OM").input("CAAML")
    _texto(app, "Nome completo").input("Fulano de Tal")
    next(t for t in app.text_input if t.key == "cad_senha").input("senha-fulano-1")
    _texto(app, "E-mail para contato").input("f@x.com")
    _texto(app, "Ramal").input("2345")
    next(t for t in app.text_input if t.key == "cad_cel").input("21988887777")
    next(b for b in app.button if b.label == "Solicitar cadastro").click().run()
    assert not app.exception and any("aprovação" in x.value for x in app.success)
    ctx = app.session_state["ctx"]
    novo = next(u for u in ctx.usuarios if u.login == "12345678")
    assert novo.situacao == "pendente" and novo.om == "CAAML"
    _entrar(app, "12345678", "senha-fulano-1")
    assert "uid" not in app.session_state                                # pendente não entra


def test_usuario_novo_sem_escala_abre_as_paginas_e_vira_detalhista_ao_criar(app):
    _criar_admin(app)
    ctx = app.session_state["ctx"]
    adm = ctx.usuario("u1")
    novo = auth.cadastrar_se(ctx, "12345678", "Novo Usuário", "senha-nova-123", "n@x.com", "2345", "21988887777", om="CAAML")
    auth.aprovar_usuario(ctx, adm.id, novo.id)
    app.run()
    del app.session_state["uid"]
    app.run()
    _entrar(app, "12345678", "senha-nova-123")
    assert app.session_state["uid"] == novo.id and not app.exception
    for p in PAGINAS_MILITAR:
        app.switch_page(f"paginas/{p}.py").run()
        assert not app.exception, (p, [e.value for e in app.exception])
    from sisescala import gestao
    from sisescala.modelos import Escala, Pertinencia
    ctx = app.session_state["ctx"]
    ids = [m.id for m in ctx.militares[:4]]
    e = gestao.criar_escala(ctx, novo.id, Escala("ex", "Minha", membros=[Pertinencia(i) for i in ids]))
    app.run()
    for p in PAGINAS_GESTAO[:-4] + ["acessos"]:
        if p in ("usuarios",):
            continue
        app.switch_page(f"paginas/{p}.py").run()
        assert not app.exception, (p, [x.value for x in app.exception])


def test_deploy_novo_com_modulos_velhos_na_memoria_recarrega_sem_erro(app):
    """Simula o servidor que já tinha `sisescala` carregado de um deploy anterior (ImportError na nuvem)."""
    import sys
    guardados = {n: m for n, m in sys.modules.items() if n == "sisescala" or n.startswith("sisescala.")}
    try:
        _recarrega_modulos_velhos(app, sys)
    finally:                      # o app descarta e recarrega os módulos; devolve os originais para não afetar outros testes
        for n in [n for n in sys.modules if n == "sisescala" or n.startswith("sisescala.")]:
            del sys.modules[n]
        sys.modules.update(guardados)


def _recarrega_modulos_velhos(app, sys):
    _criar_admin(app)
    del sys.modules["sisescala"]._assinatura                          # deploy anterior: pacote sem assinatura
    sys.modules["sisescala"].__dict__.pop("x", None)                         # "módulos de outra versão do código"
    del sys.modules["sisescala.modelos"].PedidoAcesso                  # o que quebrava: classe nova ausente
    app.run()
    assert not app.exception
    assert hasattr(sys.modules["sisescala.modelos"], "PedidoAcesso")
    assert any(b.label == "Entrar" for b in app.button)                # sessão antiga descartada: pede login

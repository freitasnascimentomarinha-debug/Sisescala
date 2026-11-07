"""Fumaça do app: todas as páginas abrem (administrador e militar) sem erro."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from sisescala import auth

RAIZ = Path(__file__).resolve().parent.parent
PAGINAS_GESTAO = ["painel", "escala", "papeletas", "devolucoes", "detalhe", "regras", "escalas", "militares",
                  "lancamentos", "importar", "vinculos", "usuarios", "conta", "notificacoes"]
PAGINAS_MILITAR = ["painel", "escala", "papeletas", "devolucoes", "detalhe", "regras", "conta", "notificacoes"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SISESCALA_ARQUIVO", str(tmp_path / "d.json"))
    monkeypatch.setenv("SISESCALA_DEMO", "1")
    st.cache_resource.clear()
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120).run()
    return at


def _texto(at, rotulo):
    return next(t for t in at.text_input if t.label == rotulo)


def _criar_admin(at):
    for rot, val in (("Login", "admin"), ("Nome", "Adm"), ("Senha (8+ caracteres)", "senha-admin-1"),
                     ("E-mail", "a@b.com"), ("Ramal", "2000"), ("Celular (com DDD)", "21999990000")):
        _texto(at, rot).input(val)
    next(b for b in at.button if "Criar administrador" in b.label).click().run()


def test_primeiro_acesso_e_todas_as_paginas_do_administrador(app):
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
    _texto(app, "Login").input("mil1")
    next(t for t in app.text_input if t.label == "Senha").input("senha-mil-123")
    next(b for b in app.button if b.label == "Entrar").click().run()
    assert app.session_state["uid"] == u.id and not app.exception
    for p in PAGINAS_MILITAR:
        app.switch_page(f"paginas/{p}.py").run()
        assert not app.exception, (p, [e.value for e in app.exception])


def test_senha_errada_nao_entra(app):
    _criar_admin(app)
    del app.session_state["uid"]
    app.run()
    _texto(app, "Login").input("admin")
    next(t for t in app.text_input if t.label == "Senha").input("errada")
    next(b for b in app.button if b.label == "Entrar").click().run()
    assert "uid" not in app.session_state and any("incorretos" in e.value for e in app.error)


def test_paginas_do_auxiliar_que_decide_papeletas_e_vinculos(app):
    _criar_admin(app)
    ctx = app.session_state["ctx"]
    ctx.escala("per").auxiliar_id = "m2"
    auth.criar_usuario(ctx, "u1", "aux", "Auxiliar", "senha-aux-1234", perfil="militar", militar_id="m2",
                       email="a@x.com", ramal="2345", celular="21988887777")
    app.run()
    del app.session_state["uid"]
    app.run()
    _texto(app, "Login").input("aux")
    next(t for t in app.text_input if t.label == "Senha").input("senha-aux-1234")
    next(b for b in app.button if b.label == "Entrar").click().run()
    assert app.session_state["uid"] == "u2" and not app.exception
    for p in PAGINAS_MILITAR + ["vinculos"]:
        app.switch_page(f"paginas/{p}.py").run()
        assert not app.exception, (p, [e.value for e in app.exception])

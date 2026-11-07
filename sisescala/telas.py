"""Telas fora do menu: login, primeiro acesso e criação de conta."""
from __future__ import annotations

import streamlit as st

from . import auth, ui
from .modelos import Contexto

_BULLETS = [
    ("calendar", "Escalas de serviço, retém e quartos geradas pelas regras do seu serviço"),
    ("swap", "Troca e devolução por papeleta, com PIN, aprovação e assinatura registrada"),
    ("shield", "Cada militar vê a sua escala; o detalhista decide e acompanha tudo"),
]


def _hero() -> str:
    itens = "".join(f'<li><span class="dot">{ui.icone(i, 15)}</span><span>{ui.esc(t)}</span></li>' for i, t in _BULLETS)
    return (f'<div class="hero"><div class="brand"><div class="ph-ic">{ui.icone("anchor", 22)}</div>SisEscala</div>'
            f'<h1>Escalas de serviço,<br>sem planilha.</h1>'
            f'<p>Detalhe de serviço, trocas, devoluções e documentos para assinatura, num só lugar.</p><ul>{itens}</ul></div>')


def tela_login(ctx: Contexto, armazenamento: str) -> None:
    esq, dir_ = st.columns([1.15, 1], gap="large")
    esq.html(_hero())
    with dir_:
        st.html('<div style="height:2.2rem"></div>')
        if not auth.tem_usuarios(ctx):
            st.html('<div class="logincard"><h2>Bem-vindo!</h2><p>Primeiro acesso: crie a conta do administrador.</p></div>')
            with st.form("primeiro"):
                lg = st.text_input("Login")
                nm = st.text_input("Nome")
                sn = st.text_input("Senha (8+ caracteres)", type="password")
                c1, c2 = st.columns(2)
                em, ra = c1.text_input("E-mail"), c2.text_input("Ramal")
                ce = st.text_input("Celular (com DDD)")
                if st.form_submit_button("Criar administrador", type="primary", use_container_width=True):
                    try:
                        u = auth.criar_usuario(ctx, None, lg, nm, sn, email=em, ramal=ra, celular=ce, exigir_contato=True)
                        st.session_state.uid = u.id
                        st.rerun()
                    except ValueError as ex:
                        st.error(str(ex))
        else:
            t_in, t_new = st.tabs(["Entrar", "Criar conta"])
            with t_in:
                st.html('<div class="logincard"><h2>Entrar</h2><p>Use o login e a senha da sua conta.</p></div>')
                with st.form("login"):
                    lg = st.text_input("Login")
                    sn = st.text_input("Senha", type="password")
                    if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                        try:
                            st.session_state.uid = auth.entrar(ctx, lg, sn).id
                            st.rerun()
                        except auth.AutenticacaoErro as ex:
                            st.error(str(ex))
            with t_new:
                if not ctx.cadastro_aberto:
                    st.info("O cadastro de novas contas está fechado. Fale com o administrador.")
                else:
                    st.html('<div class="logincard"><h2>Criar conta de militar</h2>'
                            '<p>Depois, peça ao detalhista acesso à sua escala e vincule-se ao seu nome.</p></div>')
                    with st.form("cadastro"):
                        cl = st.text_input("Login", key="cad_login")
                        cn = st.text_input("Nome completo")
                        cs = st.text_input("Senha (8+)", type="password", key="cad_senha")
                        c1, c2 = st.columns(2)
                        ce, cr = c1.text_input("E-mail para contato"), c2.text_input("Ramal")
                        cc = st.text_input("Celular (com DDD)", key="cad_cel")
                        if st.form_submit_button("Criar conta", type="primary", use_container_width=True):
                            try:
                                u = auth.cadastrar_se(ctx, cl, cn, cs, ce, cr, cc)
                                st.session_state.uid = u.id
                                st.rerun()
                            except (ValueError, PermissionError) as ex:
                                st.error(str(ex))
        st.caption(f"Armazenamento: {armazenamento}")

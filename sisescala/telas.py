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
        t_in, t_new = st.tabs(["Entrar", "Criar conta"])
        with t_in:
            st.html('<div class="logincard"><h2>Entrar</h2><p>Use o seu NIP e a senha.</p></div>')
            with st.form("login"):
                nip = st.text_input("NIP")
                sn = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    try:
                        st.session_state.uid = auth.entrar(ctx, nip, sn).id
                        st.rerun()
                    except auth.AutenticacaoErro as ex:
                        st.error(str(ex))
        with t_new:
            if not ctx.cadastro_aberto:
                st.info("O cadastro de novas contas está fechado. Fale com o administrador.")
            else:
                st.html('<div class="logincard"><h2>Criar conta de militar</h2>'
                        '<p>O administrador aprova o seu cadastro. Depois você cria ou importa uma escala, '
                        'ou pede acesso à de outro detalhista.</p></div>')
                with st.form("cadastro"):
                    c1, c2 = st.columns(2)
                    cn_nip = c1.text_input("NIP (somente números)", key="cad_nip")
                    c_om = c2.text_input("OM", key="cad_om")
                    cn = st.text_input("Nome completo")
                    cs = st.text_input("Senha (8+)", type="password", key="cad_senha")
                    c1, c2 = st.columns(2)
                    ce, cr = c1.text_input("E-mail para contato"), c2.text_input("Ramal")
                    cc = st.text_input("Celular (com DDD)", key="cad_cel")
                    if st.form_submit_button("Solicitar cadastro", type="primary", use_container_width=True):
                        try:
                            auth.cadastrar_se(ctx, cn_nip, cn, cs, ce, cr, cc, om=c_om)
                            st.success("Cadastro enviado. Aguarde a aprovação do administrador para entrar.")
                        except (ValueError, PermissionError) as ex:
                            st.error(str(ex))
        st.caption(f"Armazenamento: {armazenamento}")


def tela_troca_senha(ctx: Contexto, user) -> None:
    """Senha provisória (administrador gerado ou redefinida): troca obrigatória antes de usar o sistema."""
    _, meio, _ = st.columns([1, 1.2, 1])
    with meio:
        st.html('<div style="height:3rem"></div><div class="logincard"><h2>Defina a sua senha</h2>'
                '<p>Você entrou com uma senha provisória. Escolha uma nova para continuar.</p></div>')
        with st.form("troca_obrigatoria"):
            atual = st.text_input("Senha provisória", type="password")
            nova = st.text_input("Nova senha (8+)", type="password")
            conf = st.text_input("Repita a nova senha", type="password")
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Salvar senha", type="primary", use_container_width=True):
                try:
                    if nova != conf:
                        raise ValueError("as senhas não conferem")
                    auth.trocar_senha(ctx, user.id, atual, nova)
                    st.rerun()
                except (ValueError, auth.AutenticacaoErro) as ex:
                    st.error(str(ex))
            if c2.form_submit_button("Sair", use_container_width=True):
                st.session_state.pop("uid", None)
                st.rerun()

"""SisEscala – ponto de entrada: tema, login, navegação por páginas e gravação.

Rodar: streamlit run app.py
"""
import os
from datetime import date, datetime

import streamlit as st

from sisescala import auth, ui
from sisescala import notificacoes as nt
from sisescala import papeletas as pp
from sisescala import permissoes as pm
from sisescala import sessao
from sisescala import vinculos as vc
from sisescala import disponibilidade as dp
from sisescala.demo import contexto_demo
from sisescala.motor import gerar
from sisescala.persistencia import ConflitoDeVersao, Repositorio, criar_repositorio
from sisescala.previa import periodo
from sisescala.telas import tela_login

st.set_page_config(page_title="SisEscala", page_icon="⚓", layout="wide", initial_sidebar_state="expanded")
ui.aplicar_tema()


@st.cache_resource(show_spinner=False)
def _backend():
    """Google Sheets se houver credenciais em st.secrets; senão arquivo local (desenvolvimento)."""
    try:
        seg = {k: dict(st.secrets[k]) for k in ("gcp_service_account", "sheets") if k in st.secrets}
    except Exception:  # sem secrets.toml
        seg = {}
    repo, nome = criar_repositorio(seg, os.environ.get("SISESCALA_ARQUIVO", "data/sisescala.json"))
    return repo.backend, nome


backend, ARMAZENAMENTO = _backend()


def _carregar_novo():
    ctx_ = st.session_state.repo.carregar()
    if not ctx_.militares and not ctx_.usuarios and os.environ.get("SISESCALA_DEMO") == "1":
        ctx_ = contexto_demo()            # só em desenvolvimento
    st.session_state.ctx = ctx_


def _sincronizar():
    """Grava pendências locais e traz mudanças de outras pessoas (versão da planilha)."""
    try:
        if "repo" not in st.session_state:
            st.session_state.repo = Repositorio(backend)
            _carregar_novo()
            return
        repo, ctx_ = st.session_state.repo, st.session_state.ctx
        try:
            repo.salvar(ctx_)
        except ConflitoDeVersao:
            _carregar_novo()
            st.session_state["aviso"] = ("Outra pessoa alterou os dados ao mesmo tempo. Recarreguei a versão mais "
                                         "recente; refaça a sua última ação se ela não aparecer.")
            return
        if repo.desatualizado():
            _carregar_novo()
    except Exception as ex:   # rede, cota da API, permissão da planilha
        st.error(f"Não consegui acessar o armazenamento ({ARMAZENAMENTO}): {ex}")
        st.stop()


def _gravar():
    """Ao fim de cada execução (inclusive em st.rerun/st.stop): grava só o que mudou."""
    try:
        st.session_state.repo.salvar(st.session_state.ctx)
    except ConflitoDeVersao:
        _carregar_novo()
        st.session_state["aviso"] = ("Outra pessoa alterou os dados ao mesmo tempo. Recarreguei a versão mais "
                                     "recente; refaça a sua última ação se ela não aparecer.")
    except Exception as ex:
        st.error(f"Não consegui gravar em {ARMAZENAMENTO}: {ex}")


_sincronizar()
ctx = st.session_state.ctx
user = ctx.usuario(st.session_state.get("uid", ""))
if user is None or not user.ativo:
    st.session_state.pop("uid", None)
    tela_login(ctx, ARMAZENAMENTO)
    _gravar()
    st.stop()

# ---------------------------------------------------------------- estado desta execução
uid = user.id
gerir = user.perfil == "detalhista"
nt.podar(ctx)
dp.podar(ctx)
visiveis = pm.escalas_visiveis(ctx, uid)
n_pend, n_vinc, n_novas = len(pp.pedidos_pendentes(ctx, uid)), len(vc.pendentes_para(ctx, uid)), nt.nao_lidas(ctx, uid)


def _pg(arq, titulo, icone, url, padrao=False):
    return st.Page(f"paginas/{arq}.py", title=titulo, icon=f":material/{icone}:", url_path=url, default=padrao)


def _c(n):
    return f" ({n})" if n else ""


menu = {
    "Início": [_pg("painel", "Painel", "dashboard", "painel", True)],
    "Operação": [_pg("escala", "Escala", "calendar_month", "escala"),
                 _pg("papeletas", "Papeletas" + _c(n_pend), "swap_horiz", "papeletas"),
                 _pg("devolucoes", "Devoluções", "undo", "devolucoes")],
    "Documentos": [_pg("detalhe", "Detalhe de serviço", "description", "detalhe"),
                   _pg("regras", "Regras da escala", "menu_book", "regras")],
}
if gerir:
    menu["Gestão"] = [_pg("escalas", "Escalas", "tune", "escalas"),
                      _pg("militares", "Militares", "group", "militares"),
                      _pg("lancamentos", "Lançamentos", "edit_calendar", "lancamentos"),
                      _pg("importar", "Importar planilha", "upload_file", "importar"),
                      _pg("vinculos", "Vínculos" + _c(n_vinc), "link", "vinculos")]
if user.admin:
    menu["Administração"] = [_pg("usuarios", "Usuários", "admin_panel_settings", "usuarios")]
conta = [_pg("notificacoes", "Notificações" + _c(n_novas), "notifications", "notificacoes"),
         _pg("conta", "Minha conta", "manage_accounts", "conta")]
if not gerir and not user.militar_id:
    conta.insert(0, _pg("vinculos", "Vincular-me ao meu nome", "link", "vinculos"))
menu["Conta"] = conta

atual = st.navigation(menu, expanded=True)
st.logo(str(ui.RAIZ / "assets" / "logo.svg"), size="large")

with st.sidebar:
    papel = ("Administrador" if user.admin else "Detalhista" if gerir else "Militar")
    st.html(f'<div class="usercard">{ui.avatar(user.nome)}<div><b>{ui.esc(user.nome)}</b><small>{papel}</small></div></div>')
    if st.button("Sair", icon=":material/logout:", use_container_width=True):
        st.session_state.pop("uid", None)
        st.rerun()

# escala ativa e período vêm dos controles do topo das páginas (sessao.barra_contexto); os valores
# sobrevivem à navegação reatribuindo-os a cada execução
for _k in ("eid", "inicio", "per"):
    if _k in st.session_state:
        st.session_state[_k] = st.session_state[_k]
_ids = [e.id for e in visiveis]
eid = st.session_state.get("eid") if st.session_state.get("eid") in _ids else (_ids[0] if _ids else None)
inicio = st.session_state.get("inicio") or date.today()
per = st.session_state.get("per") or "7 dias"
dias = periodo(inicio, sessao.PERIODOS[per])
sessao.definir(sessao.Pagina(ctx=ctx, user=user, esc=ctx.escala(eid) if eid else None, res=gerar(ctx, dias[-1]),
                             dias=dias, inicio=inicio, visiveis=visiveis, n_pend=n_pend, n_vinc=n_vinc,
                             n_novas=n_novas))

if (t := st.session_state.pop("toast", None)):
    st.toast(t, icon="✅")
if (a := st.session_state.pop("aviso", None)):
    st.warning(a, icon="⚠️")

try:
    atual.run()
finally:
    _gravar()

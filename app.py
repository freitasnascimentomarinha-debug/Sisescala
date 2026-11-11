"""SisEscala – ponto de entrada: tema, login, navegação por páginas e gravação.

Rodar: streamlit run app.py
"""
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import streamlit as st

# Fuso horário: o servidor costuma rodar em UTC, mas todo horário e "hoje" do sistema são os de Brasília (assinaturas,
# papeletas, notificações, prévia). Vale para datetime.now() e date.today() em todo o processo; mude com SISESCALA_TZ.
os.environ["TZ"] = os.environ.get("SISESCALA_TZ", "America/Sao_Paulo")
if hasattr(time, "tzset"):
    time.tzset()

# O servidor do Streamlit continua rodando depois de um deploy novo e mantém em memória os módulos antigos de
# `sisescala/` (o app.py é reexecutado, o pacote não). Isso gera ImportError ("cannot import name ...") e objetos de
# classes velhas na sessão. Se o código mudou, descarta os módulos, o cache e a sessão (o usuário entra de novo).
_ASSINATURA = max((p.stat().st_mtime_ns for p in (Path(__file__).parent / "sisescala").glob("*.py")), default=0)
# (módulos de uma versão anterior nem têm `_assinatura`: contam como velhos)
if st.session_state.get("_assinatura_codigo") not in (None, _ASSINATURA) or (
        "sisescala" in sys.modules and getattr(sys.modules["sisescala"], "_assinatura", None) != _ASSINATURA):
    for _n in [n for n in sys.modules if n == "sisescala" or n.startswith("sisescala.")]:
        del sys.modules[_n]
    st.cache_resource.clear()
    st.session_state.clear()
st.session_state["_assinatura_codigo"] = _ASSINATURA

from sisescala import auth, ui  # noqa: E402

from sisescala import acessos as ac
from sisescala import assinaturas as asn
from sisescala import notificacoes as nt
from sisescala import papeletas as pp
from sisescala import permissoes as pm
from sisescala import sessao
from sisescala import vinculos as vc
from sisescala import disponibilidade as dp
from sisescala.demo import contexto_demo
from sisescala.motor import gerar
from sisescala.persistencia import ConfiguracaoSheetsErro, ConflitoDeVersao, Repositorio, criar_repositorio
from sisescala.previa import periodo
from sisescala.telas import tela_login, tela_troca_senha

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


try:
    backend, ARMAZENAMENTO = _backend()
except ConfiguracaoSheetsErro as _ex:        # segredos do Google Sheets malformados: explica em vez de "erro redigido"
    st.error(f"**Configuração do Google Sheets inválida.** {_ex}")
    st.info("Corrija em **Manage app → Settings → Secrets** (modelo em `.streamlit/secrets.toml.example`) e reinicie o app.")
    st.stop()


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


def _config_admin() -> tuple[str, str | None]:
    """NIP e senha do administrador criado automaticamente: segredos do deploy, depois ambiente, depois padrão."""
    try:
        seg = dict(st.secrets["admin"]) if "admin" in st.secrets else {}
    except Exception:
        seg = {}
    return (seg.get("nip") or os.environ.get("SISESCALA_ADMIN_NIP") or "admin",
            seg.get("senha") or os.environ.get("SISESCALA_ADMIN_SENHA") or None)


_nip_cfg, _senha_cfg = _config_admin()
if _senha_cfg:
    # NIP e senha dos segredos são a fonte da verdade: se mudaram (ou nunca foram aplicados), valem para o administrador
    # (serve também para recuperar o acesso: troque a senha nos segredos e reinicie o app).
    try:
        if auth.sincronizar_admin(ctx, _nip_cfg, _senha_cfg):
            _gravar()
    except ValueError as _ex:
        st.error(f"Senha do administrador nos segredos inválida: {_ex}")
        st.stop()

if not any(u.admin for u in ctx.usuarios):
    # O sistema cria o administrador sozinho. Sem senha configurada, gera uma provisória forte e a escreve no log do
    # servidor (Manage app → Logs, no Community Cloud); o primeiro acesso exige a troca.
    _nip_adm, _senha_adm = _config_admin()
    _adm, _gerada = auth.garantir_admin(ctx, _nip_adm, _senha_adm)
    if _gerada:
        print(f"[SisEscala] Administrador criado. NIP: {_nip_adm}  Senha provisória: {_gerada}  "
              f"(troque no primeiro acesso)", flush=True)
    _gravar()

def _tela_unica(funcao, titulo: str, caminho: str) -> None:
    """Mostra uma tela sem menu. Registra uma navegação oculta: se o script só parasse (st.stop), o menu lateral da execução
    anterior (usuário que acabou de sair) continuaria na tela. Além da tela, vale sempre a verificação pública de documento
    (/verificar), que o QR code do PDF assinado abre sem pedir login."""
    def pagina():
        st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],"
                    "[data-testid='stExpandSidebarButton']{display:none !important}</style>", unsafe_allow_html=True)
        funcao()

    principal = st.Page(pagina, title=titulo, url_path=caminho, default=True)
    st.navigation([principal, st.Page("publico/verificar.py", title="Verificar documento", url_path="verificar")],
                  position="hidden").run()


user = ctx.usuario(st.session_state.get("uid", ""))
if user is None or not user.ativo:
    st.session_state.pop("uid", None)
    _tela_unica(lambda: tela_login(ctx, ARMAZENAMENTO), "Entrar", "entrar")
    _gravar()
    st.stop()

if user.trocar_senha:                       # senha provisória (administrador gerado ou redefinida): troca obrigatória
    _tela_unica(lambda: tela_troca_senha(ctx, user), "Nova senha", "nova-senha")
    _gravar()
    st.stop()

# ---------------------------------------------------------------- estado desta execução
uid = user.id
nt.podar(ctx)
dp.podar(ctx)
visiveis = pm.escalas_visiveis(ctx, uid)
n_pend, n_vinc, n_novas = len(pp.pedidos_pendentes(ctx, uid)), len(vc.pendentes_para(ctx, uid)), nt.nao_lidas(ctx, uid)
n_acessos = len(ac.pendentes_para(ctx, uid))
n_convites = len(vc.convites_do_usuario(ctx, uid))
n_assinar = len(asn.para_assinar(ctx, uid))
n_cad = len(auth.pendentes(ctx)) if user.admin else 0
e_detalhista = any(pm.eh_detalhista(ctx, uid, e) for e in ctx.escalas)
e_auxiliar = bool(user.militar_id) and any(user.militar_id in e.auxiliares for e in ctx.escalas)


def _pg(arq, titulo, icone, url, padrao=False):
    return st.Page(f"paginas/{arq}.py", title=titulo, icon=f":material/{icone}:", url_path=url, default=padrao)


def _c(n):
    return f" ({n})" if n else ""


menu = {
    "Início": [_pg("painel", "Painel", "dashboard", "painel", True)],
    "Operação": [_pg("escala", "Prévia da escala", "calendar_month", "escala"),
                 _pg("papeletas", "Papeletas" + _c(n_pend), "swap_horiz", "papeletas"),
                 _pg("devolucoes", "Devoluções", "undo", "devolucoes"),
                 _pg("vinculos", "Vínculos" + _c(n_vinc + n_convites), "link", "vinculos")],
    "Documentos": [_pg("detalhe", "Detalhe de serviço", "description", "detalhe"),
                   _pg("regras", "Regras da escala", "menu_book", "regras"),
                   _pg("assinar", "Assinar documentos" + _c(n_assinar), "draw", "assinar"),
                   _pg("verificar", "Verificar documento", "verified", "verificar")],
    # todo usuário aprovado cria ou importa escalas (e vira o detalhista delas) e busca as de outros
    "Minhas escalas": [_pg("escalas", "Gerenciar escalas", "tune", "escalas"),
                       _pg("importar", "Importar planilha", "upload_file", "importar"),
                       _pg("buscar", "Buscar escalas", "search", "buscar")],
}
if e_detalhista or e_auxiliar:
    menu["Documentos"].insert(1, _pg("unificado", "Detalhe unificado", "library_books", "unificado"))
    gestao_pgs = [_pg("lancamentos", "Lançamentos", "edit_calendar", "lancamentos"),
                      _pg("calendario", "Calendário da escala", "event", "calendario")]
    if e_detalhista:
        gestao_pgs = [_pg("militares", "Militares", "group", "militares")] + gestao_pgs + [
            _pg("acessos", "Pedidos de acesso" + _c(n_acessos), "how_to_reg", "acessos")]
    menu["Gestão"] = gestao_pgs
if user.admin:
    menu["Administração"] = [_pg("usuarios", "Usuários" + _c(n_cad), "admin_panel_settings", "usuarios")]
menu["Conta"] = [_pg("notificacoes", "Notificações" + _c(n_novas), "notifications", "notificacoes"),
                 _pg("conta", "Minha conta", "manage_accounts", "conta")]

atual = st.navigation(menu, expanded=True)
st.logo(str(ui.RAIZ / "static" / "logo_menu.png"), size="large")

with st.sidebar:
    st.html('<img class="menu-anim" alt="" src="app/static/animacao_menu.gif"/>')     # animação sob os botões do menu
    papel = ("Administrador" if user.admin else "Detalhista" if e_detalhista else "Auxiliar" if e_auxiliar else "Usuário")
    st.html(f'<div class="usercard">{ui.avatar(user.nome)}<div><b>{ui.esc(user.nome)}</b><small>{papel}</small></div></div>')
    if st.button("Sair", icon=":material/logout:", use_container_width=True):
        st.session_state.pop("uid", None)
        st.rerun()

# escala ativa e período vêm dos controles do topo das páginas (sessao.barra_contexto); os valores
# sobrevivem à navegação reatribuindo-os a cada execução
if st.session_state.get("_hoje") != date.today():      # virou o dia: o início que era "hoje" acompanha
    if st.session_state.get("inicio") == st.session_state.get("_hoje"):
        st.session_state["inicio"] = date.today()
    st.session_state["_hoje"] = date.today()
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
                             n_novas=n_novas, n_acessos=n_acessos, n_convites=n_convites))

if (t := st.session_state.pop("toast", None)):
    st.toast(t, icon="✅")
if (a := st.session_state.pop("aviso", None)):
    st.warning(a, icon="⚠️")

try:
    atual.run()
finally:
    _gravar()

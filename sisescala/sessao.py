"""Estado compartilhado entre as páginas: o app.py monta uma vez por execução e cada página consome."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import streamlit as st

from . import permissoes as pm
from .modelos import Contexto, Escala, Usuario
from .motor import Resultado


@dataclass
class Pagina:
    ctx: Contexto
    user: Usuario
    esc: Escala | None
    res: Resultado
    dias: list[date]
    inicio: date
    visiveis: list[Escala]
    n_pend: int = 0          # pedidos de troca aguardando decisão (para quem decide)
    n_vinc: int = 0          # pedidos de vínculo aguardando decisão
    n_novas: int = 0         # notificações não lidas
    n_convites: int = 0      # convites de vínculo recebidos aguardando resposta
    n_acessos: int = 0       # pedidos de acesso às escalas dele aguardando decisão
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return self.user.id

    @property
    def gerir(self) -> bool:
        """É o detalhista de pelo menos uma escala (quem cria uma escala vira o detalhista dela)."""
        return any(pm.eh_detalhista(self.ctx, self.uid, e) for e in self.ctx.escalas)

    @property
    def decide(self) -> bool:
        """Detalhista ou auxiliar de alguma escala: decide papeletas e vínculos."""
        return self.gerir or (bool(self.user.militar_id)
                              and any(self.user.militar_id in e.auxiliares for e in self.ctx.escalas))

    @property
    def nomes_m(self) -> dict[str, str]:
        return {m.id: m.rotulo for m in self.ctx.militares}   # GRAD-ESP Nome (NIP)

    @property
    def nomes_u(self) -> dict[str, str]:
        return {u.id: self.ctx.rotulo_do_usuario(u) for u in self.ctx.usuarios}

    def editaveis(self) -> list[Escala]:
        return [e for e in self.visiveis if pm.eh_detalhista(self.ctx, self.uid, e)]


def definir(p: Pagina) -> None:
    st.session_state["_pagina"] = p


def pagina() -> Pagina:
    return st.session_state["_pagina"]


def agir(f, ok: str = "Feito.") -> None:
    """Executa uma ação de negócio; avisos viram faixa na próxima tela, erros aparecem na hora."""
    try:
        r = f()
        if isinstance(r, list) and r:
            st.session_state["aviso"] = " ".join(r)       # ex.: descanso curto
        st.session_state["toast"] = ok
        st.rerun()
    except Exception as ex:   # regra de negócio: ValueError/PermissaoNegada/AutenticacaoErro
        from .auth import AutenticacaoErro
        from .permissoes import PermissaoNegada
        if isinstance(ex, (ValueError, PermissaoNegada, AutenticacaoErro, PermissionError)):
            st.error(str(ex))
        else:
            raise


def contato(ctx: Contexto, m) -> str:
    u = next((x for x in ctx.usuarios if x.militar_id == m.id), None)
    em = m.email or (u.email if u else "")
    ra = m.ramal or (u.ramal if u else "")
    ce = m.celular or (u.celular if u else "")
    return " · ".join(p for p in (f"✉ {em}" if em else "", f"ramal {ra}" if ra else "", f"📱 {ce}" if ce else "")
                      if p) or "—"


def fmt_dia(d: date) -> str:
    return f"{d:%d/%m/%Y} ({'seg ter qua qui sex sáb dom'.split()[d.weekday()]})"


def exigir_escala(P: Pagina) -> Escala:
    """Páginas que dependem de uma escala: sem escala visível, mostra orientação e para."""
    from . import ui
    if P.esc is None:
        ui.vazio("Nenhuma escala disponível",
                 "Crie uma escala (ou importe uma planilha) ou busque a escala da sua OM e peça acesso ao detalhista.", "calendar")
        st.stop()
    return P.esc


PERIODOS = {"7 dias": 7, "15 dias": 15, "1 mês": 30}


def barra_contexto(P: Pagina, periodo: bool = True, escala: bool = True) -> None:
    """Escala ativa e período, no topo das páginas que dependem deles (o estado vale para todas as páginas)."""
    if not P.visiveis:
        return
    ids = [e.id for e in P.visiveis]
    if st.session_state.get("eid") not in ids:
        st.session_state["eid"] = ids[0]
    if not escala:                       # só o período (páginas que não dependem de uma escala só)
        c1, c2, _ = st.columns([1.2, 1.6, 2])
        c1.date_input("Início", date.today(), key="inicio", format="DD/MM/YYYY")
        c2.segmented_control("Período", list(PERIODOS), default="7 dias", key="per")
        return
    cols = st.columns([2, 1.2, 1.6] if periodo else [2])
    cols[0].selectbox("Escala", ids, format_func=lambda i: P.ctx.escala(i).nome, key="eid")
    if periodo:
        cols[1].date_input("Início", date.today(), key="inicio", format="DD/MM/YYYY")
        cols[2].segmented_control("Período", list(PERIODOS), default="7 dias", key="per")

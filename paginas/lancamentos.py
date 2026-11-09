"""Lançamentos: um botão para incluir (escala → tipo → militar → motivo → salvar) e uma lista com filtros.

Detalhista e auxiliar lançam. O auxiliar só nas escalas dele e só para os militares delas, e ninguém lança para si mesmo.
"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from sisescala import lancamentos as lc
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.modelos import (ROTULO_IMPEDIMENTO, TIPOS_IMPEDIMENTO, TIPOS_VISIVEIS, Evento, Guarnecimento,
                               Impedimento, Ocorrencia)
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid = P.ctx, P.uid
nomes_m = P.nomes_m
escalas_ok = lc.escalas_lancaveis(ctx, uid)
ui.cabecalho("Lançamentos", "Dispensas, impedimentos, guarnecimento e eventos das suas escalas. Feriados e licenças ficam em Calendário da escala.",
             "calendar", [ui.chip("Escalas", ", ".join(e.nome for e in escalas_ok) or "—")])
if not escalas_ok:
    ui.vazio("Sem permissão para lançar", "Só o detalhista e o auxiliar de uma escala lançam.", "shield")
    st.stop()
if not P.gerir:
    st.caption("Como auxiliar, você lança nas escalas em que é auxiliar e para os militares delas, menos para você mesmo.")

meu_mil = P.user.militar_id
TIPOS_LANC = {
    "impedimento": "Impedimento ou dispensa (férias, curso, dispensa, destaque…)",
    "dispensa_dia": "Dispensa do serviço em que está escalado (o retém avança)",
    "guarnece": "Decisão do comando: guarnece ou não",
    "evento": "Evento (palestra, cerimônia, apoio…)",
}


def _militares_da(eid: str) -> list[str]:
    """Militares da escala, do mais antigo ao mais moderno, sem o próprio usuário (ninguém lança para si)."""
    esc = ctx.escala(eid)
    return [i for i in ctx.ordem_na_escala(esc) if i != meu_mil]


def _rotulo_mil(i: str) -> str:
    m = ctx.militar(i)
    return m.rotulo


@st.dialog("Incluir lançamento", width="large")
def dialogo_incluir():
    ids = [e.id for e in escalas_ok]
    eid = st.selectbox("1 · Escala", ids, format_func=lambda i: ctx.escala(i).nome, key="lc_esc")
    esc = ctx.escala(eid)
    opcoes = [k for k in TIPOS_LANC if k != "evento" or esc.modo == "eventos"]
    tipo = st.selectbox("2 · O que lançar", opcoes, format_func=TIPOS_LANC.get, key="lc_tipo")
    st.divider()
    mil = _militares_da(eid)

    if tipo in ("impedimento", "dispensa_dia"):
        if not mil:
            st.info("Esta escala não tem outros militares para receber lançamento.")
            return
        mid = st.selectbox("3 · Militar", mil, format_func=_rotulo_mil, key="lc_mil")
    if tipo == "impedimento":
        sit = st.selectbox("4 · Motivo (situação)", TIPOS_VISIVEIS, key="lc_sit",
                           format_func=lambda t: f"{ROTULO_IMPEDIMENTO[t]}  ·  {TIPOS_IMPEDIMENTO[t]}")
        a, b = st.columns(2)
        ini = a.date_input("Início", date.today(), format="DD/MM/YYYY", key="lc_ini")
        fim = b.date_input("Fim", ini, format="DD/MM/YYYY", key="lc_fim", disabled=sit == "desembarque",
                           help="Desembarque não tem data final." if sit == "desembarque" else None)
        just = st.text_area("5 · Justificativa / OM de destino", key="lc_just", height=90,
                            help="Obrigatória para dispensas (baixa, falta ou com documento).")
        anexo = st.text_input("Arquivo ou link (obrigatório na dispensa com documento)", key="lc_anexo")
        if st.button("Salvar lançamento", type="primary", use_container_width=True, key="lc_ok"):
            agir(lambda: lc.lancar_impedimento(ctx, uid, Impedimento(
                mid, sit, ini, None if sit == "desembarque" else fim, just.strip(), anexo.strip())), "Lançamento salvo.")
    elif tipo == "dispensa_dia":
        dt = st.date_input("4 · Dia do serviço", date.today(), format="DD/MM/YYYY", key="lc_dia")
        just = st.text_area("5 · Justificativa (obrigatória)", key="lc_just2", height=90,
                            help="Baixa, falta ou outro motivo. Aparece na prévia e no detalhe.")
        st.caption("O militar passa a Dispensado (Disp) nesse dia, o retém avança e a prévia e o detalhe se reconfiguram.")
        if st.button("Salvar lançamento", type="primary", use_container_width=True, key="lc_ok2"):
            agir(lambda: lc.lancar_dispensa_no_dia(ctx, uid, Ocorrencia(dt, eid, mid, just.strip())),
                 "Dispensa lançada; o retém avançou e a escala foi reconfigurada.")
    elif tipo == "guarnece":
        dg = st.date_input("3 · Dia", date.today(), format="DD/MM/YYYY", key="lc_dg")
        gu = st.toggle("Guarnece neste dia", True, key="lc_gu")
        suas = [e.id for e in escalas_ok if pm.eh_detalhista(ctx, uid, e)]        # só onde a pessoa é detalhista
        destinos = [eid]
        if len(suas) > 1 and eid in suas:
            destinos = st.multiselect("Vale para estas escalas (só as que você é detalhista)", suas, default=[eid],
                                      format_func=lambda i: ctx.escala(i).nome, key=f"lc_dest_{eid}",
                                      help="A mesma decisão é lançada em cada escala escolhida. Uma decisão nova para o "
                                           "mesmo dia substitui a anterior.")
        if st.button("Salvar lançamento", type="primary", use_container_width=True, key="lc_ok4"):
            agir(lambda: lc.lancar_guarnecimento_em(ctx, uid, Guarnecimento(dg, eid, gu), destinos),
                 "Decisão lançada." if len(destinos) <= 1 else f"Decisão lançada em {len(destinos)} escalas.")
    else:
        a, b = st.columns(2)
        de = a.date_input("3 · Data do evento", date.today(), format="DD/MM/YYYY", key="lc_de")
        desc = b.text_input("4 · Descrição", key="lc_desc")
        a, b, c = st.columns(3)
        hora, local = a.text_input("Hora", key="lc_hora"), b.text_input("Local", key="lc_local")
        vagas = c.number_input("Vagas (0 = padrão)", 0, 99, 0, key="lc_vagas")
        if st.button("Salvar lançamento", type="primary", use_container_width=True, key="lc_ok5"):
            agir(lambda: lc.lancar_evento(ctx, uid, Evento(eid, de, desc, hora, local, vagas or None)), "Evento lançado.")


@st.dialog("Editar lançamento", width="large")
def dialogo_editar(item):
    """Mesmo formulário do Incluir, já preenchido com o lançamento. Ao salvar, o lançamento é substituído pela nova versão."""
    k = f"ed{id(item)}"
    ids = [e.id for e in escalas_ok]

    def salvar(novo, msg="Lançamento atualizado."):
        if st.button("Salvar alterações", type="primary", use_container_width=True, key=f"{k}_ok"):
            agir(lambda: lc.editar_lancamento(ctx, uid, item, novo), msg)

    if isinstance(item, Impedimento):
        mil = lc.militares_lancaveis(ctx, uid)
        if item.militar_id not in mil:
            st.info("Você não pode alterar este lançamento (o militar não é de uma escala em que você lança, ou é você mesmo).")
            return
        mid = st.selectbox("Militar", mil, mil.index(item.militar_id), format_func=_rotulo_mil, key=f"{k}_mil")
        sit = st.selectbox("Motivo (situação)", TIPOS_VISIVEIS, TIPOS_VISIVEIS.index(item.tipo) if item.tipo in TIPOS_VISIVEIS else 0,
                           key=f"{k}_sit", format_func=lambda t: f"{ROTULO_IMPEDIMENTO[t]}  ·  {TIPOS_IMPEDIMENTO[t]}")
        a, b = st.columns(2)
        ini = a.date_input("Início", item.inicio, format="DD/MM/YYYY", key=f"{k}_ini")
        fim = b.date_input("Fim", item.fim or ini, format="DD/MM/YYYY", key=f"{k}_fim", disabled=sit == "desembarque")
        just = st.text_area("Justificativa / OM de destino", item.motivo, key=f"{k}_just", height=90)
        anexo = st.text_input("Arquivo ou link", item.anexo, key=f"{k}_anexo")
        salvar(Impedimento(mid, sit, ini, None if sit == "desembarque" else fim, just.strip(), anexo.strip()))
    elif isinstance(item, Ocorrencia):
        eid = st.selectbox("Escala", ids, ids.index(item.escala_id) if item.escala_id in ids else 0,
                           format_func=lambda i: ctx.escala(i).nome, key=f"{k}_esc")
        mil = _militares_da(eid)
        if not mil:
            st.info("Esta escala não tem outros militares.")
            return
        mid = st.selectbox("Militar", mil, mil.index(item.militar_id) if item.militar_id in mil else 0,
                           format_func=_rotulo_mil, key=f"{k}_mil")
        dt = st.date_input("Dia do serviço", item.data, format="DD/MM/YYYY", key=f"{k}_dia")
        just = st.text_area("Justificativa (obrigatória)", item.motivo, key=f"{k}_just", height=90)
        salvar(Ocorrencia(dt, eid, mid, just.strip()))
    elif isinstance(item, Guarnecimento):
        eid = st.selectbox("Escala", ids, ids.index(item.escala_id) if item.escala_id in ids else 0,
                           format_func=lambda i: ctx.escala(i).nome, key=f"{k}_esc")
        dg = st.date_input("Dia", item.data, format="DD/MM/YYYY", key=f"{k}_dia")
        gu = st.toggle("Guarnece neste dia", item.guarnece, key=f"{k}_gu")
        salvar(Guarnecimento(dg, eid, gu))
    elif isinstance(item, Evento):
        evt = [i for i in ids if ctx.escala(i).modo == "eventos"]
        eid = st.selectbox("Escala", evt, evt.index(item.escala_id) if item.escala_id in evt else 0,
                           format_func=lambda i: ctx.escala(i).nome, key=f"{k}_esc")
        a, b = st.columns(2)
        de = a.date_input("Data do evento", item.data, format="DD/MM/YYYY", key=f"{k}_de")
        desc = b.text_input("Descrição", item.descricao, key=f"{k}_desc")
        a, b, c = st.columns(3)
        hora, local = a.text_input("Hora", item.hora, key=f"{k}_hora"), b.text_input("Local", item.local, key=f"{k}_local")
        vagas = c.number_input("Vagas (0 = padrão)", 0, 99, item.vagas or 0, key=f"{k}_vagas")
        salvar(Evento(eid, de, desc, hora, local, vagas or None))
    if item.criado_por:
        st.caption(f"Lançado por {ctx.usuario(item.criado_por).nome if ctx.usuario(item.criado_por) else '—'}"
                   + (f" em {item.criado_em:%d/%m/%Y %H:%M}" if item.criado_em else "") + ".")


c1, _ = st.columns([1.2, 4.8])
if c1.button("Incluir", type="primary", icon=":material/add:"):
    dialogo_incluir()

# ------------------------------------------------------------------ lista: tudo que está lançado nas minhas escalas
minhas = {e.id: e for e in escalas_ok}
escalas_do_mil: dict[str, list[str]] = {}
for e in escalas_ok:
    for p in e.membros:
        if e.nome not in escalas_do_mil.setdefault(p.militar_id, []):
            escalas_do_mil[p.militar_id].append(e.nome)

itens: list[tuple[object, dict]] = []
for x in ctx.impedimentos:
    if x.militar_id in escalas_do_mil:
        itens.append((x, {"Início": x.inicio, "Fim": x.fim, "Tipo": ROTULO_IMPEDIMENTO.get(x.tipo, x.tipo),
                          "Escala": ", ".join(escalas_do_mil[x.militar_id]),
                          "Militar": nomes_m.get(x.militar_id, x.militar_id),
                          "Justificativa / detalhe": " · ".join(t for t in (x.motivo, x.anexo) if t)}))
for x in ctx.ocorrencias:
    if x.escala_id in minhas:
        itens.append((x, {"Início": x.data, "Fim": x.data, "Tipo": "Dispensa no dia do serviço",
                          "Escala": minhas[x.escala_id].nome, "Militar": nomes_m.get(x.militar_id, x.militar_id),
                          "Justificativa / detalhe": x.motivo}))
for x in ctx.guarnecimentos:
    if x.escala_id in minhas:
        itens.append((x, {"Início": x.data, "Fim": x.data, "Tipo": "Guarnece" if x.guarnece else "Não guarnece",
                          "Escala": minhas[x.escala_id].nome, "Militar": "—", "Justificativa / detalhe": "Decisão do comando"}))
for x in ctx.eventos:
    if x.escala_id in minhas:
        itens.append((x, {"Início": x.data, "Fim": x.data, "Tipo": "Evento", "Escala": minhas[x.escala_id].nome,
                          "Militar": "—", "Justificativa / detalhe": " · ".join(t for t in (x.descricao, x.hora, x.local) if t)}))

def _quem(x) -> str:
    u = ctx.usuario(x.criado_por) if x.criado_por else None
    return u.nome if u else "—"


for x, d in itens:                                  # quem lançou e quando (dados antigos não têm); e a última edição
    d["Lançado por"], d["Lançado em"] = _quem(x), (f"{x.criado_em:%d/%m/%Y %H:%M}" if x.criado_em else "—")
    ua = ctx.usuario(x.alterado_por) if x.alterado_por else None
    d["Alterado"] = (f"{ua.nome if ua else '—'} em {x.alterado_em:%d/%m/%Y %H:%M}" if x.alterado_em else "")

with st.container(border=True):
    ui.secao("Lançamentos")
    f1, f2, f3 = st.columns([1.3, 1.2, 1.2])
    todos_periodos = f1.checkbox("Todos os períodos", True, key="lf_todos")
    hoje = date.today()
    per = f1.date_input("Período", (hoje - timedelta(days=30), hoje + timedelta(days=60)), format="DD/MM/YYYY",
                        key="lf_per", disabled=todos_periodos)
    tipos_disp = sorted({d["Tipo"] for _, d in itens})
    f_tipo = f2.multiselect("Tipo", tipos_disp, key="lf_tipo", placeholder="Todos os tipos")
    f_esc = f2.multiselect("Escala (detalhe)", sorted({e.nome for e in escalas_ok}), key="lf_esc", placeholder="Todas as escalas")
    f_mil = f3.text_input("Militar", key="lf_mil", placeholder="Nome ou parte do nome")
    f_por = f3.multiselect("Lançado por", sorted({d["Lançado por"] for _, d in itens}), key="lf_por", placeholder="Qualquer pessoa")
    f_txt = f3.text_input("Buscar no texto", key="lf_txt", placeholder="Justificativa, local, descrição…")

    def passa(d: dict) -> bool:
        if not todos_periodos and isinstance(per, (tuple, list)) and len(per) == 2:
            ini, fim = d["Início"], d["Fim"] or date.max          # sem data final: vale daí em diante
            if not (ini <= per[1] and fim >= per[0]):
                return False
        if f_tipo and d["Tipo"] not in f_tipo:
            return False
        if f_esc and not any(n in f_esc for n in d["Escala"].split(", ")):
            return False
        if f_mil and f_mil.lower() not in d["Militar"].lower():
            return False
        if f_por and d["Lançado por"] not in f_por:
            return False
        if f_txt and f_txt.lower() not in " ".join(str(v) for v in d.values() if v is not None).lower():
            return False
        return True

    vistos = sorted((par for par in itens if passa(par[1])), key=lambda par: (par[1]["Início"], par[1]["Tipo"]), reverse=True)
    if not vistos:
        ui.vazio("Nenhum lançamento", "Nada com esses filtros. Use Incluir para lançar." if itens else "Use Incluir para lançar.", "list")
    else:
        df = pd.DataFrame([{"Marcar": False, **d} for _, d in vistos])
        ed = st.data_editor(df, hide_index=True, width="stretch", key=f"lf_tab_{len(vistos)}",
                            disabled=[c for c in df.columns if c != "Marcar"],
                            column_config={"Marcar": st.column_config.CheckboxColumn(width="small"),
                                           "Início": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                           "Fim": st.column_config.DateColumn(format="DD/MM/YYYY")})
        st.caption(f"{len(vistos)} lançamento(s)" + (f" de {len(itens)}" if len(vistos) != len(itens) else "") + ".")
        marcados = [vistos[i][0] for i in ed.index[ed["Marcar"]]]
        b_ed, b_rm, _ = st.columns([1, 1.4, 3])
        if b_ed.button("Editar", icon=":material/edit:", disabled=len(marcados) != 1, key="lf_ed",
                       help="Marque um lançamento na tabela para editar." if len(marcados) != 1 else None):
            dialogo_editar(marcados[0])
        with b_rm.popover("Remover marcados", icon=":material/delete:", disabled=not marcados):
            st.write(f"{len(marcados)} lançamento(s) marcado(s). A escala volta a ser calculada sem eles. **Tem certeza?**")
            if st.button("Sim, remover", key="lf_rm", type="primary"):
                agir(lambda: [lc.remover(ctx, uid, x) for x in marcados] and None, "Lançamentos removidos.")

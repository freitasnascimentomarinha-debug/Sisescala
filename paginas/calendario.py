"""Calendário da escala: feriados, licenças administrativas, pontos facultativos e períodos roxos.

Aqui se define como cada dia ou período conta para a fila da escala: automático (feriado e sem expediente = vermelha),
preta, vermelha ou roxa. Detalhista e auxiliar lançam dias; período roxo é regra da escala (só o detalhista).
"""
from datetime import date

import pandas as pd
import streamlit as st

from sisescala import lancamentos as lc
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.calendario import feriados_oficiais, pontos_facultativos, uf_da_escala
from sisescala.modelos import DiaEspecial, PeriodoRoxa
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid = P.ctx, P.uid
escalas_ok = lc.escalas_lancaveis(ctx, uid)
ui.cabecalho("Calendário da escala", "Feriados, licenças administrativas, pontos facultativos e períodos roxos: como cada dia conta na fila.",
             "calendar")
if not escalas_ok:
    ui.vazio("Sem permissão", "Só o detalhista e o auxiliar de uma escala lançam dias especiais.", "shield")
    st.stop()

eid = st.selectbox("Escala", [e.id for e in escalas_ok], format_func=lambda i: ctx.escala(i).nome, key="cal_esc")
esc = ctx.escala(eid)
sou_detalhista = pm.eh_detalhista(ctx, uid, esc)
uf = uf_da_escala(ctx, esc)
st.html("".join([ui.chip("Funciona", "todos os dias" if esc.funciona_em == "todos" else "só dias úteis"),
                 ui.chip("Participa da roxa", "sim" if esc.participa_roxa else "não"),
                 ui.chip("UF dos feriados", uf or "—"), ui.chip("Modo", {"corrida": "Corrida", "preta_vermelha": "Preta e vermelha", "eventos": "Por evento"}.get(esc.modo, esc.modo))]))
st.caption("Como contam: **preta** = dia útil · **vermelha** = sábado, domingo, feriado e dia sem expediente · "
           "**roxa** = período com fila própria (recesso etc.). Para mudar quando a escala funciona ou se participa da roxa, "
           "use Escalas → Editar.")

CONTA = {"": "Automático (feriado e sem expediente contam como vermelha)", "preta": "Preta (conta como dia útil)",
         "vermelha": "Vermelha (conta como sábado, domingo ou feriado)"}
TIPOS = {"feriado": "Feriado", "licenca": "Licença administrativa / sem expediente",
         "facultativo": "Ponto facultativo", "roxa": "Período roxo (fila própria)"}


@st.dialog("Incluir no calendário", width="large")
def dialogo_incluir():
    ids_tipos = list(TIPOS) if sou_detalhista else [t for t in TIPOS if t != "roxa"]
    tipo = st.selectbox("1 · O que é", ids_tipos, format_func=TIPOS.get, key="cal_tipo")
    sug_data, sug_nome = None, ""
    if tipo == "facultativo":
        sugestoes = sorted(pontos_facultativos(date.today().year, uf).items())
        sel = st.selectbox("Começar de uma sugestão do ano", [""] + [d.isoformat() for d, _ in sugestoes], key="cal_sug",
                           format_func=lambda v: "— digitar manualmente —" if not v else
                           f"{date.fromisoformat(v):%d/%m} · {dict(sugestoes)[date.fromisoformat(v)]}")
        if sel:
            sug_data, sug_nome = date.fromisoformat(sel), dict(sugestoes)[date.fromisoformat(sel)]
    k = f"{tipo}_{sug_data}"
    a, b = st.columns(2)
    ini = a.date_input("2 · Data", sug_data or date.today(), format="DD/MM/YYYY", key=f"cal_ini_{k}")
    periodo = b.checkbox("É um período (mais de um dia)", key=f"cal_per_{k}", value=tipo == "roxa")
    fim = b.date_input("Até", ini, format="DD/MM/YYYY", key=f"cal_fim_{k}") if periodo else None
    nome = st.text_input("3 · Descrição" if tipo != "roxa" else "3 · Nome do período roxo", sug_nome, key=f"cal_nome_{k}",
                         placeholder="Aniversário da cidade, licença administrativa, Recesso de fim de ano…")
    conta = ""
    if tipo == "roxa":
        st.info("O período roxo tem fila própria e a escala funciona todos os dias dele.")
        if not esc.participa_roxa:
            st.warning("Esta escala não participa da roxa. Ative em Escalas → Editar para o período valer.")
    else:
        conta = st.radio("4 · Como o dia conta", list(CONTA), format_func=CONTA.get, key=f"cal_conta_{k}")
    todas = P.user.admin and st.checkbox("Vale para todas as escalas do sistema (administrador)", key=f"cal_todas_{k}")
    suas = [e.id for e in escalas_ok if pm.eh_detalhista(ctx, uid, e)]        # só onde a pessoa é detalhista
    destinos = [eid]
    if not todas:
        if len(suas) > 1 and eid in suas:
            destinos = st.multiselect("Vale para estas escalas (só as que você é detalhista)", suas, default=[eid],
                                      format_func=lambda i: ctx.escala(i).nome, key=f"cal_dest_{k}_{eid}",
                                      help="O mesmo lançamento é feito em cada escala escolhida, sem precisar repetir.")
        elif len(suas) == 1 or eid not in suas:
            st.caption(f"Vale para a escala {esc.nome}.")
    if st.button("Salvar", type="primary", use_container_width=True, key=f"cal_ok_{k}"):
        def _salvar():
            if todas:
                alvos = [""]
            else:
                alvos = destinos
            if tipo == "roxa":
                if todas:
                    lc.lancar_periodo_roxo(ctx, uid, PeriodoRoxa("", nome, ini, fim or ini, ""))
                    return
                feitos = lc.lancar_periodo_roxo_em(ctx, uid, PeriodoRoxa("", nome, ini, fim or ini, ""), alvos)
            else:
                tp = "feriado" if tipo == "feriado" else "sem_expediente"
                if todas:
                    lc.lancar_dia_especial(ctx, uid, DiaEspecial(ini, tp, nome, "", fim, conta))
                    return
                feitos = lc.lancar_dia_especial_em(ctx, uid, DiaEspecial(ini, tp, nome, "", fim, conta), alvos)
            pulou = len(alvos) - len(feitos)
            if pulou:
                st.session_state["aviso"] = f"{pulou} escala(s) já tinham esse mesmo lançamento e foram puladas."
        agir(_salvar, "Lançado no calendário." if len(destinos) <= 1 or todas else f"Lançado em {len(destinos)} escalas.")


if st.button("Incluir", type="primary", icon=":material/add:"):
    dialogo_incluir()

# ------------------------------------------------------------------ lista com filtros
itens = []
for x in ctx.dias_especiais:
    if not x.escala_id or x.escala_id == eid:
        itens.append((x, {"Início": x.data, "Fim": x.data_fim or x.data,
                          "Tipo": "Feriado" if x.tipo == "feriado" else "Licença / sem expediente",
                          "Conta como": {"": "Automático (vermelha)", "preta": "Preta", "vermelha": "Vermelha"}[x.conta_como],
                          "Descrição": x.descricao, "Vale para": "Todas as escalas" if not x.escala_id else "Esta escala"}))
for x in ctx.roxas:
    if not x.escala_id or x.escala_id == eid:
        itens.append((x, {"Início": x.inicio, "Fim": x.fim, "Tipo": "Período roxo", "Conta como": "Roxa",
                          "Descrição": x.nome, "Vale para": "Todas as escalas" if not x.escala_id else "Esta escala"}))
for x, d in itens:
    u = ctx.usuario(x.criado_por) if x.criado_por else None
    d["Lançado por"], d["Lançado em"] = (u.nome if u else "—"), (f"{x.criado_em:%d/%m/%Y %H:%M}" if x.criado_em else "—")

with st.container(border=True):
    ui.secao("Lançado no calendário")
    f1, f2, f3 = st.columns(3)
    anos = sorted({d["Início"].year for _, d in itens} | {date.today().year})
    f_ano = f1.selectbox("Ano", ["Todos", *anos], index=0, key="cal_ano")
    f_tipo = f2.multiselect("Tipo", sorted({d["Tipo"] for _, d in itens}), key="cal_ftipo", placeholder="Todos os tipos")
    f_txt = f3.text_input("Buscar no texto", key="cal_ftxt", placeholder="Descrição, nome da pessoa…")
    vistos = [(x, d) for x, d in itens
              if (f_ano == "Todos" or d["Início"].year == f_ano or d["Fim"].year == f_ano)
              and (not f_tipo or d["Tipo"] in f_tipo)
              and (not f_txt or f_txt.lower() in " ".join(str(v) for v in d.values() if v is not None).lower())]
    vistos.sort(key=lambda par: par[1]["Início"])
    if not vistos:
        ui.vazio("Nada lançado", "Use Incluir para lançar feriado, licença, ponto facultativo ou período roxo.", "calendar")
    else:
        df = pd.DataFrame([{"Remover": False, **d} for _, d in vistos])
        ed = st.data_editor(df, hide_index=True, width="stretch", key=f"cal_tab_{len(vistos)}",
                            disabled=[c for c in df.columns if c != "Remover"],
                            column_config={"Remover": st.column_config.CheckboxColumn(width="small"),
                                           "Início": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                           "Fim": st.column_config.DateColumn(format="DD/MM/YYYY")})
        marcados = [vistos[i][0] for i in ed.index[ed["Remover"]]]
        with st.popover("Remover marcados", icon=":material/delete:", disabled=not marcados):
            st.write(f"{len(marcados)} item(ns) marcado(s). A escala volta a ser calculada sem eles. **Tem certeza?**")
            if st.button("Sim, remover", key="cal_rm", type="primary"):
                agir(lambda: [lc.remover(ctx, uid, x) for x in marcados] and None, "Removido do calendário.")

ano_ref = st.session_state.get("cal_ano_ref", P.inicio.year)
with st.expander("Feriados oficiais e pontos facultativos do ano"):
    ano_ref = st.number_input("Ano", 2020, 2100, P.inicio.year, key="cal_ano_ref")
    a, b = st.columns(2)
    with a:
        st.markdown(f"**Feriados oficiais ({uf or 'nacionais'})**: já entram sozinhos como vermelha")
        for d, n in sorted(feriados_oficiais(int(ano_ref), uf).items()):
            st.write(f"{d:%d/%m} – {n}")
    with b:
        st.markdown("**Pontos facultativos sugeridos**: o comando decide; use Incluir → Ponto facultativo")
        for d, n in sorted(pontos_facultativos(int(ano_ref), uf).items()):
            st.write(f"{d:%d/%m} – {n}")

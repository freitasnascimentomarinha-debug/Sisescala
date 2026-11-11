"""Escala: prévia clicável, pedido de troca (papeleta) e disponibilidade de troca."""
from datetime import date, datetime, timedelta

import streamlit as st

from sisescala import disponibilidade as dp
from sisescala import papeletas as pp
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.componente import previa_interativa
from sisescala.modelos import CATEGORIAS
from sisescala.pdf import pdf_papeleta
from sisescala.previa import html_previa, resumo_escala
from sisescala.sessao import barra_contexto, exigir_escala, fmt_dia, pagina

DIAS_PASSADOS = 14        # quantos dias para trás a tabela deixa rolar
P = pagina()
ctx, user, uid, res, dias = P.ctx, P.user, P.uid, P.res, P.dias
esc = exigir_escala(P)
nomes_m = P.nomes_m
eh_editor = pm.eh_detalhista(ctx, uid, esc)
meu_militar = pp.militar_do_usuario(ctx, uid)
em_pedido = pp.militares_em_pedido_ativo(ctx)
membros = sorted({p.militar_id for p in esc.membros}, key=lambda i: ctx.antig(esc, i))
abertas_ = dp.abertas(ctx, res, esc.id)

chips = [ui.chip("Prioridade", esc.prioridade), ui.chip("Escalados/dia", esc.militares_dia),
         ui.chip("Retém", esc.retem_qtd), ui.chip("Descanso", f"{esc.folgas_minimas}x1")]
if esc.quartos:
    chips.append(ui.chip("Quartos", f"{len(esc.quartos)}"))
ui.cabecalho(esc.nome, f"{CATEGORIAS[esc.categoria][0]}{' · ' + esc.tipo if esc.tipo else ''} · "
                       f"{dias[0]:%d/%m} a {dias[-1]:%d/%m/%Y}", "calendar", chips)
barra_contexto(P, periodo=True)
for av in res.avisos:
    if av.startswith("CONFLITO"):
        st.error(av)

rs = resumo_escala(ctx, esc, dias)
with st.container(border=True):
    def _n(x):
        return f"{x:g}"
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ritmo hoje", f"{_n(rs['ritmo_hoje'])}x1", help="Quantos disponíveis hoje para cada vaga de serviço: cada um volta a "
              "servir em, em média, esse número de dias. Já desconta quem está impedido.")
    m2.metric("Pessoas na escala", rs["militares"], help="Militares que podem ser escalados (o detalhista fora da escala não conta).")
    m3.metric("Impedidos hoje", rs["impedidos_hoje"], help="Férias, curso, dispensa, desembarque, destaque ou baixa em vigor hoje.")
    m4.metric("Disponíveis hoje", rs["disponiveis_hoje"])
    linhas = []
    if rs["ritmo_hoje"] < rs["minimo"]:
        linhas.append(f":red[**Atenção:** o ritmo de hoje ({_n(rs['ritmo_hoje'])}x1) está abaixo do mínimo da escala ({rs['minimo']}x1).]")
    if rs["pior_dia"] and rs["ritmo_pior"] < rs["ritmo_hoje"]:
        linhas.append(f"Pior dia do período: {rs['pior_dia']:%d/%m} com {_n(rs['ritmo_pior'])}x1.")
    if rs["por_tipo"]:
        linhas.append("Impedidos no período (" + str(rs["impedidos_periodo"]) + "): " +
                      " · ".join(f"{k} {v}" for k, v in rs["por_tipo"].items()))
    if linhas:
        st.caption("  \n".join(linhas))
with st.container(border=True):
    passados = [dias[0] - timedelta(days=k) for k in range(DIAS_PASSADOS, 0, -1) if dias[0] - timedelta(days=k) >= ctx.base_de(esc)]
    clique = previa_interativa(html_previa(ctx, res, passados + list(dias), esc.id, abertas_, com_card=False, ancora=dias[0]),
                               st.session_state.get("sel"), key="previa")
    if clique and clique.get("ts") != st.session_state.get("_ult_ts"):
        st.session_state["_ult_ts"] = clique["ts"]
        st.session_state["sel"] = clique
        st.session_state["_novo_clique"] = True
    st.caption("Clique numa célula: no seu serviço, abre a disponibilidade; no de um colega, pré-preenche a troca.")


def dias_servico(mid):
    return sorted(d for (d, e), de in res.dias.items() if e == esc.id and d >= ctx.base_de(esc)
                  for a in de.alocacoes if a.militar_id == mid and a.origem == "normal")


quem_sinaliza = membros if eh_editor else ([meu_militar] if meu_militar in membros else [])
# --- clique na prévia pré-preenche os formulários
if st.session_state.pop("_novo_clique", False) and st.session_state.get("sel"):
    dsel, msel = date.fromisoformat(st.session_state["sel"]["data"]), st.session_state["sel"]["militar"]
    if msel in membros and dsel in dias_servico(msel):
        if msel == meu_militar and msel in quem_sinaliza and dsel >= date.today():
            st.session_state["dp_m"], st.session_state["dp_d"] = msel, dsel
            st.toast(f"Disponibilidade: {nomes_m[msel]} em {fmt_dia(dsel)}", icon="🟢")
        elif msel not in em_pedido and msel != st.session_state.get("pp_x", meu_militar):
            st.session_state["pp_y"], st.session_state["pp_dy"] = msel, dsel
            st.toast(f"Troca com {nomes_m[msel]} em {fmt_dia(dsel)}", icon="🔁")
        else:
            st.toast("Esse serviço não pode ser selecionado agora.", icon="⚠️")

col_troca, col_disp = st.columns([1.5, 1], gap="large")

# ------------------------------------------------------------------ troca de serviço
with col_troca:
    with st.container(border=True):
        ui.secao("Pedir troca de serviço")
        if eh_editor:
            quem_pede = [m for m in membros if m not in em_pedido]
        else:
            quem_pede = [meu_militar] if meu_militar in membros and meu_militar not in em_pedido else []
            if meu_militar in em_pedido:
                q = em_pedido[meu_militar]
                st.info(f"Você já tem a papeleta {q.numero:04d} em andamento. Conclua ou cancele antes de pedir outra.")
            elif meu_militar not in membros:
                st.caption("Você não faz parte desta escala.")
        bloq = [ctx.militar(m).nome for m in membros if m in em_pedido]
        if bloq:
            st.caption("Em pedido ativo (não podem ser selecionados): " + ", ".join(bloq))
        if not meu_militar and not eh_editor:
            ui.vazio("Só militar vinculado pede troca",
                     "A sua conta ainda não está vinculada a um militar. A vinculação precisa da autorização do detalhista.", "link")
            st.page_link("paginas/vinculos.py", label="Pedir vínculo ao meu nome", icon=":material/link:")
        elif not quem_pede:
            ui.vazio("Pedido indisponível", "Só quem está na escala e sem pedido ativo pode pedir.", "swap")
        else:
            t1, t2 = st.columns(2)
            sx = t1.selectbox("Quem pede a troca", quem_pede, format_func=nomes_m.get, key="pp_x")
            ddx = dias_servico(sx)
            dx = t1.selectbox("Dia do serviço dele", ddx, format_func=fmt_dia, key="pp_dx") if ddx else None
            opcoes_y = [m for m in membros if m != sx and m not in em_pedido]
            sy = t2.selectbox("Trocar com", opcoes_y, key="pp_y",
                              format_func=lambda m: nomes_m[m] + (" ●" if any(k[1] == m for k in abertas_) else "")) \
                if opcoes_y else None
            ddy = dias_servico(sy) if sy else []
            dy = t2.selectbox("Dia do serviço do outro", ddy, key="pp_dy",
                              format_func=lambda d: fmt_dia(d) + (" ● aberto a troca" if (d, sy) in abertas_ else ""),
                              index=next((i for i, d in enumerate(ddy) if d != dx), 0)) if ddy else None
            mot = st.text_input("Motivo da troca (obrigatório)", key="pp_mot")
            if dx and dy:
                erros, avisos, _ = pp.validar_troca(ctx, esc, sx, dx, sy, dy)
                agora = datetime.now()
                if not erros and not pp.antecedencia_ok(esc, dx, dy, agora):
                    erros.append(f"mínimo de {esc.antecedencia_horas}h de antecedência do primeiro serviço")
                st.html(f'<div class="person" style="margin:.4rem 0"><div style="width:20px;height:20px">{ui.icone("swap", 20, "blue")}</div><div><b>{ui.esc(nomes_m[sx])} '
                        f'dará o serviço de {ui.esc(fmt_dia(dy))}</b><small>{ui.esc(nomes_m[sy])} dará o de '
                        f'{ui.esc(fmt_dia(dx))}</small></div></div>')
                for t in erros:
                    st.error(t)
                for t in avisos:
                    st.warning(t)
                if not user.pin_hash:
                    st.warning("Cadastre o seu PIN em Minha conta para poder pedir a troca.")
                pin_in = st.text_input("Seu PIN para confirmar o pedido", type="password", key="pp_pin")
                pronto = not erros and mot.strip() and user.pin_hash
                if st.button("Confirmar e gerar papeleta", type="primary", disabled=not pronto):
                    try:
                        novo = pp.criar(ctx, uid, esc.id, sx, dx, sy, dy, mot, agora, pin=pin_in)
                        st.success(f"Papeleta {novo.numero:04d} criada. Assinem pelo sistema em Papeletas; "
                                   "a prévia só muda depois que o detalhista aprovar.")
                        st.download_button("Baixar documento (PDF)", pdf_papeleta(ctx, novo),
                                           f"papeleta_{novo.numero:04d}.pdf", "application/pdf", key=f"dl_novo_{novo.id}")
                    except (ValueError, pm.PermissaoNegada) as ex:
                        st.error(str(ex))
            else:
                st.caption("Os dois militares precisam ter serviço (efetivo ou retém) no período para a troca.")

# ------------------------------------------------------------------ disponibilidade
with col_disp:
    with st.container(border=True):
        ui.secao("Disponibilidade de troca")
        st.caption("Sinaliza na prévia, com uma bolinha piscando, que o seu serviço está aberto a troca.")
        if not quem_sinaliza:
            ui.vazio("Sem serviço seu aqui", "Só quem está escalado pode sinalizar.", "clock")
        else:
            sm = st.selectbox("Militar", quem_sinaliza, format_func=nomes_m.get, key="dp_m")
            futuros = [d for d in dias_servico(sm) if d >= date.today()]
            if futuros:
                dd = st.selectbox("Dia do serviço", futuros, key="dp_d",
                                  format_func=lambda d: fmt_dia(d) + (" ● aberto" if (d, sm) in abertas_ else ""))
                aberta = (dd, sm) in abertas_
                if st.button("Fechar disponibilidade" if aberta else "Abrir disponibilidade de troca", key="dp_b",
                             type="secondary" if aberta else "primary"):
                    try:
                        dp.alternar(ctx, uid, esc.id, sm, dd, res)
                        st.session_state["toast"] = "Disponibilidade atualizada."
                        st.rerun()
                    except (ValueError, pm.PermissaoNegada) as ex:
                        st.error(str(ex))
            else:
                st.caption("Sem serviço futuro nesta prévia.")
        if abertas_:
            ui.secao("Abertos a troca agora")
            for (d, m), _ in sorted(abertas_.items()):
                st.html(ui.item_data(d, nomes_m[m], fmt_dia(d), ui.pill("aberto", "verde")))
    n_dev = len([x for x in pp.devolucoes_em_aberto(ctx, res, {esc.id}) if x["estado"] != "em_andamento"])
    if n_dev:
        st.page_link("paginas/devolucoes.py", label=f"{n_dev} serviço(s) a devolver nesta escala", icon=":material/undo:",
                     use_container_width=True)

"""Painel: o que precisa de atenção hoje e quem está de serviço."""
from datetime import date, datetime

import streamlit as st

from sisescala import notificacoes as nt
from sisescala import papeletas as pp
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.motor import gerar
from sisescala.sessao import fmt_dia, pagina

P = pagina()
ctx, user, uid = P.ctx, P.user, P.uid
hoje = date.today()
meu_m = pp.militar_do_usuario(ctx, uid)
saud = "Bom dia" if datetime.now().hour < 12 else "Boa tarde" if datetime.now().hour < 18 else "Boa noite"
dia_sem = "segunda terça quarta quinta sexta sábado domingo".split()[hoje.weekday()]
ui.cabecalho(f"{saud}, {user.nome.split()[0]}", f"{dia_sem}-feira, {hoje:%d/%m/%Y}".replace("sábado-feira", "sábado").replace("domingo-feira", "domingo"),
             "home", [ui.chip("Perfil", "Administrador" if user.admin else "Detalhista" if P.gerir else "Militar")])

# ------------------------------------------------------------------ números
esc_ids = {e.id for e in P.visiveis}
ed_ids = {e.id for e in P.editaveis()}
res_dev = gerar(ctx, max([hoje] + [d.prazo for d in P.res.devolucoes]))
devs = [x for x in pp.devolucoes_em_aberto(ctx, res_dev, esc_ids)
        if x["estado"] != "em_andamento" and (x["devolucao"].militar_id == meu_m or x["devolucao"].escala_id in ed_ids)]
meus = [(d, e) for (d, e), de in P.res.dias.items() if d >= hoje and e in esc_ids
        for a in de.efetivos if a.militar_id == meu_m] if meu_m else []
minhas_pap = [p for p in ctx.papeletas if p.status in pp.ABERTAS and pp.e_parte(ctx, uid, p)]
a_assinar = [p for p in minhas_pap if meu_m not in p.assinaturas]
conflitos = [a for a in P.res.avisos if a.startswith("CONFLITO")]

if P.gerir:
    ui.kpis([("Pedidos de troca", P.n_pend, "swap", "ambar" if P.n_pend else "cinza", "aguardando a sua decisão"),
             ("Vínculos", P.n_vinc, "link", "ambar" if P.n_vinc else "cinza", "aguardando a sua decisão"),
             ("Serviços a devolver", len(devs), "undo", "azul", "nas suas escalas"),
             ("Conflitos na escala", len(conflitos), "alert", "vermelho" if conflitos else "verde",
              "sem troca possível" if conflitos else "tudo resolvido")])
else:
    ui.kpis([("Meus próximos serviços", len(meus), "calendar", "azul", "nos próximos dias"),
             ("Papeletas em andamento", len(minhas_pap), "swap", "violeta"),
             ("Assinaturas pendentes", len(a_assinar), "key", "ambar" if a_assinar else "verde"),
             ("Serviços a devolver", len(devs), "undo", "vermelho" if devs else "verde")])

# ------------------------------------------------------------------ pendências e hoje
esq, dir_ = st.columns([1.15, 1], gap="large")
with esq:
    with st.container(border=True):
        ui.secao("Precisa da sua atenção")
        itens = []
        if P.gerir and P.n_pend:
            itens.append(("paginas/papeletas.py", f"{P.n_pend} pedido(s) de troca aguardando decisão", ":material/swap_horiz:"))
        if P.gerir and P.n_vinc:
            itens.append(("paginas/vinculos.py", f"{P.n_vinc} pedido(s) de vínculo aguardando decisão", ":material/link:"))
        if a_assinar:
            itens.append(("paginas/papeletas.py", f"{len(a_assinar)} papeleta(s) aguardando a sua assinatura", ":material/draw:"))
        if devs:
            itens.append(("paginas/devolucoes.py", f"{len(devs)} serviço(s) a devolver", ":material/undo:"))
        if conflitos and P.gerir:
            itens.append(("paginas/escala.py", f"{len(conflitos)} conflito(s) de escala sem troca possível", ":material/warning:"))
        if not user.pin_hash:
            itens.append(("paginas/conta.py", "Cadastre o seu PIN (necessário para pedir trocas e assinar)", ":material/key:"))
        if not user.militar_id and not P.gerir:
            itens.append(("paginas/vinculos.py", "Vincule a sua conta ao seu nome na escala", ":material/link:"))
        if not itens:
            ui.vazio("Tudo em dia", "Nada pendente por aqui.", "check")
        for pagina_, rotulo, ic in itens:
            st.page_link(pagina_, label=rotulo, icon=ic, use_container_width=True)
    with st.container(border=True):
        ui.secao("Hoje")
        if not P.visiveis:
            ui.vazio("Sem escalas", "Você ainda não tem acesso a nenhuma escala.", "calendar")
        for e in P.visiveis[:5]:
            dia = P.res.dia(hoje, e.id)
            if not dia or not dia.funciona:
                corpo = '<span style="color:var(--muted)">não guarnece hoje</span>'
            else:
                corpo = " ".join(ui.pill(ctx.militar(a.militar_id).nome, "azul", False) for a in dia.efetivos) or "—"
                rt = " ".join(ui.pill(ctx.militar(a.militar_id).nome, "cinza", False) for a in dia.retens)
                corpo += f'  <span style="color:var(--muted);font-size:.75rem;margin-left:.5rem">RT</span> {rt}' if rt else ""
            st.html(f'<div class="item"><div class="tx" style="flex:1"><b>{ui.esc(e.nome)}</b>'
                    f'<span>{ui.esc(e.tipo or "")}</span></div><div>{corpo}</div></div>')
with dir_:
    with st.container(border=True):
        ui.secao("Meus próximos serviços" if meu_m else "Sua conta")
        if meu_m:
            prox = sorted(meus)[:5]
            if not prox:
                ui.vazio("Nenhum serviço à frente", "Você não está escalado nos próximos dias.", "calendar")
            for d, e_id in prox:
                a = next(x for x in P.res.dia(d, e_id).efetivos if x.militar_id == meu_m)
                st.html(ui.item_data(d, ctx.escala(e_id).nome, a.sigla + (f" · {', '.join(h.split('-')[0] for h in a.horarios)}" if a.horarios else "")))
        else:
            st.html(f'<div class="person">{ui.avatar(user.nome)}<div><b>{ui.esc(user.nome)}</b>'
                    f'<small>{ui.esc(user.email or "sem e-mail")} · {ui.esc(user.celular or "sem celular")}</small></div></div>')
    with st.container(border=True):
        ui.secao("Atividade recente")
        ultimas = nt.do_usuario(ctx, uid)[:6]
        if not ultimas:
            ui.vazio("Sem novidades", "Os avisos aparecem aqui.", "bell")
        for n in ultimas:
            st.html(f'<div class="item"><div class="tx" style="flex:1"><b>{ui.esc(n.texto)}</b>'
                    f'<span>{n.criado_em:%d/%m %H:%M}</span></div>{ui.pill("novo", "azul") if not n.lida else ""}</div>')
        st.page_link("paginas/notificacoes.py", label="Ver todas as notificações", icon=":material/notifications:")

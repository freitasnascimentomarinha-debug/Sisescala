"""SisEscala – app Streamlit (protótipo). Rodar: streamlit run app.py"""
import dataclasses
import os
from datetime import date, datetime

import streamlit as st

import pandas as pd

from sisescala import auth
from sisescala import cadastro as cd
from sisescala import papeletas as pp
from sisescala import permissoes as pm
from sisescala.importacao import MODELO_CSV, importar, ler_tabela
from sisescala.calendario import pontos_facultativos
from sisescala.demo import contexto_demo
from sisescala.modelos import (CATEGORIAS, TIPOS_IMPEDIMENTO, DiaEspecial, Escala, Evento, Guarnecimento,
                               Impedimento, Ocorrencia, Pertinencia, quartos_padrao)
from sisescala.motor import gerar, validar_escala
from sisescala.persistencia import ConflitoDeVersao, Repositorio, criar_repositorio
from sisescala.pdf import gerar_pdf, pdf_papeleta
from sisescala.previa import html_previa, periodo
from sisescala.relatorio import html_regras, pdf_regras

st.set_page_config(page_title="SisEscala", layout="wide")


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
    repo = st.session_state.repo
    ctx_ = repo.carregar()
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
            st.session_state.aviso = ("Outra pessoa alterou os dados ao mesmo tempo. Recarreguei a versão mais "
                                      "recente; refaça a sua última ação se ela não aparecer.")
            return
        if repo.desatualizado():
            _carregar_novo()
    except Exception as ex:   # rede, cota da API, permissão da planilha
        st.error(f"Não consegui acessar o armazenamento ({ARMAZENAMENTO}): {ex}")
        st.stop()


_sincronizar()
ctx = st.session_state.ctx
# ---------------------------------------------------------------- login
user = ctx.usuario(st.session_state.get("uid", ""))
if user is None or not user.ativo:
    st.session_state.pop("uid", None)
    st.title("SisEscala")
    st.caption(f"Armazenamento: {ARMAZENAMENTO}")
    if not auth.tem_usuarios(ctx):
        st.subheader("Primeiro acesso: criar o administrador")
        with st.form("primeiro"):
            l1, l2, l3 = st.columns(3)
            lg, nm_, sn = l1.text_input("Login"), l2.text_input("Nome"), l3.text_input("Senha (8+ caracteres)", type="password")
            if st.form_submit_button("Criar administrador"):
                try:
                    novo_u = auth.criar_usuario(ctx, None, lg, nm_, sn)
                    st.session_state.uid = novo_u.id
                    st.rerun()
                except ValueError as ex:
                    st.error(str(ex))
    else:
        with st.form("login"):
            lg, sn = st.text_input("Login"), st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                try:
                    st.session_state.uid = auth.entrar(ctx, lg, sn).id
                    st.rerun()
                except auth.AutenticacaoErro as ex:
                    st.error(str(ex))
    st.stop()

uid = user.id
PODE_GERIR = user.perfil == "detalhista"
nomes_u = {u.id: u.nome for u in ctx.usuarios}
nomes_m = {m.id: m.nome for m in ctx.militares}

with st.sidebar:
    st.header("SisEscala")
    st.caption(f"👤 {user.nome} ({'administrador · ' if user.admin else ''}{user.perfil}) · {ARMAZENAMENTO}")
    with st.expander("Minha conta"):
        with st.form("minha_conta", clear_on_submit=True):
            sa, sn1 = st.text_input("Senha atual", type="password"), st.text_input("Nova senha (8+)", type="password")
            if st.form_submit_button("Trocar senha"):
                try:
                    auth.trocar_senha(ctx, uid, sa, sn1)
                    st.success("Senha alterada.")
                except (ValueError, auth.AutenticacaoErro) as ex:
                    st.error(str(ex))
        if st.button("Sair"):
            st.session_state.pop("uid", None)
            st.rerun()
    visiveis = pm.escalas_visiveis(ctx, uid)
    if not visiveis:
        st.info("Você ainda não tem escalas." + (" Crie uma na aba Escalas." if PODE_GERIR else ""))
    eid = st.selectbox("Escala", [e.id for e in visiveis], format_func=lambda i: ctx.escala(i).nome) \
        if visiveis else None
    n_pend = len(pp.pedidos_pendentes(ctx, uid))
    if n_pend:
        st.warning(f"🔔 {n_pend} pedido(s) de troca de serviço aguardando sua decisão (aba Papeletas).")
    if PODE_GERIR:
        st.divider()
        ctx.uf = st.text_input("UF da OM (feriados)", ctx.uf, max_chars=2).upper()
        ctx.janela_devolucao_dias = st.number_input("Prazo de devolução (dias)", 1, 365, ctx.janela_devolucao_dias)
        ctx.janela_troca_dias = st.number_input("Janela da troca forçada (dias)", 1, 60, ctx.janela_troca_dias)
    st.divider()
    inicio = st.date_input("Início da prévia", date.today())
    dias_n = {"7 dias": 7, "15 dias": 15, "1 mês": 30}[st.radio("Período", ["7 dias", "15 dias", "1 mês"])]

if "aviso" in st.session_state:
    st.warning(st.session_state.pop("aviso"))

dias = periodo(inicio, dias_n)
res = gerar(ctx, dias[-1])
esc = ctx.escala(eid) if eid else None
_abas = [("prev", "Prévia"), ("pdf", "Detalhe (PDF)"), ("pap", f"Papeletas{f' ({n_pend})' if n_pend else ''}"),
         ("reg", "Regras da escala")]
if PODE_GERIR:
    _abas += [("lanc", "Lançamentos"), ("esc", "Escalas"), ("mil", "Militares"), ("imp", "Importar planilha")]
if user.admin:
    _abas += [("usr", "Usuários")]
_tabs = dict(zip([k for k, _ in _abas], st.tabs([r for _, r in _abas])))
aba_prev, aba_pdf, aba_pap, aba_reg = (_tabs[k] for k in ("prev", "pdf", "pap", "reg"))
aba_lanc, aba_esc, aba_mil, aba_imp, aba_usr = (_tabs.get(k) for k in ("lanc", "esc", "mil", "imp", "usr"))

with aba_prev:
    if esc:
        for av in res.avisos:
            if av.startswith("CONFLITO"):
                st.error(av)
        st.html(html_previa(ctx, res, dias, esc.id))
        pend = [d for d in res.devolucoes if d.escala_id == esc.id]
        if pend:
            st.subheader("Serviços a devolver")
            for dv in pend:
                st.write(f"{nomes_m[dv.militar_id]} – origem {dv.data_origem:%d/%m}, prazo {dv.prazo:%d/%m}")

with aba_prev:
    if esc:
        st.divider()
        st.subheader("Solicitar troca de serviço (papeleta)")
        eh_editor = pm.pode_editar(ctx, uid, esc)
        meu_militar = pp.militar_do_usuario(ctx, uid)
        em_pedido = pp.militares_em_pedido_ativo(ctx)       # pedido ativo trava as partes
        membros = sorted({p.militar_id for p in esc.membros}, key=lambda i: ctx.militar(i).antiguidade)

        def dias_servico(mid):
            return sorted(d for (d, e), de in res.dias.items() if e == esc.id and d >= ctx.data_base
                          for a in de.alocacoes if a.militar_id == mid and a.origem == "normal")

        fmt_d = lambda d: f"{d:%d/%m/%Y} ({'seg ter qua qui sex sáb dom'.split()[d.weekday()]})"  # noqa: E731
        if eh_editor:
            quem_pede = [m for m in membros if m not in em_pedido]
        else:
            quem_pede = [meu_militar] if meu_militar in membros and meu_militar not in em_pedido else []
            if meu_militar in em_pedido:
                q = em_pedido[meu_militar]
                st.info(f"Você já tem a papeleta {q.numero:04d} em andamento; conclua ou cancele antes de pedir outra.")
            elif meu_militar not in membros:
                st.caption("Você não faz parte desta escala.")
        com_quem = lambda sx: [m for m in membros if m != sx and m not in em_pedido]  # noqa: E731
        if em_pedido:
            bloq = [ctx.militar(m).nome for m in membros if m in em_pedido]
            if bloq:
                st.caption("Em pedido ativo (não podem ser selecionados): " + ", ".join(bloq))
        if quem_pede:
            t1, t2 = st.columns(2)
            sx = t1.selectbox("Militar que pede a troca", quem_pede, format_func=nomes_m.get, key="pp_x")
            ddx = dias_servico(sx)
            dx = t1.selectbox("Dia do serviço dele", ddx, format_func=fmt_d, key="pp_dx") if ddx else None
            opcoes_y = com_quem(sx)
            sy = t2.selectbox("Trocar com", opcoes_y, format_func=nomes_m.get, key="pp_y") if opcoes_y else None
            ddy = dias_servico(sy) if sy else []
            dy = t2.selectbox("Dia do serviço do outro", ddy, format_func=fmt_d, key="pp_dy",
                              index=next((i for i, d in enumerate(ddy) if d != dx), 0)) if ddy else None
            mot = st.text_input("Motivo da troca (obrigatório)", key="pp_mot")
            if dx and dy:
                erros, avisos, _ = pp.validar_troca(ctx, esc, sx, dx, sy, dy)
                agora = datetime.now()
                if not erros and not pp.antecedencia_ok(esc, dx, dy, agora):
                    erros.append(f"mínimo de {esc.antecedencia_horas}h de antecedência do primeiro serviço")
                st.info(f"{nomes_m[sx]} dará o serviço de {fmt_d(dy)} e {nomes_m[sy]} dará o de {fmt_d(dx)}.")
                for t in erros:
                    st.error(t)
                for t in avisos:
                    st.warning(t)
                if not erros and not mot.strip():
                    st.caption("Informe o motivo para continuar.")
                if not erros and mot.strip() and st.button("Confirmar e gerar papeleta"):
                    try:
                        novo = pp.criar(ctx, uid, esc.id, sx, dx, sy, dy, mot, agora)
                        st.success(f"Papeleta {novo.numero:04d} criada. Assinem pelo sistema na aba Papeletas; "
                                   "a prévia só muda depois que o detalhista aprovar.")
                        st.download_button("Baixar documento (PDF)", pdf_papeleta(ctx, novo),
                                           f"papeleta_{novo.numero:04d}.pdf", "application/pdf", key=f"dl_novo_{novo.id}")
                    except (ValueError, pm.PermissaoNegada) as ex:
                        st.error(str(ex))
            else:
                st.caption("Os dois militares precisam ter serviço (efetivo ou retém) no período para a troca.")


def _agir(f):
    try:
        r = f()
        if isinstance(r, list) and r:
            st.session_state.aviso = " ".join(r)      # avisos (ex.: descanso curto) sobrevivem ao rerun
        st.rerun()
    except (ValueError, pm.PermissaoNegada) as ex:
        st.error(str(ex))


with aba_pap:
    if esc:
        eh_editor = pm.pode_editar(ctx, uid, esc)
        lista = pp.papeletas_visiveis(ctx, uid, esc.id)
        if eh_editor:
            st.subheader("Pedidos desta escala")
            st.caption("Você recebe aqui os pedidos de troca. Aprovar aplica a troca na prévia; "
                       "confirme depois que as duas partes assinarem.")
        elif not lista:
            st.caption("Você não tem papeletas nesta escala. Peça uma troca na aba Prévia.")
        ROT = {"pendente": "🟡 pendente", "aprovada": "🟢 aprovada (aguardando assinaturas)", "rejeitada": "🔴 rejeitada",
               "confirmada": "✅ confirmada", "cancelada": "⚪ cancelada"}
        for p in lista:
            x, y = ctx.militar(p.solicitante_id), ctx.militar(p.outro_id)
            sou_parte = pp.e_parte(ctx, uid, p)
            with st.expander(f"Nº {p.numero:04d} · {ROT[p.status]} · {x.nome} ↔ {y.nome}",
                             expanded=p.status in pp.ABERTAS):
                st.markdown(
                    f"**Pedido em** {p.criado_em:%d/%m/%Y às %H:%M} · **Escala:** {esc.nome}  \n"
                    f"**Quem pediu:** {x.posto} {x.nome} · NIP {x.nip or '—'} · OM {x.om or '—'} "
                    f"(lançado por {nomes_u.get(p.criado_por, p.criado_por)})  \n"
                    f"**Troca com:** {y.posto} {y.nome} · NIP {y.nip or '—'} · OM {y.om or '—'}  \n"
                    f"**Serviços:** {x.nome} em {p.data_solicitante:%d/%m/%Y} ↔ {y.nome} em {p.data_outro:%d/%m/%Y}  \n"
                    f"**Motivo:** {p.motivo}")
                if p.motivo_rejeicao:
                    st.write(f"**Motivo da rejeição:** {p.motivo_rejeicao}")
                if eh_editor or sou_parte:
                    st.markdown("**Contas e assinaturas**")
                    for s_ in pp.situacao_partes(ctx, p):
                        conta = f"✔ conta @{s_['login']}" if s_["tem_conta"] else "✖ sem conta no sistema"
                        ass = (f"✔ assinou {s_['em']:%d/%m/%Y %H:%M} "
                               f"({'pelo sistema' if s_['metodo'] == 'conta' else 'documento externo: ' + s_['referencia']})"
                               if s_["assinou"] else "⏳ não assinou")
                        st.write(f"• {s_['militar'].nome} ({s_['papel']}): {conta} · {ass}")
                st.download_button("Baixar documento (PDF)", pdf_papeleta(ctx, p), f"papeleta_{p.numero:04d}.pdf",
                                   "application/pdf", key=f"dl_{p.id}")
                # --- decisão do detalhista/editores
                if eh_editor and p.status == "pendente":
                    b1, b2 = st.columns(2)
                    if b1.button("Aprovar e trocar", key=f"ap_{p.id}"):
                        _agir(lambda: pp.aprovar(ctx, uid, p.id))
                    rej = b2.text_input("Motivo da rejeição", key=f"rjm_{p.id}")
                    if b2.button("Rejeitar", key=f"rj_{p.id}"):
                        _agir(lambda: pp.rejeitar(ctx, uid, p.id, rej))
                # --- as partes cancelam enquanto não aprovado
                if p.status == "pendente" and (sou_parte or p.criado_por == uid) and not eh_editor:
                    if st.button("Cancelar este pedido", key=f"cp_{p.id}"):
                        _agir(lambda: pp.cancelar(ctx, uid, p.id, "cancelado pelo solicitante/parte"))
                # --- assinatura pela própria conta
                minha = pp.militar_do_usuario(ctx, uid)
                if p.status in pp.ABERTAS and sou_parte and minha not in p.assinaturas:
                    with st.form(f"as_{p.id}", clear_on_submit=True):
                        st.caption("Assinar pelo sistema: confirme a senha da sua conta")
                        senha_ass = st.text_input("Senha", type="password")
                        if st.form_submit_button("Assinar"):
                            _agir(lambda: pp.assinar(ctx, p.id, uid, senha_ass))
                if eh_editor and p.status in pp.ABERTAS:
                    with st.form(f"ext_{p.id}", clear_on_submit=True):
                        st.caption("Registrar documento assinado fora do sistema (gov.br, ICP, papel)")
                        e1, e2 = st.columns(2)
                        quem2 = e1.selectbox("Militar ", [p.solicitante_id, p.outro_id], format_func=nomes_m.get)
                        ref = e2.text_input("Link ou nº do documento")
                        if st.form_submit_button("Registrar"):
                            _agir(lambda: pp.registrar_assinatura_externa(ctx, uid, p.id, quem2, ref))
                # --- detalhista: confirmar e cancelar (inclusive depois de aprovar)
                if eh_editor and p.status in ("aprovada", "confirmada"):
                    c1, c2 = st.columns(2)
                    if p.status == "aprovada" and c1.button("Confirmar (assinaturas recebidas)", key=f"cf_{p.id}"):
                        _agir(lambda: pp.confirmar(ctx, uid, p.id))
                    mcanc = c2.text_input("Motivo do cancelamento", key=f"ccm_{p.id}")
                    if c2.button("Cancelar e desfazer a troca", key=f"cc_{p.id}"):
                        _agir(lambda: pp.cancelar(ctx, uid, p.id, mcanc))
                st.caption("Histórico: " + " → ".join(f"{h[0]:%d/%m %H:%M} {h[2]}" for h in p.historico))
        st.caption("Assinatura pelo sistema: o militar entra na própria conta e reconfirma a senha; fica registrado com "
                   "data, hora e código de verificação do documento. Não substitui certificado ICP-Brasil; para isso "
                   "o detalhista registra o documento assinado externamente.")

with aba_pdf:
    if esc:
        om = st.text_input("Organização Militar")
        ins = st.text_area("Instruções do serviço")
        rec = st.text_area("Recomendações")
        reg = st.text_area("Regras (horário de parada, acumulação de trabalho etc.)")
        a1, a2, a3 = st.columns(3)
        ass = (a1.text_input("Detalhista"), a2.text_input("Encarregado do Detalhe"), a3.text_input("Vice-Diretor"))
        st.download_button(f"Gerar PDF – {esc.nome}", gerar_pdf(ctx, res, dias, esc.id, om, ins, rec, reg, ass),
                           f"detalhe_{esc.id}_{dias[0]:%Y%m%d}.pdf", "application/pdf")

with aba_reg:
    if esc:
        st.caption("Gerado a partir da configuração atual: ajustou algo, o relatório muda.")
        st.html(html_regras(ctx, esc))
        st.download_button("Baixar regras em PDF", pdf_regras(ctx, esc), f"regras_{esc.id}.pdf", "application/pdf")

if PODE_GERIR:
    with aba_lanc:
        editaveis = [e.id for e in visiveis if pm.pode_editar(ctx, uid, e)]
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Impedimento / destaque (DTQ)")
            with st.form("imp", clear_on_submit=True):
                mid = st.selectbox("Militar", list(nomes_m), format_func=nomes_m.get)
                tipo = st.selectbox("Tipo", list(TIPOS_IMPEDIMENTO))
                i, f = st.date_input("Início", date.today()), st.date_input("Fim", date.today())
                motivo, anexo = st.text_input("Motivo / OM de destino"), st.text_input("Arquivo/link (obrigatório p/ dispensa)")
                if st.form_submit_button("Lançar"):
                    imp = Impedimento(mid, tipo, i, None if tipo == "desembarque" else f, motivo, anexo)
                    if erros := imp.validar():
                        st.error("; ".join(erros))
                    else:
                        ctx.impedimentos.append(imp); st.rerun()
            if editaveis:
                st.subheader("Falta no serviço (avança o retém)")
                with st.form("oc", clear_on_submit=True):
                    e = st.selectbox("Escala", editaveis, format_func=lambda x: ctx.escala(x).nome)
                    m2 = st.selectbox("Militar escalado", list(nomes_m), format_func=nomes_m.get)
                    dt, mot = st.date_input("Dia", date.today()), st.text_input("Motivo ")
                    if st.form_submit_button("Lançar falta"):
                        ctx.ocorrencias.append(Ocorrencia(dt, e, m2, mot)); st.rerun()
        with c2:
            st.subheader("Feriado / dia sem expediente")
            with st.form("de", clear_on_submit=True):
                dd = st.date_input("Data", date.today())
                tp = st.selectbox("Tipo", ["feriado", "sem_expediente"])
                ds = st.text_input("Descrição (ex.: aniversário da cidade, licença administrativa)")
                if st.form_submit_button("Lançar"):
                    ctx.dias_especiais.append(DiaEspecial(dd, tp, ds)); st.rerun()
            with st.expander(f"Pontos facultativos de {inicio.year} (sugestões)"):
                for d, n in sorted(pontos_facultativos(inicio.year, ctx.uf).items()):
                    st.write(f"{d:%d/%m} – {n}")
            if editaveis:
                st.subheader("Comando guarnece / não guarnece")
                with st.form("gu", clear_on_submit=True):
                    e2 = st.selectbox("Escala ", editaveis, format_func=lambda x: ctx.escala(x).nome)
                    dg, gu = st.date_input("Dia ", date.today()), st.checkbox("Guarnece", True)
                    if st.form_submit_button("Lançar"):
                        ctx.guarnecimentos.append(Guarnecimento(dg, e2, gu)); st.rerun()
                evt = [e for e in editaveis if ctx.escala(e).modo == "eventos"]
                if evt:
                    st.subheader("Evento (palestra, cerimônia, apoio...)")
                    with st.form("ev", clear_on_submit=True):
                        e3 = st.selectbox("Escala  ", evt, format_func=lambda x: ctx.escala(x).nome)
                        de, desc = st.date_input("Data do evento", date.today()), st.text_input("Descrição")
                        hora, local = st.text_input("Hora"), st.text_input("Local")
                        vagas = st.number_input("Vagas (0 = padrão da escala)", 0, 99, 0)
                        if st.form_submit_button("Lançar evento"):
                            ctx.eventos.append(Evento(e3, de, desc, hora, local, vagas or None)); st.rerun()

if PODE_GERIR:
    with aba_lanc:
        st.divider()
        st.subheader("Editar / remover lançamentos")
        ed_ids = {e.id for e in visiveis if pm.pode_editar(ctx, uid, e)}
        def removivel(titulo, lista, rotulo, pertence=lambda x: True):
            idx = [i for i, x in enumerate(lista) if pertence(x)]
            if not idx:
                return
            sel = st.multiselect(titulo, idx, format_func=lambda i: rotulo(lista[i]), key=f"rm_{titulo}")
            if sel and st.button(f"Remover selecionados ({titulo})", key=f"btn_{titulo}"):
                for i in sorted(sel, reverse=True):
                    del lista[i]
                st.rerun()
        removivel("Impedimentos", ctx.impedimentos,
                  lambda x: f"{nomes_m.get(x.militar_id, x.militar_id)} – {TIPOS_IMPEDIMENTO[x.tipo]} {x.inicio:%d/%m}"
                            f"{'–' + format(x.fim, '%d/%m') if x.fim else ''} {x.motivo}")
        removivel("Dias especiais", ctx.dias_especiais, lambda x: f"{x.data:%d/%m} {x.tipo} {x.descricao}")
        removivel("Guarnecimentos", ctx.guarnecimentos,
                  lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: {'guarnece' if x.guarnece else 'não guarnece'}",
                  lambda x: x.escala_id in ed_ids)
        removivel("Faltas", ctx.ocorrencias, lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: {nomes_m.get(x.militar_id)}",
                  lambda x: x.escala_id in ed_ids)
        removivel("Eventos", ctx.eventos, lambda x: f"{x.data:%d/%m} {ctx.escala(x.escala_id).nome}: {x.descricao}",
                  lambda x: x.escala_id in ed_ids)

if PODE_GERIR:
    with aba_esc:
        st.subheader("Criar escala")
        with st.form("nova", clear_on_submit=True):
            n1, n2, n3 = st.columns(3)
            nome = n1.text_input("Nome")
            cat = n2.selectbox("Categoria", list(CATEGORIAS), format_func=lambda c: CATEGORIAS[c][0])
            tipo_txt = n3.text_input("Tipo (ex.: Diária, Pernoite)")
            m1, m2_, m3 = st.columns(3)
            modo = m1.selectbox("Modo", ["corrida", "preta_vermelha", "eventos"])
            funciona = m2_.selectbox("Funciona em", ["todos", "uteis"], format_func=lambda x: "todos os dias" if x == "todos" else "só dias úteis")
            prio = m3.number_input("Prioridade (maior prevalece)", 1, 99, 1)
            p1, p2, p3, p4 = st.columns(4)
            por_dia = p1.number_input("Escalados por dia", 1, 20, 1)
            retem = p2.number_input("Retém por dia", 0, 5, 1)
            folgas = p3.number_input("Folgas mínimas entre serviços (2 = 2x1)", 0, 10, 2)
            horas_q = p4.selectbox("Quartos", [0, 4, 2, 3, 6], format_func=lambda h: "sem quartos" if h == 0 else f"de {h}h")
            membros = st.multiselect("Militares", list(nomes_m), format_func=nomes_m.get)
            refs = st.multiselect("Escalas que prevalecem sobre esta (compartilhadas com você)",
                                  [e.id for e in visiveis], format_func=lambda i: ctx.escala(i).nome)
            if st.form_submit_button("Criar"):
                nova = Escala(f"e{len(ctx.escalas) + 1}", nome, dono_id=uid, categoria=cat, tipo=tipo_txt, modo=modo,
                              funciona_em=funciona, prioridade=prio, militares_dia=por_dia, retem_qtd=retem,
                              folgas_minimas=folgas, quartos=quartos_padrao(horas_q) if horas_q else [],
                              membros=[Pertinencia(m) for m in membros], participa_roxa=modo != "eventos")
                if erros := validar_escala(ctx, nova):
                    st.error(" ".join(erros))
                else:
                    ctx.escalas.append(nova)
                    for r in refs:
                        pm.referenciar(ctx, uid, nova.id, r)
                    st.rerun()
        st.subheader("Compartilhar acesso")
        minhas = [e for e in visiveis if e.dono_id == uid]
        if not minhas:
            st.caption("Você não é dono de nenhuma escala.")
        for e in minhas:
            with st.expander(e.nome):
                st.write({nomes_u.get(u, u): n for u, n in e.compartilhado_com.items()} or "Não compartilhada.")
                outros = [u for u in nomes_u if u != uid]
                cc1, cc2, cc3 = st.columns([2, 2, 1])
                com = cc1.selectbox("Usuário", outros, format_func=nomes_u.get, key=f"u{e.id}")
                niv = cc2.selectbox("Nível", ["leitura", "edicao", "revogar"], key=f"n{e.id}")
                if cc3.button("Aplicar", key=f"b{e.id}"):
                    pm.compartilhar(ctx, uid, e.id, com, None if niv == "revogar" else niv); st.rerun()


if PODE_GERIR:
    with aba_esc:
        st.subheader("Editar escala")
        for e in [x for x in visiveis if pm.pode_editar(ctx, uid, x)]:
            with st.expander(f"Editar – {e.nome}"):
                with st.form(f"ed_{e.id}"):
                    e1, e2, e3 = st.columns(3)
                    nome_n = e1.text_input("Nome", e.nome)
                    tipo_n = e2.text_input("Tipo", e.tipo)
                    cat_n = e3.selectbox("Categoria", list(CATEGORIAS), list(CATEGORIAS).index(e.categoria),
                                         format_func=lambda c: CATEGORIAS[c][0])
                    f1, f2, f3 = st.columns(3)
                    modo_n = f1.selectbox("Modo", ["corrida", "preta_vermelha", "eventos"],
                                          ["corrida", "preta_vermelha", "eventos"].index(e.modo))
                    func_n = f2.selectbox("Funciona em", ["todos", "uteis"], ["todos", "uteis"].index(e.funciona_em))
                    prio_n = f3.number_input("Prioridade", 1, 99, e.prioridade)
                    g1, g2, g3, g4 = st.columns(4)
                    dia_n = g1.number_input("Escalados por dia", 1, 20, e.militares_dia)
                    ret_n = g2.number_input("Retém por dia", 0, 5, e.retem_qtd)
                    fol_n = g3.number_input("Folgas mínimas (2 = 2x1)", 0, 10, e.folgas_minimas)
                    hq_atual = (int(e.quartos[0].fim[:2]) - int(e.quartos[0].inicio[:2])) % 24 or 24 if e.quartos else 0
                    opcoes_q = [0, 2, 3, 4, 6]
                    hq_n = g4.selectbox("Quartos", opcoes_q, opcoes_q.index(hq_atual) if hq_atual in opcoes_q else 0,
                                        format_func=lambda h: "sem quartos" if h == 0 else f"de {h}h")
                    ant_n = st.number_input("Antecedência mínima da papeleta de troca (horas)", 0, 720, e.antecedencia_horas)
                    h1, h2 = st.columns(2)
                    rox_n = h1.checkbox("Participa da escala roxa", e.participa_roxa)
                    resp_n = h2.checkbox("Não-serviço só escala quem não está de serviço", e.respeita_servicos)
                    if st.form_submit_button("Salvar"):
                        novo = dataclasses.replace(
                            e, nome=nome_n, tipo=tipo_n, categoria=cat_n, modo=modo_n, funciona_em=func_n,
                            prioridade=prio_n, militares_dia=dia_n, retem_qtd=ret_n, folgas_minimas=fol_n,
                            quartos=quartos_padrao(hq_n) if hq_n else [], participa_roxa=rox_n, respeita_servicos=resp_n, antecedencia_horas=ant_n)
                        if erros := validar_escala(ctx, novo):
                            st.error(" ".join(erros))
                        else:
                            ctx.escalas[ctx.escalas.index(e)] = novo
                            st.rerun()
                if e.dono_id == uid and st.button("Excluir esta escala", key=f"del_{e.id}"):
                    ctx.escalas.remove(e)
                    for o in ctx.escalas:
                        o.referencias = [r for r in o.referencias if r != e.id]
                    st.rerun()

if PODE_GERIR:
    with aba_mil:
        st.subheader("Militares")
        df = pd.DataFrame([{"Excluir": False, "id": m.id, "Antiguidade": m.antiguidade, "Nome de guerra": m.nome,
                            "Posto/Grad.": m.posto, "NIP": m.nip, "OM": m.om}
                           for m in sorted(ctx.militares, key=lambda m: m.antiguidade)])
        ed = st.data_editor(df, hide_index=True, width="stretch", disabled=["id"], key="mil_editor",
                            column_config={"id": None})
        b1, b2 = st.columns(2)
        if b1.button("Salvar edições"):
            try:
                for _, r in ed.iterrows():
                    cd.editar_militar(ctx, r["id"], nome=r["Nome de guerra"], posto=r["Posto/Grad."] or "",
                                      nip=r["NIP"] or "", om=r["OM"] or "")
                for _, r in ed.sort_values("Antiguidade").iterrows():
                    if ctx.militar(r["id"]).antiguidade != int(r["Antiguidade"]):
                        cd.editar_militar(ctx, r["id"], antiguidade=int(r["Antiguidade"]))
                st.rerun()
            except ValueError as ex:
                st.error(str(ex))
        if b2.button("Excluir marcados (do cadastro e de todas as escalas)"):
            try:
                n = cd.excluir_militares(ctx, list(ed.loc[ed["Excluir"], "id"]), uid)
                st.success(f"{n} militar(es) excluído(s).") if n else st.info("Nenhum marcado.")
                st.rerun()
            except pm.PermissaoNegada as ex:
                st.error(str(ex))
        st.subheader("Adicionar militar")
        with st.form("novo_mil", clear_on_submit=True):
            a1, a2, a3, a4, a5 = st.columns(5)
            nm, pt, nip, om_, ant = (a1.text_input("Nome de guerra"), a2.text_input("Posto/Grad."),
                                     a3.text_input("NIP"), a4.text_input("OM"),
                                     a5.number_input("Antiguidade (0 = mais moderno)", 0, 999, 0))
            if st.form_submit_button("Adicionar"):
                try:
                    cd.adicionar_militar(ctx, nm, pt, nip, om_, ant or None); st.rerun()
                except ValueError as ex:
                    st.error(str(ex))
        st.subheader("Vincular à escala")
        ed_esc = [e.id for e in visiveis if pm.pode_editar(ctx, uid, e)]
        if ed_esc:
            alvo = st.selectbox("Escala", ed_esc, format_func=lambda i: ctx.escala(i).nome, key="vinc_esc")
            sel = st.multiselect("Militares", list(nomes_m), format_func=nomes_m.get, key="vinc_sel")
            data_v = st.date_input("A partir de / até (para mudança de escala)", date.today(), key="vinc_data")
            v1, v2, v3 = st.columns(3)
            if v1.button("Adicionar à escala"):
                cd.adicionar_a_escala(ctx, alvo, sel, data_v); st.rerun()
            if v2.button("Encerrar participação na data"):
                cd.remover_da_escala(ctx, alvo, sel, data_v); st.rerun()
            if v3.button("Remover da escala (definitivo)"):
                cd.remover_da_escala(ctx, alvo, sel); st.rerun()

if PODE_GERIR:
    with aba_imp:
        st.subheader("Importar planilha existente (CSV ou XLSX)")
        st.caption("Colunas: Nome de guerra, Posto/Graduação, NIP, OM (sigla/código), Escala, Ordem, Último serviço "
                   "e/ou Data. A escala continua do dia seguinte à última data da planilha.")
        st.download_button("Baixar modelo (CSV)", MODELO_CSV.encode("utf-8-sig"), "modelo_importacao.csv", "text/csv")
        arq = st.file_uploader("Planilha", type=["csv", "xlsx"])
        i1, i2, i3 = st.columns(3)
        sentido = i1.selectbox("Ordem das linhas", ["topo_mais_antigo", "base_mais_antigo"],
                               format_func=lambda x: "1ª linha = mais antigo" if x == "topo_mais_antigo" else "última linha = mais antigo")
        criar = i2.checkbox("Criar escalas que não existirem", True)
        subst = i3.checkbox("Membros das escalas citadas = os da planilha", False)
        if arq and st.button("Pré-visualizar importação"):
            try:
                st.session_state.import_prev = importar(ctx, ler_tabela(arq.getvalue(), arq.name), sentido=sentido,
                                                        criar_escalas=criar, dono_id=uid, substituir_membros=subst)
            except Exception as ex:  # planilha malformada
                st.error(f"Não consegui ler a planilha: {ex}")
        if "import_prev" in st.session_state:
            novo_ctx, rel = st.session_state.import_prev
            for t in rel.erros:
                st.error(t)
            st.write(f"**Novos:** {len(rel.novos)} · **Atualizados:** {len(rel.atualizados)} · "
                     f"**Vínculos:** {rel.vinculos} · **Escalas criadas:** {', '.join(rel.escalas_criadas) or '—'}")
            if rel.data_base:
                st.info(f"A escala continua em {rel.data_base:%d/%m/%Y}. " + "; ".join(
                    f"{k}: último = {v}" for k, v in rel.continuidade.items()))
            for t in rel.avisos:
                st.warning(t)
            if not rel.erros and st.button("Aplicar importação"):
                st.session_state.ctx = novo_ctx
                del st.session_state["import_prev"]
                st.rerun()


if user.admin:
    with aba_usr:
        st.subheader("Contas de acesso")
        st.caption("Detalhista: cria e edita escalas. Militar: vê a própria escala e pede troca para si.")
        tab = [{"Login": u.login, "Nome": u.nome, "Perfil": u.perfil, "Admin": "sim" if u.admin else "",
                "Militar": nomes_m.get(u.militar_id, ""), "Ativo": "sim" if u.ativo else "não",
                "Bloqueada até": f"{u.bloqueado_ate:%d/%m %H:%M}" if u.bloqueado_ate else ""} for u in ctx.usuarios]
        st.dataframe(pd.DataFrame(tab), hide_index=True, width="stretch")
        with st.form("novo_usuario", clear_on_submit=True):
            n1, n2, n3 = st.columns(3)
            lg2, nm2, sn2 = n1.text_input("Login"), n2.text_input("Nome"), n3.text_input("Senha provisória (8+)", type="password")
            n4, n5, n6 = st.columns(3)
            perfil2 = n4.selectbox("Perfil", list(auth.PERFIS))
            sem_conta = [m.id for m in ctx.militares if not any(u.militar_id == m.id for u in ctx.usuarios)]
            mil2 = n5.selectbox("Militar (perfil militar)", [""] + sem_conta, format_func=lambda i: nomes_m.get(i, "—"))
            adm2 = n6.checkbox("Administrador")
            if st.form_submit_button("Criar conta"):
                try:
                    auth.criar_usuario(ctx, uid, lg2, nm2, sn2, perfil=perfil2, militar_id=mil2, admin=adm2)
                    st.rerun()
                except (ValueError, PermissionError) as ex:
                    st.error(str(ex))
        st.subheader("Redefinir senha / ativar / desativar")
        alvo_u = st.selectbox("Conta", [u.id for u in ctx.usuarios],
                              format_func=lambda i: f"{ctx.usuario(i).login} – {ctx.usuario(i).nome}")
        r1, r2, r3 = st.columns(3)
        nova_s = r1.text_input("Nova senha (8+)", type="password", key="rs")
        if r1.button("Redefinir senha"):
            try:
                auth.redefinir_senha(ctx, uid, alvo_u, nova_s)
                st.success("Senha redefinida.")
            except (ValueError, PermissionError) as ex:
                st.error(str(ex))
        ativo_atual = ctx.usuario(alvo_u).ativo
        if r2.button("Desativar conta" if ativo_atual else "Reativar conta"):
            try:
                auth.definir_ativo(ctx, uid, alvo_u, not ativo_atual)
                st.rerun()
            except (ValueError, PermissionError) as ex:
                st.error(str(ex))

# ---------------------------------------------------------------- gravação (só o que mudou)
try:
    st.session_state.repo.salvar(ctx)
except ConflitoDeVersao:
    _carregar_novo()
    st.session_state.aviso = ("Outra pessoa alterou os dados ao mesmo tempo. Recarreguei a versão mais recente; "
                              "refaça a sua última ação se ela não aparecer.")
    st.rerun()
except Exception as ex:
    st.error(f"Não consegui gravar em {ARMAZENAMENTO}: {ex}")

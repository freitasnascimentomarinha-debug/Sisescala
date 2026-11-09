"""Gestão das escalas: criar, editar, compartilhar e excluir."""
from datetime import date

import streamlit as st

from sisescala import gestao
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.modelos import CATEGORIAS, Escala, Pertinencia, quartos_padrao
from sisescala.motor import avisos_escala, filas_da_escala, proximo_da_fila
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid, user = P.ctx, P.uid, P.user
nomes_m, nomes_u = P.nomes_m, P.nomes_u
MODOS = {"corrida": "Corrida (fila única)", "preta_vermelha": "Preta e vermelha", "eventos": "Por evento"}
QUARTOS = [0, 2, 3, 4, 6]


def _horas(e):
    return (int(e.quartos[0].fim[:2]) - int(e.quartos[0].inicio[:2])) % 24 or 24 if e.quartos else 0


def _militares_da_escolha(e: Escala | None) -> list[str]:
    """Militares que o detalhista pode indicar como detalhista/auxiliares: os das escalas dele e o militar da conta dele
    (o administrador vê todos). Nunca os cadastros de outros detalhistas."""
    if user.admin:
        return [m.id for m in ctx.militares]
    ids = {p.militar_id for esc in P.editaveis() for p in esc.membros}
    ids |= {p.militar_id for p in (e.membros if e else [])}
    meu = gestao.militar_do_detalhista(ctx, user)
    if meu:
        ids.add(meu)
    return [m.id for m in sorted((x for x in ctx.militares if x.id in ids), key=lambda m: m.nome.lower())]


def _campos(e: Escala | None, k: str):
    """Formulário compartilhado entre criar e editar. Retorna os valores digitados."""
    d = e or Escala("", "", data_base=date.today())   # quem cria vira o detalhista
    a, b, c = st.columns(3)
    nome = a.text_input("Nome", d.nome, key=f"{k}_nome")
    tipo = b.text_input("Tipo (ex.: Diária, Pernoite)", d.tipo, key=f"{k}_tipo")
    cats = list(CATEGORIAS)
    cat = c.selectbox("Categoria", cats, cats.index(d.categoria), format_func=lambda x: CATEGORIAS[x][0], key=f"{k}_cat")
    om = st.text_input("OM que gerencia a escala (aparece no cabeçalho dos documentos)", d.om, key=f"{k}_om",
                       placeholder="Ex.: Centro de Operações do Abastecimento")
    a, b, c = st.columns(3)
    modos = list(MODOS)
    modo = a.selectbox("Modo", modos, modos.index(d.modo), format_func=MODOS.get, key=f"{k}_modo")
    func = b.selectbox("Funciona em", ["todos", "uteis"], ["todos", "uteis"].index(d.funciona_em), key=f"{k}_func",
                       format_func=lambda x: "todos os dias" if x == "todos" else "só dias úteis")
    prio = c.number_input("Prioridade (maior prevalece)", 1, 99, d.prioridade, key=f"{k}_prio")
    a, b, c, dd = st.columns(4)
    por_dia = a.number_input("Escalados por dia", 1, 20, d.militares_dia, key=f"{k}_pd")
    ret = b.number_input("Retém por dia", 0, 5, d.retem_qtd, key=f"{k}_ret")
    fol = c.number_input("Folgas mínimas (2 = 2x1)", 0, 10, d.folgas_minimas, key=f"{k}_fol")
    h = _horas(d)
    hq = dd.selectbox("Quartos", QUARTOS, QUARTOS.index(h) if h in QUARTOS else 0, key=f"{k}_q",
                      format_func=lambda x: "sem quartos" if x == 0 else f"de {x}h")
    ant = st.number_input("Antecedência mínima da papeleta de troca (horas)", 0, 720, d.antecedencia_horas, key=f"{k}_ant")
    sentidos = ["moderno_antigo", "antigo_moderno"]
    sentido = st.selectbox("Sentido da fila", sentidos, sentidos.index(d.sentido_fila if d.sentido_fila in sentidos else sentidos[0]),
                           key=f"{k}_sent",
                           format_func={"moderno_antigo": "Do mais moderno para o mais antigo (padrão)",
                                        "antigo_moderno": "Do mais antigo para o mais moderno"}.get,
                           help="Quem tira o próximo serviço depois de quem acabou de servir. A numeração da antiguidade "
                                "continua: 1 é o mais antigo.")
    st.html('<div class="secao">Detalhista e auxiliar</div>')
    dono = ctx.usuario(e.dono_id) if e and e.dono_id else user
    st.html(f'<div class="f"><small>Detalhista (responsável pela escala)</small><b>{ui.esc(nomes_u.get(dono.id, dono.nome)) if dono else "—"}</b></div>')
    st.caption("O responsável é quem criou a escala. Para passar a função a outra pessoa, use **Entregar o detalhe** no cartão da escala.")
    opc = _militares_da_escolha(e)
    if not opc:
        st.info("Ainda não há militares cadastrados: tudo bem, você continua sendo o detalhista. Depois de cadastrar os "
                "militares (Militares ou Importar planilha), volte aqui para indicar qual deles é o militar do detalhista.")
    a, b = st.columns(2)
    ids = [""] + opc
    atual = d.detalhista_id if d.detalhista_id in ids else (gestao.militar_do_detalhista(ctx, dono) if dono else "")
    det = a.selectbox("Militar do detalhista (fica fora da escala)", ids, ids.index(atual) if atual in ids else 0,
                      format_func=lambda i: nomes_m.get(i, "— nenhum —"), key=f"{k}_det",
                      help="Se o detalhista também é um militar da lista, escolha-o: ele fica dispensado de serviço nesta escala "
                           "(a menos que marque que concorre). Se não for da lista, deixe “nenhum”.")
    aux = b.multiselect("Auxiliares do detalhista (vários)", opc, [m for m in d.auxiliares if m in opc],
                        format_func=nomes_m.get, key=f"{k}_aux",
                        help="Os auxiliares aprovam papeletas e vínculos e fazem lançamentos desta escala (menos os próprios), "
                             "concorrendo ou não à escala. Precisam ter conta ligada ao militar.")
    det_esc = st.checkbox("O detalhista também concorre a esta escala (raro)", d.detalhista_escalavel, key=f"{k}_detesc",
                          help="Desmarcado (padrão): o detalhista não é escalado para nada nesta escala.")
    a, b = st.columns(2)
    rox = a.checkbox("Participa da escala roxa", d.participa_roxa if e else True, key=f"{k}_rox")
    resp = b.checkbox("Não-serviço só escala quem não está de serviço", d.respeita_servicos, key=f"{k}_resp")
    return dict(nome=nome, om=om, tipo=tipo, categoria=cat, modo=modo, funciona_em=func, prioridade=prio, militares_dia=por_dia,
                retem_qtd=ret, folgas_minimas=fol, quartos=quartos_padrao(hq) if hq else [], antecedencia_horas=ant,
                participa_roxa=rox and modo != "eventos", respeita_servicos=resp, detalhista_id=det, sentido_fila=sentido,
                detalhista_escalavel=det_esc, auxiliares=aux)


@st.dialog("Nova escala", width="large")
def dialogo_nova():
    v = _campos(None, "nova")
    _vis = {p.militar_id for e in P.visiveis for p in e.membros}
    _cand = [m for m in nomes_m if user.admin or m in _vis]
    membros = st.multiselect("Militares da escala (você também pode adicionar depois, em Militares)", _cand,
                             format_func=nomes_m.get, key="nova_mem",
                             help="A ordem em que você escolhe define a antiguidade NESTA escala (o 1º é o mais antigo). "
                                  "O detalhista fica fora da escala, a menos que você marque que ele concorre.")
    if not _cand:
        st.caption("Ainda não há militares cadastrados: tudo bem. Crie a escala vazia e depois adicione os militares em "
                   "Militares ou importe uma planilha (em Importar planilha, use o mesmo nome da escala). Ela só gera "
                   "serviços quando tiver militares suficientes; não precisa de vínculo de ninguém para funcionar.")
    refs = st.multiselect("Escalas que prevalecem sobre esta (compartilhadas com você)", [e.id for e in P.visiveis],
                          format_func=lambda i: ctx.escala(i).nome, key="nova_refs")
    if st.button("Criar escala", type="primary", use_container_width=True):
        nova = Escala(f"e{max([int(e.id[1:]) for e in ctx.escalas if e.id[1:].isdigit()] + [0]) + 1}", v["nome"],
                      membros=[Pertinencia(m, None, None, k) for k, m in enumerate(membros, 1)], **{k: x for k, x in v.items() if k != "nome"})
        def _criar():
            e = gestao.criar_escala(ctx, uid, nova, refs)
            return avisos_escala(ctx, e)                  # só avisa: a escala pode nascer vazia e receber militares depois
        agir(_criar, "Escala criada.")


@st.dialog("Editar escala", width="large")
def dialogo_editar(eid: str):
    e = ctx.escala(eid)
    v = _campos(e, f"ed_{eid}")
    if st.button("Salvar alterações", type="primary", use_container_width=True):
        agir(lambda: avisos_escala(ctx, gestao.editar_escala(ctx, uid, eid, **v)), "Escala atualizada.")


@st.dialog("Ponto de partida da escala", width="large")
def dialogo_partida(eid: str):
    e = ctx.escala(eid)
    ordem = [m for m in ctx.ordem_da_fila(e) if m in ctx.escalaveis(e)]
    if not ordem:
        st.info("Esta escala ainda não tem militares que possam ser escalados. Cadastre-os em Militares ou importe uma planilha.")
        return
    sentido = "do mais antigo ao mais moderno" if e.sentido_fila == "antigo_moderno" else "do mais moderno ao mais antigo"
    st.caption(f"Diga onde a escala está hoje, para o sistema continuar dela. A fila gira {sentido}. "
               f"Em cada fila, escolha o militar que **está de serviço** (ou que entra primeiro) na data.")
    desde = st.date_input("A escala passa a ser calculada a partir de", e.data_base or date.today(), format="DD/MM/YYYY",
                          key=f"pp_data_{eid}")
    escolhas: dict[str, str] = {}
    nomes_fila = {"corrida": "Fila única", "preta": "Fila preta (dias úteis)", "vermelha": "Fila vermelha (sáb, dom e feriados)"}
    for fila in filas_da_escala(e):
        atual = proximo_da_fila(ctx, e, fila, desde)
        opcoes = [""] + ordem
        escolhas[fila] = st.selectbox(
            f"{nomes_fila[fila]}: quem está de serviço", opcoes, opcoes.index(atual) if atual in opcoes else 0,
            format_func=lambda i: "— início da fila —" if not i else ctx.militar(i).rotulo, key=f"pp_{eid}_{fila}",
            help="O militar escolhido é o primeiro a servir nessa fila a partir da data. Quem vem antes dele na fila "
                 "é tratado como quem acabou de servir.")
    st.warning("Os dias anteriores à data deixam de ser calculados e a fila recomeça desse ponto. "
               "Trocas, dispensas e lançamentos já feitos continuam registrados. **Tem certeza?**")
    if st.button("Sim, definir o ponto de partida", type="primary", use_container_width=True, key=f"pp_ok_{eid}"):
        agir(lambda: gestao.definir_ponto_de_partida(ctx, uid, eid, desde, escolhas), "Ponto de partida definido.")


ui.cabecalho("Gerenciar escalas", "Só o detalhista cria, ajusta as regras e compartilha o acesso das escalas. O auxiliar não edita regras.", "sliders")
if st.button("Nova escala", type="primary", icon=":material/add:"):
    dialogo_nova()

minhas = P.editaveis()
if not minhas:
    ui.vazio("Nenhuma escala ainda", "Clique em “Nova escala” para criar a primeira.", "calendar")
for e in minhas:
    dono = e.dono_id == uid
    with st.container(border=True):
        st.html(f'<div style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap"><div style="font-weight:800;font-size:1.1rem;'
                f'color:var(--ink)">{ui.esc(e.nome)}</div>{ui.chip(CATEGORIAS[e.categoria][0])}{ui.chip("OM", e.om or "não informada")}{ui.chip("Detalhista", (nomes_m.get(e.detalhista_id, "—") + (" · concorre" if e.detalhista_escalavel else " · fora")) if e.detalhista_id else nomes_u.get(e.dono_id, "—"))}{ui.chip("Auxiliares", ", ".join(nomes_m.get(a, "—") for a in e.auxiliares)) if e.auxiliares else ""}{ui.chip("Modo", MODOS[e.modo])}'
                f'{ui.chip("Prioridade", e.prioridade)}{ui.chip(str(e.militares_dia) + " por dia")}'
                f'{ui.chip(str(len(e.membros)) + " militares")}{ui.chip("Descanso", str(e.folgas_minimas) + "x1")}'
                f'<div style="margin-left:auto">{ui.pill("Responsável: " + nomes_u.get(e.dono_id, e.dono_id or "—"), "azul" if dono else "cinza", False)}</div></div>')
        if e.compartilhado_com:
            st.html('<div style="margin:.5rem 0 0">' + " ".join(
                ui.pill(f"{nomes_u.get(u, u)} · {n}", "violeta", False) for u, n in e.compartilhado_com.items()) + "</div>")
        b1, b2, b4, b3, _ = st.columns([1, 1.2, 1.7, 1, 1.2])
        if b1.button("Editar", key=f"ed_{e.id}", icon=":material/edit:"):
            dialogo_editar(e.id)
        if dono and st.button("Ponto de partida da fila", key=f"pp_{e.id}", icon=":material/flag:",
                              help="Informe onde a escala está hoje e quem está de serviço."):
            dialogo_partida(e.id)
        if dono:
            with b2.popover("Compartilhar", icon=":material/share:"):
                outros = [u for u in nomes_u if u != uid]
                if not outros:
                    st.caption("Não há outros usuários cadastrados.")
                else:
                    com = st.selectbox("Usuário", outros, format_func=lambda u: f"{nomes_u[u]} (NIP {ctx.usuario(u).login})", key=f"u{e.id}")
                    niv = st.selectbox("Acesso", ["leitura", "revogar"], key=f"n{e.id}",
                                       format_func={"leitura": "Leitura", "revogar": "Revogar acesso"}.get)
                    st.caption("Leitura permite ver a escala. Quem decide e lança são o detalhista e os auxiliares "
                               "(defina em Editar → Auxiliares).")
                    if st.button("Aplicar", key=f"b{e.id}", type="primary"):
                        agir(lambda: pm.compartilhar(ctx, uid, e.id, com, None if niv == "revogar" else niv),
                             "Acesso atualizado.")
            with b4.popover("Entregar o detalhe", icon=":material/swap_horiz:"):
                st.caption("Passa o detalhe desta escala a outra pessoa. Você não fica sem detalhista: é preciso designar outro.")
                cand = [u.id for u in ctx.usuarios if u.ativo and u.id != uid]
                if not cand:
                    st.warning("Não há outro usuário ativo para receber o detalhe.")
                else:
                    novo_det = st.selectbox("Novo detalhista", cand, format_func=lambda u: f"{nomes_u[u]} (NIP {ctx.usuario(u).login})",
                                            key=f"td_{e.id}")
                    papel = st.radio("Depois de entregar, eu serei", list(gestao.PAPEIS), format_func=gestao.PAPEIS.get, key=f"tp_{e.id}")
                    meu_mil = ctx.usuario(uid).militar_id or e.detalhista_id
                    mil_ant = ""
                    if papel in ("escalado", "auxiliar") and not meu_mil:
                        mil_ant = st.selectbox("Qual é o seu militar no cadastro?", [""] + list(nomes_m), format_func=lambda i: nomes_m.get(i, "—"),
                                               key=f"tm_{e.id}")
                    conc = papel == "auxiliar" and st.checkbox("Continuar concorrendo à escala", key=f"tc_{e.id}")
                    if st.button("Entregar o detalhe", key=f"tb_{e.id}", type="primary"):
                        agir(lambda: gestao.transferir_detalhe(ctx, uid, e.id, novo_det, papel, mil_ant, conc),
                             "Detalhe entregue.")
            with b3.popover("Excluir", icon=":material/delete:"):
                st.warning("Isso apaga a escala e as referências a ela.")
                if st.button("Confirmar exclusão", key=f"del_{e.id}"):
                    agir(lambda: gestao.excluir_escala(ctx, uid, e.id), "Escala excluída.")

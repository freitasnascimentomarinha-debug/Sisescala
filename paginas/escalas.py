"""Gestão das escalas: criar, editar, compartilhar e excluir."""
from datetime import date

import streamlit as st

from sisescala import gestao
from sisescala import permissoes as pm
from sisescala import ui
from sisescala.modelos import CATEGORIAS, Escala, Pertinencia, quartos_padrao
from sisescala.motor import avisos_escala
from sisescala.sessao import agir, pagina

P = pagina()
ctx, uid, user = P.ctx, P.uid, P.user
nomes_m, nomes_u = P.nomes_m, P.nomes_u
MODOS = {"corrida": "Corrida (fila única)", "preta_vermelha": "Preta e vermelha", "eventos": "Por evento"}
QUARTOS = [0, 2, 3, 4, 6]


def _horas(e):
    return (int(e.quartos[0].fim[:2]) - int(e.quartos[0].inicio[:2])) % 24 or 24 if e.quartos else 0


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
    st.html('<div class="secao">Detalhista e auxiliar</div>')
    a, b = st.columns(2)
    ids = [""] + list(nomes_m)
    det = a.selectbox("Detalhista da escala (um só)", ids, ids.index(d.detalhista_id) if d.detalhista_id in ids else 0,
                      format_func=lambda i: nomes_m.get(i, "— nenhum —"), key=f"{k}_det",
                      help="Pode ser o mesmo detalhista de várias escalas. Por padrão ele fica fora da escala.")
    aux = b.multiselect("Auxiliares do detalhista (vários)", [m for m in ids if m], [m for m in d.auxiliares if m in nomes_m],
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
                participa_roxa=rox and modo != "eventos", respeita_servicos=resp, detalhista_id=det,
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
                f'color:var(--ink)">{ui.esc(e.nome)}</div>{ui.chip(CATEGORIAS[e.categoria][0])}{ui.chip("OM", e.om or "não informada")}{ui.chip("Detalhista", (nomes_m.get(e.detalhista_id, "—") + (" · concorre" if e.detalhista_escalavel else " · fora")) if e.detalhista_id else "não definido")}{ui.chip("Auxiliares", ", ".join(nomes_m.get(a, "—") for a in e.auxiliares)) if e.auxiliares else ""}{ui.chip("Modo", MODOS[e.modo])}'
                f'{ui.chip("Prioridade", e.prioridade)}{ui.chip(str(e.militares_dia) + " por dia")}'
                f'{ui.chip(str(len(e.membros)) + " militares")}{ui.chip("Descanso", str(e.folgas_minimas) + "x1")}'
                f'<div style="margin-left:auto">{ui.pill("Responsável: " + nomes_u.get(e.dono_id, e.dono_id or "—"), "azul" if dono else "cinza", False)}</div></div>')
        if e.compartilhado_com:
            st.html('<div style="margin:.5rem 0 0">' + " ".join(
                ui.pill(f"{nomes_u.get(u, u)} · {n}", "violeta", False) for u, n in e.compartilhado_com.items()) + "</div>")
        b1, b2, b4, b3, _ = st.columns([1, 1.2, 1.7, 1, 1.2])
        if b1.button("Editar", key=f"ed_{e.id}", icon=":material/edit:"):
            dialogo_editar(e.id)
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

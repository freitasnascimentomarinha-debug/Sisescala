"""Importar planilha existente (CSV/XLSX) em três passos: enviar, revisar, aplicar."""
import streamlit as st

from sisescala import ui
from sisescala.importacao import MODELO_CSV, importar, ler_tabela
from sisescala.sessao import pagina

P = pagina()
ctx, uid = P.ctx, P.uid
prev = st.session_state.get("import_prev")
ui.cabecalho("Importar planilha", "Migre uma escala existente e continue do dia em que parou.", "upload")
ui.linha_do_tempo(["Enviar planilha", "Revisar", "Aplicar"], 1 if prev else 0)

esq, dir_ = st.columns([1, 1.2], gap="large")
with esq, st.container(border=True):
    ui.secao("1 · Enviar")
    st.caption("**Só o nome de guerra é obrigatório.** As demais colunas (Posto/Graduação, NIP, OM, Escala, Ordem, "
               "Último serviço e/ou Data, E-mail, Ramal e Celular) são opcionais. E-mail, ramal e celular em branco "
               "são completados depois: quando o militar pede o vínculo e o detalhista aprova, o contato da conta "
               "dele entra no cadastro; o detalhista também pode digitar em Militares. A escala continua do dia "
               "seguinte à última data da planilha.")
    st.download_button("Baixar modelo (CSV)", MODELO_CSV.encode("utf-8-sig"), "modelo_importacao.csv", "text/csv",
                       icon=":material/download:")
    arq = st.file_uploader("Planilha", type=["csv", "xlsx"], label_visibility="collapsed")
    sentido = st.selectbox("Ordem das linhas", ["topo_mais_antigo", "base_mais_antigo"],
                           format_func=lambda x: "1ª linha = mais antigo" if x == "topo_mais_antigo" else "última linha = mais antigo")
    meus = {e.id: e.nome for e in P.editaveis()}
    destino = st.selectbox("Para qual escala?", ["", *meus],
                           format_func=lambda i: meus.get(i, "Usar a coluna Escala da planilha (cria as que não existirem)"),
                           help="Escolha uma escala sua para importar os dados dentro dela, ignorando a coluna Escala.")
    modo = "acrescentar"
    if destino:
        modo = st.radio("O que fazer com os dados que já estão nela?", ["acrescentar", "substituir"],
                        format_func={"acrescentar": "Acrescentar: inclui quem falta e completa campos vazios; ninguém sai",
                                     "substituir": "Substituir: a escala fica exatamente como a planilha"}.get)
        if modo == "substituir":
            st.warning("Quem não está na planilha sai da escala, a antiguidade passa a ser a da planilha e os dados "
                       "cadastrais dos militares (só os que estão apenas nas suas escalas) são trocados. "
                       "Você poderá revisar tudo antes e confirmar.")
    subst = modo == "substituir"
    if arq and st.button("Revisar importação", type="primary", icon=":material/fact_check:"):
        try:
            st.session_state.import_prev = importar(
                ctx, ler_tabela(arq.getvalue(), arq.name), sentido=sentido, criar_escalas=not destino, dono_id=uid,
                substituir_membros=subst, usuario_id=uid, sobrescrever=subst, escala_destino=destino)
            st.session_state.import_subst = subst
            st.rerun()
        except Exception as ex:  # planilha malformada
            st.error(f"Não consegui ler a planilha: {ex}")
with dir_, st.container(border=True):
    ui.secao("2 · Revisar e aplicar")
    if not prev:
        ui.vazio("Nada para revisar", "Envie uma planilha e clique em “Revisar importação”.", "upload")
    else:
        novo_ctx, rel = prev
        for t in rel.erros:
            st.error(t)
        ui.kpis([("Novos", len(rel.novos), "users", "verde"), ("Atualizados", len(rel.atualizados), "edit", "azul"),
                 ("Vínculos", rel.vinculos, "link", "violeta"), ("Escalas criadas", len(rel.escalas_criadas), "calendar", "ambar")])
        if rel.datas_base:
            st.info("; ".join(f"{(novo_ctx.escala(k).nome if novo_ctx.escala(k) else k)} continua em {v:%d/%m/%Y}"
                              for k, v in rel.datas_base.items()) + ". " + "; ".join(
                f"{k}: último = {v}" for k, v in rel.continuidade.items()))
        for t in rel.avisos:
            st.warning(t)
        substituindo = st.session_state.get("import_subst", False)
        if substituindo:
            st.error(f"**Modo substituir.** {len(rel.removidos)} militar(es) saem da escala, {len(rel.atualizados)} "
                     f"têm dados atualizados e {len(rel.novos)} são novos."
                     + (f" {rel.protegidos} militar(es) também estão em escalas de outros e não tiveram os dados trocados."
                        if rel.protegidos else ""))
            if rel.removidos:
                with st.expander(f"Quem sai da escala ({len(rel.removidos)})"):
                    st.write(", ".join(rel.removidos))
        c1, c2, _ = st.columns([1, 1, 2])

        @st.dialog("Tem certeza?")
        def confirmar():
            st.write(f"A escala será **substituída** pelos dados da planilha: {len(rel.removidos)} militar(es) saem, "
                     f"{len(rel.atualizados)} são atualizados e {len(rel.novos)} entram. Isso **não pode ser desfeito**.")
            ok, nao = st.columns(2)
            if ok.button("Sim, substituir", type="primary", use_container_width=True):
                st.session_state.ctx = novo_ctx
                st.session_state.pop("import_prev", None)
                st.session_state["toast"] = "Escala substituída pela planilha."
                st.rerun()
            if nao.button("Cancelar", use_container_width=True):
                st.rerun()

        if not rel.erros and c1.button("Substituir a escala" if substituindo else "Aplicar importação", type="primary",
                                       icon=":material/check:"):
            if substituindo:
                confirmar()
            else:
                st.session_state.ctx = novo_ctx
                del st.session_state["import_prev"]
                st.session_state["toast"] = "Importação aplicada."
                st.rerun()
        if c2.button("Descartar"):
            del st.session_state["import_prev"]
            st.rerun()

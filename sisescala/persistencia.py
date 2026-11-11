"""Persistência: o estado (Contexto) vira abas de planilha e volta.

Camadas
- `para_tabelas` / `de_tabelas`: tradução entre o Contexto e tabelas de texto (uma aba por tipo).
- `Backend`: onde as tabelas ficam. `SheetsBackend` (Google Sheets), `ArquivoBackend` (JSON local, para
  desenvolvimento) e `MemoriaBackend` (testes). Para migrar para PostgreSQL basta um novo Backend/Repositório
  (o motor e a tela não conhecem o armazenamento).
- `Repositorio`: carrega, salva só o que mudou e protege contra duas pessoas gravando ao mesmo tempo
  (controle de versão: se outra pessoa gravou antes, `ConflitoDeVersao`).

Todos os valores são gravados como texto cru (RAW), então NIP, datas e ids não são "interpretados" pela
planilha e não há injeção de fórmulas.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from .modelos import (Assinatura, Contexto, DiaEspecial, Disponibilidade, Escala, Evento, Guarnecimento,
                      AssinaturaDetalhe, ConviteVinculo, DetalheConjunto, DetalheDoc, Impedimento, Militar, Notificacao, Ocorrencia, Papeleta, PedidoAcesso, PeriodoRoxa, Pertinencia, Quarto, Troca,
                      Usuario, Vinculo)


class ConflitoDeVersao(Exception):
    """Outra pessoa gravou os dados depois de você carregá-los."""


# ------------------------------------------------------------------ conversões
def _w(v, t: str) -> str:
    if v is None or v == "":
        return ""
    if t == "b":
        return "1" if v else "0"
    if t == "d":
        return v.isoformat()
    if t == "dt":
        return v.isoformat(timespec="seconds")
    return str(v)


def _r(txt: str, t: str):
    txt = (txt or "").strip() if t != "s" else (txt or "")
    if t == "s":
        return txt
    if t == "i":
        return int(float(txt)) if txt else 0
    if t == "b":
        return txt == "1"
    if t == "d":
        return date.fromisoformat(txt) if txt else None
    if t == "dt":
        return datetime.fromisoformat(txt) if txt else None
    raise ValueError(t)


# nome da aba -> [(campo, tipo)]   tipos: s texto, i inteiro, b booleano, d data, dt data-hora
SCHEMA: dict[str, list[tuple[str, str]]] = {
    "Config": [("chave", "s"), ("valor", "s")],
    "Militares": [("id", "s"), ("nome", "s"), ("posto", "s"), ("antiguidade", "i"), ("nip", "s"), ("om", "s"),
                  ("email", "s"), ("ramal", "s"), ("celular", "s"), ("especialidade", "s")],
    "Usuarios": [("id", "s"), ("nome", "s"), ("login", "s"), ("senha_hash", "s"), ("militar_id", "s"),
                 ("perfil", "s"), ("admin", "b"), ("ativo", "b"), ("tentativas", "i"), ("bloqueado_ate", "dt"),
                 ("email", "s"), ("ramal", "s"), ("celular", "s"), ("pin_hash", "s"), ("nip", "s"), ("om", "s"),
                 ("situacao", "s"), ("trocar_senha", "b"), ("nome_guerra", "s"), ("posto", "s"), ("especialidade", "s")],
    "Escalas": [("id", "s"), ("nome", "s"), ("sigla", "s"), ("dono_id", "s"), ("om", "s"), ("uf", "s"), ("data_base", "d"), ("detalhista_id", "s"), ("detalhista_escalavel", "b"),
                ("categoria", "s"),
                ("sigla_evento", "s"), ("tipo", "s"), ("prioridade", "i"), ("modo", "s"), ("funciona_em", "s"),
                ("militares_dia", "i"), ("retem_qtd", "i"), ("folgas_minimas", "i"), ("antecedencia_horas", "i"),
                ("respeita_servicos", "b"), ("participa_roxa", "b"), ("quartos", "s"), ("sentido_fila", "s"),
                ("det_instrucoes", "s"), ("det_recomendacoes", "s"), ("det_regras", "s"),
                ("ass_detalhista", "s"), ("ass_auxiliar", "s"), ("brasao_b64", "s"), ("encarregado_usuario_id", "s"), ("vice_usuario_id", "s"), ("ass_encarregado", "s"), ("ass_vice_diretor", "s")],
    "EscalaMembros": [("escala_id", "s"), ("militar_id", "s"), ("inicio", "d"), ("fim", "d"), ("antiguidade", "i")],
    "EscalaAuxiliares": [("escala_id", "s"), ("militar_id", "s")],
    "EscalaUltimo": [("escala_id", "s"), ("fila", "s"), ("militar_id", "s")],
    "EscalaRefs": [("escala_id", "s"), ("referencia_id", "s")],
    "EscalaCompart": [("escala_id", "s"), ("usuario_id", "s"), ("nivel", "s")],
    "Impedimentos": [("militar_id", "s"), ("tipo", "s"), ("inicio", "d"), ("fim", "d"), ("motivo", "s"),
                     ("anexo", "s"), ("criado_por", "s"), ("criado_em", "dt"), ("alterado_por", "s"), ("alterado_em", "dt")],
    "DiasEspeciais": [("data", "d"), ("tipo", "s"), ("descricao", "s"), ("escala_id", "s"), ("data_fim", "d"),
                      ("conta_como", "s"), ("criado_por", "s"), ("criado_em", "dt"), ("alterado_por", "s"), ("alterado_em", "dt")],
    "Guarnecimentos": [("data", "d"), ("escala_id", "s"), ("guarnece", "b"), ("criado_por", "s"), ("criado_em", "dt"), ("alterado_por", "s"), ("alterado_em", "dt")],
    "Roxas": [("id", "s"), ("nome", "s"), ("inicio", "d"), ("fim", "d"), ("escala_id", "s"), ("criado_por", "s"), ("criado_em", "dt"), ("alterado_por", "s"), ("alterado_em", "dt")],
    "Ocorrencias": [("data", "d"), ("escala_id", "s"), ("militar_id", "s"), ("motivo", "s"), ("criado_por", "s"), ("criado_em", "dt"), ("alterado_por", "s"), ("alterado_em", "dt")],
    "Trocas": [("data", "d"), ("escala_id", "s"), ("saindo", "s"), ("entrando", "s"), ("aceite_saindo", "b"),
               ("aceite_entrando", "b"), ("observacao", "s"), ("papeleta_id", "s")],
    "Eventos": [("escala_id", "s"), ("data", "d"), ("descricao", "s"), ("hora", "s"), ("local", "s"),
                ("vagas", "s"), ("criado_por", "s"), ("criado_em", "dt"), ("alterado_por", "s"), ("alterado_em", "dt")],
    "Papeletas": [("id", "s"), ("numero", "i"), ("escala_id", "s"), ("solicitante_id", "s"),
                  ("data_solicitante", "d"), ("outro_id", "s"), ("data_outro", "d"), ("criado_em", "dt"),
                  ("criado_por", "s"), ("motivo", "s"), ("status", "s"), ("tipo", "s"), ("decidido_por", "s"),
                  ("decidido_em", "dt"), ("motivo_rejeicao", "s"), ("confirmada_por", "s"),
                  ("confirmada_em", "dt")],
    "Vinculos": [("id", "s"), ("usuario_id", "s"), ("militar_id", "s"), ("escala_id", "s"), ("criado_em", "dt"),
                 ("pin_hash", "s"), ("status", "s"), ("decidido_por", "s"), ("decidido_em", "dt"),
                 ("motivo_rejeicao", "s")],
    "Disponibilidades": [("escala_id", "s"), ("militar_id", "s"), ("data", "d"), ("criado_em", "dt"),
                         ("criado_por", "s")],
    "PedidosAcesso": [("id", "s"), ("usuario_id", "s"), ("escala_id", "s"), ("criado_em", "dt"), ("mensagem", "s"),
                      ("status", "s"), ("decidido_por", "s"), ("decidido_em", "dt"), ("motivo_rejeicao", "s")],
    "ConvitesVinculo": [("id", "s"), ("usuario_id", "s"), ("militar_id", "s"), ("escala_id", "s"), ("criado_em", "dt"),
                        ("convidado_por", "s"), ("status", "s"), ("decidido_em", "dt")],
    "Notificacoes": [("id", "s"), ("usuario_id", "s"), ("tipo", "s"), ("texto", "s"), ("criado_em", "dt"),
                     ("lida", "b"), ("escala_id", "s")],
    "PapeletaAssinaturas": [("papeleta_id", "s"), ("militar_id", "s"), ("em", "dt"), ("hash_documento", "s"),
                            ("metodo", "s"), ("referencia", "s")],
    "AssinaturasDetalhe": [("codigo", "s"), ("escala_id", "s"), ("inicio", "d"), ("fim", "d"), ("usuario_id", "s"),
                           ("nome", "s"), ("nip", "s"), ("om", "s"), ("em", "dt"), ("conteudo", "s"), ("papel", "s"), ("doc_id", "s")],
    "DetalhesParaAssinar": [("id", "s"), ("codigo", "s"), ("escala_id", "s"), ("inicio", "d"), ("fim", "d"), ("enviado_por", "s"),
                            ("enviado_em", "dt"), ("status", "s"), ("conteudo", "s"), ("conjunto_id", "s"), ("encerrado_por", "s"),
                            ("encerrado_em", "dt"), ("motivo", "s")],
    "DetalhesConjuntos": [("id", "s"), ("nome", "s"), ("dono_id", "s"), ("om", "s"), ("escala_ids", "s"), ("det_instrucoes", "s"),
                          ("det_recomendacoes", "s"), ("det_regras", "s"), ("ass_detalhista", "s"), ("ass_auxiliar", "s"),
                          ("ass_encarregado", "s"), ("ass_vice_diretor", "s"), ("auxiliar_usuario_id", "s"),
                          ("encarregado_usuario_id", "s"), ("vice_usuario_id", "s"), ("brasao_b64", "s")],
    "PapeletaHistorico": [("papeleta_id", "s"), ("em", "dt"), ("quem", "s"), ("texto", "s")],
}
ABAS = list(SCHEMA)


def _linha(obj_ou_dict, spec) -> list[str]:
    g = (lambda k: obj_ou_dict[k]) if isinstance(obj_ou_dict, dict) else (lambda k: getattr(obj_ou_dict, k))
    return [_w(g(c), t) for c, t in spec]


def _dict(row: list[str], spec) -> dict:
    row = list(row) + [""] * (len(spec) - len(row))
    return {c: _r(row[i], t) for i, (c, t) in enumerate(spec)}


def para_tabelas(ctx: Contexto) -> dict[str, list[list[str]]]:
    """Contexto -> {aba: [cabeçalho, linhas...]}"""
    T: dict[str, list[list[str]]] = {n: [[c for c, _ in SCHEMA[n]]] for n in ABAS}

    def add(aba, obj):
        T[aba].append(_linha(obj, SCHEMA[aba]))
    for chave, valor in (("data_base", ctx.data_base.isoformat()), ("uf", ctx.uf),
                         ("janela_devolucao_dias", str(ctx.janela_devolucao_dias)),
                         ("janela_troca_dias", str(ctx.janela_troca_dias)),
                         ("cadastro_aberto", "1" if ctx.cadastro_aberto else "0"),
                         ("admin_cfg_sig", ctx.admin_cfg_sig), ("brasao_b64", ctx.brasao_b64)):
        T["Config"].append([chave, valor])
    for m in ctx.militares:
        add("Militares", m)
    for u in ctx.usuarios:
        add("Usuarios", u)
    for e in ctx.escalas:
        d = {c: getattr(e, c) for c, _ in SCHEMA["Escalas"] if c != "quartos"}
        d["quartos"] = json.dumps([[q.inicio, q.fim] for q in e.quartos])
        add("Escalas", d)
        for p in e.membros:
            add("EscalaMembros", {"escala_id": e.id, "militar_id": p.militar_id, "inicio": p.inicio, "fim": p.fim,
                                    "antiguidade": p.antiguidade})
        for mid in e.auxiliares:
            add("EscalaAuxiliares", {"escala_id": e.id, "militar_id": mid})
        for fila, mid in e.ultimo_servico.items():
            add("EscalaUltimo", {"escala_id": e.id, "fila": fila, "militar_id": mid})
        for r in e.referencias:
            add("EscalaRefs", {"escala_id": e.id, "referencia_id": r})
        for uid, nv in e.compartilhado_com.items():
            add("EscalaCompart", {"escala_id": e.id, "usuario_id": uid, "nivel": nv})
    for aba, lista in (("Impedimentos", ctx.impedimentos), ("DiasEspeciais", ctx.dias_especiais),
                       ("Guarnecimentos", ctx.guarnecimentos), ("Roxas", ctx.roxas),
                       ("Ocorrencias", ctx.ocorrencias), ("Trocas", ctx.trocas)):
        for o in lista:
            add(aba, o)
    for ev in ctx.eventos:
        add("Eventos", {**{c: getattr(ev, c) for c, _ in SCHEMA["Eventos"]}, "vagas": "" if ev.vagas is None else ev.vagas})
    for v in ctx.vinculos:
        add("Vinculos", v)
    for x in ctx.disponibilidades:
        add("Disponibilidades", x)
    for n in ctx.notificacoes:
        add("Notificacoes", n)
    for pa in ctx.pedidos_acesso:
        add("PedidosAcesso", pa)
    for cv in ctx.convites_vinculo:
        add("ConvitesVinculo", cv)
    for a in ctx.assinaturas_detalhe:
        add("AssinaturasDetalhe", a)
    for dd in ctx.detalhes_docs:
        add("DetalhesParaAssinar", dd)
    for cj in ctx.conjuntos:
        add("DetalhesConjuntos", {**{c: getattr(cj, c) for c, _ in SCHEMA["DetalhesConjuntos"]}, "escala_ids": ",".join(cj.escala_ids)})
    for p in ctx.papeletas:
        add("Papeletas", p)
        for a in p.assinaturas.values():
            add("PapeletaAssinaturas", {"papeleta_id": p.id, "militar_id": a.militar_id, "em": a.em,
                                        "hash_documento": a.hash_documento, "metodo": a.metodo,
                                        "referencia": a.referencia})
        for em, quem, texto in p.historico:
            add("PapeletaHistorico", {"papeleta_id": p.id, "em": em, "quem": quem, "texto": texto})
    return T


def _linhas_de(T: dict, aba: str) -> list[dict]:
    """Lê pelo NOME das colunas (cabeçalho), não pela posição: planilhas gravadas por versões anteriores,
    sem colunas novas ou com colunas em outra ordem, continuam carregando."""
    spec = SCHEMA[aba]
    linhas = T.get(aba) or []
    if not linhas:
        return []
    cab = [str(c).strip() for c in linhas[0]]
    out = []
    for r in linhas[1:]:
        if not any(str(c).strip() for c in r):
            continue
        r = list(r) + [""] * (len(cab) - len(r))
        por_nome = {cab[i]: r[i] for i in range(len(cab))}
        out.append({c: _r(por_nome.get(c, ""), t) for c, t in spec})
    return out


def _migrar_auxiliar_unico(T: dict, escalas: dict) -> None:
    """Planilhas antigas guardavam um único `auxiliar_id` na aba Escalas: passa para a lista de auxiliares."""
    linhas = T.get("Escalas") or []
    if not linhas:
        return
    cab = [str(c).strip() for c in linhas[0]]
    if "auxiliar_id" not in cab or "id" not in cab:
        return
    ia, ii = cab.index("auxiliar_id"), cab.index("id")
    for r in linhas[1:]:
        if len(r) > max(ia, ii) and str(r[ia]).strip() and str(r[ii]).strip() in escalas:
            esc = escalas[str(r[ii]).strip()]
            if str(r[ia]).strip() not in esc.auxiliares:
                esc.auxiliares.append(str(r[ia]).strip())


def de_tabelas(T: dict[str, list[list[str]]]) -> Contexto:
    """{aba: linhas} -> Contexto. Abas ausentes viram listas vazias."""
    cfg = {r[0]: (r[1] if len(r) > 1 else "") for r in (T.get("Config") or [])[1:] if r}
    ctx = Contexto(
        militares=[Militar(**d) for d in _linhas_de(T, "Militares")], escalas=[],
        data_base=date.fromisoformat(cfg["data_base"]) if cfg.get("data_base") else date.today(),
        uf=cfg.get("uf") or "RJ",
        janela_devolucao_dias=int(cfg.get("janela_devolucao_dias") or 30),
        janela_troca_dias=int(cfg.get("janela_troca_dias") or 15),
        cadastro_aberto=cfg.get("cadastro_aberto", "1") != "0", admin_cfg_sig=cfg.get("admin_cfg_sig", ""), brasao_b64=cfg.get("brasao_b64", ""))
    ctx.usuarios = [Usuario(**d) for d in _linhas_de(T, "Usuarios")]
    for u in ctx.usuarios:            # contas anteriores ao cadastro por NIP/aprovação: continuam entrando como antes
        u.situacao = u.situacao or ("ativo" if u.ativo else "bloqueado")
        u.nip = u.nip or u.login
    escalas = {}
    for d in _linhas_de(T, "Escalas"):
        quartos = [Quarto(a, b) for a, b in json.loads(d.pop("quartos") or "[]")]
        d["sentido_fila"] = d.get("sentido_fila") or "moderno_antigo"          # planilha antiga: padrão atual
        e = Escala(**d, quartos=quartos)
        escalas[e.id] = e
        ctx.escalas.append(e)
    for d in _linhas_de(T, "EscalaMembros"):
        escalas[d["escala_id"]].membros.append(Pertinencia(d["militar_id"], d["inicio"], d["fim"], d["antiguidade"] or 0))
    for e in ctx.escalas:                              # planilha antiga: cada escala herda a ordem do cadastro uma vez
        ctx.numerar_escala(e)
    for d in _linhas_de(T, "EscalaAuxiliares"):
        if d["militar_id"] not in escalas[d["escala_id"]].auxiliares:
            escalas[d["escala_id"]].auxiliares.append(d["militar_id"])
    _migrar_auxiliar_unico(T, escalas)
    for d in _linhas_de(T, "EscalaUltimo"):
        escalas[d["escala_id"]].ultimo_servico[d["fila"]] = d["militar_id"]
    for d in _linhas_de(T, "EscalaRefs"):
        escalas[d["escala_id"]].referencias.append(d["referencia_id"])
    for d in _linhas_de(T, "EscalaCompart"):
        escalas[d["escala_id"]].compartilhado_com[d["usuario_id"]] = d["nivel"]
    ctx.impedimentos = [Impedimento(**d) for d in _linhas_de(T, "Impedimentos")]
    ctx.dias_especiais = [DiaEspecial(**d) for d in _linhas_de(T, "DiasEspeciais")]
    ctx.guarnecimentos = [Guarnecimento(**d) for d in _linhas_de(T, "Guarnecimentos")]
    ctx.roxas = [PeriodoRoxa(**d) for d in _linhas_de(T, "Roxas")]
    ctx.ocorrencias = [Ocorrencia(**d) for d in _linhas_de(T, "Ocorrencias")]
    ctx.trocas = [Troca(**d) for d in _linhas_de(T, "Trocas")]
    for d in _linhas_de(T, "Eventos"):
        ctx.eventos.append(Evento(d["escala_id"], d["data"], d["descricao"], d["hora"], d["local"],
                                  int(d["vagas"]) if str(d["vagas"]).strip() else None, d["criado_por"], d["criado_em"],
                                  d["alterado_por"], d["alterado_em"]))
    ctx.vinculos = [Vinculo(**d) for d in _linhas_de(T, "Vinculos")]
    ctx.disponibilidades = [Disponibilidade(**d) for d in _linhas_de(T, "Disponibilidades")]
    ctx.notificacoes = [Notificacao(**d) for d in _linhas_de(T, "Notificacoes")]
    ctx.pedidos_acesso = [PedidoAcesso(**d) for d in _linhas_de(T, "PedidosAcesso")]
    ctx.convites_vinculo = [ConviteVinculo(**d) for d in _linhas_de(T, "ConvitesVinculo")]
    ctx.detalhes_docs = [DetalheDoc(**d) for d in _linhas_de(T, "DetalhesParaAssinar")]
    ctx.conjuntos = [DetalheConjunto(**{**d, "escala_ids": [x for x in d["escala_ids"].split(",") if x]})
                     for d in _linhas_de(T, "DetalhesConjuntos")]
    ctx.assinaturas_detalhe = [AssinaturaDetalhe(**{**d, "papel": d["papel"] or "detalhista"}) for d in _linhas_de(T, "AssinaturasDetalhe")]
    papeletas = {}
    for d in _linhas_de(T, "Papeletas"):
        d["tipo"] = d["tipo"] or "troca"          # planilhas antigas sem a coluna
        p = Papeleta(**d)
        papeletas[p.id] = p
        ctx.papeletas.append(p)
    for d in _linhas_de(T, "PapeletaAssinaturas"):
        papeletas[d["papeleta_id"]].assinaturas[d["militar_id"]] = Assinatura(
            d["militar_id"], d["em"], d["hash_documento"], d["metodo"], d["referencia"])
    for d in _linhas_de(T, "PapeletaHistorico"):
        papeletas[d["papeleta_id"]].historico.append((d["em"], d["quem"], d["texto"]))
    return ctx


# ------------------------------------------------------------------ backends
class Backend(Protocol):
    def ler_versao(self) -> int: ...
    def ler_tudo(self) -> tuple[int, dict[str, list[list[str]]]]: ...
    def gravar(self, alteradas: dict[str, list[list[str]]], versao_esperada: int,
               tamanho_anterior: dict[str, tuple[int, int]]) -> int: ...


class MemoriaBackend:
    """Para testes."""

    def __init__(self) -> None:
        self.abas: dict[str, list[list[str]]] = {}
        self.versao = 0
        self.escritas = 0

    def ler_versao(self) -> int:
        return self.versao

    def ler_tudo(self):
        return self.versao, {k: [list(r) for r in v] for k, v in self.abas.items()}

    def gravar(self, alteradas, versao_esperada, tamanho_anterior=None) -> int:
        if versao_esperada != self.versao:
            raise ConflitoDeVersao("os dados foram alterados por outra pessoa")
        for k, v in alteradas.items():
            self.abas[k] = [list(r) for r in v]
        self.versao += 1
        self.escritas += 1
        return self.versao


class ArquivoBackend(MemoriaBackend):
    """JSON local (desenvolvimento, sem Google). Gravação atômica."""

    def __init__(self, caminho: str | os.PathLike) -> None:
        super().__init__()
        self.caminho = Path(caminho)
        self._carregar()

    def _carregar(self) -> None:
        if self.caminho.exists():
            d = json.loads(self.caminho.read_text("utf-8"))
            self.versao, self.abas = int(d["versao"]), d["abas"]

    def ler_versao(self) -> int:
        self._carregar()
        return self.versao

    def ler_tudo(self):
        self._carregar()
        return super().ler_tudo()

    def gravar(self, alteradas, versao_esperada, tamanho_anterior=None) -> int:
        self._carregar()
        nova = super().gravar(alteradas, versao_esperada, tamanho_anterior)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.caminho.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"versao": self.versao, "abas": self.abas}, f, ensure_ascii=False)
        os.replace(tmp, self.caminho)
        return nova


class ConfiguracaoSheetsErro(ValueError):
    """Credenciais do Google Sheets inválidas nos segredos (mensagem segura: nunca inclui a chave)."""


def normalizar_conta_servico(info: dict) -> dict:
    """Conserta a `private_key` colada nos segredos: \\n literal, aspas sobrando, espaços no lugar de quebras de linha,
    cabeçalho e rodapé na mesma linha. Reescreve o PEM no formato exato (64 colunas)."""
    import re
    d = dict(info)
    chave = str(d.get("private_key", "") or "").strip().strip("\"'").replace("\\n", "\n").replace("\r", "")
    m = re.search(r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----(.*?)-----END \1-----", chave, re.S)
    if not m:
        raise ConfiguracaoSheetsErro(
            "A private_key dos segredos não está no formato esperado: ela deve começar com "
            "-----BEGIN PRIVATE KEY----- e terminar com -----END PRIVATE KEY-----. Copie o campo private_key do "
            "arquivo JSON da conta de serviço exatamente como está.")
    corpo = re.sub(r"\s+", "", m.group(2).replace("\\n", ""))
    linhas = [corpo[i:i + 64] for i in range(0, len(corpo), 64)]
    d["private_key"] = f"-----BEGIN {m.group(1)}-----\n" + "\n".join(linhas) + f"\n-----END {m.group(1)}-----\n"
    return d


class SheetsBackend:
    """Google Sheets via conta de serviço (gspread). A planilha precisa estar compartilhada com o e-mail
    da conta de serviço. A versão fica em Config!B1 ("versao")."""

    ABA_VERSAO = "Versao"

    def __init__(self, info_conta_servico: dict, spreadsheet_id: str, cliente=None) -> None:
        if cliente is None:
            import gspread
            info = normalizar_conta_servico(info_conta_servico)
            faltam = [c for c in ("client_email", "token_uri") if not info.get(c)]
            if faltam:
                raise ConfiguracaoSheetsErro("Faltam campos em [gcp_service_account] nos segredos: " + ", ".join(faltam))
            try:
                cliente = gspread.service_account_from_dict(info)
            except ValueError as ex:             # chave que ainda assim não carrega (corrompida ou incompleta)
                raise ConfiguracaoSheetsErro(
                    "A chave privada da conta de serviço nos segredos está corrompida ou incompleta. Gere uma nova chave "
                    "JSON no Google Cloud e copie o private_key inteiro.") from ex
        self.sh = cliente.open_by_key(spreadsheet_id)

    # --- utilidades
    @staticmethod
    def _col(n: int) -> str:
        s = ""
        while n:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s or "A"

    def _garantir_abas(self) -> None:
        existentes = {w.title for w in self.sh.worksheets()}
        for nome in [*ABAS, self.ABA_VERSAO]:
            if nome not in existentes:
                self.sh.add_worksheet(nome, rows=100, cols=max(26, len(SCHEMA.get(nome, [])) + 1))

    def ler_versao(self) -> int:
        r = self.sh.values_batch_get([f"'{self.ABA_VERSAO}'!A1"])
        vals = r.get("valueRanges", [{}])[0].get("values", [])
        return int(vals[0][0]) if vals and vals[0] and str(vals[0][0]).isdigit() else 0

    def ler_tudo(self):
        self._garantir_abas()
        r = self.sh.values_batch_get([f"'{n}'" for n in [self.ABA_VERSAO, *ABAS]])
        vr = r.get("valueRanges", [])
        v = vr[0].get("values", []) if vr else []
        versao = int(v[0][0]) if v and v[0] and str(v[0][0]).isdigit() else 0
        tabelas = {n: (vr[i + 1].get("values", []) if i + 1 < len(vr) else []) for i, n in enumerate(ABAS)}
        return versao, tabelas

    def gravar(self, alteradas, versao_esperada, tamanho_anterior=None) -> int:
        if self.ler_versao() != versao_esperada:
            raise ConflitoDeVersao("os dados foram alterados por outra pessoa")
        tamanho_anterior = tamanho_anterior or {}
        dados = []
        for nome, linhas in alteradas.items():
            lin0, col0 = tamanho_anterior.get(nome, (0, 0))
            ncol = max([len(r) for r in linhas] + [col0, 1])
            nlin = max(len(linhas), lin0)           # apaga o que sobrou das linhas antigas
            bloco = [list(r) + [""] * (ncol - len(r)) for r in linhas] + [[""] * ncol] * (nlin - len(linhas))
            dados.append({"range": f"'{nome}'!A1:{self._col(ncol)}{nlin}", "values": bloco})
        nova = versao_esperada + 1
        dados.append({"range": f"'{self.ABA_VERSAO}'!A1", "values": [[str(nova)]]})
        self.sh.values_batch_update({"valueInputOption": "RAW", "data": dados})
        return nova


# ------------------------------------------------------------------ repositório
class Repositorio:
    """Uma instância por sessão de usuário: lembra a versão e o que já foi gravado."""

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        self.versao = -1
        self._snap: dict[str, list[list[str]]] = {}

    def carregar(self) -> Contexto:
        self.versao, tabelas = self.backend.ler_tudo()
        ctx = de_tabelas(tabelas) if tabelas.get("Militares") or tabelas.get("Usuarios") or tabelas.get("Escalas") \
            else Contexto([], [], date.today())
        self._snap = para_tabelas(ctx)
        return ctx

    def desatualizado(self) -> bool:
        """Alguém gravou depois do meu último carregar/salvar?"""
        return self.backend.ler_versao() != self.versao

    def alterado(self, ctx: Contexto) -> bool:
        return para_tabelas(ctx) != self._snap

    def salvar(self, ctx: Contexto) -> bool:
        """Grava só as abas que mudaram. Retorna True se gravou. Levanta ConflitoDeVersao."""
        novo = para_tabelas(ctx)
        diff = {k: v for k, v in novo.items() if v != self._snap.get(k)}
        if not diff:
            return False
        tam = {k: (len(self._snap[k]), max((len(r) for r in self._snap[k]), default=0)) for k in diff if k in self._snap}
        self.versao = self.backend.gravar(diff, self.versao, tam)
        self._snap = novo
        return True


def criar_repositorio(secrets: dict | None = None, caminho_local: str = "data/sisescala.json") -> tuple[Repositorio, str]:
    """Sheets se houver credenciais em `secrets` (gcp_service_account + sheets.spreadsheet_id); senão arquivo local."""
    if secrets and secrets.get("gcp_service_account") and (secrets.get("sheets") or {}).get("spreadsheet_id"):
        b = SheetsBackend(secrets["gcp_service_account"], secrets["sheets"]["spreadsheet_id"])
        return Repositorio(b), "Google Sheets"
    return Repositorio(ArquivoBackend(caminho_local)), "arquivo local (sem Google Sheets)"

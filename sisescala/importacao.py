"""Importação de planilha existente (CSV/XLSX) para migrar e dar continuidade à escala.

Colunas reconhecidas (nomes flexíveis, sem acento e sem diferenciar maiúsculas):
  Nome de guerra (obrigatória) | Posto/Graduação | NIP | OM (sigla ou código) |
  Escala (uma ou várias, separadas por ; ou ,) | Ordem/Antiguidade |
  Último serviço (data) | Data + Escala (linhas de histórico: quem deu serviço em cada dia)

A continuidade ("dia em que parou") vem das datas: a data-base passa a ser o dia seguinte à
última data da planilha, e em cada fila a escala continua depois de quem deu o último serviço.
"""
from __future__ import annotations

import copy
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .cadastro import novo_id, renumerar
from .contatos import normalizar_contato
from .modelos import Contexto, Escala, Militar, Pertinencia
from .motor import fila_do_dia

SINONIMOS = {
    "nome": {"nome de guerra", "nome guerra", "guerra", "nome", "militar"},
    "posto": {"posto", "graduacao", "posto graduacao", "posto ou graduacao", "posto/graduacao", "p/g", "pg"},
    "nip": {"nip", "n.i.p", "numero de identificacao"},
    "om": {"om", "sigla om", "sigla da om", "codigo om", "cod om", "codigo da om", "sigla", "organizacao militar"},
    "escala": {"escala", "escalas", "servico", "servicos"},
    "ordem": {"ordem", "antiguidade", "seq", "sequencia", "numero", "n", "no", "nº", "posicao"},
    "ultimo": {"ultimo servico", "ultimo serv", "data ultimo servico", "ult servico", "ultimo"},
    "data": {"data", "dia", "data do servico"},
    "email": {"email", "e-mail", "e mail", "correio eletronico"},
    "ramal": {"ramal", "telefone", "telefone fixo"},
    "celular": {"celular", "cel", "whatsapp", "telefone celular", "movel"},
}
MODELO_CSV = (
    "Nome de guerra;Posto/Graduação;NIP;OM;Escala;Ordem;Último serviço;Data\n"
    "SILVA;1SG;12.3456.78;COPAB;Serviço de Pernoite;1;28/02/2027;\n"
    "SOUZA;CB;98.7654.32;COPAB;\"Serviço de Pernoite, Serviço Diário\";2;27/02/2027;\n")


def _norm(s) -> str:
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/. ]", " ", t)).strip()


def parse_data(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


def ler_tabela(conteudo: bytes, nome_arquivo: str) -> list[dict[str, str]]:
    """Lê CSV (separador detectado) ou XLSX (primeira aba). Retorna linhas como dicionários."""
    if nome_arquivo.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True).worksheets[0]
        linhas = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        try:
            txt = conteudo.decode("utf-8-sig")
        except UnicodeDecodeError:
            txt = conteudo.decode("latin-1")
        try:
            dialect = csv.Sniffer().sniff(txt[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        linhas = list(csv.reader(io.StringIO(txt), dialect))
    linhas = [r for r in linhas if any(str(c or "").strip() for c in r)]
    if not linhas:
        return []
    cab = [str(c or "").strip() for c in linhas[0]]
    return [{cab[i]: (r[i] if i < len(r) else "") for i in range(len(cab)) if cab[i]} for r in linhas[1:]]


def mapear_colunas(cabecalhos: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in cabecalhos:
        n = _norm(h)
        for campo, sins in SINONIMOS.items():
            if campo not in out and n in {_norm(s) for s in sins}:
                out[campo] = h
    return out


@dataclass
class Relatorio:
    novos: list[str] = field(default_factory=list)
    atualizados: list[str] = field(default_factory=list)
    vinculos: int = 0
    escalas_criadas: list[str] = field(default_factory=list)
    continuidade: dict[str, str] = field(default_factory=dict)   # "escala / fila" -> militar
    data_base: date | None = None
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)


def _achar_escala(ctx: Contexto, nome: str) -> Escala | None:
    n = _norm(nome)
    return next((e for e in ctx.escalas if n in {_norm(e.nome), _norm(e.id), _norm(e.sigla)}), None)


def _achar_militar(ctx: Contexto, nome: str, posto: str, nip: str) -> Militar | None:
    if nip:
        achado = next((m for m in ctx.militares if m.nip == nip), None)
        if achado:
            return achado
        # cadastro antigo sem NIP: casa pelo nome de guerra
        sem_nip = [m for m in ctx.militares if not m.nip and _norm(m.nome) == _norm(nome)]
        return sem_nip[0] if len(sem_nip) == 1 else None
    cand = [m for m in ctx.militares if _norm(m.nome) == _norm(nome)]
    if posto and len(cand) > 1:
        cand = [m for m in cand if _norm(m.posto) == _norm(posto)] or cand
    return cand[0] if cand else None


def importar(ctx: Contexto, linhas: list[dict], *, sentido: str = "topo_mais_antigo",
             criar_escalas: bool = True, dono_id: str = "",
             substituir_membros: bool = False) -> tuple[Contexto, Relatorio]:
    """Aplica a planilha sobre uma CÓPIA do contexto (use para pré-visualizar; aceite trocando o ctx).

    sentido: "topo_mais_antigo" (1ª linha = mais antigo) ou "base_mais_antigo" (última = mais antigo).
    substituir_membros: nas escalas citadas, os membros passam a ser exatamente os da planilha.
    """
    ctx = copy.deepcopy(ctx)
    rel = Relatorio()
    if not linhas:
        rel.erros.append("Planilha vazia.")
        return ctx, rel
    cols = mapear_colunas(list(linhas[0].keys()))
    if "nome" not in cols:
        rel.erros.append("Não encontrei a coluna do nome de guerra (esperado: 'Nome de guerra').")
        return ctx, rel
    g = lambda row, campo: str(row.get(cols[campo], "") or "").strip() if campo in cols else ""  # noqa: E731
    gv = lambda row, campo: row.get(cols[campo]) if campo in cols else None  # noqa: E731

    ordem_planilha: list[str] = []
    vinc: dict[str, set[str]] = {}
    hist: list[tuple[date, Escala, str]] = []
    vistos_nip: set[str] = set()
    for n_lin, row in enumerate(linhas, 2):
        nome, posto, nip, om = g(row, "nome"), g(row, "posto"), g(row, "nip"), g(row, "om")
        try:
            email_, ramal_, cel_ = normalizar_contato(g(row, "email"), g(row, "ramal"), g(row, "celular"), False)
        except ValueError as ex:
            rel.avisos.append(f"Linha {n_lin}: contato ignorado ({ex}).")
            email_, ramal_, cel_ = "", "", ""
        if not nome and not nip:
            continue
        if nip and nip in vistos_nip and not g(row, "data"):
            rel.avisos.append(f"Linha {n_lin}: NIP {nip} repetido; usei o mesmo militar.")
        vistos_nip.add(nip)
        m = _achar_militar(ctx, nome, posto, nip)
        if m is None:
            m = Militar(novo_id(ctx, nip or nome), nome, posto, 10 ** 6, nip, om, email_, ramal_, cel_)
            ctx.militares.append(m)
            rel.novos.append(nome)
        else:
            mudou = [k for k, v in (("nome", nome), ("posto", posto), ("nip", nip), ("om", om))
                     if v and getattr(m, k) != v]
            for k, v in (("nome", nome), ("posto", posto), ("nip", nip), ("om", om),
                         ("email", email_), ("ramal", ramal_), ("celular", cel_)):
                if v:
                    setattr(m, k, v)
            if mudou and m.nome not in rel.atualizados:
                rel.atualizados.append(m.nome)
        if m.id not in ordem_planilha:
            ordem_planilha.append(m.id)
        # escalas citadas
        escalas_txt = [t.strip() for t in re.split(r"[;,]", g(row, "escala")) if t.strip()]
        d_hist = parse_data(gv(row, "data"))
        d_ult = parse_data(gv(row, "ultimo"))
        for nome_esc in escalas_txt:
            esc = _achar_escala(ctx, nome_esc)
            if esc is None:
                if not criar_escalas:
                    rel.avisos.append(f"Linha {n_lin}: escala '{nome_esc}' não existe.")
                    continue
                esc = Escala(_slug_escala(ctx, nome_esc), nome_esc,
                             dono_id=dono_id)
                ctx.escalas.append(esc)
                rel.escalas_criadas.append(nome_esc)
            vinc.setdefault(esc.id, set()).add(m.id)
            if not any(p.militar_id == m.id and p.fim is None for p in esc.membros):
                esc.membros.append(Pertinencia(m.id))
                rel.vinculos += 1
            for d in (d_hist, d_ult):
                if d:
                    hist.append((d, esc, m.id))
        if (d_hist or d_ult) and not escalas_txt:
            rel.avisos.append(f"Linha {n_lin}: data informada sem escala; ignorada.")
        if "ordem" in cols and g(row, "ordem"):
            try:
                m.antiguidade = int(float(g(row, "ordem")))
                continue
            except ValueError:
                rel.avisos.append(f"Linha {n_lin}: ordem inválida '{g(row, 'ordem')}'.")
    # antiguidade: ordem explícita (se houver) senão a ordem das linhas; quem não está na planilha segue depois
    tem_ordem = "ordem" in cols
    na_planilha = [ctx.militar(i) for i in ordem_planilha]
    if tem_ordem:
        sem = [m for m in na_planilha if m.antiguidade >= 10 ** 6]
        com = sorted((m for m in na_planilha if m.antiguidade < 10 ** 6), key=lambda m: m.antiguidade)
        base = com + sem
    else:
        base = na_planilha if sentido == "topo_mais_antigo" else list(reversed(na_planilha))
    resto = sorted((m for m in ctx.militares if m.id not in {x.id for x in base}), key=lambda m: m.antiguidade)
    for i, m in enumerate(base + resto, 1):
        m.antiguidade = i
    renumerar(ctx)
    if substituir_membros:
        for eid, ids in vinc.items():
            esc = ctx.escala(eid)
            esc.membros = [p for p in esc.membros if p.militar_id in ids]
    # continuidade a partir do histórico
    if hist:
        ultima = max(d for d, _, _ in hist)
        rel.data_base = ultima + timedelta(days=1)
        ctx.data_base = rel.data_base
        antig = {m.id: m.antiguidade for m in ctx.militares}
        por_fila: dict[tuple[str, str], dict[date, set[str]]] = {}
        for d, esc, mid in hist:
            por_fila.setdefault((esc.id, fila_do_dia(ctx, esc, d)), {}).setdefault(d, set()).add(mid)
        for (eid, fila), dias in por_fila.items():
            esc = ctx.escala(eid)
            grupo = dias[max(dias)]
            ordem = sorted((p.militar_id for p in esc.membros), key=lambda i: antig[i])
            ultimo = None
            for i, mid in enumerate(ordem):          # último da sequência circular do dia
                if mid in grupo and ordem[(i + 1) % len(ordem)] not in grupo:
                    ultimo = mid
            ultimo = ultimo or max(grupo, key=lambda i: antig[i])
            esc.ultimo_servico[fila] = ultimo
            rel.continuidade[f"{esc.nome} / {fila}"] = ctx.militar(ultimo).nome
            if (ultima - max(dias)).days > 45:
                rel.avisos.append(f"{esc.nome} / {fila}: último serviço há mais de 45 dias da data-base.")
    else:
        rel.avisos.append("Sem datas na planilha: a escala recomeça do mais antigo na data-base atual.")
    return ctx, rel


def _slug_escala(ctx: Contexto, nome: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _norm(nome)).strip("-") or "escala"
    ids = {e.id for e in ctx.escalas}
    cand, k = base, 2
    while cand in ids:
        cand, k = f"{base}-{k}", k + 1
    return cand

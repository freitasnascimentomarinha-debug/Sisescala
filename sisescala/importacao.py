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
from .permissoes import eh_detalhista

SINONIMOS = {
    "nome": {"nome de guerra", "nome guerra", "guerra", "nome", "militar"},
    "posto": {"posto", "graduacao", "posto graduacao", "posto ou graduacao", "posto/graduacao", "p/g", "pg"},
    "nip": {"nip", "n.i.p", "numero de identificacao"},
    "om": {"om", "sigla om", "sigla da om", "codigo om", "cod om", "codigo da om", "sigla", "organizacao militar"},
    "escala": {"escala", "escalas", "servico", "servicos"},
    "ordem": {"ordem", "antiguidade", "seq", "sequencia", "numero", "n", "no", "nº", "posicao"},
    "ultimo": {"ultimo servico", "ultimo serv", "data ultimo servico", "ult servico", "ultimo"},
    "data": {"data", "dia", "data do servico"},
    "detalhista": {"detalhista", "dispensado de servico", "dispensado"},
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
    data_base: date | None = None             # a mais recente entre as escalas com histórico
    datas_base: dict[str, date] = field(default_factory=dict)   # escala -> dia em que ela continua
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    removidos: list[str] = field(default_factory=list)          # "militar (escala)": saíram da escala (modo substituir)
    protegidos: int = 0                                         # militares cujos dados não foram trocados (são de outras escalas)


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
             substituir_membros: bool = False, usuario_id: str | None = None,
             sobrescrever: bool = True, escala_destino: str = "") -> tuple[Contexto, Relatorio]:
    """Aplica a planilha sobre uma CÓPIA do contexto (use para pré-visualizar; aceite trocando o ctx).

    sentido: "topo_mais_antigo" (1ª linha = mais antigo) ou "base_mais_antigo" (última = mais antigo).
    substituir_membros: nas escalas citadas, os membros passam a ser exatamente os da planilha.
    sobrescrever: troca os dados cadastrais (nome, posto, NIP, OM, contato) pelos da planilha. Quem não é
    administrador só troca os de militares que estão apenas em escalas dele; os demais são só completados.
    escala_destino: id de uma escala existente; todas as linhas vão para ela (a coluna Escala é ignorada).
    """
    ctx = copy.deepcopy(ctx)
    rel = Relatorio()
    quem = ctx.usuario(usuario_id) if usuario_id else None
    admin = usuario_id is None or bool(quem and quem.admin)
    glob = sobrescrever and admin            # renumerar a antiguidade GLOBAL (legado) só o administrador
    escalas_de: dict[str, list[Escala]] = {}
    for e_ in ctx.escalas:
        for p_ in e_.membros:
            escalas_de.setdefault(p_.militar_id, []).append(e_)
    destino = ctx.escala(escala_destino) if escala_destino else None
    if escala_destino and (destino is None or (usuario_id and not eh_detalhista(ctx, usuario_id, destino))):
        rel.erros.append("Escala de destino inválida ou que não é sua.")
        return ctx, rel

    def pode_trocar_dados(m_) -> bool:
        if not sobrescrever:
            return False
        if admin:
            return True
        suas = escalas_de.get(m_.id, [])
        return bool(suas) and all(eh_detalhista(ctx, usuario_id, e_) for e_ in suas)
    if not linhas:
        rel.erros.append("Planilha vazia.")
        return ctx, rel
    cols = mapear_colunas(list(linhas[0].keys()))
    if "nome" not in cols:
        rel.erros.append("Não encontrei a coluna do nome de guerra (esperado: 'Nome de guerra').")
        return ctx, rel
    g = lambda row, campo: str(row.get(cols[campo], "") or "").strip() if campo in cols else ""  # noqa: E731
    gv = lambda row, campo: row.get(cols[campo]) if campo in cols else None  # noqa: E731

    for e in ctx.escalas:                    # congela a numeração de cada escala: mexer no cadastro não a desloca
        ctx.numerar_escala(e)
    previos = {e.id: ctx.ordem_na_escala(e) for e in ctx.escalas}
    ordem_col: dict[str, int] = {}
    criadas: set[str] = set()
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
            campos = (("nome", nome), ("posto", posto), ("nip", nip), ("om", om),
                      ("email", email_), ("ramal", ramal_), ("celular", cel_))
            if not pode_trocar_dados(m):        # completa só o que está vazio, sem alterar dados já existentes
                if sobrescrever and any(v and getattr(m, k) and getattr(m, k) != v for k, v in campos):
                    rel.protegidos += 1             # queria trocar, mas o militar também é de outra escala
                campos = tuple((k, v) for k, v in campos if not getattr(m, k))
            mudou = [k for k, v in campos if v and getattr(m, k) != v and k in ("nome", "posto", "nip", "om")]
            for k, v in campos:
                if v:
                    setattr(m, k, v)
            if mudou and m.nome not in rel.atualizados:
                rel.atualizados.append(m.nome)
        marcado_detalhista = "detalhista" in cols and _norm(g(row, "detalhista")) in {"sim", "s", "x", "1", "true", "verdadeiro"}
        if m.id not in ordem_planilha:
            ordem_planilha.append(m.id)
        # escalas citadas
        escalas_txt = ([destino.nome] if destino else
                       [t.strip() for t in re.split(r"[;,]", g(row, "escala")) if t.strip()])
        d_hist = parse_data(gv(row, "data"))
        d_ult = parse_data(gv(row, "ultimo"))
        for nome_esc in escalas_txt:
            esc = _achar_escala(ctx, nome_esc)
            if esc is not None and usuario_id is not None and not eh_detalhista(ctx, usuario_id, esc):
                aviso = f"A escala '{esc.nome}' é de outro detalhista: peça acesso a ele; linha ignorada nessa escala."
                if aviso not in rel.avisos:
                    rel.avisos.append(aviso)
                continue
            if esc is None:
                if not criar_escalas:
                    rel.avisos.append(f"Linha {n_lin}: escala '{nome_esc}' não existe.")
                    continue
                esc = Escala(_slug_escala(ctx, nome_esc), nome_esc, dono_id=dono_id)
                dono = ctx.usuario(dono_id)
                if dono is not None:                         # quem importa vira o detalhista da escala criada
                    from .gestao import militar_do_detalhista
                    esc.detalhista_id = militar_do_detalhista(ctx, dono)
                criadas.add(esc.id)
                ctx.escalas.append(esc)
                rel.escalas_criadas.append(nome_esc)
            vinc.setdefault(esc.id, set()).add(m.id)
            if marcado_detalhista and not esc.detalhista_id:        # um só detalhista por escala (o primeiro marcado)
                esc.detalhista_id = m.id
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
                ordem_col[m.id] = int(float(g(row, "ordem")))
                if glob or m.antiguidade >= 10 ** 6:
                    m.antiguidade = ordem_col[m.id]
                continue
            except ValueError:
                rel.avisos.append(f"Linha {n_lin}: ordem inválida '{g(row, 'ordem')}'.")
    if not glob:
        # usuário comum: os militares que já existiam mantêm a antiguidade; os novos entram depois, na ordem da planilha
        ultimo_n = max([m.antiguidade for m in ctx.militares if m.antiguidade < 10 ** 6] + [0])
        novos = [ctx.militar(i) for i in ordem_planilha if ctx.militar(i).antiguidade >= 10 ** 6]
        if sentido != "topo_mais_antigo":
            novos.reverse()
        for k, m in enumerate(novos, 1):
            m.antiguidade = ultimo_n + k
        renumerar(ctx)
        tem_ordem = None
    # antiguidade: ordem explícita (se houver) senão a ordem das linhas; quem não está na planilha segue depois
    tem_ordem = "ordem" in cols
    na_planilha = [ctx.militar(i) for i in ordem_planilha]
    if not glob:
        pass
    elif tem_ordem:
        sem = [m for m in na_planilha if m.antiguidade >= 10 ** 6]
        com = sorted((m for m in na_planilha if m.antiguidade < 10 ** 6), key=lambda m: m.antiguidade)
        base = com + sem
    else:
        base = na_planilha if sentido == "topo_mais_antigo" else list(reversed(na_planilha))
    if glob:
        resto = sorted((m for m in ctx.militares if m.id not in {x.id for x in base}), key=lambda m: m.antiguidade)
        for i, m in enumerate(base + resto, 1):
            m.antiguidade = i
        renumerar(ctx)
    if substituir_membros:
        for eid, ids in vinc.items():
            esc = ctx.escala(eid)
            rel.removidos += [f"{ctx.militar(p.militar_id).nome} ({esc.nome})" for p in esc.membros
                              if p.militar_id not in ids]
            esc.membros = [p for p in esc.membros if p.militar_id in ids]
            esc.ultimo_servico = {f: u for f, u in esc.ultimo_servico.items() if u in ids}   # fila sem ponteiro solto
    # antiguidade DENTRO de cada escala citada: ordem da planilha (ou da coluna Ordem); em escala que já existia e
    # que o usuário não sobrescreve, quem já estava mantém o lugar e os novos entram depois
    if "ordem" in cols and ordem_col:
        ordem_sheet = sorted(ordem_planilha, key=lambda i: (ordem_col.get(i, 10 ** 6), ordem_planilha.index(i)))
    else:
        ordem_sheet = ordem_planilha if sentido == "topo_mais_antigo" else list(reversed(ordem_planilha))
    for eid, ids in vinc.items():
        esc = ctx.escala(eid)
        atuais = {p.militar_id for p in esc.membros}
        da_planilha = [i for i in ordem_sheet if i in ids and i in atuais]
        previo = [i for i in previos.get(eid, []) if i in atuais]
        if eid in criadas or sobrescrever or substituir_membros:
            ordem = da_planilha + [i for i in previo if i not in da_planilha]
        else:
            ordem = previo + [i for i in da_planilha if i not in previo]
        ordem += [i for i in ctx.ordem_na_escala(esc) if i not in ordem]
        pos = {i: k for k, i in enumerate(ordem, 1)}
        for p in esc.membros:
            p.antiguidade = pos[p.militar_id]
    # continuidade a partir do histórico
    if hist:
        ultima = max(d for d, _, _ in hist)
        rel.data_base = ultima + timedelta(days=1)
        for eid in {e.id for _, e, _ in hist}:               # cada escala continua do dia seguinte ao SEU último serviço
            ult_e = max(d for d, e, _ in hist if e.id == eid)
            ctx.escala(eid).data_base = ult_e + timedelta(days=1)
            rel.datas_base[eid] = ult_e + timedelta(days=1)
        por_fila: dict[tuple[str, str], dict[date, set[str]]] = {}
        for d, esc, mid in hist:
            por_fila.setdefault((esc.id, fila_do_dia(ctx, esc, d)), {}).setdefault(d, set()).add(mid)
        for (eid, fila), dias in por_fila.items():
            esc = ctx.escala(eid)
            grupo = dias[max(dias)]
            ordem = ctx.ordem_na_escala(esc)
            ultimo = None
            for i, mid in enumerate(ordem):          # último da sequência circular do dia
                if mid in grupo and ordem[(i + 1) % len(ordem)] not in grupo:
                    ultimo = mid
            ultimo = ultimo or max(grupo, key=lambda i: ctx.antig(esc, i))
            esc.ultimo_servico[fila] = ultimo
            rel.continuidade[f"{esc.nome} / {fila}"] = ctx.militar(ultimo).nome
            if (ultima - max(dias)).days > 45:
                rel.avisos.append(f"{esc.nome} / {fila}: último serviço há mais de 45 dias da data-base.")
    else:
        rel.avisos.append("Sem datas na planilha: a escala recomeça do mais antigo na data-base atual.")
    for eid in criadas:                                      # escala nova sem histórico começa hoje, do topo da fila
        if ctx.escala(eid).data_base is None:
            ctx.escala(eid).data_base = date.today()
    return ctx, rel


def _slug_escala(ctx: Contexto, nome: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _norm(nome)).strip("-") or "escala"
    ids = {e.id for e in ctx.escalas}
    cand, k = base, 2
    while cand in ids:
        cand, k = f"{base}-{k}", k + 1
    return cand

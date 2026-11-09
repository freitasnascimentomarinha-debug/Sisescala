"""Motor de geração das escalas.

Regras principais
- Cada escala tem filas independentes (corrida | preta | vermelha | roxa:<período>).
  A fila que não é do dia fica congelada e retoma de onde parou.
- Ordem: começa pelo mais MODERNO e sobe até o mais antigo (antiguidade 1), circular, a partir de quem deu o último
  serviço. Cada escala pode inverter o sentido (`sentido_fila`).
- Descanso mínimo ("2x1"): entre dois serviços na mesma escala o militar tem `folgas_minimas` folgas,
  inclusive entre filas diferentes (sexta preta / sábado vermelha). Quem é pulado por descanso
  não perde a vez (fica "pendente" e entra na primeira oportunidade).
- Retém = próximos da fila após os efetivos. Se um efetivo falha (Ocorrencia), o retém avança.
- Troca consensual (papeleta) só vale com os dois aceites -> (T).
- Troca forçada (TF): militar com duas escalações no mesmo dia mantém a que prevalece e é
  realocado, por troca de datas com outro militar da escala que perdeu, para dar ambas.
- Prevalência: escala referenciada > escala que a referencia; senão maior prioridade.
  Escalas de donos diferentes só interferem entre si quando há referência.
- Escalas de categoria não-serviço (palestra, cerimônia, apoio...) com modo "eventos" só
  funcionam nos dias de evento.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .calendario import dia_util, roxa_do_dia
from .modelos import CATEGORIAS, DISP, SVC, Contexto, Escala, Quarto


@dataclass
class Alocacao:
    militar_id: str
    escala_id: str
    data: date
    papel: str                     # "efetivo" | "retem"
    sigla: str                     # SVÇ, SVÇ (TF), SVÇ (T), RT, RT (TF), PAL, PAL (TF)...
    horarios: list[str] = field(default_factory=list)
    obs: str = ""
    origem: str = "normal"         # "normal" | "tf" | "t" | "falta" (= dispensado do serviço escalado)


@dataclass
class DiaEscala:
    escala_id: str
    data: date
    funciona: bool
    fila: str | None = None
    descricao: str = ""            # evento do dia, quando houver
    alocacoes: list[Alocacao] = field(default_factory=list)

    @property
    def efetivos(self) -> list[Alocacao]:
        return [a for a in self.alocacoes if a.papel == "efetivo" and a.origem != "falta"]

    @property
    def retens(self) -> list[Alocacao]:
        return [a for a in self.alocacoes if a.papel == "retem"]


@dataclass
class Devolucao:
    militar_id: str
    escala_id: str
    data_origem: date
    prazo: date


@dataclass
class Resultado:
    dias: dict[tuple[date, str], DiaEscala]
    devolucoes: list[Devolucao] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def dia(self, d: date, escala_id: str) -> DiaEscala | None:
        return self.dias.get((d, escala_id))

    def alocacoes_do_dia(self, d: date) -> list[Alocacao]:
        return [a for (dd, _), de in self.dias.items() if dd == d for a in de.alocacoes
                if a.origem != "falta"]


# ------------------------------------------------------------------ siglas
def sigla_base(esc: Escala) -> str:
    return esc.sigla_evento or CATEGORIAS.get(esc.categoria, ("", SVC))[1]


def sigla_de(esc: Escala, papel: str, origem: str = "normal") -> str:
    base = "RT" if papel == "retem" else sigla_base(esc)
    return base + {"normal": "", "tf": " (TF)", "t": " (T)"}[origem]


# ------------------------------------------------------------------ utilidades
def _impedido(ctx: Contexto, mid: str, d: date) -> bool:
    return any(i.militar_id == mid and i.cobre(d) for i in ctx.impedimentos)


def _folgas(esc: Escala) -> int:
    return 0 if esc.modo == "eventos" else max(0, esc.folgas_minimas)


def _eventos(ctx: Contexto, esc: Escala, d: date):
    return [e for e in ctx.eventos if e.escala_id == esc.id and e.data == d]


def funciona(ctx: Contexto, esc: Escala, d: date) -> bool:
    if esc.modo == "eventos":
        return bool(_eventos(ctx, esc, d))
    manual = next((g for g in ctx.guarnecimentos if g.data == d and g.escala_id == esc.id), None)
    if manual is not None:
        return manual.guarnece
    if esc.participa_roxa and roxa_do_dia(d, ctx, esc):
        return True
    return esc.funciona_em == "todos" or dia_util(d, ctx, esc)


def fila_do_dia(ctx: Contexto, esc: Escala, d: date) -> str:
    if esc.modo == "eventos":
        return "corrida"
    if esc.participa_roxa:
        r = roxa_do_dia(d, ctx, esc)
        if r:
            return f"roxa:{r.id}"
    if esc.modo == "corrida":
        return "corrida"
    return "preta" if dia_util(d, ctx, esc) else "vermelha"


def _sequencia(ctx: Contexto, esc: Escala, d: date, ultimo: str | None) -> list[str]:
    """Militares ativos e disponíveis, em ordem circular depois de `ultimo`."""
    rodada = {m: i for i, m in enumerate(ctx.ordem_da_fila(esc))}          # ordem em que a fila gira (padrão: moderno → antigo)
    ativos = sorted(dict.fromkeys(m for m in esc.membros_ativos(d) if not ctx.dispensado_na_escala(m, esc)),
                    key=lambda m: rodada[m])
    ref = rodada.get(ultimo, -1) if ultimo else -1
    ordem = [m for m in ativos if rodada[m] > ref] + [m for m in ativos if rodada[m] <= ref]
    return [m for m in ordem if not _impedido(ctx, m, d)]


def filas_da_escala(esc: Escala) -> list[str]:
    """Filas que o detalhista acompanha na escala (o período roxo tem a sua, criada pelo próprio período)."""
    return ["preta", "vermelha"] if esc.modo == "preta_vermelha" else ["corrida"]


def proximo_da_fila(ctx: Contexto, esc: Escala, fila: str, d: date) -> str | None:
    """Quem é o primeiro a entrar nesta fila a partir de `d` (considera impedimentos e descanso só pela ordem da fila)."""
    seq = _sequencia(ctx, esc, d, esc.ultimo_servico.get(fila))
    return seq[0] if seq else None


def _distribuir_quartos(quartos: list[Quarto], efetivos: list[str]) -> dict[str, list[str]]:
    """Quarto i fica com o efetivo i % n (intercala os militares)."""
    h: dict[str, list[str]] = {m: [] for m in efetivos}
    if efetivos:
        for i, q in enumerate(quartos):
            h[efetivos[i % len(efetivos)]].append(str(q))
    return h


def validar_escala(ctx: Contexto, esc: Escala) -> list[str]:
    """Erros de configuração (ex.: 1x1 não permitido)."""
    erros = []
    for rotulo, mid in [("detalhista", esc.detalhista_id)] + [("auxiliar", a) for a in esc.auxiliares]:
        if mid and not any(m.id == mid for m in ctx.militares):
            erros.append(f"{esc.nome}: {rotulo} não encontrado no cadastro.")
    if esc.detalhista_id and esc.detalhista_id in esc.auxiliares:
        erros.append(f"{esc.nome}: o auxiliar não pode ser o próprio detalhista.")
    if len(set(esc.auxiliares)) != len(esc.auxiliares):
        erros.append(f"{esc.nome}: auxiliar repetido.")
    if esc.categoria not in CATEGORIAS:
        erros.append(f"{esc.nome}: categoria inválida.")
    return erros


def avisos_escala(ctx: Contexto, esc: Escala) -> list[str]:
    """Avisos que NÃO impedem criar ou editar: a escala pode nascer vazia e receber os militares depois (cadastro,
    importação de planilha ou vínculo). Enquanto faltar gente, ela apenas não funciona direito."""
    n = len(ctx.escalaveis(esc))             # detalhista fora da escala não conta
    precisa = esc.militares_dia * (_folgas(esc) + 1)
    if esc.modo == "eventos" or n >= precisa:
        return []
    if n == 0:
        return [f"{esc.nome} ainda não tem militares: cadastre-os em Militares ou importe uma planilha. "
                f"Ela só gera serviços quando tiver pelo menos {precisa} (por dia e descanso configurados)."]
    return [f"{esc.nome} tem {n} militar(es) para {esc.militares_dia} por dia e {_folgas(esc)} folga(s) entre serviços: "
            f"precisa de pelo menos {precisa} para respeitar o descanso."]


# ------------------------------------------------------------------ prevalência
def _ancestrais(ctx: Contexto, esc: Escala) -> set[str]:
    vistos: set[str] = set()
    pilha = list(esc.referencias)
    while pilha:
        i = pilha.pop()
        if i in vistos:
            continue
        vistos.add(i)
        outra = next((e for e in ctx.escalas if e.id == i), None)
        if outra:
            pilha += outra.referencias
    return vistos


def relacionadas(ctx: Contexto, a: Escala, b: Escala) -> bool:
    if (a.categoria == "servico") != (b.categoria == "servico"):
        return True  # serviço x outra escalação: sempre se influenciam, qualquer dono
    return a.dono_id == b.dono_id or b.id in _ancestrais(ctx, a) or a.id in _ancestrais(ctx, b)


def prevalece(ctx: Contexto, a: Escala, b: Escala) -> Escala:
    if (a.categoria == "servico") != (b.categoria == "servico"):
        return a if a.categoria == "servico" else b  # serviço sempre prevalece
    if b.id in _ancestrais(ctx, a):
        return b
    if a.id in _ancestrais(ctx, b):
        return a
    if a.prioridade != b.prioridade:
        return a if a.prioridade > b.prioridade else b
    return a if a.id <= b.id else b


# ------------------------------------------------------------------ geração base
def _inicio(ctx: Contexto) -> date:
    """Primeiro dia a simular: a menor data-base entre as escalas (ou a do sistema, sem escalas)."""
    return min([ctx.base_de(e) for e in ctx.escalas] or [ctx.data_base])


def _gerar_base(ctx: Contexto, fim: date) -> Resultado:
    res = Resultado(dias={})
    ultimo: dict[tuple[str, str], str | None] = {
        (e.id, f): m for e in ctx.escalas for f, m in e.ultimo_servico.items()}
    ultimo_dia: dict[tuple[str, str], date] = {}
    pendentes: dict[tuple[str, str], list[str]] = {}
    d = _inicio(ctx)
    while d <= fim:
        for esc in sorted(ctx.escalas, key=lambda e: (e.categoria != "servico", -e.prioridade, e.id)):
            if d < ctx.base_de(esc) or not funciona(ctx, esc, d):      # antes da data-base da escala: nada
                res.dias[(d, esc.id)] = DiaEscala(esc.id, d, False)
                continue
            evs = _eventos(ctx, esc, d)
            fila = fila_do_dia(ctx, esc, d)
            chave = (esc.id, fila)
            dia = DiaEscala(esc.id, d, True, fila, "; ".join(e.descricao for e in evs if e.descricao))
            res.dias[(d, esc.id)] = dia
            faltas = {o.militar_id: o for o in ctx.ocorrencias
                      if o.data == d and o.escala_id == esc.id}
            seq_full = _sequencia(ctx, esc, d, ultimo.get(chave))
            n = (sum((e.vagas if e.vagas is not None else esc.militares_dia) for e in evs)
                 if esc.modo == "eventos" else esc.militares_dia)
            folgas = _folgas(esc)

            def descansando(m: str) -> bool:
                u = ultimo_dia.get((esc.id, m))
                return u is not None and (d - u).days <= folgas

            ocupados: set[str] = set()
            if esc.categoria != "servico" and esc.respeita_servicos:
                # escalações que não são serviço nunca têm prioridade sobre serviço
                ocupados = {a.militar_id for a in res.alocacoes_do_dia(d) if a.papel == "efetivo"
                            and ctx.escala(a.escala_id).categoria == "servico"}
            bloq = [m for m in seq_full if descansando(m) or m in ocupados]
            pend = [m for m in pendentes.get(chave, []) if m in seq_full and m not in bloq]
            cands = pend + [m for m in seq_full if m not in bloq and m not in pend]
            efet: list[tuple[str, int]] = []
            pos = 0
            while pos < len(cands) and len(efet) < n:
                m = cands[pos]
                if m in faltas:
                    res.devolucoes.append(Devolucao(
                        m, esc.id, d, d + timedelta(days=ctx.janela_devolucao_dias)))
                    dia.alocacoes.append(Alocacao(
                        m, esc.id, d, "efetivo", DISP, [],
                        f"Dispensado do serviço: {faltas[m].motivo.strip() or 'justificativa não informada'}. "
                        f"O retém avançou.", "falta"))
                else:
                    efet.append((m, pos))
                pos += 1
            horarios = _distribuir_quartos(esc.quartos, [m for m, _ in efet])
            for m, p in efet:
                obs = "Avanço de retém (escalado anterior não deu o serviço)." if p >= n else ""
                dia.alocacoes.append(Alocacao(
                    m, esc.id, d, "efetivo", sigla_de(esc, "efetivo"), horarios[m], obs))
            usados = {m for m, _ in efet}
            retens = [m for m in cands[pos:] if m not in faltas and m not in usados][:esc.retem_qtd]
            for m in retens:
                dia.alocacoes.append(Alocacao(m, esc.id, d, "retem", sigla_de(esc, "retem")))
            if len(efet) < n:
                res.avisos.append(
                    f"{d:%d/%m}: {esc.nome} com {len(efet)} de {n} escalados "
                    f"(faltam militares disponíveis/descansados).")
            # avança a fila e guarda quem foi pulado por descanso (não perde a vez)
            da_fila = [m for m, _ in efet if m not in pend]
            novos: list[str] = []
            if da_fila:
                ultimo[chave] = da_fila[-1]
                corte = seq_full.index(da_fila[-1])
                novos = [m for m in bloq if seq_full.index(m) < corte]
            restantes = [m for m in pend if m not in usados]
            antigos = [m for m in pendentes.get(chave, []) if m in bloq]
            pendentes[chave] = list(dict.fromkeys(
                m for m in restantes + antigos + novos if m not in usados))
            for m in usados:
                ultimo_dia[(esc.id, m)] = d
        d += timedelta(days=1)
    return res


# ------------------------------------------------------------------ trocas
def _achar(res: Resultado, d: date, escala_id: str, mid: str) -> Alocacao | None:
    dia = res.dia(d, escala_id)
    return next((a for a in dia.alocacoes if a.militar_id == mid and a.origem != "falta"), None) \
        if dia else None


def _aplicar_trocas_consensuais(ctx: Contexto, res: Resultado) -> None:
    def nome(m):
        return ctx.militar(m).nome
    for t in ctx.trocas:
        if not t.valida:
            res.avisos.append(
                f"Papeleta de {nome(t.saindo)} ↔ {nome(t.entrando)} em {t.data:%d/%m} sem os dois aceites: ignorada.")
            continue
        a = _achar(res, t.data, t.escala_id, t.saindo)
        if a is None:
            res.avisos.append(
                f"Papeleta em {t.data:%d/%m}: {nome(t.saindo)} não está escalado; ignorada.")
            continue
        if _impedido(ctx, t.entrando, t.data) or ctx.dispensado_na_escala(t.entrando, ctx.escala(t.escala_id)):
            res.avisos.append(
                f"Papeleta em {t.data:%d/%m}: {nome(t.entrando)} está impedido; ignorada.")
            continue
        esc = ctx.escala(t.escala_id)
        a.militar_id, a.origem = t.entrando, "t"
        a.sigla = sigla_de(esc, a.papel, "t")
        a.obs = (t.observacao or "Troca de serviço por papeleta") + f" ({nome(t.saindo)} → {nome(t.entrando)})."


def _livre(ctx: Contexto, res: Resultado, mid: str, d: date, esc: Escala) -> bool:
    return (mid in esc.membros_ativos(d)
            and not ctx.dispensado_na_escala(mid, esc)
            and not _impedido(ctx, mid, d)
            and all(a.militar_id != mid for a in res.alocacoes_do_dia(d)))


def _descansado(res: Resultado, esc: Escala, mid: str, d: date, ignorar: date | None = None) -> bool:
    """Respeita o mínimo de folgas em torno de `d` na própria escala."""
    f = _folgas(esc)
    for k in range(-f, f + 1):
        d2 = d + timedelta(days=k)
        if k == 0 or d2 == ignorar:
            continue
        dia = res.dia(d2, esc.id)
        if dia and any(a.militar_id == mid for a in dia.efetivos):
            return False
    return True


def _resolver_conflitos(ctx: Contexto, res: Resultado, fim: date) -> None:
    def nome(m):
        return ctx.militar(m).nome
    ignorados: set[tuple[date, str, str]] = set()
    d = _inicio(ctx)
    while d <= fim:
        while True:
            por_militar: dict[str, list[Alocacao]] = {}
            for a in res.alocacoes_do_dia(d):
                por_militar.setdefault(a.militar_id, []).append(a)
            conflito = None
            for mid, lista in por_militar.items():
                for i in range(len(lista)):
                    for j in range(i + 1, len(lista)):
                        a1, a2 = lista[i], lista[j]
                        e1, e2 = ctx.escala(a1.escala_id), ctx.escala(a2.escala_id)
                        if e1.id == e2.id or not relacionadas(ctx, e1, e2):
                            continue
                        if ((a1.papel == "retem" and e1.categoria == "servico" and e2.categoria != "servico")
                                or (a2.papel == "retem" and e2.categoria == "servico" and e1.categoria != "servico")):
                            continue  # retém de serviço não impede palestra etc.
                        alto, baixo = (a1, a2) if prevalece(ctx, e1, e2).id == e1.id else (a2, a1)
                        if (d, mid, baixo.escala_id) not in ignorados:
                            conflito = (alto, baixo)
                            break
                    if conflito:
                        break
                if conflito:
                    break
            if not conflito:
                break
            alto, baixo = conflito
            esc, esc_alto = ctx.escala(baixo.escala_id), ctx.escala(alto.escala_id)
            if baixo.papel == "retem":
                sub = _substituto_retem(ctx, res, esc, d, baixo)
                if sub:
                    antigo = baixo.militar_id
                    baixo.militar_id, baixo.origem = sub, "tf"
                    baixo.sigla = sigla_de(esc, "retem", "tf")
                    baixo.obs = (f"TF: {nome(antigo)} está em {esc_alto.nome} "
                                 f"({alto.sigla}) no mesmo dia; retém passou a {nome(sub)}.")
                    continue
            else:
                p_aloc = _parceiro_troca(ctx, res, esc, d, baixo, fim)
                if p_aloc:
                    x, p, d2 = baixo.militar_id, p_aloc.militar_id, p_aloc.data
                    texto = (f"TF: {nome(x)} acumulava {esc_alto.nome} em {d:%d/%m}; "
                             f"trocou de data com {nome(p)} ({d2:%d/%m} ↔ {d:%d/%m}).")
                    horarios_x, horarios_p = list(baixo.horarios), list(p_aloc.horarios)
                    baixo.militar_id, baixo.origem, baixo.obs = p, "tf", texto
                    baixo.sigla, baixo.horarios = sigla_de(esc, "efetivo", "tf"), horarios_x
                    p_aloc.militar_id, p_aloc.origem, p_aloc.obs = x, "tf", texto
                    p_aloc.sigla, p_aloc.horarios = sigla_de(esc, "efetivo", "tf"), horarios_p
                    continue
                if esc.modo == "eventos":
                    # escalação avulsa (palestra, cerimônia...): sem outra data para trocar,
                    # entra o próximo livre da fila e o titular fica com a vaga a repor.
                    sub = _substituto_retem(ctx, res, esc, d, baixo)
                    if sub:
                        antigo = baixo.militar_id
                        baixo.militar_id, baixo.origem = sub, "tf"
                        baixo.sigla = sigla_de(esc, "efetivo", "tf")
                        baixo.obs = (f"TF: {nome(antigo)} está em {esc_alto.nome} ({alto.sigla}) no mesmo dia; "
                                     f"substituído por {nome(sub)} e fica com a vaga a repor.")
                        res.devolucoes.append(Devolucao(
                            antigo, esc.id, d, d + timedelta(days=ctx.janela_devolucao_dias)))
                        continue
            ignorados.add((d, baixo.militar_id, baixo.escala_id))
            res.avisos.append(
                f"CONFLITO {d:%d/%m}: {nome(baixo.militar_id)} em {esc_alto.nome} e {esc.nome} "
                f"sem troca possível; resolver manualmente.")
            baixo.obs = (baixo.obs + " CONFLITO sem troca possível.").strip()
        d += timedelta(days=1)


def _substituto_retem(ctx, res, esc: Escala, d: date, aloc: Alocacao) -> str | None:
    seq = _sequencia(ctx, esc, d, aloc.militar_id)
    ocupados = {a.militar_id for a in res.alocacoes_do_dia(d)}
    return next((m for m in seq if m not in ocupados), None)


def _parceiro_troca(ctx, res, esc: Escala, d: date, baixo: Alocacao, fim: date) -> Alocacao | None:
    x = baixo.militar_id
    util_d = dia_util(d, ctx, esc)
    melhores: list[tuple[tuple, Alocacao]] = []
    for delta in range(-ctx.janela_troca_dias, ctx.janela_troca_dias + 1):
        d2 = d + timedelta(days=delta)
        if delta == 0 or d2 < ctx.base_de(esc) or d2 > fim:
            continue
        dia2 = res.dia(d2, esc.id)
        if not dia2 or not dia2.funciona:
            continue
        for a in dia2.efetivos:
            if a.origem != "normal" or a.militar_id == x:
                continue
            if (_livre(ctx, res, a.militar_id, d, esc) and _livre(ctx, res, x, d2, esc)
                    and _descansado(res, esc, a.militar_id, d, ignorar=d2)
                    and _descansado(res, esc, x, d2, ignorar=d)):
                chave = (dia_util(d2, ctx, esc) != util_d, abs(delta), delta < 0)
                melhores.append((chave, a))
    return min(melhores, key=lambda t: t[0])[1] if melhores else None


# ------------------------------------------------------------------ API pública
def gerar(ctx: Contexto, fim: date) -> Resultado:
    """Gera todas as escalas, cada uma a partir da sua data-base, até `fim`.

    Internamente vai até `fim + janela_troca_dias` para que o resultado de um dia não dependa
    do tamanho da prévia pedida (7, 15 ou 30 dias).
    """
    limite = fim + timedelta(days=ctx.janela_troca_dias)
    res = _gerar_base(ctx, limite)
    _aplicar_trocas_consensuais(ctx, res)
    _resolver_conflitos(ctx, res, limite)
    return res


def respeita_descanso(res: Resultado, esc: Escala, mid: str, d: date) -> bool:
    return _descansado(res, esc, mid, d)


def sugerir_devolucao(ctx: Contexto, res: Resultado, dev: Devolucao,
                      exigir_descanso: bool = True) -> list[tuple[date, str]]:
    """Dias dentro do prazo, mais próximos do original, em que o militar está livre.

    Devolve (data, militar que serve naquele dia): é com ele que se faz a papeleta.
    Com `exigir_descanso=False`, inclui também dias que deixam o militar com menos folgas que o mínimo
    (a tela avisa), mas as que respeitam o descanso vêm primeiro.
    """
    esc = ctx.escala(dev.escala_id)
    out = []
    d = dev.data_origem + timedelta(days=1)
    while d <= dev.prazo:
        dia = res.dia(d, esc.id)
        if dia and dia.funciona and _livre(ctx, res, dev.militar_id, d, esc):
            descansado = _descansado(res, esc, dev.militar_id, d)
            if descansado or not exigir_descanso:
                out.extend(((d, a.militar_id), descansado) for a in dia.efetivos if a.origem == "normal")
        d += timedelta(days=1)
    out.sort(key=lambda t: (not t[1], abs((t[0][0] - dev.data_origem).days)))
    return [x for x, _ in out]

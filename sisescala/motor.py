"""Motor de geração das escalas.

Regras principais
- Cada escala tem filas independentes (corrida | preta | vermelha | roxa:<período>).
  A fila que não é do dia fica congelada e retoma de onde parou.
- Ordem: do mais antigo (antiguidade 1) ao mais moderno, circular, a partir de quem deu o último serviço.
- Retém = próximos da fila após os efetivos. Se um efetivo falha (Ocorrencia), o retém avança.
- Troca consensual (papeleta) só vale com os dois aceites -> SVÇ (T).
- Troca forçada (TF): militar com dois serviços no mesmo dia mantém o de maior prioridade e
  é realocado, por troca de datas com outro militar da escala de menor prioridade, para dar ambos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .calendario import dia_util, roxa_do_dia
from .modelos import (RT, RT_T, RT_TF, SVC, SVC_T, SVC_TF, Contexto, Escala, Quarto)


@dataclass
class Alocacao:
    militar_id: str
    escala_id: str
    data: date
    papel: str                     # "efetivo" | "retem"
    sigla: str                     # SVÇ, SVÇ (TF), SVÇ (T), RT, RT (TF), RT (T)
    horarios: list[str] = field(default_factory=list)
    obs: str = ""


@dataclass
class DiaEscala:
    escala_id: str
    data: date
    funciona: bool
    fila: str | None = None
    alocacoes: list[Alocacao] = field(default_factory=list)

    @property
    def efetivos(self) -> list[Alocacao]:
        return [a for a in self.alocacoes if a.papel == "efetivo"]

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
        return [a for (dd, _), de in self.dias.items() if dd == d for a in de.alocacoes]


# ------------------------------------------------------------------ utilidades
def _impedido(ctx: Contexto, mid: str, d: date) -> bool:
    return any(i.militar_id == mid and i.cobre(d) for i in ctx.impedimentos)


def funciona(ctx: Contexto, esc: Escala, d: date) -> bool:
    manual = next((g for g in ctx.guarnecimentos if g.data == d and g.escala_id == esc.id), None)
    if manual is not None:
        return manual.guarnece
    if esc.participa_roxa and roxa_do_dia(d, ctx):
        return True
    return esc.funciona_em == "todos" or dia_util(d, ctx)


def fila_do_dia(ctx: Contexto, esc: Escala, d: date) -> str:
    if esc.participa_roxa:
        r = roxa_do_dia(d, ctx)
        if r:
            return f"roxa:{r.id}"
    if esc.modo == "corrida":
        return "corrida"
    return "preta" if dia_util(d, ctx) else "vermelha"


def _sequencia(ctx: Contexto, esc: Escala, d: date, ultimo: str | None) -> list[str]:
    """Militares ativos e disponíveis, em ordem circular depois de `ultimo`."""
    antig = {m.id: m.antiguidade for m in ctx.militares}
    ativos = sorted(esc.membros_ativos(d), key=lambda m: antig[m])
    ref = antig.get(ultimo, 0) if ultimo else 0
    ordem = [m for m in ativos if antig[m] > ref] + [m for m in ativos if antig[m] <= ref]
    return [m for m in ordem if not _impedido(ctx, m, d)]


def _distribuir_quartos(quartos: list[Quarto], efetivos: list[str]) -> dict[str, list[str]]:
    """Quarto i fica com o efetivo i % n (intercala os militares)."""
    h: dict[str, list[str]] = {m: [] for m in efetivos}
    if efetivos:
        for i, q in enumerate(quartos):
            h[efetivos[i % len(efetivos)]].append(str(q))
    return h


# ------------------------------------------------------------------ geração base
def _gerar_base(ctx: Contexto, fim: date) -> Resultado:
    res = Resultado(dias={})
    ultimo: dict[tuple[str, str], str | None] = {
        (e.id, f): m for e in ctx.escalas for f, m in e.ultimo_servico.items()}
    d = ctx.data_base
    while d <= fim:
        for esc in sorted(ctx.escalas, key=lambda e: -e.prioridade):
            if not funciona(ctx, esc, d):
                res.dias[(d, esc.id)] = DiaEscala(esc.id, d, False)
                continue
            fila = fila_do_dia(ctx, esc, d)
            chave = (esc.id, fila)
            dia = DiaEscala(esc.id, d, True, fila)
            res.dias[(d, esc.id)] = dia
            faltas = {o.militar_id: o for o in ctx.ocorrencias
                      if o.data == d and o.escala_id == esc.id}
            seq = _sequencia(ctx, esc, d, ultimo.get(chave))
            n = esc.militares_dia
            efet: list[tuple[str, int]] = []   # (militar, posição na sequência)
            pos = 0
            while pos < len(seq) and len(efet) < n:
                m = seq[pos]
                if m in faltas:
                    res.devolucoes.append(Devolucao(
                        m, esc.id, d, d + timedelta(days=ctx.janela_devolucao_dias)))
                    dia.alocacoes.append(Alocacao(
                        m, esc.id, d, "efetivo", "Falta", [],
                        f"Não pôde dar o serviço ({faltas[m].motivo or 'sem motivo informado'}); "
                        f"retém avançou."))
                else:
                    efet.append((m, pos))
                pos += 1
            horarios = _distribuir_quartos(esc.quartos, [m for m, _ in efet])
            for m, p in efet:
                obs = ""
                if p >= n:  # veio do retém
                    obs = "Avanço de retém (escalado anterior não deu o serviço)."
                dia.alocacoes.append(Alocacao(m, esc.id, d, "efetivo", SVC, horarios[m], obs))
            usados = {m for m, _ in efet}
            retens = [m for m in seq[pos:] if m not in faltas and m not in usados][:esc.retem_qtd]
            for m in retens:
                dia.alocacoes.append(Alocacao(m, esc.id, d, "retem", RT))
            if len(efet) < n:
                res.avisos.append(
                    f"{d:%d/%m}: {esc.nome} com {len(efet)} de {n} efetivos (faltam militares disponíveis).")
            if efet:
                ultimo[chave] = efet[-1][0]
        d += timedelta(days=1)
    return res


# ------------------------------------------------------------------ trocas
def _achar(res: Resultado, d: date, escala_id: str, mid: str) -> Alocacao | None:
    dia = res.dia(d, escala_id)
    return next((a for a in dia.alocacoes if a.militar_id == mid and a.sigla != "Falta"), None) \
        if dia else None


def _aplicar_trocas_consensuais(ctx: Contexto, res: Resultado) -> None:
    for t in ctx.trocas:
        nome = lambda m: ctx.militar(m).nome  # noqa: E731
        if not t.valida:
            res.avisos.append(
                f"Papeleta de {nome(t.saindo)} ↔ {nome(t.entrando)} em {t.data:%d/%m} sem os dois aceites: ignorada.")
            continue
        a = _achar(res, t.data, t.escala_id, t.saindo)
        if a is None:
            res.avisos.append(
                f"Papeleta em {t.data:%d/%m}: {nome(t.saindo)} não está escalado; ignorada.")
            continue
        if _impedido(ctx, t.entrando, t.data):
            res.avisos.append(
                f"Papeleta em {t.data:%d/%m}: {nome(t.entrando)} está impedido; ignorada.")
            continue
        a.militar_id = t.entrando
        a.sigla = SVC_T if a.papel == "efetivo" else RT_T
        a.obs = (t.observacao or "Troca de serviço por papeleta") + f" ({nome(t.saindo)} → {nome(t.entrando)})."


def _livre(ctx: Contexto, res: Resultado, mid: str, d: date, esc: Escala) -> bool:
    return (mid in esc.membros_ativos(d)
            and not _impedido(ctx, mid, d)
            and all(a.militar_id != mid for a in res.alocacoes_do_dia(d)))


def _resolver_conflitos(ctx: Contexto, res: Resultado, fim: date) -> None:
    prio = {e.id: e.prioridade for e in ctx.escalas}
    nome = lambda m: ctx.militar(m).nome  # noqa: E731
    ignorados: set[tuple[date, str, str]] = set()
    d = ctx.data_base
    while d <= fim:
        while True:
            por_militar: dict[str, list[Alocacao]] = {}
            for a in res.alocacoes_do_dia(d):
                if a.sigla != "Falta":
                    por_militar.setdefault(a.militar_id, []).append(a)
            conflito = None
            for mid, lista in por_militar.items():
                if len(lista) > 1:
                    lista.sort(key=lambda a: (-prio[a.escala_id], a.papel != "efetivo"))
                    for baixo in lista[1:]:
                        if (d, mid, baixo.escala_id) not in ignorados:
                            conflito = (lista[0], baixo)
                            break
                if conflito:
                    break
            if not conflito:
                break
            alto, baixo = conflito
            esc = ctx.escala(baixo.escala_id)
            esc_alto = ctx.escala(alto.escala_id)
            if baixo.papel == "retem":
                sub = _substituto_retem(ctx, res, esc, d, baixo)
                if sub:
                    antigo = baixo.militar_id
                    baixo.militar_id, baixo.sigla = sub, RT_TF
                    baixo.obs = (f"TF: {nome(antigo)} está de {esc_alto.nome} "
                                 f"({alto.sigla}) no mesmo dia; retém passou a {nome(sub)}.")
                    continue
            else:
                parceiro = _parceiro_troca(ctx, res, esc, d, baixo, fim)
                if parceiro:
                    p_aloc = parceiro
                    x, p, d2 = baixo.militar_id, p_aloc.militar_id, p_aloc.data
                    texto = (f"TF: {nome(x)} acumulava {esc_alto.nome} em {d:%d/%m}; "
                             f"trocou de data com {nome(p)} ({d2:%d/%m} ↔ {d:%d/%m}).")
                    baixo.militar_id, baixo.sigla, baixo.obs = p, SVC_TF, texto
                    p_aloc.militar_id, p_aloc.sigla, p_aloc.obs = x, SVC_TF, texto
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
    util_d = dia_util(d, ctx)
    melhores: list[tuple[tuple, Alocacao]] = []
    for delta in range(-ctx.janela_troca_dias, ctx.janela_troca_dias + 1):
        d2 = d + timedelta(days=delta)
        if delta == 0 or d2 < ctx.data_base or d2 > fim:
            continue
        dia2 = res.dia(d2, esc.id)
        if not dia2 or not dia2.funciona:
            continue
        for a in dia2.efetivos:
            if a.sigla != SVC or a.militar_id == x:
                continue
            if _livre(ctx, res, a.militar_id, d, esc) and _livre(ctx, res, x, d2, esc):
                chave = (dia_util(d2, ctx) != util_d, abs(delta), delta < 0)
                melhores.append((chave, a))
    return min(melhores, key=lambda t: t[0])[1] if melhores else None


# ------------------------------------------------------------------ API pública
def gerar(ctx: Contexto, fim: date) -> Resultado:
    """Gera a escala de `ctx.data_base` até `fim`.

    Internamente vai até `fim + janela_troca_dias` para que o resultado de um dia não dependa
    do tamanho da prévia pedida (7, 15 ou 30 dias).
    """
    limite = fim + timedelta(days=ctx.janela_troca_dias)
    res = _gerar_base(ctx, limite)
    _aplicar_trocas_consensuais(ctx, res)
    _resolver_conflitos(ctx, res, limite)
    return res


def sugerir_devolucao(ctx: Contexto, res: Resultado, dev: Devolucao) -> list[tuple[date, str]]:
    """Dias dentro do prazo, mais próximos do original, em que o militar está livre.

    Devolve (data, militar que serve naquele dia): é com ele que se faz a papeleta.
    """
    esc = ctx.escala(dev.escala_id)
    out = []
    d = dev.data_origem + timedelta(days=1)
    while d <= dev.prazo:
        dia = res.dia(d, esc.id)
        if dia and dia.funciona and _livre(ctx, res, dev.militar_id, d, esc):
            out.extend((d, a.militar_id) for a in dia.efetivos if a.sigla == SVC)
        d += timedelta(days=1)
    return sorted(out, key=lambda t: abs((t[0] - dev.data_origem).days))

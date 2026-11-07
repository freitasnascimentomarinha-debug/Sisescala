"""Modelos de dados. Tudo que é regra de negócio é configurável aqui (com padrões)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# --- siglas exibidas na prévia -------------------------------------------------
SVC, SVC_TF, SVC_T = "SVÇ", "SVÇ (TF)", "SVÇ (T)"
RT, RT_TF, RT_T = "RT", "RT (TF)", "RT (T)"
FERIAS, DISP, DBQ, CURSO, BAIXA, FALTA = "Férias", "Disp", "DBQ", "Curso", "Baixa", "Falta"

# tipo de impedimento -> sigla
TIPOS_IMPEDIMENTO = {
    "ferias": FERIAS,
    "curso": CURSO,
    "dispensa": DISP,   # exige motivo e arquivo
    "baixa": BAIXA,     # passou mal / baixa médica
    "desembarque": DBQ,  # sem data fim: nunca mais dá serviço
}


@dataclass
class Militar:
    id: str
    nome: str
    posto: str = ""
    antiguidade: int = 0  # 1 = mais antigo


@dataclass
class Pertinencia:
    """Participação do militar numa escala (permite mudança de escala por período)."""
    militar_id: str
    inicio: date | None = None
    fim: date | None = None

    def ativo(self, d: date) -> bool:
        return (self.inicio is None or d >= self.inicio) and (self.fim is None or d <= self.fim)


@dataclass
class Quarto:
    inicio: str  # "00:00"
    fim: str     # "04:00"

    def __str__(self) -> str:
        return f"{self.inicio}-{self.fim}"


def quartos_padrao(horas: int = 4) -> list[Quarto]:
    """Divide as 24h em quartos de `horas` horas (4h -> 6 quartos, 2h -> 12 quartos)."""
    return [Quarto(f"{h:02d}:00", f"{(h + horas) % 24:02d}:00") for h in range(0, 24, horas)]


@dataclass
class Escala:
    id: str
    nome: str
    sigla: str = ""
    prioridade: int = 1            # maior prevalece (pernoite > diária)
    modo: str = "corrida"          # "corrida" | "preta_vermelha"
    funciona_em: str = "todos"     # "todos" | "uteis" (padrão se não houver guarnecimento manual)
    militares_dia: int = 1         # efetivos por dia
    retem_qtd: int = 1
    quartos: list[Quarto] = field(default_factory=list)  # vazio = serviço corrido sem quartos
    membros: list[Pertinencia] = field(default_factory=list)
    participa_roxa: bool = True
    # ponto de partida de cada fila na data-base: {"corrida"|"preta"|"vermelha": militar_id}
    ultimo_servico: dict[str, str] = field(default_factory=dict)

    def membros_ativos(self, d: date) -> list[str]:
        return [p.militar_id for p in self.membros if p.ativo(d)]


@dataclass
class Impedimento:
    militar_id: str
    tipo: str                 # chave de TIPOS_IMPEDIMENTO
    inicio: date
    fim: date | None = None   # None = indeterminado (ex.: desembarque)
    motivo: str = ""
    anexo: str = ""           # link/arquivo (obrigatório para dispensa)

    def cobre(self, d: date) -> bool:
        return d >= self.inicio and (self.fim is None or d <= self.fim)

    def validar(self) -> list[str]:
        erros = []
        if self.tipo not in TIPOS_IMPEDIMENTO:
            erros.append(f"tipo inválido: {self.tipo}")
        if self.tipo == "dispensa" and not (self.motivo and self.anexo):
            erros.append("dispensa exige motivo e arquivo anexo")
        if self.tipo != "desembarque" and self.fim is None:
            erros.append("informe a data final")
        return erros


@dataclass
class DiaEspecial:
    """Feriado manual (municipal etc.) ou dia sem expediente (licença administrativa)."""
    data: date
    tipo: str = "sem_expediente"  # "feriado" | "sem_expediente"
    descricao: str = ""


@dataclass
class Guarnecimento:
    """Decisão do comando de guarnecer (ou não) uma escala em um dia específico."""
    data: date
    escala_id: str
    guarnece: bool = True


@dataclass
class PeriodoRoxa:
    id: str
    nome: str
    inicio: date
    fim: date


@dataclass
class Ocorrencia:
    """Militar escalado não pôde dar o serviço: o retém avança."""
    data: date
    escala_id: str
    militar_id: str
    motivo: str = ""


@dataclass
class Troca:
    """Papeleta de troca de serviço (consensual). Só vale com os dois aceites."""
    data: date
    escala_id: str
    saindo: str
    entrando: str
    aceite_saindo: bool = False
    aceite_entrando: bool = False
    observacao: str = ""

    @property
    def valida(self) -> bool:
        return self.aceite_saindo and self.aceite_entrando


@dataclass
class Contexto:
    """Tudo que o motor precisa. Vem do repositório (Sheets hoje, PostgreSQL depois)."""
    militares: list[Militar]
    escalas: list[Escala]
    data_base: date                       # data a partir da qual `ultimo_servico` é válido
    impedimentos: list[Impedimento] = field(default_factory=list)
    dias_especiais: list[DiaEspecial] = field(default_factory=list)
    guarnecimentos: list[Guarnecimento] = field(default_factory=list)
    roxas: list[PeriodoRoxa] = field(default_factory=list)
    ocorrencias: list[Ocorrencia] = field(default_factory=list)
    trocas: list[Troca] = field(default_factory=list)
    uf: str = "RJ"
    janela_devolucao_dias: int = 30       # configurável
    janela_troca_dias: int = 15           # busca de parceiro na troca forçada

    def militar(self, mid: str) -> Militar:
        return next(m for m in self.militares if m.id == mid)

    def escala(self, eid: str) -> Escala:
        return next(e for e in self.escalas if e.id == eid)

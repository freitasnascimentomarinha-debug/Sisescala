"""Modelos de dados. Tudo que é regra de negócio é configurável aqui (com padrões)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# --- siglas exibidas na prévia -------------------------------------------------
SVC, SVC_TF, SVC_T = "SVÇ", "SVÇ (TF)", "SVÇ (T)"
RT, RT_TF, RT_T = "RT", "RT (TF)", "RT (T)"
FERIAS, DISP, DBQ, CURSO, BAIXA, FALTA = "Férias", "Disp", "DBQ", "Curso", "Baixa", "Falta"
DTQ = "DTQ"  # destaque: militar destacado por período, não concorre à escala

# tipo de impedimento -> sigla
TIPOS_IMPEDIMENTO = {
    "ferias": FERIAS,
    "curso": CURSO,
    "dispensa": DISP,   # exige motivo e arquivo
    "baixa": BAIXA,     # passou mal / baixa médica
    "desembarque": DBQ,  # sem data fim: nunca mais dá serviço
    "destaque": DTQ,     # destacado (em outra OM etc.) durante um período
}

# categorias de escalação: (rótulo, sigla do militar escalado). "servico" usa SVÇ.
CATEGORIAS = {
    "servico": ("Serviço", SVC),
    "palestra": ("Palestra", "PAL"),
    "curso": ("Curso (escalação)", "CUR"),
    "visita_religiosa": ("Visitação religiosa", "VIS"),
    "cerimonia": ("Participação em cerimônia", "CER"),
    "apoio": ("Apoio (destaque em outra OM)", "APO"),
    "outro": ("Outro", "OUT"),
}
NIVEIS = ("leitura", "edicao")


@dataclass
class Militar:
    id: str
    nome: str                 # nome de guerra
    posto: str = ""           # posto ou graduação
    antiguidade: int = 0      # 1 = mais antigo
    nip: str = ""
    om: str = ""              # sigla ou código da OM


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


def hora_curta(hhmm: str) -> str:
    h, m = hhmm.split(":")
    return f"{int(h)}h" + (m if m != "00" else "")


def horarios_curtos(horarios: list[str]) -> str:
    """["04:00-08:00", "16:00-20:00"] -> "4h/16h" (hora de início de cada quarto)."""
    return "/".join(hora_curta(h.split("-")[0]) for h in horarios)


def quartos_padrao(horas: int = 4) -> list[Quarto]:
    """Divide as 24h em quartos de `horas` horas (4h -> 6 quartos, 2h -> 12 quartos)."""
    return [Quarto(f"{h:02d}:00", f"{(h + horas) % 24:02d}:00") for h in range(0, 24, horas)]


@dataclass
class Escala:
    id: str
    nome: str
    sigla: str = ""
    dono_id: str = ""              # usuário que criou a escala
    categoria: str = "servico"     # chave de CATEGORIAS
    sigla_evento: str = ""         # sigla própria (categoria "outro" ou personalizada)
    tipo: str = ""                 # texto livre de destaque no card: "Diária", "Pernoite"...
    prioridade: int = 1            # maior prevalece (pernoite > diária)
    modo: str = "corrida"          # "corrida" | "preta_vermelha" | "eventos" (só nos dias de evento)
    respeita_servicos: bool = True  # categorias que não são serviço só escalam quem não está de efetivo serviço
    folgas_minimas: int = 2        # "2x1": mínimo de folgas entre dois serviços do mesmo militar
    referencias: list[str] = field(default_factory=list)  # escalas (de outros) que prevalecem sobre esta
    compartilhado_com: dict[str, str] = field(default_factory=dict)  # usuario_id -> "leitura"|"edicao"
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
class Evento:
    """Dia de uma escalação avulsa (palestra, cerimônia, apoio...) numa escala de modo "eventos"."""
    escala_id: str
    data: date
    descricao: str = ""
    hora: str = ""
    local: str = ""
    vagas: int | None = None     # None = usa militares_dia da escala


@dataclass
class Usuario:
    id: str
    nome: str


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
    usuarios: list[Usuario] = field(default_factory=list)
    eventos: list[Evento] = field(default_factory=list)
    janela_devolucao_dias: int = 30       # configurável
    janela_troca_dias: int = 15           # busca de parceiro na troca forçada

    def militar(self, mid: str) -> Militar:
        return next(m for m in self.militares if m.id == mid)

    def escala(self, eid: str) -> Escala:
        return next(e for e in self.escalas if e.id == eid)

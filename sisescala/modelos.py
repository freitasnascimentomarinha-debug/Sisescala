"""Modelos de dados. Tudo que é regra de negócio é configurável aqui (com padrões)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

# --- siglas exibidas na prévia -------------------------------------------------
SVC, SVC_TF, SVC_T = "SVÇ", "SVÇ (TF)", "SVÇ (T)"
RT, RT_TF, RT_T = "RT", "RT (TF)", "RT (T)"
FERIAS, DISP, DBQ, CURSO = "Férias", "Disp", "DBQ", "Curso"
DTQ = "DTQ"  # destaque: militar destacado por período, não concorre à escala

# tipo de impedimento -> sigla. Baixa e falta NÃO são status próprios: o militar fica "Disp" (dispensado),
# com a justificativa lançada pelo detalhista.
TIPOS_IMPEDIMENTO = {
    "ferias": FERIAS,
    "curso": CURSO,
    "dispensa": DISP,               # com documento: exige motivo e arquivo
    "dispensa_justificada": DISP,   # baixa/falta: exige a justificativa do detalhista
    "desembarque": DBQ,             # sem data fim: nunca mais dá serviço
    "destaque": DTQ,                # destacado (em outra OM etc.) durante um período
    "baixa": DISP,                  # legado (dados antigos): tratado como dispensa; não aparece mais nas telas
}
TIPOS_VISIVEIS = [t for t in TIPOS_IMPEDIMENTO if t != "baixa"]
ROTULO_IMPEDIMENTO = {
    "ferias": "Férias", "curso": "Curso", "dispensa": "Dispensado – com documento",
    "dispensa_justificada": "Dispensado – baixa ou falta (justificativa)", "desembarque": "Desembarque (DBQ)",
    "destaque": "Destaque (DTQ)", "baixa": "Dispensado – baixa (legado)",
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
    email: str = ""
    ramal: str = ""
    celular: str = ""
    especialidade: str = ""   # ex.: PL, MO, CL (aparece depois do posto: 2ºSG-PL)

    @property
    def rotulo(self) -> str:
        """Como o militar aparece na escalação e na prévia: GRADUAÇÃO-ESPECIALIDADE NOME DE GUERRA (NIP)."""
        return rotulo_militar(self)


def formatar_nip(nip: str) -> str:
    """NIP de 8 dígitos no formato do cartão: 11.0316.11 (outros tamanhos ficam como foram digitados)."""
    import re
    d = re.sub(r"\D", "", nip or "")
    return f"{d[:2]}.{d[2:6]}.{d[6:]}" if len(d) == 8 else (nip or "").strip()


def rotulo_militar(m: "Militar", com_nip: bool = True) -> str:
    """`2ºSG-PL Freitas (11.0316.11)`: posto/graduação, especialidade, nome de guerra e NIP (o que existir)."""
    posto = (m.posto or "").strip()
    esp = (m.especialidade or "").strip()
    cargo = f"{posto}-{esp}" if posto and esp else (posto or esp)
    txt = f"{cargo} {m.nome}".strip()
    if com_nip and (m.nip or "").strip():
        txt += f" ({formatar_nip(m.nip)})"
    return txt


@dataclass
class Pertinencia:
    """Participação do militar numa escala (permite mudança de escala por período)."""
    militar_id: str
    inicio: date | None = None
    fim: date | None = None
    antiguidade: int = 0   # posição NESTA escala (1 = mais antigo); 0 = ainda não numerada (usa a do cadastro)

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
    om: str = ""                   # Organização Militar que gerencia a escala (cabeçalho dos documentos)
    # Detalhe de serviço (salvos para saírem sempre no documento)
    det_instrucoes: str = ""
    det_recomendacoes: str = ""
    det_regras: str = ""
    ass_detalhista: str = ""
    ass_auxiliar: str = ""
    brasao_b64: str = ""               # brasão próprio da escala (PNG reduzido, base64); vazio = Armas Nacionais (padrão)
    encarregado_usuario_id: str = ""   # conta designada para assinar como Encarregado do Detalhe
    vice_usuario_id: str = ""          # conta designada para assinar como Vice-Diretor
    ass_encarregado: str = ""
    ass_vice_diretor: str = ""
    uf: str = ""                   # UF da OM (feriados estaduais); vazio = padrão do sistema
    data_base: date | None = None  # a partir daqui `ultimo_servico` vale; vazio = data-base do sistema
    detalhista_id: str = ""        # militar que é o detalhista desta escala (um só por escala)
    detalhista_escalavel: bool = False  # padrão: o detalhista fica FORA da escala; True = concorre como os demais
    auxiliares: list[str] = field(default_factory=list)  # auxiliares do detalhista (militares): vários, concorrendo ou não
    categoria: str = "servico"     # chave de CATEGORIAS
    sigla_evento: str = ""         # sigla própria (categoria "outro" ou personalizada)
    tipo: str = ""                 # texto livre de destaque no card: "Diária", "Pernoite"...
    prioridade: int = 1            # maior prevalece (pernoite > diária)
    modo: str = "corrida"          # "corrida" | "preta_vermelha" | "eventos" (só nos dias de evento)
    antecedencia_horas: int = 24   # papeleta de troca: antecedência mínima antes do serviço
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
    # sentido da fila: "moderno_antigo" (padrão: começa pelo mais moderno e vai subindo até o mais antigo) ou "antigo_moderno"
    sentido_fila: str = "moderno_antigo"

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
    criado_por: str = ""          # conta de quem lançou
    criado_em: datetime | None = None
    alterado_por: str = ""         # última edição do lançamento (quem e quando)
    alterado_em: datetime | None = None

    def cobre(self, d: date) -> bool:
        return d >= self.inicio and (self.fim is None or d <= self.fim)

    def validar(self) -> list[str]:
        erros = []
        if self.tipo not in TIPOS_IMPEDIMENTO:
            erros.append(f"tipo inválido: {self.tipo}")
        if self.tipo == "dispensa" and not (self.motivo.strip() and self.anexo.strip()):
            erros.append("dispensa com documento exige motivo e arquivo anexo")
        if self.tipo in ("dispensa_justificada", "baixa") and not self.motivo.strip():
            erros.append("informe a justificativa da dispensa (baixa ou falta)")
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
    criado_por: str = ""          # conta de quem lançou
    criado_em: datetime | None = None
    alterado_por: str = ""         # última edição do lançamento (quem e quando)
    alterado_em: datetime | None = None


@dataclass
class Usuario:
    """Conta de acesso. `perfil`: "detalhista" (cria/edita escalas) ou "militar" (vê a própria escala e
    pede trocas para si). `admin` gerencia contas."""
    id: str
    nome: str
    login: str = ""
    senha_hash: str = ""          # bcrypt; nunca a senha
    militar_id: str = ""          # militar a quem a conta pertence (obrigatório para perfil militar)
    perfil: str = "detalhista"
    admin: bool = False
    ativo: bool = True
    tentativas: int = 0           # falhas seguidas de login/PIN
    bloqueado_ate: datetime | None = None
    email: str = ""
    ramal: str = ""
    celular: str = ""
    pin_hash: str = ""            # PIN de assinatura (bcrypt), criado ao pedir o vínculo
    nip: str = ""                 # NIP informado no cadastro (o login é o NIP normalizado)
    om: str = ""                  # OM informada no cadastro
    situacao: str = "ativo"       # pendente (aguarda o administrador) | ativo | bloqueado | rejeitado
    trocar_senha: bool = False    # senha provisória: precisa ser trocada no primeiro acesso
    nome_guerra: str = ""         # informados no cadastro; completam o cadastro do militar ao vincular
    posto: str = ""               # posto ou graduação
    especialidade: str = ""


@dataclass
class DiaEspecial:
    """Feriado manual (municipal etc.) ou dia sem expediente (licença administrativa)."""
    data: date
    tipo: str = "sem_expediente"  # "feriado" | "sem_expediente"
    descricao: str = ""
    escala_id: str = ""           # vazio = vale para todas as escalas (só o administrador cria); senão, só para essa escala
    data_fim: date | None = None  # período (licença administrativa, recesso…): de `data` até `data_fim`
    conta_como: str = ""          # "" = pelo tipo (feriado e sem expediente contam como vermelha) | "preta" | "vermelha"
    criado_por: str = ""          # conta de quem lançou
    criado_em: datetime | None = None
    alterado_por: str = ""         # última edição do lançamento (quem e quando)
    alterado_em: datetime | None = None

    def abrange(self, d: date) -> bool:
        return self.data <= d <= (self.data_fim or self.data)


@dataclass
class Guarnecimento:
    """Decisão do comando de guarnecer (ou não) uma escala em um dia específico."""
    data: date
    escala_id: str
    guarnece: bool = True
    criado_por: str = ""          # conta de quem lançou
    criado_em: datetime | None = None
    alterado_por: str = ""         # última edição do lançamento (quem e quando)
    alterado_em: datetime | None = None


@dataclass
class PeriodoRoxa:
    id: str
    nome: str
    inicio: date
    fim: date
    escala_id: str = ""           # vazio = vale para todas as escalas (só o administrador cria)
    criado_por: str = ""          # conta de quem lançou
    criado_em: datetime | None = None
    alterado_por: str = ""         # última edição do lançamento (quem e quando)
    alterado_em: datetime | None = None


@dataclass
class Ocorrencia:
    """Militar escalado não pôde dar o serviço: o retém avança."""
    data: date
    escala_id: str
    militar_id: str
    motivo: str = ""              # justificativa lançada pelo detalhista (obrigatória na tela)
    criado_por: str = ""          # conta de quem lançou
    criado_em: datetime | None = None
    alterado_por: str = ""         # última edição do lançamento (quem e quando)
    alterado_em: datetime | None = None

    def validar(self) -> list[str]:
        return [] if self.motivo.strip() else ["informe a justificativa da dispensa"]


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
    papeleta_id: str = ""         # preenchido quando a troca nasce de uma papeleta

    @property
    def valida(self) -> bool:
        return self.aceite_saindo and self.aceite_entrando


@dataclass
class Vinculo:
    """Pedido de uma conta para ser reconhecida como um militar da escala (aprovado pelo detalhista)."""
    id: str
    usuario_id: str
    militar_id: str
    escala_id: str                # escala (detalhe) em que o pedido foi feito; quem a edita decide
    criado_em: datetime
    pin_hash: str = ""            # PIN escolhido; passa para a conta quando aprovado
    status: str = "pendente"      # pendente | aprovado | rejeitado | cancelado
    decidido_por: str = ""
    decidido_em: datetime | None = None
    motivo_rejeicao: str = ""


@dataclass
class Disponibilidade:
    """Militar sinaliza que está aberto a trocar o serviço de um dia em que está escalado."""
    escala_id: str
    militar_id: str
    data: date
    criado_em: datetime
    criado_por: str = ""


@dataclass
class PedidoAcesso:
    """Pedido de um usuário para enxergar uma escala de outro detalhista (o detalhista aprova ou rejeita)."""
    id: str
    usuario_id: str
    escala_id: str
    criado_em: datetime
    mensagem: str = ""
    status: str = "pendente"      # pendente | aprovado | rejeitado | cancelado
    decidido_por: str = ""
    decidido_em: datetime | None = None
    motivo_rejeicao: str = ""


@dataclass
class AssinaturaDetalhe:
    """Assinatura eletrônica (PIN) do detalhista num detalhe de serviço. `codigo` é o SHA-256 do `conteudo` (o JSON do que foi
    assinado: escala, período, textos e quem estava escalado), de modo que o registro se confere sozinho."""
    codigo: str
    escala_id: str
    inicio: date
    fim: date
    usuario_id: str
    nome: str
    nip: str
    om: str
    em: datetime
    conteudo: str
    papel: str = "detalhista"      # "detalhista" | "auxiliar" (quem assinou, no detalhe de serviço)


@dataclass
class DetalheDoc:
    """Versão congelada de um detalhe de serviço enviada para assinatura: as autoridades assinam ESTE conteúdo (`conteudo` é o
    JSON empacotado do documento; `codigo` é o SHA-256 do JSON). Status: aberto | substituido | cancelado."""
    id: str
    codigo: str
    escala_id: str
    inicio: date
    fim: date
    enviado_por: str
    enviado_em: datetime
    status: str
    conteudo: str
    conjunto_id: str = ""          # documento unificado (várias escalas): `escala_id` fica vazio


@dataclass
class DetalheConjunto:
    """Documento de serviço que reúne várias escalas (fiscal, sentinela, contramestre...) com instruções, recomendações e regras
    gerais, assinado pelas quatro autoridades. O detalhista (`dono_id`) o monta e envia; os papéis de assinatura seguem os
    mesmos campos de uma escala (auxiliar, encarregado e vice-diretor são contas designadas)."""
    id: str
    nome: str                                   # título do documento, ex.: "Escala de Serviço do Dia"
    dono_id: str
    om: str = ""
    escala_ids: list[str] = field(default_factory=list)
    det_instrucoes: str = ""
    det_recomendacoes: str = ""
    det_regras: str = ""
    ass_detalhista: str = ""
    ass_auxiliar: str = ""
    ass_encarregado: str = ""
    ass_vice_diretor: str = ""
    auxiliar_usuario_id: str = ""
    encarregado_usuario_id: str = ""
    vice_usuario_id: str = ""
    brasao_b64: str = ""


@dataclass
class ConviteVinculo:
    """O detalhista (ou auxiliar) convida um usuário a ser reconhecido como um militar da escala. Só vale quando o
    próprio usuário aceita, confirmando o NIP e criando o PIN dele."""
    id: str
    usuario_id: str               # conta convidada
    militar_id: str               # persona que ela passaria a ser
    escala_id: str
    criado_em: datetime
    convidado_por: str = ""       # conta de quem convidou
    status: str = "pendente"      # pendente | aceito | recusado | cancelado
    decidido_em: datetime | None = None


@dataclass
class Notificacao:
    """Aviso dentro do sistema para um usuário."""
    id: str
    usuario_id: str
    tipo: str                     # disponibilidade | papeleta | vinculo | devolucao ...
    texto: str
    criado_em: datetime
    lida: bool = False
    escala_id: str = ""


@dataclass
class Assinatura:
    militar_id: str
    em: datetime
    hash_documento: str
    metodo: str = "conta"         # "conta" (logado + senha) | "externo" (gov.br, ICP, papel)
    referencia: str = ""          # link/arquivo do documento assinado externamente


@dataclass
class Papeleta:
    """Pedido de troca de serviço entre dois militares da mesma escala (troca de datas)."""
    id: str
    numero: int
    escala_id: str
    solicitante_id: str           # militar que pede
    data_solicitante: date        # dia em que ele estava de serviço
    outro_id: str                 # militar com quem quer trocar
    data_outro: date              # dia em que o outro estava de serviço
    criado_em: datetime
    criado_por: str               # usuário do sistema que lançou o pedido
    motivo: str = ""
    status: str = "pendente"      # pendente | aprovada | rejeitada | confirmada | cancelada
    tipo: str = "troca"           # "troca" (datas entre dois militares) | "devolucao" (devolver serviço devido)
    decidido_por: str = ""
    decidido_em: datetime | None = None
    motivo_rejeicao: str = ""
    assinaturas: dict[str, Assinatura] = field(default_factory=dict)  # militar_id -> assinatura
    confirmada_por: str = ""
    confirmada_em: datetime | None = None
    historico: list[tuple[datetime, str, str]] = field(default_factory=list)  # (quando, quem, o quê)


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
    papeletas: list[Papeleta] = field(default_factory=list)
    vinculos: list[Vinculo] = field(default_factory=list)
    disponibilidades: list[Disponibilidade] = field(default_factory=list)
    notificacoes: list[Notificacao] = field(default_factory=list)
    pedidos_acesso: list[PedidoAcesso] = field(default_factory=list)
    convites_vinculo: list[ConviteVinculo] = field(default_factory=list)
    assinaturas_detalhe: list[AssinaturaDetalhe] = field(default_factory=list)
    detalhes_docs: list[DetalheDoc] = field(default_factory=list)
    conjuntos: list[DetalheConjunto] = field(default_factory=list)
    cadastro_aberto: bool = True          # permite que militares criem a própria conta
    brasao_b64: str = ""                  # Brasão de Armas (PNG reduzido, base64) do cabeçalho dos documentos
    admin_cfg_sig: str = ""               # assinatura (NIP+senha) dos segredos já aplicada ao administrador
    janela_devolucao_dias: int = 30       # configurável
    janela_troca_dias: int = 15           # busca de parceiro na troca forçada

    def usuario(self, uid: str) -> Usuario | None:
        return next((u for u in self.usuarios if u.id == uid), None)

    def dispensado_na_escala(self, mid: str, esc: "Escala") -> bool:
        """O detalhista de uma escala não dá nenhum serviço nela (efetivo, retém, palestra...) e não é escalado,
        a menos que a escala permita que ele concorra. Em outra escala, ele é um militar como os outros."""
        return bool(esc.detalhista_id and mid == esc.detalhista_id and not esc.detalhista_escalavel)

    def escalaveis(self, esc: "Escala") -> list[str]:
        """Membros da escala que podem ser escalados (sem o detalhista, se ele estiver fora)."""
        return [p.militar_id for p in esc.membros if not self.dispensado_na_escala(p.militar_id, esc)]

    def antig(self, esc: "Escala", mid: str) -> int:
        """Antiguidade do militar NA ESCALA (cada escala tem a sua numeração, independente das outras)."""
        pos = [p.antiguidade for p in esc.membros if p.militar_id == mid and p.antiguidade > 0]
        if pos:
            return min(pos)
        m = next((m for m in self.militares if m.id == mid), None)
        return m.antiguidade if m else 10 ** 6

    def ordem_na_escala(self, esc: "Escala", ids=None) -> list[str]:
        """Ids (sem repetir) do mais antigo ao mais moderno na escala; `ids` restringe o conjunto."""
        todos = dict.fromkeys(p.militar_id for p in esc.membros)
        alvo = [i for i in todos if ids is None or i in set(ids)]
        return sorted(alvo, key=lambda i: (self.antig(esc, i), i))

    def ordem_da_fila(self, esc: "Escala") -> list[str]:
        """Ids na ORDEM EM QUE A FILA GIRA. Padrão: do mais moderno para o mais antigo (e volta ao mais moderno);
        a antiguidade em si continua 1 = mais antigo."""
        base = self.ordem_na_escala(esc)
        return base if esc.sentido_fila == "antigo_moderno" else base[::-1]

    def numerar_escala(self, esc: "Escala") -> None:
        """Deixa a numeração da escala sequencial (1..n). Quem ainda não tinha número entra depois, pela
        antiguidade do cadastro; a ordem já definida nunca muda."""
        def chave(i):
            pos = [p.antiguidade for p in esc.membros if p.militar_id == i and p.antiguidade > 0]
            return (0, min(pos), i) if pos else (1, self.antig(esc, i), i)
        ordem = sorted(dict.fromkeys(p.militar_id for p in esc.membros), key=chave)
        n = {i: k for k, i in enumerate(ordem, 1)}
        for p in esc.membros:
            p.antiguidade = n[p.militar_id]

    def base_de(self, esc: "Escala") -> date:
        """Data a partir da qual a escala é calculada (cada escala tem a sua, para uma importação não mexer nas outras)."""
        return esc.data_base or self.data_base

    def rotulo_do_usuario(self, u: "Usuario") -> str:
        """Como a conta aparece nas telas: como o militar dela (se vinculada) ou GRAD-ESP Nome de guerra (NIP)."""
        m = next((x for x in self.militares if x.id == u.militar_id), None) if u.militar_id else None
        if m is not None:
            return m.rotulo
        return rotulo_militar(Militar(u.id, u.nome_guerra or u.nome, u.posto, 0, u.nip, especialidade=u.especialidade))

    def militar(self, mid: str) -> Militar:
        return next(m for m in self.militares if m.id == mid)

    def escala(self, eid: str) -> Escala:
        return next(e for e in self.escalas if e.id == eid)

    def escala_ou_none(self, eid: str) -> "Escala | None":
        return next((e for e in self.escalas if e.id == eid), None)

    def conjunto(self, cid: str) -> "DetalheConjunto | None":
        return next((c for c in self.conjuntos if c.id == cid), None)

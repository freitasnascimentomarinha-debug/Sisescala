import json
from datetime import date, datetime, timedelta

import pytest

from sisescala import auth
from sisescala import papeletas as pp
from sisescala.demo import contexto_demo
from sisescala.modelos import *
from sisescala.persistencia import (ABAS, ArquivoBackend, ConflitoDeVersao, MemoriaBackend, Repositorio,
                                    SheetsBackend, criar_repositorio, de_tabelas, para_tabelas)

AGORA = datetime(2027, 2, 27, 9, 0)


# ------------------------------------------------------------ login
def test_primeira_conta_vira_admin_e_depois_so_admin_cria():
    c = Contexto([Militar("m1", "A", "", 1)], [], date(2027, 3, 1))
    adm = auth.criar_usuario(c, None, "Admin", "Administrador", "umasenha123")
    assert adm.admin and adm.login == "admin" and "umasenha123" not in adm.senha_hash
    with pytest.raises(PermissionError):
        auth.criar_usuario(c, None, "x", "X", "umasenha123")
    u = auth.criar_usuario(c, adm.id, "mil1", "Militar 1", "umasenha123", perfil="militar", militar_id="m1")
    with pytest.raises(PermissionError):
        auth.criar_usuario(c, u.id, "y", "Y", "umasenha123")            # militar não cria contas
    with pytest.raises(ValueError, match="já existe"):
        auth.criar_usuario(c, adm.id, "ADMIN", "Z", "umasenha123")
    with pytest.raises(ValueError, match="8"):
        auth.criar_usuario(c, adm.id, "curta", "C", "123")
    with pytest.raises(ValueError, match="já tem conta"):
        auth.criar_usuario(c, adm.id, "outra", "O", "umasenha123", perfil="militar", militar_id="m1")


def test_login_bloqueio_e_troca_de_senha():
    c = Contexto([], [], date(2027, 3, 1))
    adm = auth.criar_usuario(c, None, "admin", "Adm", "umasenha123")
    assert auth.entrar(c, "ADMIN", "umasenha123").id == adm.id
    for i in range(auth.MAX_TENTATIVAS):
        with pytest.raises(auth.AutenticacaoErro, match="incorretos"):
            auth.entrar(c, "admin", "errada", AGORA)
    with pytest.raises(auth.AutenticacaoErro, match="bloqueada"):
        auth.entrar(c, "admin", "umasenha123", AGORA)                    # bloqueada mesmo com a senha certa
    assert auth.entrar(c, "admin", "umasenha123", AGORA + timedelta(minutes=6)).id == adm.id
    with pytest.raises(auth.AutenticacaoErro):
        auth.entrar(c, "naoexiste", "x")
    auth.trocar_senha(c, adm.id, "umasenha123", "novasenha456")
    assert auth.entrar(c, "admin", "novasenha456").id == adm.id
    with pytest.raises(auth.AutenticacaoErro):
        auth.trocar_senha(c, adm.id, "errada", "outrasenha789")


def test_admin_redefine_senha_desativa_mas_nao_o_unico_admin():
    c = Contexto([], [], date(2027, 3, 1))
    adm = auth.criar_usuario(c, None, "admin", "Adm", "umasenha123")
    u = auth.criar_usuario(c, adm.id, "joao", "João", "umasenha123")
    auth.redefinir_senha(c, adm.id, u.id, "senhaNova999")
    assert auth.entrar(c, "joao", "senhaNova999")
    auth.definir_ativo(c, adm.id, u.id, False)
    with pytest.raises(auth.AutenticacaoErro):
        auth.entrar(c, "joao", "senhaNova999")
    with pytest.raises(ValueError, match="único administrador"):
        auth.definir_ativo(c, adm.id, adm.id, False)


# ------------------------------------------------------------ persistência
def ctx_completo():
    c = contexto_demo(date(2027, 3, 1))
    c.usuarios = []
    adm = auth.criar_usuario(c, None, "admin", "Adm", "umasenha123")
    det = auth.criar_usuario(c, adm.id, "det", "Detalhista", "umasenha123")
    for e in c.escalas:
        e.dono_id = det.id
    c.escala("per").compartilhado_com = {adm.id: "leitura"}
    c.escala("per").ultimo_servico = {"preta": "m3", "vermelha": "m9"}
    for i in range(1, 11):
        auth.criar_usuario(c, adm.id, f"mil{i}", f"Mil {i}", "umasenha123", perfil="militar", militar_id=f"m{i}")
    c.impedimentos.append(Impedimento("m2", "dispensa", date(2027, 3, 3), date(2027, 3, 4), "luto; com ; ponto", "arq.pdf"))
    c.impedimentos.append(Impedimento("m5", "desembarque", date(2027, 3, 9)))
    c.dias_especiais.append(DiaEspecial(date(2027, 3, 10), "feriado", "Aniversário da cidade"))
    c.guarnecimentos.append(Guarnecimento(date(2027, 3, 6), "dia", True))
    c.ocorrencias.append(Ocorrencia(date(2027, 3, 2), "per", "m1", "passou mal"))
    c.eventos.append(Evento("pal", date(2027, 3, 12), "Palestra", "10h", "Auditório", 3))
    c.escala("per").membros[0].fim = date(2027, 12, 31)
    esc = c.escala("per")
    ids = [q.militar_id for q in esc.membros]
    par = next((x, dx, y, dy) for x in ids for y in ids if x != y
               for dx in (date(2027, 3, k) for k in range(8, 20)) for dy in (date(2027, 3, k) for k in range(8, 20))
               if dx != dy and not pp.validar_troca(c, esc, x, dx, y, dy)[0])
    x, dx, y, dy = par
    p = pp.criar(c, det.id, "per", x, dx, y, dy, "consulta", AGORA)
    pp.aprovar(c, det.id, p.id, AGORA)
    conta = next((u for u in c.usuarios if u.militar_id == x), None)
    if conta:
        pp.assinar(c, p.id, conta.id, "umasenha123", AGORA)
    return c


def test_roundtrip_completo_sem_perder_nada():
    c = ctx_completo()
    T = para_tabelas(c)
    assert set(T) == set(ABAS)
    c2 = de_tabelas(json.loads(json.dumps(T)))               # passa por JSON como texto puro
    assert para_tabelas(c2) == T
    assert c2.militares == c.militares and c2.usuarios == c.usuarios
    assert c2.escalas == c.escalas and c2.papeletas == c.papeletas
    assert c2.trocas == c.trocas and c2.eventos == c.eventos and c2.impedimentos == c.impedimentos
    assert c2.data_base == c.data_base and c2.uf == c.uf and c2.janela_troca_dias == c.janela_troca_dias


def test_repositorio_salva_so_o_que_mudou_e_recarrega():
    b = MemoriaBackend()
    repo = Repositorio(b)
    c = repo.carregar()
    assert c.militares == []
    adm = auth.criar_usuario(c, None, "admin", "Adm", "umasenha123")
    assert repo.salvar(c) and b.escritas == 1
    assert not repo.salvar(c) and b.escritas == 1             # nada mudou: não grava
    c.militares.append(Militar("m1", "Silva", "CB", 1, "1.1", "COPAB"))
    repo.salvar(c)
    assert set(b.abas) >= {"Militares", "Usuarios"} and b.versao == 2
    outra = Repositorio(b).carregar()
    assert [m.nome for m in outra.militares] == ["Silva"] and outra.usuarios[0].login == "admin"


def test_dois_usuarios_gravando_ao_mesmo_tempo_conflito():
    b = MemoriaBackend()
    r1, r2 = Repositorio(b), Repositorio(b)
    c1, c2 = r1.carregar(), r2.carregar()
    c1.militares.append(Militar("m1", "A", "", 1))
    r1.salvar(c1)
    assert r2.desatualizado()
    c2.militares.append(Militar("m2", "B", "", 1))
    with pytest.raises(ConflitoDeVersao):
        r2.salvar(c2)                                          # não sobrescreve o que o outro gravou
    c2 = r2.carregar()
    assert [m.id for m in c2.militares] == ["m1"]
    c2.militares.append(Militar("m2", "B", "", 2))
    r2.salvar(c2)
    assert [m.id for m in r1.carregar().militares] == ["m1", "m2"]


def test_arquivo_backend_persiste_entre_instancias(tmp_path):
    caminho = tmp_path / "d" / "x.json"
    r = Repositorio(ArquivoBackend(caminho))
    c = r.carregar()
    auth.criar_usuario(c, None, "admin", "Adm", "umasenha123")
    r.salvar(c)
    c2 = Repositorio(ArquivoBackend(caminho)).carregar()
    assert c2.usuarios[0].login == "admin"


class FakeSheet:
    """Imita a parte do gspread usada pelo SheetsBackend."""

    class WS:
        def __init__(self, title): self.title = title

    def __init__(self):
        self.dados: dict[str, list[list[str]]] = {}
        self.titulos: list[str] = []
        self.chamadas = {"get": 0, "update": 0}

    def worksheets(self): return [self.WS(t) for t in self.titulos]
    def add_worksheet(self, title, rows, cols):
        self.titulos.append(title); self.dados.setdefault(title, [])
        return self.WS(title)

    def values_batch_get(self, ranges, params=None):
        self.chamadas["get"] += 1
        out = []
        for rg in ranges:
            nome = rg.split("!")[0].strip("'")
            linhas = [list(r) for r in self.dados.get(nome, [])]
            if "!A1" in rg:                         # A1 apenas
                linhas = linhas[:1] and [linhas[0][:1]]
            # a API real corta células vazias do fim
            linhas = [(lambda r: r[:max([i + 1 for i, c in enumerate(r) if c != ""] + [0])])(r) for r in linhas]
            while linhas and not linhas[-1]:
                linhas.pop()
            out.append({"values": linhas} if linhas else {})
        return {"valueRanges": out}

    def values_batch_update(self, body):
        self.chamadas["update"] += 1
        assert body["valueInputOption"] == "RAW"
        for item in body["data"]:
            nome = item["range"].split("!")[0].strip("'")
            self.dados[nome] = [list(r) for r in item["values"]]


class FakeClient:
    def __init__(self, sh): self.sh = sh
    def open_by_key(self, _): return self.sh


def test_sheets_backend_roundtrip_conflito_e_limpeza_de_linhas():
    sh = FakeSheet()
    mk = lambda: Repositorio(SheetsBackend({}, "id", cliente=FakeClient(sh)))   # noqa: E731
    r1, r2 = mk(), mk()
    c1 = r1.carregar()
    assert set(sh.titulos) >= set(ABAS) and "Versao" in sh.titulos             # abas criadas sozinhas
    c = ctx_completo()
    c1.__dict__.update(c.__dict__)
    assert r1.salvar(c1)
    assert sh.chamadas["update"] == 1                                           # uma única chamada de escrita
    c2 = r2.carregar()
    assert c2.papeletas == c.papeletas and c2.usuarios == c.usuarios and c2.escalas == c.escalas
    # remover linhas: sobra de linhas antigas é apagada
    c1.impedimentos.clear()
    r1.salvar(c1)
    assert all(not any(r) for r in sh.dados["Impedimentos"][1:])
    assert Repositorio(SheetsBackend({}, "id", cliente=FakeClient(sh))).carregar().impedimentos == []
    # conflito
    c2.militares.append(Militar("mx", "X", "", 99))
    with pytest.raises(ConflitoDeVersao):
        r2.salvar(c2)


def test_criar_repositorio_escolhe_backend():
    r, nome = criar_repositorio(None, "/tmp/nao-usado.json")
    assert "local" in nome
    r, nome = criar_repositorio({"gcp_service_account": {"a": 1}, "sheets": {}}, "/tmp/nao-usado.json")
    assert "local" in nome                                    # incompleto: cai no local

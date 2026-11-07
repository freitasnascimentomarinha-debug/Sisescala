import io
from datetime import date, timedelta

import pytest

from sisescala import cadastro as cd
from sisescala.importacao import MODELO_CSV, importar, ler_tabela, mapear_colunas, parse_data
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.permissoes import PermissaoNegada
from sisescala.relatorio import html_regras, itens_configuracao, pdf_regras

D = date(2027, 3, 1)


def base(n=6):
    ms = [Militar(f"m{i}", f"M{i}", "CB", i) for i in range(1, n + 1)]
    e = Escala("A", "Pernoite", dono_id="u1", membros=[Pertinencia(m.id) for m in ms])
    c = Contexto(ms, [e], D)
    c.usuarios = [Usuario("u1", "Detalhista", "1"), Usuario("u9", "Outro", "9")]
    return c


# ------------------------------------------------------------ cadastro
def test_adicionar_editar_excluir_militares():
    c = base()
    m = cd.adicionar_militar(c, "Novo", "1SG", "11.1111.11", "COPAB", antiguidade=2)
    assert m.antiguidade == 2 and c.militar("m2").antiguidade == 3
    with pytest.raises(ValueError):
        cd.adicionar_militar(c, "Outro", nip="11.1111.11")
    cd.editar_militar(c, "m1", posto="CT", om="CIAGA")
    assert (c.militar("m1").posto, c.militar("m1").om) == ("CT", "CIAGA")
    cd.editar_militar(c, m.id, antiguidade=1)
    assert m.antiguidade == 1 and c.militar("m1").antiguidade == 2
    assert sorted(x.antiguidade for x in c.militares) == list(range(1, 8))
    assert cd.excluir_militares(c, ["m3", "m4", "inexistente"]) == 2
    assert {x.id for x in c.militares} == {"m1", "m2", "m5", "m6", m.id}
    assert all(p.militar_id not in ("m3", "m4") for p in c.escala("A").membros)


def test_excluir_quem_deu_o_ultimo_servico_mantem_a_fila():
    c = base()
    c.escala("A").ultimo_servico = {"corrida": "m3"}
    cd.excluir_militares(c, ["m3"])
    assert c.escala("A").ultimo_servico["corrida"] == "m2"
    r = gerar(c, D)
    assert r.dia(D, "A").efetivos[0].militar_id == "m4"      # segue de onde estava


def test_excluir_apaga_impedimentos_e_respeita_permissao():
    c = base()
    c.impedimentos.append(Impedimento("m2", "ferias", D, D + timedelta(days=5)))
    with pytest.raises(PermissaoNegada):
        cd.excluir_militares(c, ["m2"], usuario_id="u9")
    cd.excluir_militares(c, ["m2"], usuario_id="u1")                     # detalhista da única escala dele
    assert c.impedimentos == []


def test_remover_da_escala_com_data_encerra_participacao():
    c = base()
    cd.remover_da_escala(c, "A", ["m2"], a_partir_de=D + timedelta(days=3))
    r = gerar(c, D + timedelta(days=10))
    quem = lambda i: [a.militar_id for a in r.dia(D + timedelta(days=i), "A").efetivos]  # noqa: E731
    assert quem(1) == ["m2"] and all("m2" not in quem(i) for i in range(4, 11))
    cd.adicionar_a_escala(c, "A", ["m2"], desde=D + timedelta(days=20))
    assert any(p.militar_id == "m2" and p.fim is None for p in c.escala("A").membros)


# ------------------------------------------------------------ importação
CSV = """Nome de Guerra;Posto/Graduação;NIP;Sigla da OM;Escala;Último Serviço
SILVA;1SG;11.1111.11;COPAB;Pernoite;25/02/2027
SOUZA;CB;22.2222.22;COPAB;Pernoite;26/02/2027
LIMA;MN;33.3333.33;COPAB;Pernoite;27/02/2027
ROCHA;CB;44.4444.44;COPAB;Pernoite;
"""


def test_mapeia_colunas_com_nomes_flexiveis():
    m = mapear_colunas(["Nome de Guerra", "Posto/Graduação", "NIP", "Sigla da OM", "Escala", "Último Serviço"])
    assert set(m) == {"nome", "posto", "nip", "om", "escala", "ultimo"}
    assert parse_data("28/02/2027") == date(2027, 2, 28) and parse_data("2027-02-28") == date(2027, 2, 28)


def test_importa_csv_cria_escala_e_continua_de_onde_parou():
    c = Contexto([], [], D)
    novo, rel = importar(c, ler_tabela(CSV.encode("utf-8"), "x.csv"), dono_id="u1")
    assert not rel.erros and rel.novos == ["SILVA", "SOUZA", "LIMA", "ROCHA"]
    assert rel.escalas_criadas == ["Pernoite"] and novo.escalas[0].dono_id == "u1"
    assert [m.nome for m in sorted(novo.militares, key=lambda m: m.antiguidade)] == ["SILVA", "SOUZA", "LIMA", "ROCHA"]
    assert novo.militar("11-1111-11").om == "COPAB"
    assert rel.data_base == date(2027, 2, 28)                  # dia seguinte ao último serviço
    r = gerar(novo, date(2027, 3, 3))
    esc = novo.escalas[0].id
    assert r.dia(date(2027, 2, 28), esc).efetivos[0].militar_id == "44-4444-44"   # LIMA deu o último
    assert c.militares == []                                    # contexto original intacto (pré-visualização)


def test_importa_xlsx_com_datas_e_atualiza_existentes():
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["Guerra", "Graduação", "NIP", "OM", "Escalas", "Ordem", "Data"])
    ws.append(["M1", "SO", "9.9999.99", "COPAB", "A", 2, date(2027, 2, 27)])
    ws.append(["M2", "CB", None, "COPAB", "A", 1, date(2027, 2, 27)])
    buf = io.BytesIO(); wb.save(buf)
    c = base(3)
    novo, rel = importar(c, ler_tabela(buf.getvalue(), "planilha.xlsx"))
    assert rel.atualizados == ["M1", "M2"] and not rel.novos   # ganharam NIP/OM
    assert novo.militar("m1").nip == "9.9999.99" and novo.militar("m1").posto == "SO"
    assert novo.militar("m2").antiguidade == 1 and novo.militar("m1").antiguidade == 2   # ordem da planilha
    assert rel.data_base == date(2027, 2, 28)
    # dois serviram no mesmo dia (m2, m1): continua depois do último da sequência circular -> m3
    assert gerar(novo, date(2027, 2, 28)).dia(date(2027, 2, 28), "A").efetivos[0].militar_id == "m3"


def test_sentido_base_mais_antigo_e_erros():
    c = Contexto([], [], D)
    novo, _ = importar(c, ler_tabela(CSV.encode(), "x.csv"), sentido="base_mais_antigo")
    assert [m.nome for m in sorted(novo.militares, key=lambda m: m.antiguidade)][0] == "ROCHA"
    _, rel = importar(c, ler_tabela(b"Foo;Bar\n1;2\n", "x.csv"))
    assert rel.erros
    novo, rel = importar(c, ler_tabela(CSV.encode(), "x.csv"), criar_escalas=False)
    assert novo.escalas == [] and rel.avisos


def test_modelo_csv_e_valido():
    novo, rel = importar(Contexto([], [], D), ler_tabela(MODELO_CSV.encode(), "modelo.csv"))
    assert not rel.erros and len(novo.militares) == 2 and len(novo.escalas) == 2


# ------------------------------------------------------------ relatório de regras
def test_relatorio_mostra_alteracoes_em_relacao_ao_padrao():
    c = base()
    esc = c.escala("A")
    assert not any(i.alterado for _, its in itens_configuracao(c, esc)
                   for i in its if i.rotulo in ("Folgas mínimas entre serviços", "Escalados por dia"))
    esc.folgas_minimas, esc.militares_dia, c.janela_devolucao_dias = 3, 2, 45
    alt = {i.rotulo for _, its in itens_configuracao(c, esc) for i in its if i.alterado}
    assert {"Folgas mínimas entre serviços", "Escalados por dia", "Prazo para devolver serviço (dias)"} <= alt
    h = html_regras(c, esc)
    assert "3x1" in h and "45" in h and "Lógica fixa" in h
    assert pdf_regras(c, esc, "OM X").startswith(b"%PDF")

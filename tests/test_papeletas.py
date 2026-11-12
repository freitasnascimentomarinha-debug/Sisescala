from datetime import date, datetime, timedelta

import pytest

from sisescala import auth
from sisescala import papeletas as pp
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.pdf import pdf_papeleta
from sisescala.permissoes import PermissaoNegada, compartilhar, pode_editar, pode_ver

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 0)      # bem antes do serviço
SENHA = "senha-forte-1"
PIN = "1234"


def mk(n=8, **kw):
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"{i}.000", om="COPAB") for i in range(1, n + 1)]
    e = Escala("A", "Diária", dono_id="u1", membros=[Pertinencia(m.id) for m in ms], **kw)
    c = Contexto(ms, [e], D)
    auth.criar_usuario(c, None, "det", "Detalhista", SENHA, admin=True)                  # u1 (dono)
    auth.criar_usuario(c, "u1", "ed", "Editor", SENHA)                                    # u2
    for i in (1, 3, 5):                                                                   # contas de militares
        auth.criar_usuario(c, "u1", f"mil{i}", f"Militar {i}", SENHA, perfil="militar", militar_id=f"m{i}")
    for u in c.usuarios:                                                                  # todos têm PIN no perfil
        u.pin_hash = auth.hash_pin(PIN)
    return c   # u3=m1, u4=m3, u5=m5


M1, M3, M5 = "u3", "u4", "u5"


def pedido(c, **kw):
    args = dict(usuario_id="u1", escala_id="A", solicitante_id="m1", data_solicitante=D, outro_id="m3",
                data_outro=D + timedelta(days=2), motivo="consulta médica", agora=AGORA, pin=PIN)
    args.update(kw)
    return pp.criar(c, **args)


def test_cria_pedido_com_data_hora_quem_com_quem_motivo_e_escala():
    c = mk()
    p = pedido(c)
    assert (p.status, p.numero, p.escala_id, p.motivo) == ("pendente", 1, "A", "consulta médica")
    assert (p.solicitante_id, p.outro_id, p.criado_em, p.criado_por) == ("m1", "m3", AGORA, "u1")


def test_antecedencia_minima_24h_e_ajustavel():
    c = mk()
    proximo = datetime(2027, 2, 28, 12, 0)
    with pytest.raises(ValueError, match="24h"):
        pedido(c, agora=proximo)
    c.escala("A").antecedencia_horas = 6
    assert pedido(c, agora=proximo).status == "pendente"
    c2 = mk(); c2.escala("A").antecedencia_horas = 72
    with pytest.raises(ValueError, match="72h"):
        pedido(c2, agora=AGORA)


def test_recusa_trocas_invalidas_e_exige_motivo():
    c = mk()
    with pytest.raises(ValueError, match="não está escalado"):
        pedido(c, solicitante_id="m5")
    with pytest.raises(ValueError, match="outro militar"):
        pedido(c, outro_id="m1")
    with pytest.raises(ValueError, match="diferentes"):
        pedido(c, data_outro=D)
    with pytest.raises(ValueError, match="motivo"):
        pedido(c, motivo=" ")
    c.impedimentos.append(Impedimento("m3", "ferias", D, D))
    with pytest.raises(ValueError, match="impedido"):
        pedido(c)


# ---------------------------------------------- o próprio militar pede, mesmo só com leitura
def test_militar_pede_para_si_mesmo_com_acesso_somente_leitura():
    c = mk()
    esc = c.escala("A")
    assert pode_ver(c, M1, esc) and not pode_editar(c, M1, esc)        # leitura implícita por ser membro
    p = pedido(c, usuario_id=M1)
    assert p.criado_por == M1 and p.solicitante_id == "m1"
    with pytest.raises(PermissaoNegada, match="próprio"):
        pedido(c, usuario_id=M3, solicitante_id="m1")                  # m3 não pede por m1


def test_militar_de_fora_da_escala_nao_pede():
    c = mk()
    c.escala("A").membros = [p for p in c.escala("A").membros if p.militar_id != "m5"]
    assert not pode_ver(c, M5, c.escala("A"))
    with pytest.raises(PermissaoNegada):
        pedido(c, usuario_id=M5, solicitante_id="m5")


# ---------------------------------------------- pedido ativo trava as partes
def test_pedido_ativo_trava_os_dois_militares():
    c = mk()
    p = pedido(c)
    assert set(pp.militares_em_pedido_ativo(c)) == {"m1", "m3"}
    with pytest.raises(ValueError, match="já está na papeleta 0001"):
        pedido(c, solicitante_id="m4", data_solicitante=D + timedelta(days=3), outro_id="m3",
               data_outro=D + timedelta(days=2))                         # m3 já está em outro pedido
    pp.aprovar(c, "u1", p.id, AGORA)
    assert set(pp.militares_em_pedido_ativo(c)) == {"m1", "m3"}          # aprovada continua travando
    pp.cancelar(c, "u1", p.id, "x", AGORA)
    assert pp.militares_em_pedido_ativo(c) == {}                          # cancelada libera
    p2 = pedido(c)
    pp.rejeitar(c, "u1", p2.id, "não", AGORA)
    assert pp.militares_em_pedido_ativo(c) == {}                          # rejeitada libera


# ---------------------------------------------- aprovação, rejeição, quem decide
def test_aprovar_faz_a_troca_automaticamente_e_so_entao_muda_a_previa():
    c = mk()
    p = pedido(c)
    antes = gerar(c, D + timedelta(days=3))
    assert antes.dia(D, "A").efetivos[0].militar_id == "m1"              # pendente: prévia intacta
    pp.aprovar(c, "u1", p.id, AGORA)
    r = gerar(c, D + timedelta(days=3))
    a1, a2 = r.dia(D, "A").efetivos[0], r.dia(D + timedelta(days=2), "A").efetivos[0]
    assert (a1.militar_id, a1.sigla) == ("m3", "SVÇ (T)") and "0001" in a1.obs
    assert (a2.militar_id, a2.sigla) == ("m1", "SVÇ (T)")


def test_rejeitar_nao_altera_a_escala_e_exige_motivo():
    c = mk()
    p = pedido(c)
    with pytest.raises(ValueError):
        pp.rejeitar(c, "u1", p.id, " ")
    pp.rejeitar(c, "u1", p.id, "efetivo insuficiente", AGORA)
    assert p.status == "rejeitada" and c.trocas == []
    with pytest.raises(ValueError):
        pp.aprovar(c, "u1", p.id, AGORA)


def test_so_detalhista_e_editores_decidem_militar_nao_aprova_o_proprio_pedido():
    c = mk()
    p = pedido(c, usuario_id=M1)
    compartilhar(c, "u1", "A", "u2", "edicao")
    with pytest.raises(PermissaoNegada):
        pp.aprovar(c, M1, p.id, AGORA)                  # o próprio militar não aprova
    assert [x.id for x in pp.pedidos_pendentes(c, "u1")] == [p.id]
    assert [x.id for x in pp.pedidos_pendentes(c, "u2")] == [p.id]
    assert pp.pedidos_pendentes(c, M1) == []
    pp.aprovar(c, "u2", p.id, AGORA)


# ---------------------------------------------- cancelamento
def test_partes_cancelam_enquanto_nao_aprovado_e_nao_depois():
    c = mk()
    p = pedido(c, usuario_id=M1)
    pp.cancelar(c, M3, p.id, "mudei de ideia", AGORA)                   # a outra parte também pode
    assert p.status == "cancelada"
    p2 = pedido(c, usuario_id=M1)
    with pytest.raises(PermissaoNegada):
        pp.cancelar(c, M5, p2.id, "", AGORA)                             # terceiro não
    pp.aprovar(c, "u1", p2.id, AGORA)
    with pytest.raises(PermissaoNegada):
        pp.cancelar(c, M1, p2.id, "", AGORA)                             # aprovado: parte não cancela
    pp.cancelar(c, "u1", p2.id, "não assinaram", AGORA)                   # detalhista cancela e desfaz
    assert p2.status == "cancelada" and c.trocas == []
    assert gerar(c, D).dia(D, "A").efetivos[0].militar_id == "m1"


# ---------------------------------------------- assinatura pela conta
def test_assinatura_pela_conta_e_confirmacao():
    c = mk()
    p = pedido(c, usuario_id=M1)
    pp.aprovar(c, "u1", p.id, AGORA)
    sit = pp.situacao_partes(c, p)
    assert [s["tem_conta"] for s in sit] == [True, True] and [s["assinou"] for s in sit] == [False, False]
    with pytest.raises(ValueError, match="aguardando assinatura"):
        pp.confirmar(c, "u1", p.id, AGORA)
    with pytest.raises(PermissaoNegada, match="incorreto"):
        pp.assinar(c, p.id, M1, "errada", AGORA)
    with pytest.raises(PermissaoNegada):
        pp.assinar(c, p.id, M5, PIN, AGORA)                            # não é parte
    with pytest.raises(PermissaoNegada):
        pp.assinar(c, p.id, "u1", PIN, AGORA)                          # detalhista não assina pelos militares
    a = pp.assinar(c, p.id, M1, PIN, AGORA)
    assert a.metodo == "conta" and a.hash_documento == pp.hash_documento(c, p)
    with pytest.raises(ValueError, match="já assinou"):
        pp.assinar(c, p.id, M1, PIN, AGORA)
    assert [s["assinou"] for s in pp.situacao_partes(c, p)] == [True, False]
    pp.assinar(c, p.id, M3, PIN, AGORA + timedelta(hours=1))
    pp.confirmar(c, "u1", p.id, AGORA + timedelta(hours=2))
    assert p.status == "confirmada"


def test_situacao_mostra_parte_sem_conta_e_assinatura_externa():
    c = mk()
    p = pedido(c, outro_id="m4", data_outro=D + timedelta(days=3))       # m4 não tem conta
    pp.aprovar(c, "u1", p.id, AGORA)
    assert [s["tem_conta"] for s in pp.situacao_partes(c, p)] == [True, False]
    pp.assinar(c, p.id, M1, PIN, AGORA)
    pp.registrar_assinatura_externa(c, "u1", p.id, "m4", "gov.br/doc/9", AGORA)
    pp.confirmar(c, "u1", p.id, AGORA)
    assert p.assinaturas["m4"].metodo == "externo"


def test_detalhista_cancela_ate_confirmada_com_motivo():
    c = mk()
    p = pedido(c, usuario_id=M1)
    pp.aprovar(c, "u1", p.id, AGORA)
    pp.assinar(c, p.id, M1, PIN, AGORA); pp.assinar(c, p.id, M3, PIN, AGORA)
    pp.confirmar(c, "u1", p.id, AGORA)
    with pytest.raises(ValueError, match="motivo"):
        pp.cancelar(c, "u1", p.id, "", AGORA)
    pp.cancelar(c, "u1", p.id, "erro de lançamento", AGORA)
    assert p.status == "cancelada" and c.trocas == []


def test_visibilidade_das_papeletas():
    c = mk()
    p = pedido(c, usuario_id=M1)
    assert [x.id for x in pp.papeletas_visiveis(c, "u1", "A")] == [p.id]   # detalhista
    assert [x.id for x in pp.papeletas_visiveis(c, M1, "A")] == [p.id]     # parte
    assert [x.id for x in pp.papeletas_visiveis(c, M3, "A")] == [p.id]     # outra parte
    assert pp.papeletas_visiveis(c, M5, "A") == []                          # terceiro não vê


def test_servico_que_veio_de_troca_nao_pode_ser_trocado_de_novo():
    c = mk()
    p = pedido(c)
    pp.aprovar(c, "u1", p.id, AGORA)
    pp.cancelar(c, "u1", p.id, "x", AGORA)
    p = pedido(c)
    pp.aprovar(c, "u1", p.id, AGORA)
    pp.assinar(c, p.id, M1, PIN, AGORA); pp.assinar(c, p.id, M3, PIN, AGORA); pp.confirmar(c, "u1", p.id, AGORA)
    with pytest.raises(ValueError, match="já veio de uma troca"):
        pedido(c, solicitante_id="m3", data_solicitante=D, outro_id="m4", data_outro=D + timedelta(days=3))


def test_documento_pdf_e_hash_muda_com_o_conteudo():
    c = mk()
    p = pedido(c)
    h = pp.hash_documento(c, p)
    assert pdf_papeleta(c, p, "COPAB").startswith(b"%PDF")
    p.motivo = "outro"
    assert pp.hash_documento(c, p) != h


def _par_retem(c):
    """Acha X (efetivo em dx) e Y (efetivo em dy) onde Y é retém em dx."""
    esc = c.escala("A")
    res = gerar(c, D + timedelta(days=12))
    for dx in (D + timedelta(days=k) for k in range(2, 10)):
        dia = res.dia(dx, "A")
        if not dia or not dia.funciona or not dia.efetivos or not dia.retens:
            continue
        x, y = dia.efetivos[0].militar_id, dia.retens[0].militar_id
        for dy in (dx + timedelta(days=k) for k in (1, 2, 3)):
            a = res.dia(dy, "A")
            if a and a.funciona and any(e.militar_id == y and e.origem == "normal" for e in a.efetivos):
                return esc, x, dx, y, dy, dia.retens[0].militar_id
    pytest.skip("sem par com retém")


def test_troca_com_retem_em_conflito_ajusta_retem_e_desfaz_ao_cancelar():
    c = mk(n=10, retem_qtd=1)
    esc, x, dx, y, dy, ret = _par_retem(c)
    erros, avisos, _ = pp.validar_troca(c, esc, x, dx, y, dy)
    assert not erros, erros
    assert any("retém" in a for a in avisos)
    p = pp.criar(c, "u1", "A", x, dx, y, dy, "motivo", AGORA, pin=PIN)
    pp.aprovar(c, "u1", p.id, AGORA)
    res = gerar(c, dy)
    dia = res.dia(dx, "A")
    assert dia.efetivos[0].militar_id == y
    assert dia.retens[0].militar_id == x
    assert dia.retens[0].origem == "tf"
    pp.cancelar(c, "u1", p.id, "desfeita", AGORA)
    dia2 = gerar(c, dy).dia(dx, "A")
    assert dia2.efetivos[0].militar_id == x and dia2.retens[0].militar_id == y


def test_troca_desfeita_se_quem_entra_falta_e_quem_saiu_reassume():
    c = mk(n=10, retem_qtd=1)
    esc, x, dx, y, dy, _ = _par_retem(c)
    p = pp.criar(c, "u1", "A", x, dx, y, dy, "motivo", AGORA, pin=PIN)
    pp.aprovar(c, "u1", p.id, AGORA)
    c.ocorrencias.append(Ocorrencia(dx, "A", y, "doente"))
    res = gerar(c, dy)
    assert res.dia(dx, "A").efetivos[0].militar_id == x
    assert any("desfeita" in a for a in res.avisos)


def test_troca_desfeita_se_saindo_avanca_do_retem_antes():
    c = mk(n=10, retem_qtd=1)
    esc, x, dx, y, dy, _ = _par_retem(c)
    p = pp.criar(c, "u1", "A", x, dx, y, dy, "motivo", AGORA, pin=PIN)
    pp.aprovar(c, "u1", p.id, AGORA)
    base = gerar(c, dy)
    # dia anterior à troca em que x é retém: o efetivo daquele dia falta e x avança
    d0 = next((d for d in (dx - timedelta(days=k) for k in range(1, 6))
               if base.dia(d, "A") and any(r.militar_id == x for r in base.dia(d, "A").retens)), None)
    if d0 is None:
        pytest.skip("x não é retém antes")
    c.ocorrencias.append(Ocorrencia(d0, "A", base.dia(d0, "A").efetivos[0].militar_id, "doente"))
    res = gerar(c, dy)
    assert res.dia(dx, "A").efetivos[0].militar_id != y or any("desfeita" in a for a in res.avisos)

from datetime import date, datetime, timedelta

import pytest

from sisescala import papeletas as pp
from sisescala.modelos import *
from sisescala.motor import gerar
from sisescala.pdf import pdf_papeleta
from sisescala.permissoes import PermissaoNegada, compartilhar

D = date(2027, 3, 1)
AGORA = datetime(2027, 2, 27, 9, 0)      # bem antes do serviço


def mk(n=8, **kw):
    ms = [Militar(f"m{i}", f"M{i}", "CB", i, nip=f"{i}.000") for i in range(1, n + 1)]
    e = Escala("A", "Diária", dono_id="u1", membros=[Pertinencia(m.id) for m in ms], **kw)
    return Contexto(ms, [e], D, usuarios=[Usuario("u1", "Det"), Usuario("u2", "Ed"), Usuario("u3", "Leitor")])


def serv(c, mid, d=None):
    r = gerar(c, D + timedelta(days=20))
    return sorted(dd for (dd, e), de in r.dias.items() for a in de.efetivos if a.militar_id == mid)


def pedido(c, **kw):
    # m1 serve em D, m3 serve em D+2: trocar
    args = dict(usuario_id="u1", escala_id="A", solicitante_id="m1", data_solicitante=D, outro_id="m3",
                data_outro=D + timedelta(days=2), motivo="consulta médica", agora=AGORA)
    args.update(kw)
    return pp.criar(c, **args)


def test_cria_pedido_com_data_hora_quem_com_quem_e_escala():
    c = mk()
    p = pedido(c)
    assert (p.status, p.numero, p.escala_id) == ("pendente", 1, "A")
    assert (p.solicitante_id, p.outro_id, p.criado_em, p.criado_por) == ("m1", "m3", AGORA, "u1")
    assert p.historico and p.historico[0][1] == "u1"


def test_antecedencia_minima_24h_e_ajustavel():
    c = mk()
    proximo = datetime(2027, 2, 28, 12, 0)       # 12h antes do serviço (01/03 00:00)
    with pytest.raises(ValueError, match="24h"):
        pedido(c, agora=proximo)
    c.escala("A").antecedencia_horas = 6          # ajustável
    assert pedido(c, agora=proximo).status == "pendente"
    c2 = mk(); c2.escala("A").antecedencia_horas = 72
    with pytest.raises(ValueError, match="72h"):
        pedido(c2, agora=AGORA)                   # 63h antes: menos de 72h


def test_recusa_trocas_invalidas():
    c = mk()
    with pytest.raises(ValueError, match="não está escalado"):
        pedido(c, solicitante_id="m5")             # m5 não serve em D
    with pytest.raises(ValueError, match="outro militar"):
        pedido(c, outro_id="m1")
    with pytest.raises(ValueError, match="diferentes"):
        pedido(c, data_outro=D)
    c.impedimentos.append(Impedimento("m3", "ferias", D, D))
    with pytest.raises(ValueError, match="impedido"):
        pedido(c)
    p = mk()
    pedido(p)
    with pytest.raises(ValueError, match="em andamento"):
        pedido(p)


def test_aprovar_faz_a_troca_automaticamente():
    c = mk()
    p = pedido(c)
    assert D in serv(c, "m1")
    pp.aprovar(c, "u1", p.id, AGORA)
    r = gerar(c, D + timedelta(days=3))
    a1, a2 = r.dia(D, "A").efetivos[0], r.dia(D + timedelta(days=2), "A").efetivos[0]
    assert (a1.militar_id, a1.sigla) == ("m3", "SVÇ (T)") and "0001" in a1.obs
    assert (a2.militar_id, a2.sigla) == ("m1", "SVÇ (T)")
    assert p.status == "aprovada" and p.decidido_por == "u1"


def test_rejeitar_nao_altera_a_escala_e_exige_motivo():
    c = mk()
    p = pedido(c)
    with pytest.raises(ValueError):
        pp.rejeitar(c, "u1", p.id, " ")
    pp.rejeitar(c, "u1", p.id, "efetivo insuficiente", AGORA)
    assert p.status == "rejeitada" and c.trocas == []
    assert gerar(c, D).dia(D, "A").efetivos[0].militar_id == "m1"
    with pytest.raises(ValueError):
        pp.aprovar(c, "u1", p.id, AGORA)


def test_so_detalhista_e_editores_decidem_e_recebem_o_pedido():
    c = mk()
    p = pedido(c, usuario_id="u1")
    compartilhar(c, "u1", "A", "u3", "leitura")
    compartilhar(c, "u1", "A", "u2", "edicao")
    with pytest.raises(PermissaoNegada):
        pp.aprovar(c, "u3", p.id, AGORA)          # leitor não decide
    assert [x.id for x in pp.pedidos_pendentes(c, "u1")] == [p.id]
    assert [x.id for x in pp.pedidos_pendentes(c, "u2")] == [p.id]     # editor recebe
    assert pp.pedidos_pendentes(c, "u3") == []
    pp.aprovar(c, "u2", p.id, AGORA)               # editor aprova
    assert pp.pedidos_pendentes(c, "u1") == []


def test_assinatura_eletronica_e_confirmacao():
    c = mk()
    p = pedido(c)
    pp.aprovar(c, "u1", p.id, AGORA)
    with pytest.raises(ValueError, match="aguardando assinatura"):
        pp.confirmar(c, "u1", p.id, AGORA)
    with pytest.raises(ValueError, match="PIN"):
        pp.assinar(c, p.id, "m1", "1.000", "1234", AGORA)           # sem PIN definido
    with pytest.raises(ValueError, match="NIP"):
        pp.definir_pin(c, "m1", "9.999", "1234")
    pp.definir_pin(c, "m1", "1.000", "1234"); pp.definir_pin(c, "m3", "3.000", "5678")
    assert "1234" not in c.militar("m1").pin_hash                     # só o hash
    with pytest.raises(PermissaoNegada):
        pp.assinar(c, p.id, "m1", "1.000", "0000", AGORA)
    with pytest.raises(PermissaoNegada):
        pp.assinar(c, p.id, "m5", "5.000", "1234", AGORA)             # não faz parte da troca
    a = pp.assinar(c, p.id, "m1", "1.000", "1234", AGORA)
    assert a.hash_documento == pp.hash_documento(c, p) and pp.faltam_assinar(c, p) == ["M3"]
    pp.assinar(c, p.id, "m3", "3.000", "5678", AGORA + timedelta(hours=1))
    pp.confirmar(c, "u1", p.id, AGORA + timedelta(hours=2))
    assert p.status == "confirmada" and p.confirmada_por == "u1"
    with pytest.raises(ValueError):
        pp.cancelar(c, "u1", p.id)                                    # confirmada é definitiva


def test_assinatura_externa_registrada_pelo_detalhista():
    c = mk()
    p = pedido(c)
    pp.aprovar(c, "u1", p.id, AGORA)
    pp.registrar_assinatura_externa(c, "u1", p.id, "m1", "gov.br/doc/123", AGORA)
    pp.registrar_assinatura_externa(c, "u1", p.id, "m3", "papel – arquivo 45", AGORA)
    pp.confirmar(c, "u1", p.id, AGORA)
    assert p.assinaturas["m1"].metodo == "externo" and p.status == "confirmada"


def test_cancelar_aprovada_desfaz_a_troca():
    c = mk()
    p = pedido(c)
    pp.aprovar(c, "u1", p.id, AGORA)
    pp.cancelar(c, "u1", p.id, "não assinaram", AGORA)
    assert p.status == "cancelada" and c.trocas == []
    assert gerar(c, D).dia(D, "A").efetivos[0].militar_id == "m1"
    assert "desfeita" in p.historico[-1][2]


def test_servico_que_veio_de_troca_nao_pode_ser_trocado_de_novo():
    c = mk()
    p = pedido(c)
    pp.aprovar(c, "u1", p.id, AGORA)
    with pytest.raises(ValueError, match="já veio de uma troca"):
        pedido(c, solicitante_id="m3", data_solicitante=D, outro_id="m4", data_outro=D + timedelta(days=3))


def test_aviso_de_descanso_curto_nao_bloqueia():
    c = mk(8)
    p = pedido(c, data_outro=D + timedelta(days=3), outro_id="m4")   # m1 passaria a D+3 e D+8... ok
    avisos = pp.aprovar(c, "u1", p.id, AGORA)
    assert isinstance(avisos, list) and p.status == "aprovada"


def test_documento_pdf_e_hash_muda_com_o_conteudo():
    c = mk()
    p = pedido(c)
    h = pp.hash_documento(c, p)
    assert pdf_papeleta(c, p, "COPAB").startswith(b"%PDF")
    p.motivo = "outro"
    assert pp.hash_documento(c, p) != h

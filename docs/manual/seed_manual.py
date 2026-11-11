"""Gera os dados FICTÍCIOS usados nas telas do manual do usuário (nenhuma pessoa real).

Uso:  python docs/manual/seed_manual.py <arquivo.json>
Depois:  SISESCALA_ARQUIVO=<arquivo.json> SISESCALA_ADMIN_NIP=admin SISESCALA_ADMIN_SENHA=Manual@2026 streamlit run app.py
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sisescala import assinaturas as asn  # noqa: E402
from sisescala import auth, gestao  # noqa: E402
from sisescala import acessos as ac  # noqa: E402
from sisescala import conjuntos as cjs  # noqa: E402
from sisescala import papeletas as pp  # noqa: E402
from sisescala import permissoes as pm  # noqa: E402
from sisescala import vinculos as vc  # noqa: E402
from sisescala.modelos import Contexto, Escala, Impedimento, Militar, Pertinencia, quartos_padrao  # noqa: E402
from sisescala.motor import gerar  # noqa: E402
from sisescala.pdf import codigo_do_corpo, corpo_conjunto, corpo_detalhe  # noqa: E402
from sisescala.persistencia import ArquivoBackend, Repositorio  # noqa: E402

SENHA, PIN = "Manual@2026", "1234"
OM = "Centro de Operações do Abastecimento"
HOJE = date.today()
AGORA = datetime.now()


def main(saida: str) -> None:
    primeiros = ["Carlos Eduardo", "Ricardo", "Marcelo", "Paulo Henrique", "André Luiz", "Fábio", "Sérgio", "Rafael", "Leandro",
                 "Thiago", "Bruno", "Diego", "Eduardo", "Gustavo", "Felipe", "Rodrigo", "Vinícius", "Alexandre", "Daniel", "Mateus",
                 "Lucas", "Renato", "Fernando", "Henrique", "Márcio", "Jorge", "Antônio", "Caio"]
    guerra = ["Menezes", "Albuquerque", "Cardoso", "Nogueira", "Teixeira", "Moura", "Pacheco", "Lacerda", "Siqueira", "Martins",
              "Carvalho", "Rocha", "Santos", "Ribeiro", "Azevedo", "Camargo", "Duarte", "Esteves", "Farias", "Gomes", "Holanda",
              "Ibrahim", "Junqueira", "Klein", "Leal", "Machado", "Nunes", "Oliveira"]
    sobrenomes = ["Menezes", "Albuquerque Tavares", "Barros Cardoso", "Silva Nogueira", "Luiz Teixeira", "Moura Ramos",
                  "Fonseca Pacheco", "Duarte Lacerda", "Costa Siqueira", "Pinto Martins", "Dias Carvalho", "Freire Rocha",
                  "Lima Santos", "Neves Ribeiro", "Alves Azevedo", "Prado Camargo", "Reis Duarte", "Sá Esteves", "Bastos Farias",
                  "Cunha Gomes", "Peixoto Holanda", "Faria Ibrahim", "Lopes Junqueira", "Mota Klein", "Viana Leal",
                  "Araújo Machado", "Brito Nunes", "Rangel Oliveira"]
    nomes = [f"{p} {s}" for p, s in zip(primeiros, sobrenomes)]
    postos = ["1ºTEN", "2ºSG", "2ºSG", "2ºSG", "3ºSG", "3ºSG", "3ºSG", "3ºSG", "CB", "CB", "CB", "CB", "CB", "CB", "MN", "MN", "MN",
              "MN", "MN", "MN", "MN", "MN", "MN", "MN", "MN", "MN", "MN", "MN"]
    esp = ["", "PL", "AM", "CN", "PL", "AM", "CL", "ET", "AR", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]
    N = len(nomes)
    ms = [Militar(f"m{i}", guerra[i - 1], postos[i - 1], i, f"11.03{i:02d}.{10 + i}", OM, f"{guerra[i - 1].lower()}@exemplo.mil.br",
                  f"23{40 + i}", "(21) 98888-" + f"{1000 + i}", esp[i - 1]) for i in range(1, N + 1)]
    c = Contexto(ms, [], HOJE - timedelta(days=25))
    auth.criar_usuario(c, None, "admin", "Administrador do Sistema", SENHA, admin=True)                      # u1
    c.usuario("u1").pin_hash = auth.hash_pin(PIN)

    def conta(login, nome, mid="", perfil="militar", **kw):
        u = auth.criar_usuario(c, "u1", login, nome, SENHA, perfil=perfil, militar_id=mid, email=f"{login}@exemplo.mil.br",
                               ramal="2345", celular="(21) 98888-7766", om="COpAb", **kw)
        u.pin_hash = auth.hash_pin(PIN)
        return u
    det = conta("20000001", nomes[0], "m1", nome_guerra=guerra[0], posto="1ºTEN", especialidade="")                # u2 detalhista
    aux = conta("20000002", nomes[1], "m2", nome_guerra=guerra[1], posto="2ºSG", especialidade="PL")               # u3 auxiliar
    enc = conta("20000003", "Roberto Lima Albuquerque", "", nome_guerra="Lima", posto="1ºTEN", especialidade="T")  # u4 encarregado
    vice = conta("20000004", "Marcos Antônio Tavares Barros", "", nome_guerra="Tavares", posto="CMG", especialidade="IM")  # u5 vice
    mil = conta("20000005", nomes[4], "m5", nome_guerra=guerra[4], posto="3ºSG", especialidade="PL")               # u6 militar
    novato = auth.criar_usuario(c, "u1", "20000006", nomes[5], SENHA, perfil="militar", email="moura@exemplo.mil.br",
                                ramal="2346", celular="(21) 98888-7701", om="COpAb", nome_guerra=guerra[5], posto="3ºSG",
                                especialidade="AM")                                                           # u7 sem vínculo
    novato.pin_hash = auth.hash_pin(PIN)
    pendente = auth.cadastrar_se(c, "20000007", "Henrique Soares Vieira", SENHA, "vieira@exemplo.mil.br", "2347",
                                 "(21) 98888-7702", om="COpAb", nome_guerra="Vieira", posto="CB")              # cadastro a aprovar

    # escalas do detalhista
    def escala(eid, nome, mem, **kw):
        e = Escala(eid, nome, om=OM, membros=[Pertinencia(f"m{i}") for i in mem], **kw)
        return gestao.criar_escala(c, det.id, e)
    e1 = escala("e1", "Portaria", range(2, 9), tipo="Diária", militares_dia=1, retem_qtd=1, funciona_em="todos")
    e2 = escala("e2", "Fiscal", range(9, 15), tipo="Diária", militares_dia=1, retem_qtd=1, funciona_em="uteis")
    e3 = escala("e3", "Sentinela", range(15, 23), tipo="Pernoite", militares_dia=2, retem_qtd=1, quartos=quartos_padrao(4))
    e4 = escala("e4", "Contramestre", range(23, 29), tipo="Diária", militares_dia=1, retem_qtd=1)
    gestao.editar_escala(c, det.id, "e1", auxiliares=["m2"], detalhista_id="m1")
    asn.designar(c, det.id, "e1", enc.id, vice.id)
    pm.compartilhar(c, det.id, "e1", novato.id, "leitura")
    gestao.editar_escala(c, det.id, "e1", om=OM,
        det_instrucoes=("<div>- Abertura do Prédio: até 06h30; pegar o envelope na Sala de Estado e assinar o livro de chaves;</div>"
                        "<div>- Ligar as luzes dos corredores, os monitores e o ar condicionado da Sala de Estado;</div>"
                        "<div>- Fechamento do Prédio às 17h: verificar se estão desligados os equipamentos e trancadas as portas;</div>"
                        "<ul><li>Cafeteiras e aparelhos elétricos;</li><li>Auditório, Cozinha e Sala de Reuniões.</li></ul>"),
        det_recomendacoes="<div>- Manter o hall de entrada limpo e arrumado (solicitar apoio quando necessário).</div>",
        det_regras=("<div>- Todo militar é responsável por conferir o detalhe imediatamente após a sua publicação;</div>"
                    "<div>- O retém assume o serviço do titular em caso de impedimento, mediante aviso ao detalhista;</div>"
                    "<div>- O detalhista poderá realizar trocas forçadas, quando necessário.</div>"),
        ass_detalhista="1ºTEN MENEZES", ass_auxiliar="2ºSG-PL ALBUQUERQUE", ass_encarregado="1ºTEN (T) LIMA", ass_vice_diretor="CMG (IM) TAVARES")

    # impedimentos
    c.impedimentos += [
        Impedimento("m3", "ferias", HOJE + timedelta(days=2), HOJE + timedelta(days=11), "Férias regulamentares", "", det.id, AGORA),
        Impedimento("m6", "curso", HOJE - timedelta(days=1), HOJE + timedelta(days=4), "Curso de Aperfeiçoamento", "", det.id, AGORA),
        Impedimento("m8", "dispensa", HOJE, HOJE + timedelta(days=1), "Consulta médica", "atestado_medico.pdf", det.id, AGORA),
        Impedimento("m11", "destaque", HOJE + timedelta(days=3), HOJE + timedelta(days=9), "Comissão em outra OM", "", det.id, AGORA)]

    # papeleta: troca entre dois militares de serviço
    res = gerar(c, HOJE + timedelta(days=20))
    servicos = {}
    for d in (HOJE + timedelta(days=i) for i in range(2, 18)):
        dia = res.dia(d, "e1")
        for a in (dia.alocacoes if dia else []):
            if a.origem == "normal":
                servicos.setdefault(a.militar_id, []).append(d)
    pares = [(x, y) for x in servicos for y in servicos if x != y and x not in ("m1",) and y not in ("m1",)]
    criadas = 0
    for x, y in pares:
        try:
            p = pp.criar(c, det.id, "e1", x, servicos[x][0], y, servicos[y][0], "Compromisso familiar", AGORA - timedelta(hours=3), pin=PIN)
            criadas += 1
            break
        except Exception:                                                      # noqa: BLE001
            continue
    # pedido de vínculo do novato e pedido de acesso
    try:
        vc.solicitar(c, novato.id, "e1", "m6", "11.0306.16", PIN, AGORA - timedelta(hours=2))
    except Exception as ex:                                                    # noqa: BLE001
        print("vínculo:", ex)
    try:
        ac.pedir_acesso(c, novato.id, "e2", "Preciso acompanhar a escala da fiscalização.", AGORA)
    except Exception as ex:                                                    # noqa: BLE001
        print("acesso:", ex)

    # documentos para assinatura: um aberto com 2 assinaturas; um rejeitado (período anterior)
    dias = [HOJE + timedelta(days=i) for i in range(7)]
    res7 = gerar(c, dias[-1])
    from sisescala import textorico as tr
    e1 = c.escala("e1")
    corpo = corpo_detalhe(c, res7, dias, "e1", OM, tr.normalizar(e1.det_instrucoes), tr.normalizar(e1.det_recomendacoes),
                          tr.normalizar(e1.det_regras), ("1ºTEN MENEZES", "2ºSG-PL ALBUQUERQUE", "1ºTEN (T) LIMA", "CMG (IM) TAVARES"))
    d1, _ = asn.enviar(c, det.id, "e1", dias, corpo, codigo_do_corpo(corpo), AGORA - timedelta(hours=1))
    asn.assinar(c, det.id, d1.id, "detalhista", PIN, agora=AGORA - timedelta(minutes=50))
    asn.assinar(c, aux.id, d1.id, "auxiliar", PIN, agora=AGORA - timedelta(minutes=35))
    ant = [HOJE - timedelta(days=7 - i) for i in range(7)]
    resp = gerar(c, ant[-1])
    corpo0 = corpo_detalhe(c, resp, ant, "e1", OM, "<div>Instruções do período anterior.</div>", "", "", ("", "", "", ""))
    d0, _ = asn.enviar(c, det.id, "e1", ant, corpo0, codigo_do_corpo(corpo0), AGORA - timedelta(days=7))
    asn.assinar(c, det.id, d0.id, "detalhista", PIN, agora=AGORA - timedelta(days=7))
    asn.rejeitar(c, enc.id, d0.id, "Falta incluir o reforço do dia 14 na escala do Fiscal.", AGORA - timedelta(days=6))

    # documento unificado
    cj = cjs.criar(c, det.id, "Escala de Serviço do Dia", ["e1", "e2", "e3", "e4"])
    cjs.editar(c, det.id, cj.id, om=OM, det_instrucoes="<div>Apresentar-se fardado e com antecedência de 30 minutos.</div>",
               det_recomendacoes="<div>Manter o telefone de contato sempre atualizado.</div>",
               det_regras="<ol><li>Parada às 17h</li><li>Não acumular serviço</li></ol>",
               ass_detalhista="1ºTEN MENEZES", ass_vice_diretor="CMG (IM) TAVARES")
    asn.designar_conjunto(c, det.id, cj, aux.id, enc.id, vice.id)

    if os.path.exists(saida):
        os.remove(saida)
    r = Repositorio(ArquivoBackend(saida))
    r.carregar()
    r.salvar(c)
    open(saida + ".codigo", "w").write(d1.codigo)
    print("ok:", saida, "| papeletas:", len(c.papeletas), "| vínculos:", len(c.vinculos), "| docs:", len(c.detalhes_docs))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "manual.json")

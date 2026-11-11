"""Fluxo de assinatura do detalhe de serviço pelas quatro autoridades (Detalhista, Auxiliar do Detalhista, Encarregado do
Detalhe e Vice-Diretor).

1. O detalhista prepara o documento e o **envia para assinatura**: o conteúdo é congelado (`DetalheDoc`) e as demais
   autoridades recebem um aviso.
2. Cada autoridade abre **Assinar documentos**, confere o conteúdo e assina com o PIN (`AssinaturaDetalhe`, uma por papel).
3. O PDF pode ser baixado a qualquer momento com as assinaturas que já existem (uma, algumas ou todas).

Quem é cada autoridade: o detalhista é o responsável pela escala; o auxiliar é a conta ligada ao militar designado auxiliar;
o encarregado e o vice-diretor são contas designadas pelo detalhista na própria escala."""
from __future__ import annotations

import base64
import zlib
from datetime import datetime

from . import notificacoes as nt
from . import verificacao as vf
from .modelos import AssinaturaDetalhe, Contexto, DetalheDoc, Escala
from .permissoes import PermissaoNegada, eh_auxiliar, eh_detalhista

PAPEIS = ("detalhista", "auxiliar", "encarregado", "vice_diretor")
ROTULO = {"detalhista": "Detalhista", "auxiliar": "Auxiliar do Detalhista", "encarregado": "Encarregado do Detalhe",
          "vice_diretor": "Vice-Diretor"}


def empacotar(texto: str) -> str:
    """JSON -> texto curto (zlib + base64), para caber nas células da planilha."""
    return base64.b64encode(zlib.compress(texto.encode(), 9)).decode()


def desempacotar(txt: str) -> str:
    if (txt or "").lstrip().startswith("{"):                 # registros antigos guardavam o JSON puro
        return txt
    try:
        return zlib.decompress(base64.b64decode(txt)).decode()
    except Exception:                                        # noqa: BLE001
        return ""


def papeis_do_usuario(ctx: Contexto, usuario_id: str, esc: Escala) -> list[str]:
    """Em quais papéis esta conta assina o detalhe desta escala (pode ser mais de um em OM pequena)."""
    p = []
    if eh_detalhista(ctx, usuario_id, esc):
        p.append("detalhista")
    if eh_auxiliar(ctx, usuario_id, esc):
        p.append("auxiliar")
    if esc.encarregado_usuario_id and esc.encarregado_usuario_id == usuario_id:
        p.append("encarregado")
    if esc.vice_usuario_id and esc.vice_usuario_id == usuario_id:
        p.append("vice_diretor")
    return p


def designar(ctx: Contexto, usuario_id: str, escala_id: str, encarregado_id: str = "", vice_id: str = "") -> None:
    """O detalhista indica as contas do Encarregado do Detalhe e do Vice-Diretor desta escala ("" = ninguém)."""
    esc = ctx.escala(escala_id)
    if not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada("só o detalhista da escala designa quem assina o detalhe")
    for papel, uid in (("Encarregado do Detalhe", encarregado_id), ("Vice-Diretor", vice_id)):
        if uid:
            u = ctx.usuario(uid)
            if u is None or not u.ativo:
                raise ValueError(f"{papel}: conta inexistente ou inativa")
            if not u.pin_hash:
                raise ValueError(f"{papel}: {u.nome} ainda não cadastrou o PIN em Minha conta (precisa dele para assinar)")
    esc.encarregado_usuario_id, esc.vice_usuario_id = encarregado_id, vice_id


def assinaturas_do(ctx: Contexto, doc: DetalheDoc) -> list[AssinaturaDetalhe]:
    return vf.do_codigo(ctx, doc.codigo)


def carimbos(ctx: Contexto, doc: DetalheDoc, url: str = "") -> dict:
    """Dicionário para o PDF (`renderizar_pdf`): carimbo de cada papel que já assinou + código e URL do QR."""
    c = {"hash": doc.codigo, "url": url}
    for a in assinaturas_do(ctx, doc):
        c[a.papel] = {"nome": a.nome, "nip": a.nip, "em": a.em}
    return c


def faltam(ctx: Contexto, doc: DetalheDoc) -> list[str]:
    feitos = {a.papel for a in assinaturas_do(ctx, doc)}
    return [p for p in PAPEIS if p not in feitos]


def _quem_assina(ctx: Contexto, esc: Escala) -> list[str]:
    """Contas que têm algum papel de assinatura nesta escala."""
    ids = [esc.dono_id]
    ids += [u.id for u in ctx.usuarios if u.ativo and u.militar_id and u.militar_id in esc.auxiliares]
    ids += [esc.encarregado_usuario_id, esc.vice_usuario_id]
    return [i for i in dict.fromkeys(ids) if i]


def enviar(ctx: Contexto, usuario_id: str, escala_id: str, dias, corpo: str, codigo: str,
           agora: datetime | None = None) -> tuple[DetalheDoc, bool]:
    """Congela o documento e avisa as autoridades. Devolve (documento, novo): o mesmo conteúdo já enviado não se duplica;
    uma versão diferente para o mesmo período substitui as abertas anteriores (as assinaturas delas não valem para a nova)."""
    agora = agora or datetime.now()
    esc = ctx.escala(escala_id)
    if not eh_detalhista(ctx, usuario_id, esc):
        raise PermissaoNegada("só o detalhista da escala envia o detalhe para assinatura")
    for d in ctx.detalhes_docs:
        if d.codigo == codigo and d.escala_id == escala_id and d.status == "aberto":
            return d, False
    for d in ctx.detalhes_docs:
        if d.escala_id == escala_id and d.inicio == dias[0] and d.fim == dias[-1] and d.status == "aberto":
            d.status = "substituido"
    n = max([int(d.id[1:]) for d in ctx.detalhes_docs if d.id[1:].isdigit()] + [0]) + 1
    doc = DetalheDoc(f"d{n}", codigo, escala_id, dias[0], dias[-1], usuario_id, agora, "aberto", empacotar(corpo))
    ctx.detalhes_docs.append(doc)
    nt.notificar(ctx, _quem_assina(ctx, esc), "assinatura",
                 f"Detalhe de serviço de {esc.nome} ({dias[0]:%d/%m} a {dias[-1]:%d/%m/%Y}) aguarda assinatura. "
                 f"Abra Documentos → Assinar documentos.", escala_id, agora, excluir=[usuario_id])
    return doc, True


def cancelar(ctx: Contexto, usuario_id: str, doc_id: str) -> None:
    doc = obter(ctx, doc_id)
    if not eh_detalhista(ctx, usuario_id, ctx.escala(doc.escala_id)):
        raise PermissaoNegada("só o detalhista da escala cancela o envio")
    if doc.status != "aberto":
        raise ValueError(f"documento {doc.status}")
    doc.status = "cancelado"


def obter(ctx: Contexto, doc_id: str) -> DetalheDoc:
    d = next((x for x in ctx.detalhes_docs if x.id == doc_id), None)
    if d is None:
        raise ValueError("documento não encontrado")
    return d


def conteudo(doc: DetalheDoc) -> dict:
    import json
    try:
        return json.loads(desempacotar(doc.conteudo))
    except ValueError:
        return {}


def para_assinar(ctx: Contexto, usuario_id: str) -> list[tuple[DetalheDoc, list[str]]]:
    """Documentos abertos em que esta conta ainda tem papel a assinar: [(documento, papéis pendentes)]."""
    out = []
    for d in sorted((x for x in ctx.detalhes_docs if x.status == "aberto"), key=lambda x: x.enviado_em, reverse=True):
        esc = ctx.escala(d.escala_id)
        if esc is None:
            continue
        feitos = {(a.usuario_id, a.papel) for a in assinaturas_do(ctx, d)} | {("", a.papel) for a in assinaturas_do(ctx, d)}
        pend = [p for p in papeis_do_usuario(ctx, usuario_id, esc) if (usuario_id, p) not in feitos]
        if pend:
            out.append((d, pend))
    return out


def meus_documentos(ctx: Contexto, usuario_id: str) -> list[DetalheDoc]:
    """Documentos abertos das escalas em que a conta tem algum papel (para acompanhar, mesmo já tendo assinado)."""
    return [d for d in sorted((x for x in ctx.detalhes_docs if x.status == "aberto"), key=lambda x: x.enviado_em, reverse=True)
            if ctx.escala(d.escala_id) is not None and papeis_do_usuario(ctx, usuario_id, ctx.escala(d.escala_id))]


def assinar(ctx: Contexto, usuario_id: str, doc_id: str, papel: str, pin: str, om: str = "",
            agora: datetime | None = None) -> AssinaturaDetalhe:
    """Assina com o PIN, no papel indicado. Erros de regra viram ValueError/PermissaoNegada/AutenticacaoErro."""
    from . import auth
    agora = agora or datetime.now()
    doc = obter(ctx, doc_id)
    if doc.status != "aberto":
        raise ValueError("este documento não está mais aberto para assinatura (foi substituído ou cancelado)")
    esc = ctx.escala(doc.escala_id)
    if papel not in papeis_do_usuario(ctx, usuario_id, esc):
        raise PermissaoNegada("você não tem este papel de assinatura nesta escala")
    if any(a.papel == papel for a in assinaturas_do(ctx, doc)):
        raise ValueError(f"o papel {ROTULO[papel]} já assinou este documento")
    if not auth.confirmar_assinatura(ctx, usuario_id, pin, agora):
        raise auth.AutenticacaoErro("PIN incorreto")
    u = ctx.usuario(usuario_id)
    mil = ctx.militar(u.militar_id) if u.militar_id else None
    nome = " ".join(u.nome.split())                       # nome completo da conta (sem posto, especialidade nem nome de guerra)
    nip = mil.nip if mil and mil.nip else (u.nip or u.login)
    cont = desempacotar(doc.conteudo)
    a = vf.registrar(ctx, usuario_id, doc.escala_id, [doc.inicio, doc.fim], cont, doc.codigo, nome, nip,
                     om or conteudo(doc).get("om", ""), agora, papel)
    nt.notificar(ctx, [doc.enviado_por], "assinatura",
                 f"{ROTULO[papel]} {nome} assinou o detalhe de serviço de {esc.nome} "
                 f"({doc.inicio:%d/%m} a {doc.fim:%d/%m/%Y}).", doc.escala_id, agora, excluir=[usuario_id])
    return a

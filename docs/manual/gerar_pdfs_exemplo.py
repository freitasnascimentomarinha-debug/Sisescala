"""Gera os PDFs de exemplo do manual (detalhe assinado com 4 assinaturas, com 1 assinatura, unificado e prévia) a partir dos dados
fictícios de seed_manual.py. Uso: python docs/manual/gerar_pdfs_exemplo.py <dados.json> <pasta_saida>"""
import os
import subprocess
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from sisescala import assinaturas as asn  # noqa: E402
from sisescala.motor import gerar  # noqa: E402
from sisescala.pdf import gerar_pdf_conjunto, renderizar_pdf  # noqa: E402
from sisescala.pdf_previa import pdf_previa  # noqa: E402
from sisescala.persistencia import ArquivoBackend, Repositorio  # noqa: E402

dados, saida = sys.argv[1:3]
os.makedirs(saida, exist_ok=True)
c = Repositorio(ArquivoBackend(dados)).carregar()
doc = next(d for d in c.detalhes_docs if d.status == "aberto")
url = "https://sisescala.exemplo.mil.br/verificar?codigo=" + doc.codigo
agora = datetime.now().replace(second=0, microsecond=0)
quatro = {"hash": doc.codigo, "url": url,
          "detalhista": {"nome": "Carlos Eduardo Menezes", "nip": "11.0301.11", "em": agora - timedelta(minutes=50)},
          "auxiliar": {"nome": "Ricardo Albuquerque Tavares", "nip": "11.0302.12", "em": agora - timedelta(minutes=35)},
          "encarregado": {"nome": "Roberto Lima Albuquerque", "nip": "11.0399.99", "em": agora - timedelta(minutes=20)},
          "vice_diretor": {"nome": "Marcos Antônio Tavares Barros", "nip": "11.0398.98", "em": agora - timedelta(minutes=5)}}
uma = {"hash": doc.codigo, "url": url, "detalhista": quatro["detalhista"]}
pdfs = {"detalhe_assinado": renderizar_pdf(asn.conteudo(doc), quatro, c),
        "detalhe_uma_assinatura": renderizar_pdf(asn.conteudo(doc), uma, c),
        "unificado": gerar_pdf_conjunto(c, gerar(c, date.today()), [date.today()], c.conjuntos[0]),
        "previa": pdf_previa(c, gerar(c, date.today() + timedelta(days=6)), [date.today() + timedelta(days=i) for i in range(7)], "e1")}
for nome, b in pdfs.items():
    open(os.path.join(saida, nome + ".pdf"), "wb").write(b)
    subprocess.run(["pdftoppm", "-r", "90", "-png", "-f", "1", "-l", "1", os.path.join(saida, nome + ".pdf"), os.path.join(saida, nome)], check=True)
# área de assinaturas ampliada (fica na página 2 quando as instruções ocupam a 1ª): 4 assinaturas e 1 assinatura
for nome in ("detalhe_assinado", "detalhe_uma_assinatura"):
    subprocess.run(["pdftoppm", "-r", "130", "-png", "-f", "2", "-l", "2", os.path.join(saida, nome + ".pdf"), os.path.join(saida, "ampl_" + nome)], check=True)
print("ok", saida)

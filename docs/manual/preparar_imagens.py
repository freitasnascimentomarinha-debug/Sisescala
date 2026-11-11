"""Recorta e apara as telas capturadas (tira o menu lateral quando não é o assunto e o vazio embaixo) e grava as imagens do manual.
Uso: python docs/manual/preparar_imagens.py <pasta_telas> <pasta_pdfs> <pasta_saida>"""
import json
import os
import sys

from PIL import Image

telas, pdfs, saida = sys.argv[1:4]
os.makedirs(saida, exist_ok=True)
INFO = {}


def aparar(im, margem=26):
    """Remove o vazio embaixo (fundo escuro uniforme)."""
    g = im.convert("L")
    w, h = g.size
    px = g.load()
    ref = px[w - 6, h - 6]
    ultimo = 0
    for y in range(h - 1, -1, -1):
        if any(abs(px[x, y] - ref) > 14 for x in range(0, w, 3)):
            ultimo = y
            break
    return im.crop((0, 0, w, min(h, ultimo + margem)))


def salvar(nome, im):
    im.save(os.path.join(saida, nome + ".png"), optimize=True)
    INFO[nome] = {"w": im.size[0], "h": im.size[1]}


for f in sorted(os.listdir(telas)):
    if not f.endswith(".png"):
        continue
    nome = f[:-4]
    im = Image.open(os.path.join(telas, f)).convert("RGB")
    if nome == "10-editor":
        salvar(nome, im.crop((40, 36, 1360, 600)))                 # só a janela do editor
    elif nome in ("01-login", "02-criar-conta", "17-verificar-publica", "20-nova-escala"):
        salvar(nome, aparar(im))                              # tela cheia (sem menu lateral)
    elif nome == "03-painel":
        salvar("03-painel", aparar(im))                       # com o menu lateral
        salvar("03b-painel-conteudo", aparar(im.crop((300, 0, im.size[0], im.size[1]))))
    elif nome == "04-previa":
        topo = im.crop((300, 0, im.size[0], 930))
        salvar("04-previa", topo)
        salvar("04b-previa-troca", aparar(im.crop((300, 930, im.size[0], im.size[1]))))
    else:
        maxh = {"09-detalhe-servico": 1350, "12-detalhe-unificado": 1250}.get(nome, 1000)   # o essencial fica no alto da página
        salvar(nome, aparar(im.crop((300, 0, im.size[0], min(im.size[1], maxh)))))
for f in sorted(os.listdir(pdfs)):
    if f.endswith(".png"):
        im = Image.open(os.path.join(pdfs, f)).convert("RGB")
        g = im.convert("L")
        w, h = g.size
        px = g.load()
        ultimo = max((y for y in range(h - 70) if any(px[x, y] < 235 for x in range(0, w, 4))), default=h)      # tira o branco do pé
        ampl = f.startswith("ampl_")                                    # ampliações: pula a faixa azul do topo e as margens laterais
        esq, dir_ = (int(w * 0.085), int(w * 0.915)) if ampl else (0, w)
        salvar("pdf-" + f.replace("-1.png", "").replace("-2.png", ""), im.crop((esq, 40 if ampl else 0, dir_, min(h, ultimo + 40))))
json.dump(INFO, open(os.path.join(saida, "info.json"), "w"), indent=1)
print(len(INFO), "imagens")

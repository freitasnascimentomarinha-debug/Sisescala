"""Gera static/camuflado.svg: camuflado digital pixelado (tons da farda), com repetição contínua.

Uso: python scripts/gerar_camuflado.py
"""
import random
from pathlib import Path

N, LADO = 44, 9                      # 44x44 células de 9px (tile de 396px)
CORES = ["#2E3B20", "#445730", "#5E7040", "#8A8159", "#A89B72", "#6B5A3C", "#3A4A29"]
PESOS = [3, 3, 2, 2, 1, 1, 2]


def gerar(semente: int = 7) -> str:
    rnd = random.Random(semente)
    sementes = [(rnd.random() * N, rnd.random() * N, rnd.choices(range(len(CORES)), PESOS)[0]) for _ in range(95)]
    grade = []
    for y in range(N):
        linha = []
        for x in range(N):
            melhor, cor = 1e9, 0
            for sx, sy, c in sementes:
                dx, dy = abs(x - sx), abs(y - sy)
                dx, dy = min(dx, N - dx), min(dy, N - dy)           # distância circular: o tile emenda sem costura
                d = dx * dx + dy * dy + rnd.random() * 5               # ruído cria a borda pixelada
                if d < melhor:
                    melhor, cor = d, c
            linha.append(cor)
        grade.append(linha)
    lado = N * LADO
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{lado}" height="{lado}" viewBox="0 0 {lado} {lado}" '
              f'shape-rendering="crispEdges"><rect width="{lado}" height="{lado}" fill="{CORES[0]}"/>']
    for y, linha in enumerate(grade):
        x = 0
        while x < N:
            fim = x
            while fim + 1 < N and linha[fim + 1] == linha[x]:
                fim += 1
            if linha[x] != 0:
                partes.append(f'<rect x="{x * LADO}" y="{y * LADO}" width="{(fim - x + 1) * LADO}" height="{LADO}" fill="{CORES[linha[x]]}"/>')
            x = fim + 1
    partes.append("</svg>")
    return "".join(partes)


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent.parent / "static" / "camuflado.svg"
    destino.write_text(gerar(), encoding="utf-8")
    print(f"{destino} ({destino.stat().st_size // 1024} KB)")

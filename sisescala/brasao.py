"""Brasão de Armas do cabeçalho dos documentos: a imagem enviada pelo administrador é reduzida e guardada na planilha
(aba Config, em texto base64), para sair centralizada acima de "MARINHA DO BRASIL" em todos os PDFs."""
from __future__ import annotations

import base64
from io import BytesIO

LIMITE = 40000          # caracteres: o limite de uma célula do Google Sheets é 50.000


def preparar(dados: bytes) -> str:
    """Imagem (PNG/JPG) -> PNG reduzido em base64, cabendo numa célula da planilha. Levanta ValueError se não for imagem."""
    from PIL import Image
    try:
        img = Image.open(BytesIO(dados))
        img.load()
    except Exception as ex:                                       # noqa: BLE001
        raise ValueError("arquivo de imagem inválido (use PNG ou JPG)") from ex
    img = img.convert("RGBA")
    for lado in (360, 300, 240, 190, 150):
        copia = img.copy()
        copia.thumbnail((lado, lado))
        for cores in (None, 128, 64):
            c = copia if cores is None else copia.quantize(colors=cores, method=Image.Quantize.FASTOCTREE).convert("RGBA")
            buf = BytesIO()
            c.save(buf, "PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            if len(b64) <= LIMITE:
                return b64
    raise ValueError("a imagem é complexa demais; use uma versão mais simples do brasão")


def bytes_de(b64: str) -> bytes | None:
    try:
        return base64.b64decode(b64) if b64 else None
    except ValueError:
        return None

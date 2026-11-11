"""Brasão do cabeçalho dos documentos: a imagem enviada pelo detalhista é reduzida e guardada na planilha (em texto base64),
para sair centralizada acima de "MARINHA DO BRASIL" nos PDFs. Aceita os formatos de imagem mais comuns e se vira para caber
numa célula da planilha (limite do Google Sheets: 50.000 caracteres)."""
from __future__ import annotations

import base64
from io import BytesIO

LIMITE = 45000          # caracteres em base64 (a célula da planilha aceita 50.000)
FORMATOS = ["png", "jpg", "jpeg", "jfif", "webp", "bmp", "gif", "tif", "tiff", "psd"]
MAX_PIXELS = 120_000_000   # recusa só imagens absurdas (acima disso o servidor pode ficar sem memória)


def _codificar(img, opaco: bool, lado: int) -> list[bytes]:
    """Versões da imagem (da melhor para a mais leve) no tamanho `lado`: PNG com transparência, PNG de paleta ou, se a imagem é
    opaca (foto, fundo branco), JPEG."""
    from PIL import Image
    c = img.copy()
    c.thumbnail((lado, lado), Image.LANCZOS)
    saidas = []
    if opaco:
        rgb = c.convert("RGB")
        for q in (92, 85, 75, 65, 55):
            b = BytesIO()
            rgb.save(b, "JPEG", quality=q, optimize=True)
            saidas.append(b.getvalue())
    else:
        b = BytesIO()
        c.save(b, "PNG", optimize=True)
        saidas.append(b.getvalue())
        for n in (256, 128, 64, 32):                    # paleta: guarda 1 byte por pixel (e a transparência)
            p = c.quantize(colors=n, method=Image.Quantize.FASTOCTREE)
            b = BytesIO()
            p.save(b, "PNG", optimize=True)
            saidas.append(b.getvalue())
    return saidas


def preparar(dados: bytes) -> str:
    """Imagem -> base64 que cabe numa célula da planilha. Levanta ValueError (com o motivo, em português) se não der."""
    from PIL import Image, ImageOps
    if not dados:
        raise ValueError("arquivo vazio")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(BytesIO(dados))
        img.load()
    except Image.DecompressionBombError as ex:
        raise ValueError("a imagem é grande demais (mais de 120 milhões de pixels); reduza o tamanho e envie de novo") from ex
    except Exception as ex:                                       # noqa: BLE001
        raise ValueError("não consegui ler este arquivo como imagem. Envie PNG ou JPG; arquivos de edição (PSD, AI, CDR, SVG) "
                         "devem ser exportados para PNG antes") from ex
    try:
        img = ImageOps.exif_transpose(img)                        # foto de celular: respeita a rotação
    except Exception:                                             # noqa: BLE001
        pass
    img = img.convert("RGBA")
    opaco = img.getchannel("A").getextrema()[0] == 255
    for lado in (320, 280, 240, 200, 170, 140, 110):
        for saida in _codificar(img, opaco, lado):
            b64 = base64.b64encode(saida).decode()
            if len(b64) <= LIMITE:
                return b64
    raise ValueError("a imagem tem detalhes demais para caber no sistema; use uma versão mais simples (menos cores/efeitos)")


def bytes_de(b64: str) -> bytes | None:
    try:
        return base64.b64decode(b64) if b64 else None
    except ValueError:
        return None

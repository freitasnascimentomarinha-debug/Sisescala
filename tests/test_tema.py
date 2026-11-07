"""Tema camuflado: o padrão existe, é servido e a paleta antiga (azul) não sobrou."""
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_padrao_camuflado_existe_e_e_um_svg_valido():
    svg = RAIZ / "static" / "camuflado.svg"
    raiz = ET.fromstring(svg.read_text("utf-8"))
    assert raiz.tag.endswith("svg") and len(list(raiz)) > 100            # centenas de blocos pixelados
    cores = set(re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg.read_text("utf-8")))
    assert len(cores) >= 5                                               # verdes, areia e marrom da farda


def test_configuracao_serve_o_padrao_e_usa_o_tema_escuro_verde():
    cfg = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text("utf-8"))
    assert cfg["server"]["enableStaticServing"] is True
    assert cfg["theme"]["base"] == "dark" and cfg["theme"]["primaryColor"] == "#7FA24A"


def test_css_usa_o_padrao_e_nao_tem_mais_o_azul_antigo():
    css = (RAIZ / "assets" / "estilo.css").read_text("utf-8")
    assert "app/static/camuflado.svg" in css
    for azul in ("#3B82F6", "#1D4ED8", "#2563EB", "#0B2545", "rgba(59,130,246"):
        assert azul not in css

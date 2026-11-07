"""SisEscala – escalas e detalhe de serviço."""

from pathlib import Path as _Path

# Versão do código carregado (maior data de modificação dos .py). O app.py compara com a do disco para descartar
# módulos velhos que o servidor manteve em memória depois de um deploy.
_assinatura = max((p.stat().st_mtime_ns for p in _Path(__file__).parent.glob("*.py")), default=0)

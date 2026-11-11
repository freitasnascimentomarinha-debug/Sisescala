# Manual do usuário do SisEscala

`SisEscala-Manual-do-Usuario.docx` (editável) e `.pdf`: manual com 41 páginas e 34 figuras (telas reais, com dados fictícios, e PDFs gerados pelo sistema).

## Como refazer o manual (depois de mudanças no sistema)

1. `python docs/manual/seed_manual.py <dados.json>` — cria dados **fictícios** realistas (contas, escalas, impedimentos, papeleta, envios assinados/rejeitados, documento unificado).
2. Suba o sistema com esses dados: `SISESCALA_ARQUIVO=<dados.json> SISESCALA_ADMIN_NIP=admin SISESCALA_ADMIN_SENHA=Manual@2026 streamlit run app.py --server.port 8599`.
3. `NODE_PATH=$(npm root -g) node docs/manual/capturar_telas.js <pasta_telas> $(cat <dados.json>.codigo)` — captura as telas com Playwright (números vermelhos nos elementos principais).
4. Gere os PDFs de exemplo (detalhe assinado, unificado e prévia) e rode `python docs/manual/preparar_imagens.py <telas> <pdfs> <img>` para recortar as imagens.
5. `node docs/manual/gerar_manual.js <img> manual.docx [paginas.json]` — monta o .docx (o sumário recebe os números de página na 2ª passada).

Contas do seed (senha `Manual@2026`, PIN `1234`): `admin`, `20000001` (detalhista), `20000002` (auxiliar), `20000003` (encarregado), `20000004` (vice-diretor), `20000005` (militar).

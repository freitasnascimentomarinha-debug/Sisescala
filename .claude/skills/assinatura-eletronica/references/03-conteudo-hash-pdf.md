# Conteúdo assinado, hash, PDF, carimbo e QR code

## Conteúdo
1. Snapshot (o que se assina)
2. JSON canônico e código SHA-256
3. Renderizar o PDF a partir do snapshot
4. Carimbo da assinatura e posição do QR
5. Paginação e layout que deram problema
6. Texto rico (editor → PDF)
7. Brasão/imagem
8. Fuso horário

## 1. Snapshot (o que se assina)

O snapshot é um dicionário **já resolvido em texto** com tudo que o PDF mostra: cabeçalho (OM, título, subtítulo), linhas das tabelas (datas, nomes formatados, siglas, horários), textos (instruções/recomendações/regras), observações, nomes das autoridades. Por quê: se o PDF fosse refeito de dados vivos (cadastro, escala), qualquer mudança posterior alteraria o documento já assinado e o código deixaria de bater.

Estrutura usada (`versao` ajuda a evoluir sem quebrar documentos antigos):

```json
{"versao": 2, "escala_id": "e1", "escala_nome": "Portaria", "om": "...", "titulo": "DETALHE DE SERVIÇO DE PORTARIA",
 "subtitulo": "Serviço · Período: 11/11/2026 a 17/11/2026 · 1 escalado(s) por dia · retém: 1",
 "periodo": ["2026-11-11","2026-11-17"], "eventos": false,
 "linhas": [{"data":"2026-11-11","dow":"QUA","util":true,"funciona":true,"efetivos":["2ºSG-PL Freitas [SVÇ]"],"retens":["CB Fulano [RT]"],"descricao":""}],
 "textos": ["<instruções html>","<recomendações>","<regras>"], "obs": ["13/11: …"],
 "nomes": ["Detalhista","Auxiliar","Encarregado","Vice"]}
```

Versão 3 (documento unificado) troca `linhas` por `secoes: [{escala_id, nome, eventos, linhas}]` e acrescenta `conjunto_id`. **O renderizador deve aceitar todas as versões já assinadas** (`snap.get("secoes")` ausente → modo antigo).

Convenções úteis: prefixo `~` num texto para renderizar em itálico (dispensado), listas de strings já formatadas.

## 2. JSON canônico e código SHA-256

```python
corpo = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
codigo = hashlib.sha256(corpo.encode()).hexdigest()
```

- `sort_keys=True` e `ensure_ascii=False` tornam a serialização determinística.
- **Não inclua** no snapshot nada que mude entre geração e verificação (data de geração, contadores, ids aleatórios).
- Mudou um nome de autoridade? Muda o código (por isso é preciso reenviar). Isso é desejado.
- O código identifica **conteúdo**, o `envio_id` identifica **a rodada de assinaturas** (regra 3 da skill).
- Guarde `conteudo = zlib+base64(corpo)` no envio e em cada assinatura. A verificação refaz `sha256(desempacotar(conteudo)) == codigo` (integridade do registro).

## 3. Renderizar o PDF a partir do snapshot

`renderizar_pdf(snapshot, carimbos, ctx)`; `gerar_pdf(dados vivos)` apenas monta o snapshot e chama o renderizador. Assim:
- o responsável vê o PDF "ao vivo" antes de enviar;
- depois do envio, qualquer pessoa baixa **o mesmo PDF** (com as assinaturas já feitas) a partir do que foi congelado;
- o brasão é cosmético e vem da origem atual (não entra no hash).

Dicionário de carimbos: `{papel: {nome, nip, em}, "hash": codigo, "url": url_do_qr}`.

## 4. Carimbo da assinatura e posição do QR

- Texto do carimbo, centralizado, **bem pequeno** (≈5,6 pt): `Assinado eletronicamente com PIN` / **`NOME COMPLETO EM MAIÚSCULAS`** (negrito) / `NIP … · dd/mm/aaaa HH:MM:SS (Brasília)`. Use o **nome completo da conta**, não posto/especialidade/nome de guerra. Nomes longos quebram em duas linhas sem desalinhar.
- Grade: 3 autoridades na primeira linha, a 4ª **centralizada abaixo** (para N diferente, mantenha a última centralizada). Linha `____` onde ainda não há assinatura; nomes digitados e rótulos do papel abaixo.
- **QR:** `reportlab.graphics.barcode.qr.QrCodeWidget` (sem dependência extra), conteúdo = URL `…/verificar?codigo=<sha256>` (ou `SISESCALA-VERIFICAR:<sha256>` se não houver URL-base).
  - **Exatamente 1 assinatura → QR ao lado do carimbo** (14 mm, na célula do assinante) e o código SHA-256 centralizado abaixo.
  - **2 ou mais → QR (17 mm) à esquerda do bloco "Código de verificação"** abaixo das assinaturas, com o hash por extenso e a frase "Confira a autenticidade lendo o QR code ou na página 'Verificar documento' (não precisa de login)".
- URL-base: variável de ambiente (`SISESCALA_URL`) ou a URL da própria página (`st.context.url`), removendo o nome da página final (`/detalhe`, `/verificar`…) antes de acrescentar `/verificar?codigo=`.

## 5. Paginação e layout que deram problema

- **Título de seção sozinho no pé da página** (o texto vai para a folha seguinte): preceda cada título por `CondPageBreak(26*mm)`. Se sobrar menos que isso, o título vai junto para a próxima página.
- Bloco de assinaturas+código em `KeepTogether` (não separar carimbo do código). Em documento curto cabe tudo numa folha; com instruções longas, o bloco vai inteiro para a seguinte.
- `Spacer` não resolve quebra de página; o problema é de fluxo, não de espaço.
- Fundo escuro de tela não é bom para impressão em PDF institucional: use paleta clara (azul-marinho/ouro sobre branco) para documentos oficiais.
- Fontes padrão do reportlab (Helvetica) cobrem Latin-1 (acentos, Ç); evite símbolos fora de Latin-1 (●, ✓) dentro do PDF.

## 6. Texto rico (editor → PDF)

Editores `contenteditable` devolvem HTML. **Higienize** (lista branca: `b/strong, i/em, u, br, p/div, ul, ol, li`, sem atributos), converta para o dialeto do reportlab (`<b>`, `<i>`, `<u>`, `<br/>`, "• " e "1. " nas listas) e para HTML seguro da tela. Texto simples antigo (sem tags) continua valendo (quebras de linha viram linhas). Cole sempre como texto simples no editor para não trazer lixo do Word. Módulo de referência: `textorico.py`.

## 7. Brasão/imagem

Guarde em base64 numa célula. Reduza ≤ 320 px; imagem opaca → JPEG (qualidade 92→55); com transparência → PNG, com paleta (256→32 cores) se preciso; respeite rotação EXIF; recuse imagens gigantes (>120 Mpx) com mensagem clara. Aceite PNG, JPG/JFIF, WEBP, BMP, GIF, TIFF, PSD; HEIC e arquivos de edição (AI, CDR, SVG) pedem exportar para PNG. Módulo: `brasao.py`. O brasão **padrão** (por exemplo as Armas Nacionais) vem de um arquivo do repositório; a origem pode ter o seu próprio.

## 8. Fuso horário

Servidores rodam em UTC. Fixe o fuso do **processo** no ponto de entrada:

```python
os.environ["TZ"] = os.environ.get("APP_TZ", "America/Sao_Paulo"); time.tzset()
```

Assim `datetime.now()` e `date.today()` de todo o sistema (assinaturas, notificações, "hoje") passam a ser os de Brasília. Dados antigos gravados em UTC continuam com o horário antigo. Em Windows (sem `tzset`) use `zoneinfo` explicitamente. Mostre sempre "(Brasília)" no carimbo.

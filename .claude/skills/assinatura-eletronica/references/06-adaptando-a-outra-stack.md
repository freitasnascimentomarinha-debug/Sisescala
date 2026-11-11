# Adaptando a outra stack

## Conteúdo
1. O que é portável e o que é da stack
2. Mapeamento por stack
3. Trava de login × página pública
4. Roteiro de adaptação (passo a passo)
5. Perguntas de descoberta do projeto do usuário

## 1. O que é portável e o que é da stack

**Portável (copie a lógica):** snapshot/JSON canônico/SHA-256; modelo de envio e assinatura; regras de papéis/estados; `assinar/rejeitar/cancelar/enviar`; `integra`/`buscar`; migração de dados antigos; regras de PIN; texto das notificações; testes de domínio.

**Da stack (reescreva):** persistência, telas, rotas, geração de PDF, QR, notificações, autenticação, agendamento/fuso.

O núcleo em `assets/referencia-sisescala/assinaturas.py` e `verificacao.py` é Python puro sobre um objeto `ctx` com listas (`detalhes_docs`, `assinaturas_detalhe`, `usuarios`, `notificacoes`). Em outras stacks, troque `ctx.lista` por repositórios/ORM mantendo a mesma API de funções.

## 2. Mapeamento por stack

| Conceito | Streamlit (referência) | Django | Flask/FastAPI | Node (Express/Nest) |
|---|---|---|---|---|
| Modelos | dataclasses + abas/planilha | `models.Model` (`Envio`, `Assinatura`) | SQLAlchemy | Prisma/TypeORM |
| Conteúdo compactado | `zlib+base64` em texto | `BinaryField`/`TextField` | `LargeBinary` | `Buffer`/`TEXT` |
| PIN | bcrypt | `django.contrib.auth.hashers` (bcrypt/argon2) | `passlib`/`bcrypt` | `bcrypt` |
| PDF | reportlab (Platypus) | reportlab/WeasyPrint | reportlab/WeasyPrint | pdf-lib / Puppeteer (HTML→PDF) |
| QR | `QrCodeWidget` (reportlab) | `qrcode`/reportlab | `qrcode` | `qrcode` |
| Página pública | navegação deslogada separada | view sem `@login_required` | rota sem dependência de auth | rota sem middleware de auth |
| Notificações | tabela + badge | `django-notifications`/tabela | tabela/WebSocket/e-mail | tabela/e-mail/push |
| Fuso | `TZ` do processo + `tzset` | `TIME_ZONE = "America/Sao_Paulo"`, `USE_TZ` | `zoneinfo` | `TZ` env / `date-fns-tz` |
| Concorrência | versão da planilha (conflito) | transação + `select_for_update` na assinatura | transação | transação |

Em SQL, adicione restrição única `(codigo, usuario_id, papel, envio_id)` em `assinatura` e índice em `envio(codigo)`; assine dentro de **transação** verificando status `aberto` e ausência da assinatura do papel.

Em Django, `USE_TZ=True` guarda em UTC; para o carimbo converta para `America/Sao_Paulo` na exibição (e no PDF). Evite `datetime.now()` ingênuo.

## 3. Trava de login × página pública

Se o sistema tem um "portão" de login antes de qualquer rota, a verificação pública precisa ficar **do lado de fora do portão**:

- **Streamlit:** no estado deslogado, chame `st.navigation([pagina_login, st.Page("publico/verificar.py", url_path="verificar")], position="hidden")`; a página pública esconde a sidebar e lê o contexto de `st.session_state`.
- **Django:** view sem `login_required`, fora do middleware de autenticação obrigatória.
- **SPA + API:** endpoint `GET /api/verificar?codigo=` público (rate limit!) e rota de front pública.
- Evite redirecionar para o login perdendo o `?codigo=`.

Acrescente **rate limit** (ex.: 30 consultas/min/IP) na rota pública se a stack permitir.

## 4. Roteiro de adaptação

1. Descobrir a stack, onde ficam usuários/permissões/notificações/PDF hoje (leia o código antes).
2. Fechar o desenho com as perguntas do SKILL.md.
3. Criar as tabelas/classes e migração (colunas por nome, padrões vazios).
4. Implementar o núcleo de domínio e **portar os testes** de `assets/referencia-sisescala/tests/` primeiro.
5. Snapshot + hash + renderização do PDF; conferir visualmente.
6. Telas: responsável → assinar → verificação (logada) → verificação pública + QR.
7. Notificações, contador, filtros.
8. Fuso, URL-base, segredos por variável de ambiente; documentação curta no README.
9. Testar ponta a ponta no navegador com contas reais de teste; listar o que não foi testado.

## 5. Perguntas de descoberta do projeto do usuário

- Que documentos serão assinados e por quem? Há ordem obrigatória? Quantos papéis?
- Já existe cadastro de usuários e senha? Perfis? Onde ficam as permissões?
- Existe sistema de notificações/e-mail?
- Como o PDF é gerado hoje (ou será)? Há modelo oficial/cabeçalho/brasão?
- O documento muda depois de pronto (dados vivos) ou já nasce fixo?
- Onde roda (nuvem, servidor da organização)? Qual o fuso? Há URL pública estável para o QR?
- Qual o nível de exigência jurídica? Algum requisito de retenção/auditoria?
- O que pode aparecer sem login na verificação?

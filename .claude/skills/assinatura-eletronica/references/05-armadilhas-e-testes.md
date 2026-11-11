# Armadilhas reais e testes

## Conteúdo
1. Bugs que realmente aconteceram (e a correção)
2. Lista de testes que valem a pena
3. Conferência visual e no navegador
4. Outras lições de implantação

## 1. Bugs que realmente aconteceram

| # | Sintoma | Causa | Correção |
|---|---|---|---|
| 1 | Cancelei o envio, reenviei e o sistema dizia "já assinei" | Assinatura ligada ao **código** do conteúdo; o novo envio tinha o mesmo código | Assinatura ligada ao **envio** (`doc_id`) |
| 2 | Mesmo após a correção #1, o bug continuou para o usuário | Assinaturas **antigas** (sem `doc_id`) ainda casavam com o envio aberto de mesmo código | Regra de dados antigos: pertencem ao último envio que já existia quando foram feitas |
| 3 | QR code abria "página não encontrada"/login | A trava de login cobria a rota `/verificar` | Página pública registrada na navegação deslogada; mostra só o essencial |
| 4 | Horário da assinatura 3 h adiantado | Servidor em UTC | Fixar `TZ` do processo; "(Brasília)" no carimbo; "hoje" também errava depois das 21h |
| 5 | Carimbo mostrava posto, especialidade e nome de guerra | Usava o rótulo militar | Usar o **nome completo da conta** (maiúsculas, fonte pequena) |
| 6 | Título "Recomendações" sozinho no pé da página, texto na folha seguinte | Quebra de página de fluxo | `CondPageBreak(26 mm)` antes de cada título; teste varrendo tamanhos de texto |
| 7 | Título "DETALHE DE SERVIÇO DE DETALHE DE SERVIÇO…" | Prefixo fixo + nome da escala já com o prefixo | Função `titulo_detalhe` que não repete |
| 8 | Brasão não carregava | Imagens complexas estouravam o limite de célula; seletor só mostrava PNG/JPG | Reduzir/recodificar (JPEG p/ opaco, PNG paleta p/ transparente), mais formatos, mensagens claras |
| 9 | Objeto "preso" desatualizado depois de editar | `dataclasses.replace` cria outro objeto; quem segurava o antigo via dados velhos | Editar **no próprio objeto** (`setattr`) ou sempre reler por id |
| 10 | Botão do PDF "não aparecia" para o usuário | O **deploy** apontava para a branch padrão do GitHub (atrasada), não para `main` | Conferir a branch de deploy; reiniciar o app |
| 11 | Detalhista "não sai da lista" na tela de gerenciar | Confusão entre **conta** responsável (não se remove) e **vínculo opcional** com um militar da lista | Rótulos e legendas distinguindo os dois conceitos |
| 12 | Detalhista não conseguia vincular a si mesmo (pedido sem quem aprovar) | Regra "ninguém decide o próprio vínculo" + detalhista fora da lista | Pedido do detalhista nasce aprovado; reaproveitar o PIN da conta |
| 13 | Testes quebraram ao deixar o nome em maiúsculas no carimbo | Asserções com a caixa antiga | Asserir com a mesma caixa impressa |
| 14 | Teste de "PDF tem imagem" por tamanho do arquivo falhou | JPEG de cor sólida é minúsculo | Contar objetos `/Subtype /Image` no PDF |

## 2. Lista de testes que valem a pena

**Domínio (sem UI), com contas de teste e PIN conhecido:**
- Papéis de cada conta; só o responsável designa; designar conta sem PIN falha.
- Envio avisa as autoridades (menos quem enviou); mesmo conteúdo não duplica; versão nova **substitui** a aberta; só o responsável envia.
- Cada autoridade vê o que falta; PIN errado falha; papel que não é dela falha; **assinar 2× o mesmo papel falha**; PDF parcial só com as que assinaram; com todas, 4 carimbos.
- **Cancelar → reenviar o mesmo conteúdo → zero assinaturas, novo ciclo** (inclusive com assinaturas "antigas" sem `doc_id`).
- Rejeitar: sem motivo/curto falha; sem papel falha; quem enviou falha; efeito (status, quem, motivo, data); **notificação ao responsável contém o motivo**; ninguém mais assina; persiste.
- Persistência: gravar → recarregar → mesmas assinaturas, mesmo código, `integra` verdadeiro; registro adulterado → `integra` falso.
- Verificação: código inteiro, prefixo, maiúsculas, `SISESCALA-VERIFICAR:<código>` e URL completa; prefixo curto não acha; consulta pública exige mais caracteres; aviso quando envio encerrado.
- PIN: admin apaga; só admin; notifica; sem PIN não assina; novo PIN exige a senha da conta.
- Fuso: `time.timezone == 3*3600` após subir o app.

**PDF:** texto extraído contém título, nomes (na caixa impressa), "(Brasília)", código; ordem cabeçalho (MARINHA DO BRASIL → OM → título); título não repetido; vários dias; nenhuma página termina em título de seção (varrer tamanhos); com 1 assinatura QR ao lado (confira visualmente).

**App (AppTest ou equivalente):** abrir todas as páginas sem exceção; fluxo "enviar → autoridade entra → assina → responsável vê 1 de 4"; rejeitar pela tela (botão desabilitado sem motivo); página pública **deslogada** autêntica e **sem NIP** no HTML.

## 3. Conferência visual e no navegador

- Gere o PDF e **renderize para PNG** (`pdftoppm -r 80`) e olhe: cabeçalho, quebra de página, carimbo, QR, grade de assinaturas (nome mais longo que a coluna?).
- Suba o app e use Playwright/Chromium para: login, enviar, assinar, abrir a página pública sem login, enviar arquivo de imagem, filtrar. Teste pelo menos um caminho feliz real — testes unitários não mostram layout nem trava de login.
- Seed de dados num arquivo/ planilha de teste para reproduzir estados (assinado, rejeitado, cancelado).

## 4. Outras lições de implantação

- Declare ao usuário **o que não foi testado com dados reais**.
- Para cada mudança de dados (colunas novas) garanta leitura por nome de coluna e padrões vazios.
- Notificação + contador no menu são o que faz o fluxo "andar" — não deixe para depois.
- Documente variáveis: URL-base do QR (`APP_URL`), fuso (`APP_TZ`), segredos (planilha, admin).
- Peça sempre o nome **completo** e a matrícula corretos nas contas: eles vão impressos.

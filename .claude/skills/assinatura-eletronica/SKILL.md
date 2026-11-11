---
name: assinatura-eletronica
description: >-
  Implementa assinatura eletrônica com PIN, fluxo de assinatura por várias autoridades, PDF assinado com carimbo, QR code e verificação pública de autenticidade em qualquer sistema (Streamlit/Python, Django, Flask, Node, Sheets/SQL). Use SEMPRE que o usuário quiser colocar assinatura eletrônica, assinar documentos dentro de um sistema, fluxo de aprovação ou assinatura por várias pessoas (detalhista, auxiliar, encarregado, vice-diretor, chefe, comandante), enviar documento para assinatura, rejeitar ou cancelar assinatura, carimbo de assinatura no PDF, código de verificação (hash SHA-256), QR code de autenticidade, página pública para conferir documento, reset de PIN, ou pedir para fazer como no SisEscala. Também use ao revisar um fluxo de assinatura existente, mesmo que o usuário não diga assinatura eletrônica, por exemplo quando disser que o chefe precisa assinar o relatório no sistema ou que quer validar se um documento é verdadeiro.
---

# Assinatura eletrônica em sistemas internos

Esta skill reúne o que foi construído e **aprendido com erros reais** no SisEscala (detalhe de serviço da Marinha) para colocar assinatura eletrônica em qualquer sistema: um **documento congelado**, **assinado com PIN por várias autoridades**, **PDF com carimbo + QR code** e **verificação pública** de autenticidade.

Há uma implementação de referência funcionando e testada em `assets/referencia-sisescala/` (Python/Streamlit; 280+ testes). Use-a como modelo de lógica e de testes; adapte nomes, persistência e telas à stack do usuário. Os detalhes vivem em `references/` — leia o arquivo indicado quando chegar na etapa.

## Primeiro: alinhe o nível jurídico (não pule)

O que esta skill entrega é **assinatura eletrônica simples** (Lei 14.063/2020): a pessoa se autentica na conta e confirma com um PIN, e o sistema registra quem, quando e o quê. É adequada para documentos **internos e administrativos** de baixo/médio risco. **Não é** assinatura ICP-Brasil (qualificada) nem gov.br avançada; não use como substituto onde a norma exige certificado digital. Diga isso ao usuário e, se o documento tiver valor externo/contratual, sugira validar com o jurídico e considerar ICP-Brasil/gov.br. Veja `references/04-seguranca-verificacao-lgpd.md` (inclui as limitações do hash e os reforços possíveis).

## Perguntas que definem o desenho (faça antes de codar)

Agrupe e pergunte só o que o usuário ainda não respondeu; proponha o padrão entre parênteses.

1. **Quem assina?** Quantos papéis, quais, e se a ordem importa (padrão: papéis fixos, qualquer ordem, todos independentes).
2. **Quem monta/envia o documento?** (o "responsável"; só ele envia e cancela.)
3. **Como as autoridades entram no sistema?** Têm conta? (padrão: contas designadas pelo responsável, com PIN cadastrado.)
4. **Autenticação da assinatura:** PIN de 4–6 dígitos além do login (padrão), senha de novo, ou outro (gov.br/certificado → fora do escopo desta skill).
5. **O documento pode ser baixado com assinaturas parciais?** (padrão: sim, 1 a N; senha-completo só quando todos assinaram.)
6. **Rejeição:** quem rejeita, justificativa obrigatória, o que acontece (padrão: qualquer autoridade menos quem enviou; motivo ≥ 5 caracteres; encerra o envio e avisa o responsável).
7. **Verificação pública:** pode abrir sem login? O que mostrar? (padrão: sim, só essencial e sem dados pessoais sensíveis.)
8. **Onde guardar?** Banco SQL, planilha (Google Sheets tem limite de 50 mil caracteres por célula), arquivo.
9. **Fuso horário e formato de data** (o servidor costuma estar em UTC — veja armadilhas).
10. **Perda de PIN:** como a pessoa recupera (padrão: ela mesma, com a senha; se perdeu a senha, o administrador *apaga* o PIN, nunca define).

## Arquitetura em uma página

```
Responsável monta o documento
        │  "Enviar para assinatura"
        ▼
SNAPSHOT congelado (JSON canônico com TUDO que o PDF mostra) ──► código = SHA-256(JSON)
        │   registro DetalheDoc/Envio {id, código, conteúdo(zlib+base64), status}
        ▼
Aviso (notificação) a cada autoridade ──► menu "Assinar documentos (n)"
        │
Cada autoridade: confere o conteúdo ─► assina com PIN (papel X) ─► registro Assinatura{envio_id, papel, usuário, nome, data, conteúdo}
        │                      └──► ou REJEITA (motivo obrigatório) ─► envio "rejeitado" + aviso ao responsável
        ▼
PDF (sem assinatura OU com as assinaturas já feitas) = renderizar(snapshot, carimbos) + QR + código
        ▼
Qualquer pessoa lê o QR ─► página PÚBLICA /verificar?codigo=… ─► "Assinatura autêntica" + quem/quando (+ aviso se cancelado/rejeitado/substituído)
```

Máquina de estados do envio: `aberto → {cancelado | rejeitado | substituido}`. "Concluído" não é status: é "aberto com todas as assinaturas". Detalhes e telas em `references/01-fluxo-de-trabalho.md`.

## As 8 regras que tornam isso confiável (e por quê)

1. **Assine o conteúdo congelado, nunca os dados vivos.** O que as pessoas assinam precisa ser exatamente o que ficou impresso; se o documento é refeito a partir de dados que mudam, o código deixa de bater e a verificação mente. Congele num *snapshot* já resolvido em texto (nomes, siglas, horários, observações).
2. **O código é o SHA-256 de um JSON canônico** (`sort_keys=True`, `ensure_ascii=False`, sem campos que mudam sozinhos como "gerado em"). Guarde o JSON junto da assinatura (compactado) para a verificação reler e recalcular.
3. **Cada assinatura pertence a um ENVIO (`envio_id`), não ao código do conteúdo.** Esse foi o bug mais caro: com a assinatura ligada só ao código, cancelar e reenviar o mesmo conteúdo "ressuscitava" as assinaturas antigas. Reenviou? Todo mundo assina de novo, com ou sem mudança.
4. **Dados antigos exigem migração em tempo de leitura.** Assinaturas gravadas antes de existir `envio_id` pertencem ao último envio daquele conteúdo que já existia quando foram feitas (comparação por data), nunca ao seguinte.
5. **Papéis vêm do documento, não da pessoa.** Uma conta pode ter vários papéis (OM pequena); cada papel assina uma vez. Quem não tem papel não assina nem rejeita; quem enviou cancela (não "rejeita").
6. **PIN: só hash (bcrypt), bloqueio por tentativas, e o administrador nunca o define** — apenas apaga; quem escolhe o novo é o dono, confirmando com a senha da conta.
7. **Rejeição exige justificativa e avisa o responsável** (a notificação traz o motivo). Sem motivo, sem rejeição.
8. **Horário é o do local, não o do servidor** (Brasília). Fixe o fuso do processo; carimbo e notificações usam o mesmo relógio. E mostre o fuso no carimbo ("(Brasília)").

## Receita de implementação (ordem sugerida)

1. **Modelo de dados** (`references/02-modelo-de-dados.md`): envio, assinatura, designação de papéis, notificação, campos de PIN no usuário. Planeje migração e o limite de célula se usar planilha.
2. **Núcleo de domínio sem UI** (copie a lógica de `assets/referencia-sisescala/assinaturas.py` e `verificacao.py`): `enviar`, `assinar`, `rejeitar`, `cancelar`, `para_assinar`, `assinaturas_do(envio)`, `faltam`, `papeis_do_usuario`, `designar`. **Teste cada regra antes de fazer tela** (veja `assets/referencia-sisescala/tests/`).
3. **Snapshot + hash + PDF** (`references/03-conteudo-hash-pdf.md`, `assets/referencia-sisescala/pdf.py`): `montar_snapshot`, `codigo_do_corpo`, `renderizar_pdf(snapshot, carimbos)`. O PDF deve ser **refeito só do snapshot** — isso permite baixar a qualquer momento idêntico e parcial.
4. **PIN** (`assets/referencia-sisescala/pin.py`): cadastro/alteração com senha, confirmação na assinatura com bloqueio, reset pelo admin que apaga.
5. **Telas:** (a) página do responsável (montar, designar, enviar, status, cancelar, baixar); (b) **"Assinar documentos"** com filtros, conferir conteúdo, assinar, rejeitar (`assets/referencia-sisescala/pagina_assinar.py`); (c) **verificação** logada (completa) e **pública** (essencial) (`tela_verificacao.py`, `pagina_publica_verificar.py`).
6. **QR e verificação pública** (`references/04-…`): URL `…/verificar?codigo=<sha256>`; se há login global, registre a página pública **fora** da trava de login.
7. **Notificações e contador no menu** (envio → autoridades; assinatura/rejeição → responsável).
8. **Testes e conferência visual** (`references/05-armadilhas-e-testes.md`): rode o app de verdade, gere o PDF, olhe o PDF renderizado (PNG) e o QR.

## Detalhes de PDF que fazem diferença (resumo)

- Cabeçalho oficial centralizado e em negrito; brasão por escala com padrão; paleta institucional.
- Assinaturas em grade: N autoridades por linha e a última centralizada abaixo; carimbo com **nome completo (maiúsculas, fonte bem pequena), NIP/matrícula, data/hora e fuso**.
- **Com uma só assinatura o QR fica ao lado do carimbo; com várias, abaixo, junto do código.**
- Título de seção nunca sozinho no pé da página (`CondPageBreak`), bloco de assinaturas em `KeepTogether`.
- Textos longos (instruções/regras) em fonte pequena; editor de texto rico → HTML higienizado (b, i, u, listas) convertido para o PDF (`textorico.py`).

## Ao entregar ao usuário

- Diga o nível jurídico (simples) e as limitações (referência 04).
- Entregue o fluxo explicado em linguagem de quem usa (quem envia, quem assina, onde vê pendências, como cancelar/rejeitar, como verificar).
- Liste o que **não** foi testado com dados reais.
- Se o usuário usa hospedagem com deploy por branch, confirme que o deploy aponta para a branch certa (um erro recorrente: o recurso existe na `main` mas o app publicado lê outra branch).

## Mapa dos arquivos

| Arquivo | Quando ler |
|---|---|
| `references/01-fluxo-de-trabalho.md` | Papéis, estados, telas, notificações, filtros, cancelar × rejeitar × substituir |
| `references/02-modelo-de-dados.md` | Tabelas/campos, migração de dados antigos, limite de célula, compactação |
| `references/03-conteudo-hash-pdf.md` | Snapshot, JSON canônico, hash, carimbo, QR, paginação, texto rico |
| `references/04-seguranca-verificacao-lgpd.md` | PIN, reset, verificação pública, LGPD, nível jurídico, reforços (HMAC, carimbo de tempo) |
| `references/05-armadilhas-e-testes.md` | Lista dos bugs reais, checklist de testes, conferência visual |
| `references/06-adaptando-a-outra-stack.md` | Mapeamento para Django/Flask/Node/SQL e trava de login |
| `assets/referencia-sisescala/` | Código real: `assinaturas.py`, `verificacao.py`, `pdf.py`, `pin.py`, telas e testes |

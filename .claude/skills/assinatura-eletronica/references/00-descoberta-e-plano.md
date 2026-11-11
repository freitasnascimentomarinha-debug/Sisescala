# Fase 0 — Entender o sistema, propor o plano e aguardar aprovação

## Conteúdo
1. Regra de ouro
2. Mapa do sistema: o que investigar (e como)
3. Princípios para a solução ficar fácil e intuitiva
4. Como escolher a melhor solução (decisões com alternativas)
5. Modelo do plano (preencha e apresente)
6. Portão de aprovação
7. Depois da aprovação
8. Exemplo condensado de plano (do SisEscala)

## 1. Regra de ouro

**Não escreva nem altere código antes de (a) entender o sistema de verdade, (b) apresentar um plano detalhado e (c) receber aprovação explícita.** Por quê: assinatura eletrônica mexe em autenticação, dados pessoais, documentos com valor administrativo e no fluxo de trabalho de pessoas reais. Um desenho errado (papéis, quem envia, o que se assina, o que aparece publicamente) custa caro para desfazer — como mostrou o bug das assinaturas que "voltavam" depois de cancelar. O plano é onde essas decisões são baratas.

Se o usuário disser "faz logo", ainda assim apresente um plano **curto** (1 tela) com as decisões que mudam o resultado e peça um "ok".

## 2. Mapa do sistema: o que investigar (e como)

Leia o código antes de perguntar ao usuário; só pergunte o que o código não responde. Use busca e leitura (Glob/Grep/Read; um agente de exploração em sistemas grandes) e produza um **resumo com referências a arquivos**.

| Área | O que descobrir | Onde olhar |
|---|---|---|
| Stack e entrada | Linguagem, framework, como roda e é publicado, branch de deploy | `README`, `requirements`/`package.json`, arquivo principal, CI/deploy |
| Usuários e acesso | Cadastro, login, senha, perfis/permissões, "quem é dono de quê" | módulos de auth/permissões, modelos de usuário |
| Dados | Banco, planilha, arquivos; como grava, versão/concorrência, migração; limites (ex.: célula) | camada de persistência, esquema |
| Documentos | Quais documentos existem, como o PDF é gerado hoje (ou DOCX/HTML), cabeçalho/brasão/identidade visual | geradores de PDF/relatório |
| Fluxo atual | Quem prepara, quem aprova hoje (papel, e-mail, WhatsApp?), gargalos | conversa com o usuário + telas existentes |
| Navegação/UI | Menu, padrões de tela, componentes, tema, idioma, contadores/chips | arquivo de navegação, módulo de UI/CSS |
| Notificações | Existe aviso interno/e-mail? contador no menu? | módulo de notificações |
| Ambiente | Fuso horário, URL pública estável (para QR), variáveis/segredos | config de deploy |
| Qualidade | Testes existentes, estilo, convenções de nome, como rodar | `tests/`, configuração de lint |
| Restrições | Normas internas, LGPD, retenção, exigência de certificado | usuário/jurídico |

Fechar o mapa com uma lista **"o que já existe e posso reaproveitar"** (usuários, permissões, notificações, gerador de PDF, tema) e **"o que falta construir"**. Reaproveitar reduz risco e dá consistência visual.

Se o sistema ainda não existe (projeto novo), o mapa vira "stack recomendada" com justificativa curta.

## 3. Princípios para a solução ficar fácil e intuitiva

Quem assina é, em geral, uma autoridade ocupada. O desenho vence se ela não precisar aprender nada:

1. **O pendente vem até a pessoa:** contador no menu ("Assinar documentos (2)") + notificação ao enviar; a lista abre já filtrada em "Aguardando minha assinatura".
2. **Ver antes de assinar, na mesma tela:** o conteúdo conferível (tabela + textos) a um clique, sem navegar por outras páginas nem exigir acesso à origem.
3. **Um botão principal, com nome claro:** "Assinar como Encarregado do Detalhe"; o PIN é um campo ao lado, não outra etapa. Botão desabilitado com motivo visível quando algo falta (sem PIN, sem justificativa).
4. **Linguagem do usuário**, nos termos da organização (detalhista, encarregado…), nunca "hash/snapshot/token" na tela; o código SHA-256 só no rodapé do PDF e na verificação.
5. **Status sempre visível:** chips "✓ assinou / pendente", faixa vermelha com o motivo quando rejeitado, aviso quando o documento mudou e precisa reenviar.
6. **Consequências explicadas onde importam:** "Rejeitar encerra o envio e o detalhista recebe o seu motivo"; "Qualquer mudança exige nova assinatura".
7. **Poucos cliques para quem envia:** designar assinantes uma vez e **lembrar** (campos salvos no documento/escala); "Enviar" com um clique; reenvio simples.
8. **Parcial é permitido e explícito:** "PDF com as assinaturas já feitas (2 de 4)".
9. **Recuperação sem fricção:** esqueci o PIN → "informe a senha e escolha outro"; só se perdeu a senha, o administrador apaga o PIN.
10. **Verificação sem atrito:** ler o QR e ver "Assinatura autêntica" em segundos, sem login, sem dado pessoal sensível.
11. **Mesmo visual do sistema** (tema, componentes, ícones) e funcionamento no celular (a autoridade pode assinar do telefone).
12. **Erros acionáveis:** "PIN incorreto (2 de 5 tentativas)", "Cadastre o seu PIN em Minha conta" com link.

Teste mentalmente cada papel: *responsável* (monta e envia), *autoridade* (assina/rejeita), *administrador* (reset de PIN), *terceiro* (confere o QR).

## 4. Como escolher a melhor solução (decisões com alternativas)

Para cada decisão relevante, apresente **2–3 alternativas com prós/contras e uma recomendação**. Decisões típicas:

| Decisão | Alternativas | Recomendação padrão |
|---|---|---|
| Nível de assinatura | PIN no sistema · senha · gov.br · ICP-Brasil | PIN + login (simples) para uso interno; ICP/gov.br se houver exigência externa |
| Onde assina | Dentro do próprio documento · página "Assinar documentos" | Página dedicada com contador (menos cliques, funciona para qualquer origem) |
| O que se assina | Dados vivos · conteúdo congelado | Congelado (snapshot) — sempre |
| Ordem das assinaturas | Livre · sequencial | Livre (menos fricção); sequencial só se a norma exigir |
| Download parcial | Só completo · parcial permitido | Parcial permitido, com rótulo "n de N" |
| Verificação | Só logado · pública essencial · pública completa | Pública essencial (sem dados pessoais) + logada completa |
| Reforço antifraude | Hash · HMAC com segredo · timestamp externo | Hash agora; HMAC se houver exigência de não repúdio |
| Armazenamento | Banco · planilha · arquivos | O que o sistema já usa (respeitando limites) |
| Notificação | Interna · e-mail · push | Interna + contador; e-mail se já existir infraestrutura |

## 5. Modelo do plano (preencha e apresente)

Apresente em português, claro, com tabelas curtas. Não despeje código. Seções:

1. **O que entendi do sistema** (5–10 linhas + arquivos-chave; o que reaproveito; o que falta).
2. **Objetivo e quem usa** (papéis, volume, exigência jurídica).
3. **Como vai funcionar para o usuário** (passo a passo por papel + esboço das telas em texto/tabela; o caminho feliz, rejeição, cancelamento, esqueci o PIN, verificação por QR).
4. **Decisões e alternativas** (tabela da §4 já com a recomendação e o motivo).
5. **Mudanças técnicas** (módulos/arquivos novos e alterados; modelo de dados e migração; PDF/QR; notificações; rotas públicas; variáveis de ambiente).
6. **Segurança, LGPD e jurídico** (nível entregue, limitações, o que aparece publicamente).
7. **Riscos e mitigação** (dados antigos, concorrência, fuso, deploy em branch errada, limites de célula…).
8. **Testes e critérios de aceite** (lista objetiva: "reenviar após cancelar exige assinar de novo", "página pública sem NIP", etc.).
9. **Entregas em fases** (ex.: F1 núcleo+PIN · F2 telas+notificações · F3 PDF/QR/verificação · F4 reforços), cada uma demonstrável, com esforço relativo (P/M/G) e o que muda para o usuário.
10. **Fora do escopo** (o que NÃO será feito agora).
11. **Perguntas em aberto** (só as que realmente mudam o desenho; marque a resposta padrão).

## 6. Portão de aprovação

- Termine o plano com uma pergunta objetiva: **"Posso executar este plano? (sim / ajustar X)"**.
- Para decisões com poucas opções, use a ferramenta de perguntas (múltipla escolha, até 4 por vez) com a **opção recomendada primeiro**. Se o ambiente tiver modo de planejamento, use o mecanismo dele para pedir a aprovação.
- **Pare e aguarde.** Aprovação vale para o plano apresentado; se o usuário pedir ajustes, **revise o plano** e peça de novo. Mudanças grandes de escopo durante a execução voltam ao portão.
- Aprovação de uma fase não é aprovação das seguintes, se houver decisão nova nelas.

## 7. Depois da aprovação

1. Execute **por fases**, na ordem do plano, com testes de domínio antes das telas.
2. Ao fim de cada fase: rode os testes, **abra o sistema de verdade** (navegador) e confira o caminho feliz; mostre ao usuário o que mudou, em linguagem dele.
3. Declare o que **não foi** testado com dados reais.
4. Respeite o fluxo de entrega do usuário (branch, PR, merge, deploy) e confirme que o deploy aponta para a branch certa.
5. Atualize a documentação curta (README: variáveis de ambiente, como assinar, como verificar).

## 8. Exemplo condensado de plano (SisEscala)

> **1. O que entendi:** Streamlit + planilha Google; contas com NIP/senha/PIN; escalas com detalhista (dono) e auxiliares; PDF do "detalhe de serviço" com reportlab; notificações internas e menu com contadores. Reaproveito: contas, PIN, notificações, tema, gerador de PDF. Falta: envio congelado, assinatura por papel, verificação.
> **3. Para o usuário:** o detalhista monta o documento → *Enviar para assinatura* → as 3 autoridades recebem aviso e veem "Assinar documentos (1)" → conferem, digitam o PIN e assinam (ou rejeitam com motivo) → o detalhista baixa o PDF com as assinaturas já feitas a qualquer momento → qualquer pessoa lê o QR e confere em segundos, sem login.
> **4. Decisões:** assinatura simples com PIN (recomendado) × ICP-Brasil (se exigir); congelar conteúdo (sim); ordem livre; download parcial; verificação pública essencial + logada completa.
> **5. Técnico:** novas entidades Envio/Assinatura (aba na planilha, conteúdo zlib+base64 por causa do limite de 50 mil caracteres); `assinaturas.py`, `verificacao.py`; PDF refeito do snapshot; rota pública `/verificar`.
> **8. Aceite:** reenviar após cancelar exige assinar de novo; rejeição sem motivo impossível; verificação pública sem NIP; horário de Brasília.
> **9. Fases:** F1 núcleo+testes · F2 telas+notificações · F3 PDF/QR/verificação · F4 documento unificado.
> **Pergunta:** "Posso executar? Posso incluir o HMAC já na F3?"

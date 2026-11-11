# Fluxo de trabalho da assinatura (papéis, estados, telas)

## Conteúdo
1. Papéis
2. Ciclo de vida do envio
3. Quem pode o quê
4. Telas
5. Notificações
6. Filtros da página "Assinar documentos"
7. Cancelar × Rejeitar × Substituir
8. Documento unificado (várias escalas/seções num só documento)

## 1. Papéis

No SisEscala são quatro autoridades, em ordem de impressão: **Detalhista**, **Auxiliar do Detalhista**, **Encarregado do Detalhe**, **Vice-Diretor**. Adapte nomes/quantidade; o desenho é o mesmo para N papéis.

- **Responsável (detalhista):** quem cria/é dono do documento. Monta, designa, **envia**, **cancela**. É também um dos assinantes.
- **Papéis designados por conta:** o responsável indica *contas* (usuários do sistema) para os demais papéis (campos `*_usuario_id` na escala ou no documento). Só se pode designar quem **já tem PIN** — falhar cedo evita um envio que ninguém consegue assinar.
- **Um usuário pode ter mais de um papel** (OM pequena). Ele escolhe "Assinar como…" e assina **uma vez por papel**.
- Papéis são resolvidos **a partir do documento/escala atual**, não gravados no usuário.

## 2. Ciclo de vida do envio

```
(montando)  ──Enviar──►  aberto ──┬─ todas as assinaturas ─► "concluído" (derivado, continua aberto)
                                   ├─ Cancelar (responsável) ──► cancelado
                                   ├─ Rejeitar (autoridade, motivo) ──► rejeitado
                                   └─ novo envio do mesmo período ──► substituido
```

- **Enviar** congela o conteúdo (snapshot) e cria o registro do envio. Mesmo conteúdo já enviado e aberto → não duplica (devolve o existente). Conteúdo diferente para o **mesmo período** → marca os abertos anteriores como `substituido`.
- **Assinar** só em envio `aberto`, no papel que a conta tem, uma vez por papel, com PIN correto.
- **PDF parcial é permitido:** "PDF com as assinaturas já feitas (n de 4)" pode ser baixado a qualquer momento; "PDF sem assinatura" sempre existe. Quem não assinou fica com a linha em branco (assina à mão, se quiser).
- Depois de **cancelar/rejeitar**, reenviar (igual ou alterado) **começa sem assinaturas**.

## 3. Quem pode o quê

| Ação | Quem | Regra |
|---|---|---|
| Montar/editar/designar | responsável | só ele |
| Enviar | responsável | exige permissão de decidir |
| Cancelar envio | responsável | só enquanto aberto |
| Assinar | conta com o papel | PIN; 1× por papel; envio aberto |
| Rejeitar | conta com papel, **exceto quem enviou** | motivo obrigatório (≥5 caracteres) |
| Ver/conferir conteúdo antes de assinar | quem tem papel | pela página de assinatura (não precisa acesso à escala/origem) |

Quem envia usa "Cancelar envio" (não "rejeitar"): a separação evita que o responsável rejeite o que ele mesmo mandou.

## 4. Telas

1. **Página do responsável** (no SisEscala: *Detalhe de serviço* e *Detalhe unificado*): editor do documento, "Quem assina" (selects de contas), **Enviar para assinatura**, status por papel (chips verde ✓ / âmbar pendente), downloads (sem assinatura / com as já feitas), **Cancelar este envio**, aviso quando o conteúdo mudou depois do último envio ("envie de novo"), e **faixa vermelha com o motivo** quando uma autoridade rejeitou.
2. **Assinar documentos** (autoridade): lista dos envios em que tem papel; por cartão: título, quem enviou/quando, chips de assinaturas, *Conferir o conteúdo*, downloads, campo **Seu PIN** + botão **Assinar como …**, popover **Rejeitar este documento** (texto obrigatório; botão só habilita com motivo).
3. **Verificar documento**: logado (completo) e público (essencial) — ver referência 04.
4. **Minha conta**: cadastrar/alterar PIN com a senha da conta.
5. **Administração de usuários**: "Redefinir PIN (esqueceu)" → apaga.

Mostre ao lado do menu um **contador** ("Assinar documentos (2)") calculado a partir de `para_assinar(usuario)`.

## 5. Notificações

- Ao **enviar**: todas as contas com papel no documento, exceto quem enviou. Texto com título, período e "Abra Documentos → Assinar documentos".
- Ao **assinar**: o responsável é avisado ("<Papel> <Nome> assinou …").
- Ao **rejeitar**: o responsável recebe "<Papel> <Nome> REJEITOU … Motivo: …".
- Reset de PIN: a pessoa é avisada de que o PIN foi apagado e deve cadastrar outro.

Reaproveite o mecanismo de notificações do sistema (tipo "assinatura"/"conta"); se não existir, o mínimo é uma tabela `notificacao(usuario, texto, lida, data)` + badge no menu.

## 6. Filtros da página "Assinar documentos"

Segmentado **Mostrar**: *Aguardando minha assinatura* (padrão quando há pendência) · *Assinados por mim* · *Com as N assinaturas* · *Cancelados / rejeitados* · *Todos*; seletor **Escala/documento**; **Busca** por título, data (15/11) ou motivo. Mostre "x de y documento(s)". Documentos encerrados ficam só no histórico (sem botão de assinar/rejeitar), com faixa explicando o motivo.

Cuidado de layout: o controle segmentado com 5 opções precisa de linha inteira (não cabe numa coluna estreita).

## 7. Cancelar × Rejeitar × Substituir

- **Cancelar:** decisão do responsável ("errei, retiro o envio"). Registra `encerrado_por`/`encerrado_em`. Some de "aguardando" para todos.
- **Rejeitar:** decisão de uma autoridade com **motivo**. Registra `motivo`, `encerrado_por`, `encerrado_em`; avisa o responsável; a página dele mostra o motivo até ele enviar de novo.
- **Substituído:** automático, quando o responsável envia uma versão diferente para o mesmo período.
- Em todos: as assinaturas do envio encerrado **ficam como histórico**, mas não valem; a verificação por QR de um documento desses mostra um **aviso** ("envio cancelado/rejeitado/substituído em …").

## 8. Documento unificado (várias seções/escalas)

Quando um mesmo documento reúne várias origens (fiscal, sentinela, contramestre…), trate-o como **outra "fonte"** do mesmo fluxo: o envio guarda `origem_id` **ou** `documento_id`; a função `papeis_do_usuario(fonte)` e `enviar(fonte)` aceitam os dois tipos. O snapshot passa a ter `secoes` (uma por origem) e textos gerais; o renderizador mantém compatibilidade com snapshots antigos (de uma origem só). Num dia só, uma tabela com uma linha por origem; em vários dias, uma tabela por origem.

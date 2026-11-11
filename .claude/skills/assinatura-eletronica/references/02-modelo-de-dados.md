# Modelo de dados

## Conteúdo
1. Entidades
2. Campos no usuário (PIN)
3. Designação de papéis
4. Migração de dados antigos
5. Persistência em planilha (Google Sheets) e limites
6. Índices/consultas que o fluxo usa

## 1. Entidades

**Envio** (`DetalheDoc` no SisEscala) — uma versão congelada enviada para assinatura:

| Campo | Tipo | Observação |
|---|---|---|
| `id` | texto | sequencial `d1, d2…` |
| `codigo` | texto(64) | SHA-256 do JSON do snapshot |
| `origem_id` / `documento_id` | texto | escala **ou** documento unificado; um deles vazio |
| `inicio`, `fim` | data | período coberto |
| `enviado_por`, `enviado_em` | usuário, datetime | quem congelou e quando |
| `status` | texto | `aberto` \| `substituido` \| `cancelado` \| `rejeitado` |
| `conteudo` | texto | **snapshot compactado** (zlib + base64) |
| `encerrado_por`, `encerrado_em`, `motivo` | | preenchidos ao cancelar/rejeitar; `motivo` obrigatório na rejeição |

**Assinatura** (`AssinaturaDetalhe`) — uma por (envio, papel):

| Campo | Observação |
|---|---|
| `codigo` | SHA-256 do conteúdo (igual ao do envio) |
| `doc_id` | **id do envio** a que pertence (chave da regra 3 da skill) |
| `papel` | `detalhista` \| `auxiliar` \| `encarregado` \| `vice_diretor` |
| `usuario_id` | quem assinou |
| `nome`, `nip` | **nome completo** da conta e matrícula no momento da assinatura (cópia: o cadastro pode mudar depois) |
| `om` | organização, para exibir na verificação |
| `em` | datetime da assinatura (horário local) |
| `conteudo` | snapshot compactado (a assinatura se verifica sozinha) |
| `inicio`, `fim`, `escala_id` | conveniência para listagens |

Deduplicação: `(codigo, usuario_id, papel, doc_id)` é único — assinar duas vezes devolve a existente.

**Documento unificado** (opcional): `id, nome, dono_id, om, escala_ids[], textos gerais (3), nomes digitados (4), contas designadas (auxiliar/encarregado/vice), brasao_b64`.

## 2. Campos no usuário (PIN)

`pin_hash` (bcrypt; vazio = sem PIN), `tentativas` (int), `bloqueado_ate` (datetime|null). `nome` completo e `nip/matrícula` são usados no carimbo. Nunca guarde o PIN em claro nem o registre em log.

## 3. Designação de papéis

Campos de conta por papel no documento/escala: `auxiliar_usuario_id` (no unificado), `encarregado_usuario_id`, `vice_usuario_id`; o detalhista é o dono. Textos de nome impressos (`ass_detalhista`, …) são **separados** das contas: o nome impresso abaixo da linha pode ser digitado à mão ("CMG Fulano"), e o carimbo eletrônico usa o nome completo da conta.

## 4. Migração de dados antigos

Quando você acrescenta `doc_id` a um sistema que já tem assinaturas, os registros antigos ficam com `doc_id` vazio. **Não** os associe pelo código sozinho (isso fez as assinaturas "voltarem" após cancelar). Regra em tempo de leitura:

> Assinatura sem `doc_id` pertence ao **último envio com o mesmo código cuja `enviado_em` ≤ `em` da assinatura**.

(Implementação: `_dono_da_assinatura_antiga` em `assets/referencia-sisescala/assinaturas.py`.) Se preferir migrar os dados, faça uma passada única aplicando a mesma regra e grave o `doc_id`.

Colunas novas em planilhas antigas: leia **por nome de coluna** com padrão vazio (planilhas gravadas por versões anteriores continuam carregando).

## 5. Persistência em planilha (Google Sheets) e limites

- **Limite de 50.000 caracteres por célula** (aplique margem: ≤ 45.000). Por isso o snapshot é **zlib+base64** (`empacotar/desempacotar`); JSON de 30 dias com ~10 pessoas e textos longos cabe, mas puro pode estourar. O desempacotar aceita JSON puro (registros antigos).
- Imagens (brasão) também em base64 numa célula: reduza (≤ 320 px), use JPEG para imagens opacas e PNG (paleta) para as com transparência.
- Gravação por **abas alteradas** com controle de versão (conflito se outra pessoa gravou antes): mantenha esse padrão para não perder assinaturas em concorrência.
- Se usar SQL, as mesmas entidades viram tabelas; mantenha `conteudo` como `TEXT`/`BYTEA`.

## 6. Consultas que o fluxo usa

- `para_assinar(usuario)`: envios `aberto` em que o usuário tem papel e ainda não assinou nele.
- `todos_do_usuario(usuario)`: todos os envios (qualquer status) em que tem papel — alimenta os filtros.
- `assinaturas_do(envio)`: assinaturas daquele envio (por `doc_id` + regra de dados antigos).
- `faltam(envio)`: papéis sem assinatura.
- `vigente_do_codigo(codigo)`: envio mais recente com esse código (prefere o `aberto`; desempate por data e id) — usado pela verificação.
- `do_codigo(codigo)`: assinaturas com esse código (verificação).
- `encerrado_do_periodo(origem, dias)`: último envio rejeitado/cancelado do período (faixa vermelha do responsável).

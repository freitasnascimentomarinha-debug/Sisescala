# Segurança, verificação pública, LGPD e nível jurídico

## Conteúdo
1. Nível jurídico
2. PIN: ciclo de vida
3. Verificação: o que prova
4. Página pública (QR code) × página logada
5. LGPD e minimização de dados
6. Limitações e reforços possíveis
7. Checklist de segurança

## 1. Nível jurídico

A Lei 14.063/2020 distingue assinatura eletrônica **simples** (identifica o signatário e associa dados; é o que esta skill entrega: login + PIN + registro), **avançada** (vinculação única ao signatário, controle exclusivo, detecção de alteração — ex.: gov.br avançado) e **qualificada** (certificado ICP-Brasil). Para documentos internos e administrativos de baixo risco, a simples costuma ser aceita pela própria organização; **a norma interna/jurídico é quem decide**. Sempre diga ao usuário o nível entregue e quando procurar o jurídico (contratos, atos com efeito externo, exigência expressa de certificado).

## 2. PIN: ciclo de vida

- **Formato:** 4 a 6 dígitos numéricos. É um *segundo fator de intenção* ("confirmo que li e assino"), não substitui a senha de login.
- **Armazenamento:** só `bcrypt` (custo 12 em produção; testes usam menos); nunca em claro, nunca em log, nunca na notificação.
- **Cadastro/alteração:** em "Minha conta", **confirmando com a senha da conta** (mesma tela serve para "esqueci o PIN").
- **Confirmação na assinatura:** `confirmar_assinatura(usuario, pin)`; 5 erros seguidos bloqueiam por 5 minutos (`tentativas`, `bloqueado_ate`); sem PIN cadastrado → erro claro "cadastre o seu PIN".
- **Esqueceu o PIN:** (a) a própria pessoa define outro com a senha; (b) se perdeu também a senha, o **administrador apaga** o PIN (`redefinir_pin`): zera tentativas/bloqueio, **notifica** a pessoa e **nunca define nem vê** o PIN. Resultado: o administrador não consegue assinar em nome de ninguém. Até cadastrar outro, a pessoa não assina.
- Assinaturas já feitas **continuam valendo** depois do reset (o registro é histórico).
- **Designação exige PIN:** impeça designar conta sem PIN.
- Permissões: só administrador redefine; só o dono troca o próprio PIN (com a senha).

## 3. Verificação: o que prova

`buscar(codigo)` (inteiro ou prefixo) → registro; `integra(registro)` recalcula `sha256(desempacotar(conteudo)) == codigo`; `do_codigo` lista os signatários **do envio vigente**; se o envio está cancelado/rejeitado/substituído, mostre aviso em destaque (com data e, para usuários logados, o motivo).

O que a conferência prova: que **este sistema** emitiu aquele código, **quem** assinou, **quando**, e que o conteúdo gravado não foi alterado. Ela **não lê o arquivo PDF**: para saber se o papel em mãos é o mesmo, a pessoa compara com o conteúdo mostrado (logado) — deixe isso claro na tela. (Reforço opcional: aceitar upload do PDF e extrair o código impresso; ver §6.)

## 4. Página pública (QR code) × página logada

- Rota **`/verificar?codigo=<sha256>`** acessível **sem login**; preencha o campo com `query_params`.
- **Pública (essencial):** autêntico ou não; signatários com **papel, nome e data/hora**; documento/escala, período, OM; código completo. **Sem NIP/matrícula e sem o conteúdo** (nomes de escalados, textos).
- **Logada (completa):** tudo acima + NIP + tabela do que foi assinado por seção + textos + observações + motivo de cancelamento/rejeição.
- **Anti-enumeração:** a consulta pública exige mais caracteres do código (16+) que a logada (12+). O QR traz o código inteiro. Códigos de 12–16 hex são inviáveis de adivinhar online, mas mantenha a diferença.
- Código não encontrado: mensagem genérica ("não foi assinado neste sistema, está incompleto/errado ou é falso") — não diferencie "existe mas é de outro".
- **Trava de login global:** em apps com uma tela de login que bloqueia tudo (ex.: Streamlit com `st.navigation`), registre a página pública **dentro da navegação do estado deslogado**; sem isso o QR cai no login com "página não encontrada" (bug real). Veja a referência 06.

## 5. LGPD e minimização de dados

- Dado pessoal exibido publicamente: **nome e papel do signatário** (já constam no documento impresso) e data/hora. **Não** exiba NIP/CPF/e-mail/telefone sem login.
- O conteúdo do documento só aparece para logados.
- Registre o mínimo no carimbo (nome completo, matrícula). Evite CPF.
- Retenção: assinaturas e envios encerrados são **histórico** (não apague junto com o usuário/escala; se excluir o documento de origem, cancele envios abertos e preserve os assinados verificáveis).
- Log de auditoria (quem enviou/assinou/rejeitou/cancelou e quando) já está nos próprios registros (`encerrado_por/em`, `motivo`, `em`).

## 6. Limitações e reforços possíveis

**Limitação principal:** o código é um *hash* (sem segredo). Quem tem **permissão de escrita no banco/planilha** pode, em tese, trocar o conteúdo **e** o código de um registro e a verificação continuará dizendo "autêntica" para o novo par. O hash prova integridade *do registro contra edição parcial*, não contra um administrador de dados mal-intencionado. Reforços, do mais barato ao mais forte:

1. **HMAC com segredo do servidor** (`hmac(segredo, corpo)`) guardado **fora** do banco (variável de ambiente/secret manager) e impresso no lugar/ao lado do SHA-256: quem só tem acesso ao banco não consegue forjar.
2. **Encadeamento (hash chain):** cada assinatura inclui o hash da anterior; adulterar uma quebra as seguintes.
3. **Carimbo de tempo externo** (ex.: serviço de timestamp/ICP-Brasil, ou publicar periodicamente a raiz dos hashes num local de terceiros).
4. **Assinatura digital com certificado** (ICP-Brasil/gov.br) para atos de maior valor.
5. **Upload do PDF** na verificação: extrair o código do PDF e conferir; combinado com (1), detecta PDF adulterado.

Registre essas opções ao usuário e implemente (1) quando houver exigência de não repúdio mais forte.

Outras limitações a declarar: PIN de 4–6 dígitos é fraco contra quem já tem a conta logada (por isso o bloqueio por tentativas e o login prévio); horário vem do servidor (não é carimbo de tempo confiável); o PDF gerado depois pode variar em detalhes cosméticos (brasão) sem alterar o código.

## 7. Checklist de segurança

- [ ] PIN só em bcrypt; erro genérico no login; bloqueio por tentativas
- [ ] Admin só **apaga** PIN; notificação ao dono
- [ ] Só quem tem papel assina/rejeita; quem enviou não rejeita; 1 assinatura por papel
- [ ] Rejeição sem motivo é impossível (backend **e** botão desabilitado)
- [ ] Verificação pública sem NIP/conteúdo; mínimo de caracteres maior
- [ ] Envio encerrado: avisa na verificação e não aceita assinatura
- [ ] Reenvio sempre exige novas assinaturas
- [ ] Segredos/URL-base por variável de ambiente
- [ ] Fuso horário fixo; horário no carimbo com fuso

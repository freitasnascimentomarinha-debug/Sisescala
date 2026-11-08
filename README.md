# SisEscala

Escalas e detalhe de serviço (Marinha). Protótipo: motor de escala em Python puro + app Streamlit.

```
pip install -r requirements.txt
pytest
streamlit run app.py
```

## Documentos e visual
- Todo documento (detalhe de serviço, papeleta, regras) abre com **MARINHA DO BRASIL** e, logo abaixo, a **OM que gerencia a escala** (campo em Gestão → Escalas; pode ser ajustada na hora no detalhe). Dispensados aparecem como `[Disp]` com a justificativa nas observações.
- Tema **escuro camuflado**, com as cores da farda (verdes de oliva e floresta, areia e marrom) e o padrão digital pixelado como textura no menu, no login e numa faixa no topo. Definido em `.streamlit/config.toml`, `assets/estilo.css` e `static/camuflado.svg` (gerado por `scripts/gerar_camuflado.py`; o servidor precisa de `enableStaticServing`, já ligado no config).
- A leitura da planilha é **pelo nome das colunas**: versões novas podem acrescentar colunas sem quebrar dados já gravados.

## Organização do app (páginas, por etapa do trabalho)
| Seção | Páginas |
|---|---|
| Início | **Painel**: pendências, quem está de serviço hoje, meus próximos serviços, atividade recente |
| Operação | **Escala** (prévia clicável, pedido de troca, disponibilidade), **Papeletas**, **Devoluções** |
| Documentos | **Detalhe de serviço** (PDF), **Regras da escala** |
| Gestão (detalhista) | **Escalas**, **Militares**, **Lançamentos**, **Importar planilha**, **Vínculos** |
| Administração | **Usuários** |
| Conta | **Notificações**, **Minha conta** (contato, PIN, senha) |

O menu mostra só o que o perfil pode usar. Código: `app.py` (login, navegação, gravação), `paginas/` (uma por tela), `sisescala/ui.py` e `assets/estilo.css` (identidade visual), `sisescala/sessao.py` (estado compartilhado), `sisescala/` (regras de negócio, sem Streamlit).

## Regras implementadas (todas configuráveis, com padrões)
- **Uma escala por vez:** prévia e detalhe são de uma escala só; o card mostra categoria, prioridade, escalados/dia, quartos, descanso mínimo, responsável, referências e compartilhamento. Na célula só aparecem a sigla e o horário compacto (`4h/16h`).
- **Categorias de escalação:** serviço, palestra, curso, visitação religiosa, cerimônia, apoio (destaque em outra OM) e outro (`modo="eventos"`: só funciona nos dias de evento lançados).
- **Filas independentes:** corrida | preta (dia útil) | vermelha (sáb/dom/feriado) | roxa (por período). Fila fora do dia fica congelada; a roxa começa do zero.
- **Ordem:** do mais antigo ao mais moderno, circular, a partir de quem deu o último serviço.
- **Descanso mínimo (2x1):** `folgas_minimas=2` por padrão (configurável): nunca 1x1, inclusive entre filas (sexta preta / sábado vermelha). Quem é pulado não perde a vez. `validar_escala` recusa configurações impossíveis.
- **Quartos** (`quartos_padrao(4)` = 6 de 4h; `(2)` = 12 de 2h), `militares_dia`, `retem_qtd` configuráveis.
- **Impedimentos:** férias, curso, **dispensado** (com documento: motivo e arquivo; ou por baixa/falta: justificativa do detalhista), desembarque e **DTQ (destaque)**: o militar não concorre no período. Baixa e falta **não são status próprios**: viram `Disp` (dispensado) com a justificativa.
- **Feriados:** nacionais/estaduais automáticos (`holidays`); municipais, licença administrativa e guarnecimento por dia são manuais.
- **Dispensado no dia do serviço:** o militar escalado aparece como `Disp`, com a justificativa (obrigatória) lançada pelo detalhista; o retém avança, a prévia e o detalhe se reconfiguram e fica uma devolução pendente (prazo padrão 30 dias, configurável).
- **Troca consensual** (papeleta com dois aceites) → `SVÇ (T)`. **Troca forçada** → `SVÇ (TF)` / `RT (TF)` com observação.
- **Compartilhamento:** o dono libera a escala como *leitura* ou *edição*. Quem recebe pode criar outras escalas **referenciando** a compartilhada: ela prevalece e o militar de serviço nela é considerado ao formar a nova. Escalas de donos diferentes sem referência não se influenciam.
- PDF do detalhe por escala, com assinaturas (Detalhista, Encarregado do Detalhe, Vice-Diretor).

## Cadastro, importação e relatório de regras
- **Militares:** adicionar, editar (inclusive antiguidade), excluir um ou vários (a fila segue de onde estava) e vincular/encerrar participação em escalas. Excluir do cadastro exige poder editar todas as escalas do militar.
- **Importar planilha (CSV/XLSX):** reconhece nome de guerra, posto/graduação, NIP, OM (sigla/código), escala, ordem e último serviço/data. Mostra uma pré-visualização (novos, atualizados, avisos) antes de aplicar, e a escala continua do dia seguinte à última data da planilha, depois de quem deu o último serviço em cada fila. Há modelo para baixar.
- **Regras da escala (relatório):** mostra, com a configuração atual, como a escala funciona, o que está no padrão e o que foi alterado, a situação atual e a lógica fixa do sistema. Atualiza sozinho ao mudar qualquer configuração; baixa em PDF.
- Escalações que não são serviço (palestra etc.) **nunca** têm prioridade sobre serviço e só escalam quem não está de efetivo serviço no dia.

## Papeleta de troca de serviço
1. Na **Prévia** (ou clicando na célula do colega), o militar (mesmo com acesso só de leitura) pede a troca **para si, confirmando com o seu PIN**; o detalhista e os editores pedem por qualquer militar da escala. Escolhe-se o dia dele, o militar e o dia com quem trocar, e o **motivo (obrigatório)**. O sistema valida na hora e respeita a **antecedência mínima** da escala (24h, ajustável).
2. **Pedido ativo (pendente ou aprovado) trava os dois militares**: não podem ser selecionados em outro pedido.
3. O pedido registra data, hora, quem pediu (posto, nome, NIP, OM), motivo, com quem e em que escala, e chega ao dono (detalhista) e aos editores da escala.
4. **A prévia só muda quando o detalhista aprova**; aprovando, a troca de datas é aplicada na hora (`SVÇ (T)` nos dois dias).
5. Cada parte **assina pelo sistema com o PIN**, na própria conta; a assinatura registra **data, hora (com segundos) e o código de verificação do documento**, e aparece na tela e no PDF. O detalhista vê se **as duas partes têm conta** e quem já assinou (ou registra documento assinado fora: gov.br/ICP/papel) e **confirma**.
6. **As partes cancelam enquanto não aprovado.** O detalhista cancela também depois de aprovar (e da confirmação, com motivo): a troca é desfeita.
- Serviço que já veio de troca (T/TF) não é trocado de novo. A assinatura pelo sistema não substitui certificado ICP-Brasil.

## Login, cadastro e vínculo com o militar
- **Acesso por NIP e senha.** O NIP (6 a 10 dígitos; pontos e traços são ignorados) é o login.
- **O administrador é criado automaticamente** na primeira execução. NIP e senha vêm dos segredos do deploy (`[admin] nip = "..." senha = "..."` em `.streamlit/secrets.toml` / Secrets do Community Cloud) ou das variáveis `SISESCALA_ADMIN_NIP` e `SISESCALA_ADMIN_SENHA`. Sem senha configurada, o sistema gera uma **provisória**, escreve no **log do servidor** (Manage app → Logs) e exige a troca no primeiro acesso.
- **O militar cria a própria conta** (aba "Criar conta") com **NIP, OM, nome, senha, e-mail, ramal e celular**. O cadastro fica **pendente** e o administrador é avisado. Em **Usuários** o administrador **aprova ou rejeita** cadastros, edita, **bloqueia/desbloqueia**, redefine a senha (provisória, com troca obrigatória), exclui (reatribuindo antes as escalas que a conta detalha) e pode fechar o cadastro aberto.
- **Não há perfil fixo: o papel é por escala.** Todo usuário aprovado **cria uma escala ou importa uma planilha e vira o detalhista dela**; também pode **buscar escalas de outros** (por nome, tipo, OM ou detalhista, sem ver os militares) em **Buscar escalas** e **pedir acesso**. O detalhista **aprova ou rejeita** (com motivo) em **Pedidos de acesso**; aprovado, a pessoa passa a ver a escala (leitura). Cada detalhista só enxerga e edita os militares das escalas dele, e data-base, UF e dias especiais são por escala (o administrador lança dias para todas). **A antiguidade é por escala:** cada escala tem a sua numeração (1 = mais antigo), que o detalhista ajusta em Militares arrastando os nomes (ou pelas setas ↑↓), com salvamento na hora; quem entra vai para o fim (ou para a posição escolhida) e mexer numa escala não desloca as outras. O cadastro (nome, NIP, contato) continua único: um militar em duas escalas tem um só cadastro, e quem importa planilha sem ser administrador só preenche campos vazios.
- O militar então abre a aba **Vínculos**, escolhe quem ele é na lista da escala, confirma o NIP (se já cadastrado) e **cria um PIN** (4 a 6 dígitos). O detalhista/editores **aprovam ou rejeitam** (com motivo). Aprovado, a conta passa a ser daquele militar e o contato dela completa o cadastro dele.
- **PIN:** todo usuário cadastra o seu em **Minha conta** (exige a senha). **Pedir troca/devolução e assinar exigem o PIN** de quem faz a ação (o detalhista que pede por um militar usa o próprio PIN). 5 erros seguidos bloqueiam a conta por 5 minutos.
- **Quem pede troca de serviço:** só **militar vinculado** (e só para o próprio serviço) ou o **detalhista da escala** (por qualquer militar). Conta sem vínculo não pede, mesmo com acesso à escala.
- **Convite do detalhista:** em Vínculos, o detalhista (ou auxiliar) pesquisa usuários ativos e sem vínculo (nome, NIP ou OM, 3 letras ou mais; só nome e OM aparecem, nunca e-mail ou telefone), escolhe o militar da escala e envia um convite. O usuário recebe o aviso e **aceita confirmando o NIP e criando o PIN dele**; só então o vínculo vale. Também pode recusar, e o detalhista pode cancelar. O usuário continua podendo pedir o vínculo por conta própria (abaixo).
- **A vinculação precisa da autorização do detalhista.** O militar pede (com NIP e PIN); a conta só passa a ser dele depois da aprovação. O administrador **não** cria contas já vinculadas.
- **Detalhista por escala:** cada escala tem **um só detalhista** (militar escolhido em Gestão → Escalas), que pode ser o mesmo de várias escalas. Por padrão ele é **dispensado de serviço naquela escala**: não dá nenhum serviço (efetivo, retém, palestra, cerimônia...), não é escalado para nada, não ocupa vaga na fila nem conta no mínimo de militares e não aparece na prévia. Opção rara por escala: **"o detalhista também concorre"**, e aí ele concorre como qualquer militar. Em outra escala em que não é o detalhista, ele é um militar comum.
- **Auxiliares do detalhista (vários por escala):** o detalhista designa quantos quiser, em Gestão → Escalas → Editar. Eles **aprovam papeletas e vínculos e fazem os lançamentos** (dispensas, dias especiais, guarnecimento, eventos) daquela escala, concorrendo ou não a ela: o auxiliar pode nem ser membro da escala (sem vinculação nela), e é o detalhista quem decide incluí-lo. Agem só nessa escala e para os militares dela, sem acesso às demais páginas de gestão; precisam ter a conta ligada ao militar. **Só o detalhista edita as regras da escala** (descanso, quartos, quantidade por dia, prioridade, quem é detalhista e auxiliares, membros, criar/excluir/compartilhar), nem pela tela nem pelo código (`sisescala/gestao.py`). **Nunca para si mesmo:** ninguém decide a própria troca nem lança (ou remove) dispensa ou impedimento para si; outro responsável faz.
- **A escala pode nascer vazia.** O mínimo de militares (descanso 2x1 etc.) é só um aviso, não impede criar nem editar: crie a escala, depois cadastre os militares em Militares ou importe uma planilha com o mesmo nome da escala. Nenhum vínculo de usuário é necessário para a escala funcionar.
- **Importar numa escala que já existe:** em Importar planilha, escolha "Para qual escala?". **Acrescentar** inclui quem falta e completa campos vazios (ninguém sai); **Substituir** deixa a escala exatamente como a planilha (quem não está nela sai, a antiguidade passa a ser a da planilha e os dados cadastrais são trocados, só dos militares que estão apenas em escalas do próprio detalhista). Antes de substituir, você revisa a lista de quem sai e confirma em "Tem certeza?".
- **Quem cria a escala vira o detalhista** (e, se a conta tem militar ligado, esse militar fica dispensado de serviço nela). **Entregar o detalhe:** o detalhista passa a função a outro usuário ativo e escolhe o que será depois: **militar escalado** (entra na escala e concorre), **auxiliar** (sem concorrer, ou concorrendo) ou **nenhum papel** (sai de membros, auxiliares e acesso). Nunca fica sem detalhista: é obrigatório designar outro. O novo detalhista fica fora da escala por padrão. O novo detalhista pode ser qualquer usuário ativo.
- **Detalhista da escala** = o dono dela (quem criou ou recebeu o detalhe). Só ele (e os auxiliares que designar) decide papeletas e vínculos. **Militar vinculado:** pede troca para si e sinaliza disponibilidade.
- Senhas e PINs só como hash bcrypt (senha com 8+ caracteres).

## Disponibilidade de troca
O militar vinculado (ou o detalhista por ele) escolhe, na **Prévia**, um dia futuro em que está escalado e abre a disponibilidade: aparece uma **bolinha verde piscando** na célula dele, para todos que veem a escala, e ● nas listas de troca. Só vale para serviço dele (se mudar de mãos, o sinal some), respeitando a antecedência mínima da escala, e fica oculta enquanto ele estiver num pedido de troca ativo. Sinais de dias passados são removidos.

## Devoluções
Quem foi dispensado de um serviço escalado (ou deslocado por outra regra) fica com um **serviço a devolver**, com prazo (30 dias por padrão, configurável). A aba **Devoluções** lista os pendentes (🟡 aberta, 🔵 em andamento, 🔴 vencida) e sugere dias, os mais próximos do original primeiro, com **⚠ descanso curto** quando o 2x1 não é respeitado (o detalhista decide). A devolução é uma papeleta do tipo "devolução": o militar assume o serviço de um colega, com PIN, aprovação do detalhista e assinaturas. Confirmada, o serviço é quitado; cancelada ou rejeitada, volta a ficar aberto. O militar é avisado quando a dispensa é lançada.

## Notificações
Central dentro do sistema (🔔 na barra lateral; não envia e-mail): disponibilidade aberta (para os colegas com conta e os editores), pedidos de troca/devolução (outra parte e editores), aprovação, rejeição, cancelamento, assinatura e confirmação, pedidos e decisões de vínculo e serviço a devolver. Lidas há mais de 30 dias são removidas.

## Prévia interativa (componente JavaScript)
A prévia é um componente Streamlit próprio (`componentes/previa/index.html`, JS puro sem build, `sisescala/componente.py`). Clicar numa célula marca-a e devolve ao Python o militar e o dia: no seu próprio serviço pré-preenche a **disponibilidade**; no de um colega, a **troca**.

## Persistência no Google Sheets
1. No Google Cloud: crie um projeto, ative a **Google Sheets API** e crie uma **conta de serviço** com chave JSON.
2. Crie uma planilha **vazia e privada** e compartilhe com o e-mail da conta de serviço como **Editor**. Não compartilhe com mais ninguém: a aba `Usuarios` guarda os hashes de senha e há dados de militares (NIP).
3. Preencha `.streamlit/secrets.toml` (modelo em `secrets.toml.example`) ou, no Streamlit Community Cloud, **Settings → Secrets**. Mantenha o app privado também no Community Cloud.
4. Abra o app e crie o administrador. As abas são criadas sozinhas.
- Sem credenciais, o app grava em `data/sisescala.json` (apenas desenvolvimento). `SISESCALA_DEMO=1` carrega dados de demonstração num armazenamento vazio.
- **Como grava:** só as abas que mudaram, em uma chamada. **Controle de concorrência:** uma versão na aba `Versao`; se outra pessoa gravou antes, o app recarrega a versão nova e avisa para refazer a última ação (o Sheets não tem transações, então a janela é de milissegundos, não zero).
- Para migrar depois para PostgreSQL basta implementar outro `Backend`/`Repositorio` (`sisescala/persistencia.py`); o motor e a tela não mudam.

## Pendente
Backend PostgreSQL (a camada `Backend`/`Repositorio` já isola o armazenamento); envio de aviso por e-mail; assinatura qualificada (ICP-Brasil/gov.br) integrada.

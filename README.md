# SisEscala

Escalas e detalhe de serviço (Marinha). Protótipo: motor de escala em Python puro + app Streamlit.

```
pip install -r requirements.txt
pytest
streamlit run app.py
```

## Regras implementadas (todas configuráveis, com padrões)
- **Uma escala por vez:** prévia e detalhe são de uma escala só; o card mostra categoria, prioridade, escalados/dia, quartos, descanso mínimo, responsável, referências e compartilhamento. Na célula só aparecem a sigla e o horário compacto (`4h/16h`).
- **Categorias de escalação:** serviço, palestra, curso, visitação religiosa, cerimônia, apoio (destaque em outra OM) e outro (`modo="eventos"`: só funciona nos dias de evento lançados).
- **Filas independentes:** corrida | preta (dia útil) | vermelha (sáb/dom/feriado) | roxa (por período). Fila fora do dia fica congelada; a roxa começa do zero.
- **Ordem:** do mais antigo ao mais moderno, circular, a partir de quem deu o último serviço.
- **Descanso mínimo (2x1):** `folgas_minimas=2` por padrão (configurável): nunca 1x1, inclusive entre filas (sexta preta / sábado vermelha). Quem é pulado não perde a vez. `validar_escala` recusa configurações impossíveis.
- **Quartos** (`quartos_padrao(4)` = 6 de 4h; `(2)` = 12 de 2h), `militares_dia`, `retem_qtd` configuráveis.
- **Impedimentos:** férias, curso, dispensa (exige motivo e arquivo), baixa, desembarque e **DTQ (destaque)**: o militar não concorre no período.
- **Feriados:** nacionais/estaduais automáticos (`holidays`); municipais, licença administrativa e guarnecimento por dia são manuais.
- **Falta no serviço:** o retém avança e fica uma devolução pendente (prazo padrão 30 dias, configurável).
- **Troca consensual** (papeleta com dois aceites) → `SVÇ (T)`. **Troca forçada** → `SVÇ (TF)` / `RT (TF)` com observação.
- **Compartilhamento:** o dono libera a escala como *leitura* ou *edição*. Quem recebe pode criar outras escalas **referenciando** a compartilhada: ela prevalece e o militar de serviço nela é considerado ao formar a nova. Escalas de donos diferentes sem referência não se influenciam.
- PDF do detalhe por escala, com assinaturas (Detalhista, Encarregado do Detalhe, Vice-Diretor).

## Cadastro, importação e relatório de regras
- **Militares:** adicionar, editar (inclusive antiguidade), excluir um ou vários (a fila segue de onde estava) e vincular/encerrar participação em escalas. Excluir do cadastro exige poder editar todas as escalas do militar.
- **Importar planilha (CSV/XLSX):** reconhece nome de guerra, posto/graduação, NIP, OM (sigla/código), escala, ordem e último serviço/data. Mostra uma pré-visualização (novos, atualizados, avisos) antes de aplicar, e a escala continua do dia seguinte à última data da planilha, depois de quem deu o último serviço em cada fila. Há modelo para baixar.
- **Regras da escala (relatório):** mostra, com a configuração atual, como a escala funciona, o que está no padrão e o que foi alterado, a situação atual e a lógica fixa do sistema. Atualiza sozinho ao mudar qualquer configuração; baixa em PDF.
- Escalações que não são serviço (palestra etc.) **nunca** têm prioridade sobre serviço e só escalam quem não está de efetivo serviço no dia.

## Papeleta de troca de serviço
1. Na **Prévia**, o militar (mesmo com acesso só de leitura) pede a troca **para si**; o detalhista e os editores pedem por qualquer militar da escala. Escolhe-se o dia dele, o militar e o dia com quem trocar, e o **motivo (obrigatório)**. O sistema valida na hora e respeita a **antecedência mínima** da escala (24h, ajustável).
2. **Pedido ativo (pendente ou aprovado) trava os dois militares**: não podem ser selecionados em outro pedido.
3. O pedido registra data, hora, quem pediu (posto, nome, NIP, OM), motivo, com quem e em que escala, e chega ao dono (detalhista) e aos editores da escala.
4. **A prévia só muda quando o detalhista aprova**; aprovando, a troca de datas é aplicada na hora (`SVÇ (T)` nos dois dias).
5. Cada parte **assina pelo sistema** entrando na própria conta e reconfirmando a senha. O detalhista vê se **as duas partes têm conta** e quem já assinou (ou registra documento assinado fora: gov.br/ICP/papel) e **confirma**.
6. **As partes cancelam enquanto não aprovado.** O detalhista cancela também depois de aprovar (e da confirmação, com motivo): a troca é desfeita.
- Serviço que já veio de troca (T/TF) não é trocado de novo. A assinatura pelo sistema não substitui certificado ICP-Brasil.

## Login e perfis
- A primeira conta criada (tela "Primeiro acesso") é a administradora. O administrador cria as contas na aba **Usuários**.
- **Detalhista:** cria e edita escalas, cadastro, importação, lançamentos. **Militar:** conta ligada a um militar do cadastro; enxerga (leitura) as escalas em que está e pede troca para si.
- Senhas só como hash bcrypt (mínimo 8 caracteres); 5 falhas seguidas bloqueiam a conta por 5 minutos.

## Persistência no Google Sheets
1. No Google Cloud: crie um projeto, ative a **Google Sheets API** e crie uma **conta de serviço** com chave JSON.
2. Crie uma planilha **vazia e privada** e compartilhe com o e-mail da conta de serviço como **Editor**. Não compartilhe com mais ninguém: a aba `Usuarios` guarda os hashes de senha e há dados de militares (NIP).
3. Preencha `.streamlit/secrets.toml` (modelo em `secrets.toml.example`) ou, no Streamlit Community Cloud, **Settings → Secrets**. Mantenha o app privado também no Community Cloud.
4. Abra o app e crie o administrador. As abas são criadas sozinhas.
- Sem credenciais, o app grava em `data/sisescala.json` (apenas desenvolvimento). `SISESCALA_DEMO=1` carrega dados de demonstração num armazenamento vazio.
- **Como grava:** só as abas que mudaram, em uma chamada. **Controle de concorrência:** uma versão na aba `Versao`; se outra pessoa gravou antes, o app recarrega a versão nova e avisa para refazer a última ação (o Sheets não tem transações, então a janela é de milissegundos, não zero).
- Para migrar depois para PostgreSQL basta implementar outro `Backend`/`Repositorio` (`sisescala/persistencia.py`); o motor e a tela não mudam.

## Pendente
Tela de devolução de serviço; backend PostgreSQL; componente JS customizado; assinatura qualificada (ICP-Brasil/gov.br) integrada.

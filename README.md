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
1. Na **Prévia**, escolha o militar e o dia do serviço dele, depois o militar e o dia com quem trocar. O sistema valida na hora (escalado, sem impedimento, sem outro serviço no dia; descanso curto vira aviso) e respeita a **antecedência mínima** da escala (24h, ajustável por escala).
2. Ao confirmar, gera-se o documento (PDF) para assinatura dos dois militares e do detalhista. O pedido registra data, hora, quem pediu, com quem e em que escala.
3. O pedido chega ao dono (detalhista) e aos editores da escala (aviso na barra lateral e aba **Papeletas**), que aprovam ou rejeitam (com motivo).
4. **Aprovando**, a troca de datas é aplicada automaticamente (`SVÇ (T)` nos dois dias).
5. O detalhista **confirma** quando as duas partes assinaram; se não assinarem, cancela e a troca é desfeita.
- Assinatura: eletrônica simples (NIP + PIN com hash bcrypt, data/hora e código SHA-256 do documento) ou registro de documento assinado fora (gov.br/ICP/papel). Não é certificado ICP-Brasil.
- Serviço que já veio de troca (T/TF) não é trocado de novo.

## Pendente
Persistência (Google Sheets, depois PostgreSQL) atrás de uma camada de repositório; login com senha (hoje o usuário é escolhido na barra lateral); tela de devolução (a papeleta de troca já existe); componente JS customizado.

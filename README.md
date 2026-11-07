# SisEscala

Escalas e detalhe de serviço (Marinha). Protótipo: motor de escala em Python puro + app Streamlit.

```
pip install -r requirements.txt
pytest
streamlit run app.py
```

## Regras implementadas (todas configuráveis, com padrões)
- Filas independentes por escala: corrida | preta (dia útil) | vermelha (sáb/dom/feriado) | roxa (por período). A fila fora do dia fica congelada; a roxa começa do zero.
- Ordem do mais antigo ao mais moderno, circular, a partir de quem deu o último serviço (`ultimo_servico`).
- Quartos configuráveis (`quartos_padrao(4)` = 6 quartos de 4h; `quartos_padrao(2)` = 12 de 2h), `militares_dia`, `retem_qtd`.
- Impedimentos: férias, curso, dispensa (exige motivo e arquivo), baixa, desembarque (sem data final).
- Feriados nacionais/estaduais automáticos (`holidays`); feriado municipal, licença administrativa e guarnecimento por dia são lançados à mão.
- Falta no serviço: o retém avança, os reténs seguintes avançam e fica uma devolução pendente (prazo padrão 30 dias, configurável).
- Troca consensual (papeleta, dois aceites) → `SVÇ (T)`.
- Troca forçada: pernoite prevalece; o militar é realocado por troca de datas com outro da escala menor → `SVÇ (TF)` / `RT (TF)`, com observação.
- Prévia 7/15/30 dias com siglas e cores; PDF do detalhe com assinaturas (Detalhista, Encarregado do Detalhe, Vice-Diretor).

## Pendente
Persistência (Google Sheets, depois PostgreSQL) atrás de uma camada de repositório; login; papeleta em PDF; componente JS customizado.

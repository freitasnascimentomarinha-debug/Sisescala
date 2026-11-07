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

## Pendente
Persistência (Google Sheets, depois PostgreSQL) atrás de uma camada de repositório; login com senha (hoje o usuário é escolhido na barra lateral); papeleta em PDF e tela de devolução; componente JS customizado.

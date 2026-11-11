# Implementação de referência (SisEscala)

Código real, em produção e testado (280+ testes), extraído do SisEscala (Python/Streamlit). **Não é uma biblioteca instalável**: é um modelo para copiar a lógica e adaptar à stack do projeto.

| Arquivo | O que mostra |
|---|---|
| `assinaturas.py` | Núcleo do fluxo: papéis, designação, enviar, assinar, rejeitar, cancelar, pendências, regra de dados antigos |
| `verificacao.py` | Registro da assinatura, busca por código (inteiro/prefixo/QR/URL), integridade, descrição do conteúdo, URL do QR |
| `tela_verificacao.py` | Tela de verificação (pública × logada) |
| `pagina_assinar.py` | Tela "Assinar documentos": filtros, conferir, assinar com PIN, rejeitar com motivo |
| `pagina_publica_verificar.py` | Página pública (sem login) aberta pelo QR |
| `pdf.py` | Snapshot, JSON canônico, hash, renderização do PDF, carimbo, QR, grade de assinaturas, `CondPageBreak` |
| `pin.py` | Ciclo de vida do PIN (bcrypt, bloqueio, alterar com senha, admin apaga) |
| `textorico.py` | HTML higienizado do editor → PDF e tela |
| `brasao.py` | Imagem enviada → célula da planilha (JPEG/PNG, limites, mensagens) |
| `tests/` | Testes de domínio do fluxo (cancelar+reenviar, rejeição, 4 autoridades, verificação) |

Dependências da referência: `reportlab`, `bcrypt`, `Pillow`, `streamlit`, `pypdf` (testes). Os módulos importam o resto do projeto (`.modelos`, `.permissoes`, `.notificacoes`, `.auth`): troque pelos equivalentes do projeto de destino (veja `references/06-adaptando-a-outra-stack.md`).

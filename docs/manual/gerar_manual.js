// Gera o Manual do Usuário do SisEscala (.docx) a partir das imagens preparadas.
// Uso: node gerar_manual.js <pasta_imagens> <saida.docx> [paginas.json]
// "paginas.json" (opcional) traz {titulo: pagina} para preencher o sumário com os números de página (2ª passada).
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, AlignmentType,
  HeadingLevel, LevelFormat, PageBreak, Header, Footer, PageNumber, PositionalTab, PositionalTabAlignment,
  PositionalTabRelativeTo, PositionalTabLeader, TabStopType, VerticalAlign,
} = require('docx');

const IMG = process.argv[2];
const SAIDA = process.argv[3];
const PAGINAS = process.argv[4] && fs.existsSync(process.argv[4]) ? JSON.parse(fs.readFileSync(process.argv[4])) : {};
const INFO = JSON.parse(fs.readFileSync(path.join(IMG, 'info.json')));
const LOGO = path.join(__dirname, '..', '..', 'static', 'logo_menu.png');

const NAVY = '0A2342', OURO = 'B8962E', CINZA = '5B6573', GELO = 'EAF0F7';
const FONTE = 'Arial';
const LARG = 9638;                       // largura útil (A4, margens 2 cm) em DXA

// ------------------------------------------------------------------ utilidades
function runs(texto, base = {}) {        // **negrito** e _itálico_ simples
  const out = [];
  const re = /(\*\*[^*]+\*\*|__[^_]+__)/g;
  let i = 0, m;
  while ((m = re.exec(texto)) !== null) {
    if (m.index > i) out.push(new TextRun({ text: texto.slice(i, m.index), font: FONTE, ...base }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ text: t.slice(2, -2), bold: true, font: FONTE, ...base }));
    else out.push(new TextRun({ text: t.slice(2, -2), italics: true, font: FONTE, ...base }));
    i = m.index + t.length;
  }
  if (i < texto.length) out.push(new TextRun({ text: texto.slice(i), font: FONTE, ...base }));
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t, o.run), spacing: { after: 120, line: 300 }, alignment: o.align, keepNext: o.keepNext, ...(o.p || {}) });
const SPACER = (n = 120) => new Paragraph({ spacing: { after: n }, children: [] });

const titulos = [];                      // para o sumário: [nivel, texto]
const H1 = (t) => { titulos.push([1, t]); return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: t, font: FONTE })], pageBreakBefore: true }); };
const H2 = (t) => { titulos.push([2, t]); return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: FONTE })] }); };
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: t, font: FONTE })] });

let contaLista = 0;
const numeracoes = [];
function UL(itens) {
  return itens.map((t) => new Paragraph({ numbering: { reference: 'marcadores', level: 0 }, children: runs(t), spacing: { after: 60, line: 288 } }));
}
function OL(itens) {
  const ref = 'passos' + (++contaLista);
  numeracoes.push({
    reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 360 } }, run: { bold: true, color: NAVY } } }],
  });
  return itens.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), spacing: { after: 80, line: 288 } }));
}

const BORDA = { style: BorderStyle.SINGLE, size: 4, color: 'C9D3E0' };
function CAIXA(tipo, texto) {
  const cfg = { dica: ['DICA', 'E6F2E0', '3E7B2F'], atencao: ['ATENÇÃO', 'FFF3D6', 'B7791F'], importante: ['IMPORTANTE', 'FBE3E0', 'B23B2E'],
                nota: ['NOTA', GELO, NAVY] }[tipo];
  const lado = { style: BorderStyle.SINGLE, size: 24, color: cfg[2] };
  return new Table({
    width: { size: LARG, type: WidthType.DXA }, columnWidths: [LARG],
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      width: { size: LARG, type: WidthType.DXA }, shading: { fill: cfg[1], type: ShadingType.CLEAR, color: 'auto' },
      margins: { top: 100, bottom: 100, left: 160, right: 160 },
      borders: { top: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' }, bottom: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
                 right: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' }, left: lado },
      children: [new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: cfg[0], bold: true, size: 17, color: cfg[2], font: FONTE })] }),
                 new Paragraph({ spacing: { after: 0, line: 280 }, children: runs(texto, { size: 20 }) })],
    })] })],
  });
}

function TAB(cab, linhas, larguras) {
  const soma = larguras.reduce((a, b) => a + b, 0);
  const cel = (t, i, head) => new TableCell({
    width: { size: larguras[i], type: WidthType.DXA }, margins: { top: 70, bottom: 70, left: 110, right: 110 },
    shading: head ? { fill: NAVY, type: ShadingType.CLEAR, color: 'auto' } : undefined, verticalAlign: VerticalAlign.CENTER,
    borders: { top: BORDA, bottom: BORDA, left: BORDA, right: BORDA },
    children: [new Paragraph({ spacing: { after: 0, line: 264 }, children: runs(t, head ? { bold: true, color: 'FFFFFF', size: 19 } : { size: 19 }) })],
  });
  return new Table({
    width: { size: soma, type: WidthType.DXA }, columnWidths: larguras,
    rows: [new TableRow({ tableHeader: true, children: cab.map((t, i) => cel(t, i, true)) }),
           ...linhas.map((l, k) => new TableRow({ cantSplit: true, children: l.map((t, i) => {
             const c = cel(t, i, false);
             return c;
           }) }))],
  });
}

let nFig = 0;
function FIG(nome, legenda, marcas = []) {
  const meta = INFO[nome];
  if (!meta) { console.log('SEM IMAGEM', nome); return [P('[imagem ausente: ' + nome + ']')]; }
  const lim = nome.startsWith('pdf-ampl') ? 620 : nome.startsWith('pdf-') ? 470 : 600;
  let w = Math.min(lim, meta.w * 0.6), h = meta.h * (w / meta.w);
  const hmax = nome.startsWith('pdf-ampl') ? 380 : 600;
  if (h > hmax) { w = w * (hmax / h); h = hmax; }
  const out = [new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
    children: [new ImageRun({ type: 'png', data: fs.readFileSync(path.join(IMG, nome + '.png')), transformation: { width: Math.round(w), height: Math.round(h) },
      altText: { title: legenda, description: legenda, name: nome } })],
  })];
  nFig += 1;
  out.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: marcas.length ? 80 : 200 },
    children: [new TextRun({ text: `Figura ${nFig} — `, bold: true, size: 18, color: NAVY, font: FONTE }), new TextRun({ text: legenda, size: 18, color: CINZA, font: FONTE })] }));
  if (marcas.length) {
    marcas.forEach((t, i) => out.push(new Paragraph({ spacing: { after: 40, line: 264 }, indent: { left: 360, hanging: 360 },
      children: [new TextRun({ text: `${i + 1}  `, bold: true, color: 'D64545', font: FONTE, size: 20 }), ...runs(t, { size: 20 })] })));
    out.push(SPACER(160));
  }
  return out;
}

// ------------------------------------------------------------------ conteúdo
const corpo = [];
const add = (...x) => x.flat().forEach((e) => corpo.push(e));

// 1 ---------------------------------------------------------------
add(H1('1. Apresentação'));
add(P('O **SisEscala** é o sistema da OM para montar e acompanhar **escalas de serviço** (portaria, fiscal, sentinela, contramestre, palestras e outras), '
  + 'controlar **trocas de serviço** por papeleta, registrar **dispensas e impedimentos** e produzir o **detalhe de serviço** em PDF, '
  + 'com **assinatura eletrônica** das autoridades e **verificação de autenticidade** por QR code.'));
add(P('Este manual mostra, passo a passo e com imagens do próprio sistema, como cada pessoa usa o SisEscala no dia a dia. Os nomes e dados das imagens são **fictícios**.'));
add(H2('1.1 Quem usa o sistema'));
add(TAB(['Perfil', 'O que faz no sistema'], [
  ['**Militar**', 'Vê a escala em que está, pede troca de serviço e devolução, assina papeletas com o PIN e sinaliza que o seu serviço está aberto a troca.'],
  ['**Detalhista**', 'Quem **criou a escala** e responde por ela. Configura as regras, decide papeletas e vínculos, faz lançamentos, monta o detalhe de serviço e o envia para assinatura.'],
  ['**Auxiliar do detalhista**', 'Militar indicado pelo detalhista. Decide papeletas e vínculos e faz lançamentos na escala em que auxilia; assina o detalhe como auxiliar. Não altera as regras da escala.'],
  ['**Encarregado do Detalhe** e **Vice-Diretor**', 'Autoridades indicadas pelo detalhista. Recebem o aviso de um novo detalhe, conferem o documento e **assinam com o PIN** (ou rejeitam, com justificativa).'],
  ['**Administrador**', 'Aprova cadastros, bloqueia/desbloqueia contas, redefine senha e PIN e cuida da configuração do sistema.'],
], [2700, 6938]));
add(SPACER());
add(H2('1.2 Conceitos que aparecem o tempo todo'));
add(TAB(['Termo', 'Significado'], [
  ['**Escala**', 'Lista de militares que se revezam num serviço (por exemplo, “Portaria”). Cada escala tem as suas regras e a sua ordem de antiguidade.'],
  ['**Retém**', 'Militar de reserva do dia: assume o serviço se o titular ficar impedido.'],
  ['**Descanso (N×1)**', 'Folgas mínimas entre dois serviços do mesmo militar. “2×1” = 2 folgas para 1 serviço.'],
  ['**Papeleta**', 'Documento do pedido de troca ou devolução de serviço, com a decisão do detalhista e a assinatura dos militares.'],
  ['**Vínculo**', 'Ligação da **conta** de uma pessoa ao **nome dela** na escala. Sem vínculo a pessoa não pede troca nem assina.'],
  ['**Detalhe de serviço**', 'Documento em PDF com quem está de serviço e de retém em cada dia, mais instruções, recomendações e regras.'],
  ['**PIN**', 'Senha curta (4 a 6 números) usada para **confirmar** pedidos de troca e **assinar** documentos. É diferente da senha de entrada.'],
  ['**Código de verificação**', 'Código (SHA-256) impresso no PDF assinado. Com ele, ou lendo o QR code, qualquer pessoa confere se o documento é autêntico.'],
], [2700, 6938]));

// 2 ---------------------------------------------------------------
add(H1('2. Primeiros passos'));
add(H2('2.1 Entrar no sistema'));
add(P('Abra o endereço do SisEscala no navegador (computador ou celular). A tela inicial pede o **NIP** e a **senha**.'));
add(...OL(['Digite o seu **NIP** (somente números) no campo 1.', 'Digite a **senha** no campo 2.', 'Clique em **Entrar** (3).']));
add(...FIG('01-login', 'Tela de entrada do SisEscala.', ['Campo do NIP.', 'Campo da senha.', 'Botão Entrar.', 'Aba **Criar conta**, para quem ainda não tem cadastro.']));
add(CAIXA('atencao', 'Cinco tentativas erradas seguidas bloqueiam a conta por alguns minutos. Se esquecer a senha, peça ao **administrador** para redefini-la; no próximo acesso o sistema pede que você escolha uma senha nova.'));
add(H2('2.2 Criar a conta (primeiro acesso)'));
add(P('Quem ainda não tem conta usa a aba **Criar conta**. O cadastro fica **pendente** até o administrador aprovar.'));
add(...OL(['Abra a aba **Criar conta**.', 'Preencha NIP (somente números), OM, nome completo, nome de guerra, posto ou graduação, especialidade (opcional), e-mail, ramal e celular com DDD.',
  'Escolha uma senha (mínimo de 8 caracteres).', 'Clique em **Solicitar cadastro** e aguarde a aprovação do administrador.']));
add(...FIG('02-criar-conta', 'Formulário de criação de conta.'));
add(CAIXA('dica', 'Depois de aprovado, o próximo passo é **cadastrar o seu PIN** em **Minha conta** (seção 2.5) e, se for militar de uma escala, **pedir o vínculo** ao seu nome (capítulo 5).'));

add(H2('2.3 O menu e o painel inicial'));
add(P('Depois de entrar, você chega ao **Painel**. O menu fica na lateral esquerda e é organizado em grupos. Os números entre parênteses mostram **quantas pendências** esperam por você (por exemplo, “Papeletas (1)” ou “Assinar documentos (2)”).'));
add(...FIG('03-painel', 'Painel inicial, com o menu lateral à esquerda.'));
add(TAB(['Grupo do menu', 'Páginas'], [
  ['**Início**', 'Painel.'],
  ['**Operação**', 'Prévia da escala · Papeletas · Devoluções · Vínculos.'],
  ['**Documentos**', 'Detalhe de serviço · Detalhe unificado · Regras da escala · Assinar documentos · Verificar documento.'],
  ['**Minhas escalas**', 'Gerenciar escalas · Importar planilha · Buscar escalas.'],
  ['**Gestão** (detalhista/auxiliar)', 'Militares · Lançamentos · Calendário da escala · Pedidos de acesso.'],
  ['**Administração** (administrador)', 'Usuários.'],
  ['**Conta**', 'Notificações · Minha conta.'],
], [3000, 6638]));
add(SPACER());
add(P('Você só vê as páginas que o seu perfil permite. Um militar comum, por exemplo, não vê o grupo **Gestão**.'));
add(...FIG('03b-painel-conteudo', 'O painel resume o que precisa da sua atenção, quem está de serviço hoje, os seus próximos serviços e a atividade recente.'));
add(UL(['**Cartões do topo:** pedidos de troca e de vínculo aguardando a sua decisão, serviços a devolver e conflitos na escala.',
  '**Precisa da sua atenção:** a lista do que depende de você agora.', '**Hoje:** quem está de serviço (nomes em destaque) e de retém (**RT**) em cada escala.',
  '**Meus próximos serviços:** os dias em que você está escalado.', '**Atividade recente:** os avisos mais novos; **Ver todas as notificações** abre a página Notificações.']));

add(H2('2.4 Notificações'));
add(P('O sistema avisa você quando algo acontece: pedido de troca, decisão do detalhista, vínculo aprovado, documento para assinar, assinatura feita, rejeição de documento etc. '
  + 'O número ao lado de **Notificações** no menu mostra os avisos novos.'));
add(...FIG('27-notificacoes', 'Página Notificações.'));
add(UL(['Use **Marcar todas como lidas** para limpar o contador.', 'Cada aviso mostra data e hora (horário de Brasília).']));

add(H2('2.5 Minha conta, senha e PIN'));
add(...FIG('28-minha-conta', 'Página Minha conta.'));
add(UL(['**Meus dados e Contato:** nome, nome de guerra, posto, especialidade, OM, e-mail, ramal e celular. Esses dados aparecem nos documentos.',
  '**Senha:** troque informando a senha atual e a nova (mínimo de 8 caracteres).',
  '**PIN de assinatura:** de 4 a 6 números. Para cadastrar ou trocar, informe a **senha da conta** e o PIN novo.',
  '**Vínculo:** mostra a que militar a sua conta está ligada.']));
add(CAIXA('importante', '**Esqueceu o PIN?** Você mesmo cadastra outro em **Minha conta**: basta informar a senha da conta. Se também esqueceu a senha, o **administrador apaga o PIN** (ele nunca define nem vê o PIN de ninguém) e você escolhe um novo. As assinaturas já feitas continuam valendo.'));
add(CAIXA('atencao', 'Cinco erros de PIN seguidos bloqueiam a conta por 5 minutos. Nunca informe o seu PIN a outra pessoa: ele equivale à sua assinatura.'));

// 3 ---------------------------------------------------------------
add(H1('3. Prévia da escala'));
add(P('A **Prévia da escala** é a página principal de acompanhamento: mostra, dia a dia, quem está de **serviço**, de **retém**, de férias, dispensado etc. na escala escolhida.'));
add(H2('3.1 Escolher a escala e o período'));
add(UL(['**Escala:** escolha no seletor (você vê as escalas a que tem acesso).', '**Início:** a data da primeira coluna (por padrão, hoje). A data acompanha a virada do dia.',
  '**Período:** 7 dias, 15 dias ou 1 mês.', 'Na tabela, **role para a esquerda** para ver os dias que já passaram (até 14 dias antes do início). Os nomes dos militares ficam fixos enquanto você rola.']));
add(...FIG('04-previa', 'Prévia da escala: botão PDF, painel de números, tabela do período e legenda.',
  ['Botão **PDF**: baixa a prévia em PDF no tema do sistema.', 'Painel de números: **ritmo de hoje**, pessoas na escala, impedidos e disponíveis.']));
add(H2('3.2 Como ler a tabela'));
add(TAB(['Sigla / cor', 'Significado'], [
  ['**SVÇ** (verde)', 'Serviço (efetivo).'], ['**RT** (cinza)', 'Retém: militar de reserva do dia.'],
  ['**SVÇ (TF)** / **RT (TF)** (dourado)', 'Serviço ou retém por **troca forçada** (feita pelo detalhista).'], ['**SVÇ (T)** (marrom)', 'Serviço por **troca consensual** (papeleta).'],
  ['**Férias** (vermelho)', 'Militar de férias.'], ['**Disp** (verde-água)', 'Dispensado (baixa, falta ou dispensa).'], ['**DBQ** (preto)', 'Desembarque.'],
  ['**Curso** (azul)', 'Em curso.'], ['**DTQ** (roxo)', 'Destaque (em comissão em outra OM).'],
  ['Cabeçalho **vermelho**', 'Sábado, domingo, feriado ou dia sem expediente.'], ['Dia hachurado', 'A escala não guarnece naquele dia.'],
], [3200, 6438]));
add(SPACER());
add(P('Embaixo da tabela, **Observações** lista as trocas, dispensas e justificativas do período.'));
add(H2('3.3 O painel de números (saúde da escala)'));
add(UL(['**Ritmo hoje (N×1):** quantos militares disponíveis existem para cada vaga de serviço **hoje**, já descontando quem está impedido. Exemplo: 5×1 significa que cada um volta a servir, em média, a cada 5 dias.',
  '**Pessoas na escala / Impedidos hoje / Disponíveis hoje:** os números que dão base ao ritmo.',
  'O painel avisa em vermelho se o ritmo ficou **abaixo do mínimo** da escala e mostra o pior dia do período e os impedidos por motivo (férias, curso, dispensa…).']));
add(CAIXA('dica', 'O ritmo ajuda a decidir se dá para conceder férias ou dispensas sem sobrecarregar os demais: se ele cair abaixo do mínimo da escala, cada militar vai servir com menos folga do que as regras preveem.'));
add(H2('3.4 Pedir troca e sinalizar disponibilidade'));
add(P('Logo abaixo da tabela ficam os dois formulários da página. Você também pode **clicar numa célula** da tabela: no seu serviço, abre a disponibilidade; no serviço de um colega, preenche o pedido de troca.'));
add(...FIG('04b-previa-troca', 'Formulários “Pedir troca de serviço” e “Disponibilidade de troca”.'));
add(H3('Pedir troca de serviço'));
add(...OL(['Escolha **quem pede** a troca e o **dia do serviço dele**.', 'Escolha **com quem** trocar e o **dia do serviço do outro**.',
  'Escreva o **motivo** (obrigatório). O sistema confere antecedência mínima, descanso e impedimentos e mostra avisos em vermelho ou amarelo.',
  'Digite o seu **PIN** e clique em **Confirmar e gerar papeleta**. A papeleta é criada e segue o fluxo do capítulo 4.']));
add(H3('Disponibilidade de troca'));
add(P('Se você quer trocar o seu serviço, escolha o militar e o dia e clique em **Abrir disponibilidade de troca**. Uma **bolinha piscando** aparece na célula da prévia para os colegas. Clique em **Fechar disponibilidade** quando não precisar mais.'));
add(...FIG('05-previa-militar', 'A mesma página vista por um militar comum (somente o que ele pode fazer).'));
add(H2('3.5 PDF da prévia'));
add(P('O botão **PDF** (no topo) gera um documento em A4 paisagem com o painel de saúde da escala, a tabela com as mesmas cores da tela, a legenda e as observações.'));
add(...FIG('pdf-previa', 'Primeira página do PDF da prévia.'));

// 4 ---------------------------------------------------------------
add(H1('4. Trocas de serviço: papeletas e devoluções'));
add(H2('4.1 O caminho de uma papeleta'));
add(P('Toda troca passa por quatro etapas, mostradas numa linha do tempo em cada papeleta:'));
add(TAB(['Etapa', 'O que acontece', 'Quem age'], [
  ['**1 · Pedido**', 'A papeleta é criada (pedido **pendente**). Os dois militares ficam “travados”: não entram em outro pedido.', 'Quem pede, com o PIN'],
  ['**2 · Decisão**', 'O detalhista (ou o auxiliar) **aprova** ou **rejeita**. Aprovada, a prévia já mostra a troca.', 'Detalhista / auxiliar'],
  ['**3 · Assinaturas**', 'Cada militar envolvido **assina com o PIN** (ou registra assinatura externa).', 'Os dois militares'],
  ['**4 · Confirmada**', 'Com as assinaturas feitas, o detalhista **confirma** e a papeleta fica concluída.', 'Detalhista'],
], [2000, 5438, 2200]));
add(SPACER());
add(...FIG('06-papeletas', 'Página Papeletas: filtros por situação e a linha do tempo de cada papeleta.'));
add(H2('4.2 O que cada pessoa faz'));
add(H3('Se você é uma das partes da troca'));
add(...OL(['Abra **Papeletas** e localize a papeleta (filtro **Em andamento**).', 'Clique em **Assinar com PIN**, digite o PIN e confirme. A data, a hora e o código do documento ficam registrados.',
  'Se não puder assinar pelo sistema, use **Assinatura externa** para registrar a assinatura feita em papel.']));
add(H3('Se você é o detalhista ou o auxiliar'));
add(...OL(['Filtre por **Aguardando decisão**.', 'Confira a papeleta e clique em **Aprovar e trocar** ou em **Rejeitar** (a rejeição exige o motivo). Ao aprovar, a prévia já mostra a troca.',
  'Quando as duas partes tiverem assinado, clique em **Confirmar**.', 'Se necessário, use **Cancelar pedido** (enquanto pendente) ou **Cancelar troca** (informando o motivo, se já estiver confirmada). O botão **PDF** da papeleta baixa o documento.']));
add(CAIXA('nota', 'Ninguém decide a própria papeleta. Se você é parte da troca, outra pessoa com poder de decisão precisa aprová-la.'));
add(H2('4.3 Devoluções'));
add(P('Quem foi **dispensado de um serviço** em que estava escalado pode **devolvê-lo** em outro dia, dentro do prazo, assumindo o serviço de um colega. A página **Devoluções** lista os serviços a devolver.'));
add(...FIG('07-devolucoes', 'Página Devoluções.'));
add(UL(['O sistema sugere os dias possíveis (dentro do prazo e respeitando o descanso). Escolha em **Devolver em** e clique em **Pedir devolução**.',
  'A devolução gera uma papeleta que segue o mesmo caminho: decisão do detalhista, assinaturas e confirmação.']));

// 5 ---------------------------------------------------------------
add(H1('5. Vínculos: ligar a conta ao nome na escala'));
add(P('O **vínculo** liga a sua conta ao **seu nome** na escala. Ele é necessário para pedir trocas, assinar papeletas e ver as escalas em que você está. Há dois caminhos.'));
add(H2('5.1 Pedir o vínculo (militar)'));
add(...OL(['O detalhista **compartilha a escala** com a sua conta (ou você pede acesso em **Buscar escalas**, capítulo 8).', 'Abra **Vínculos**, escolha a **escala** e **quem é você** na lista.',
  'Informe o NIP e, se ainda não tiver, crie o PIN. Clique em **Pedir vínculo**.', 'Aguarde o detalhista aprovar. Você recebe um aviso com a decisão.']));
add(CAIXA('dica', '**O detalhista também se vincula ao próprio nome.** Como não há ninguém acima para aprovar, o vínculo do detalhista é aprovado na hora. Quem já tem PIN cadastrado não precisa criar outro.'));
add(H2('5.2 Decidir os pedidos (detalhista e auxiliar)'));
add(...FIG('08-vinculos', 'Página Vínculos, com o pedido aguardando decisão e a opção de convidar um usuário.'));
add(UL(['Confira nome, NIP e contato e clique em **Aprovar vínculo** ou em **Rejeitar** (informando o motivo).',
  '**Convidar um usuário:** pesquise quem já tem conta, escolha o militar da escala e envie o convite; a pessoa confirma com o NIP e o PIN dela e o vínculo vale na hora.']));

// 6 ---------------------------------------------------------------
add(H1('6. Detalhe de serviço e assinatura eletrônica'));
add(P('O **detalhe de serviço** é o documento oficial da escala: quem está de serviço e de retém em cada dia, com instruções, recomendações, regras e as assinaturas das autoridades. '
  + 'O sistema gera o PDF e permite que as autoridades o **assinem eletronicamente**.'));
add(H2('6.1 Preparar o detalhe'));
add(P('Abra **Documentos → Detalhe de serviço**. A página tem uma coluna de edição (esquerda) e um resumo do período com os botões de PDF e assinatura (direita).'));
add(...FIG('09-detalhe-servico', 'Detalhe de serviço: edição do cabeçalho, textos, assinaturas e resumo do período.',
  ['**Brasão do documento:** padrão são as Armas Nacionais; o detalhista pode trocar pelo brasão da OM.', 'Botões dos **textos** do documento (instruções, recomendações e regras).',
   '**Quem assina com PIN** (Encarregado e Vice-Diretor).', 'Botão **Salvar OM, nomes e quem assina**.', '**PDF sem assinatura**: baixa o documento a qualquer momento.']));
add(H3('Cabeçalho e brasão'));
add(UL(['Informe a **OM** que aparece no cabeçalho do documento (ou cadastre em **Gerenciar escalas**).',
  'Para trocar o brasão: escolha o arquivo (PNG, JPG, WEBP, BMP, GIF ou TIFF), clique em **Usar este brasão**. Marque **Usar também nestes detalhes meus** para aplicar a outras escalas em que você é detalhista. **Voltar ao padrão** restaura as Armas Nacionais.',
  'Só o **detalhista da escala** troca o brasão.']));
add(H3('Instruções, recomendações e regras'));
add(P('Clique no botão de cada texto para abrir uma janela com o **editor**: negrito, itálico, sublinhado, listas com marcadores, listas numeradas, desfazer, refazer e limpar formatação. O botão **Salvar** fica dentro da janela.'));
add(...FIG('10-editor', 'Janela de edição de texto (exemplo: Instruções do serviço).'));
add(UL(['O texto sai no PDF com a mesma formatação, em letras pequenas.', 'Ao colar texto de outro programa, o sistema cola como texto simples (para não trazer formatações indesejadas).']));
add(H3('Nomes das autoridades e quem assina'));
add(UL(['Os **quatro campos de nome** (Detalhista, Auxiliar, Encarregado, Vice-Diretor) saem impressos abaixo da linha de assinatura.',
  'Em **Quem assina com PIN**, escolha as **contas** do Encarregado do Detalhe e do Vice-Diretor. Elas passam a receber o documento para assinar. Cada uma precisa ter o **PIN cadastrado**.',
  'O **detalhista** (você) e o **auxiliar** indicado na escala assinam pelos seus papéis automaticamente.', 'Clique em **Salvar OM, nomes e quem assina**.']));
add(CAIXA('nota', 'Se você ainda não designou o Encarregado ou o Vice-Diretor, o documento continua válido: eles assinam à mão no papel.'));

add(H2('6.2 O fluxo da assinatura eletrônica'));
add(P('O documento é **congelado** na hora do envio: as autoridades assinam exatamente o que está no PDF, mesmo que a escala mude depois.'));
add(TAB(['Passo', 'Quem', 'O que faz'], [
  ['**1 · Enviar**', 'Detalhista', 'Clica em **Enviar para assinatura**. O conteúdo é congelado e as demais autoridades recebem um aviso.'],
  ['**2 · Conferir e assinar**', 'Cada autoridade', 'Abre **Assinar documentos**, confere o conteúdo, digita o PIN e clica em **Assinar como …**.'],
  ['**3 · Acompanhar**', 'Detalhista', 'Vê quem já assinou e baixa o PDF com as assinaturas existentes, quando quiser.'],
  ['**4 · Verificar**', 'Qualquer pessoa', 'Lê o QR code do PDF e confere a autenticidade (sem login).'],
], [2400, 2000, 5238]));
add(SPACER());
add(H3('Enviar para assinatura (detalhista)'));
add(...OL(['Deixe o documento como quer que seja assinado (período, textos, nomes e quem assina).', 'Clique em **Enviar para assinatura**.',
  'A página mostra uma situação para cada autoridade: **assinou** (em verde) ou **pendente** (em amarelo).']));
add(UL(['**PDF sem assinatura:** sempre disponível.', '**PDF com as assinaturas já feitas (n de 4):** pode ser baixado a qualquer momento, mesmo que só uma ou duas autoridades tenham assinado.',
  '**Cancelar este envio:** retira o documento da fila de todos.']));
add(CAIXA('atencao', 'Se você **alterar** a escala, o período, um texto ou um nome **depois** do envio, o sistema avisa que o documento mudou. Envie de novo: as assinaturas da versão anterior não valem para a nova. Depois de **cancelar** ou de uma **rejeição**, um novo envio — mesmo sem mudança — **sempre exige assinar de novo**.'));
add(H2('6.3 Assinar documentos (autoridades)'));
add(P('O menu mostra **Assinar documentos (n)** com o número de documentos esperando a sua assinatura, e você recebe uma notificação a cada envio.'));
add(...FIG('13-assinar', 'Página Assinar documentos, vista por uma autoridade.',
  ['**Filtros** (Mostrar, escala/documento e busca).', '**Conferir o conteúdo do documento**: tabela de escalados, textos e observações.', 'Campo do **PIN**.',
   'Botão **Assinar como …** (o papel que você tem neste documento).', 'Botão **Rejeitar este documento**.']));
add(...OL(['Abra **Assinar documentos** (já abre em **Aguardando minha assinatura**).', 'Clique em **Conferir o conteúdo do documento** e leia o que está sendo assinado.',
  'Digite o seu **PIN** e clique em **Assinar como …**.', 'Pronto: o documento sai de “aguardando” e o detalhista é avisado.']));
add(H3('Filtros da página'));
add(UL(['**Aguardando minha assinatura** (padrão quando há pendência) · **Assinados por mim** · **Com as 4 assinaturas** · **Cancelados / rejeitados** · **Todos**.',
  '**Escala / documento:** mostra só um documento. **Buscar:** por título, data (ex.: 15/11) ou motivo de rejeição.']));
add(...FIG('14-assinar-detalhista', 'O detalhista também assina o próprio detalhe pela mesma página.'));
add(H3('Rejeitar um documento'));
add(P('Se o documento tem algum erro, **rejeite** em vez de assinar. A **justificativa é obrigatória**: o botão só habilita depois que você escrever o motivo.'));
add(...FIG('15-rejeitar', 'Janela de rejeição: o motivo é obrigatório.'));
add(UL(['O envio é encerrado e o **detalhista recebe uma notificação com o seu motivo** (que também aparece em destaque na página dele).',
  'As assinaturas já feitas naquele envio deixam de valer. O detalhista corrige e **envia de novo**; todos assinam outra vez.',
  'Quem enviou o documento não rejeita; usa **Cancelar este envio**.']));
add(...FIG('15b-assinar-encerrados', 'Filtro “Cancelados / rejeitados”: o histórico mostra quem rejeitou e por quê.'));

add(H2('6.4 O PDF assinado'));
add(...FIG('pdf-detalhe_assinado', 'Detalhe de serviço em PDF, página 1: cabeçalho oficial, tabela dos dias e textos do documento.'));
add(P('A área de **assinaturas** vem logo depois dos textos (na página seguinte, quando as instruções ocupam a primeira). Veja abaixo o mesmo documento com **as quatro autoridades** já assinadas:'));
add(...FIG('pdf-ampl_detalhe_assinado', 'Área de assinaturas com as quatro autoridades: carimbos eletrônicos, QR code e código de verificação.'));
add(UL(['**Carimbo eletrônico** acima de cada nome: “Assinado eletronicamente com PIN”, **nome completo**, NIP, data e hora (horário de Brasília).',
  '**Nome impresso e papel** abaixo da linha: Detalhista, Auxiliar do Detalhista e Encarregado do Detalhe lado a lado; o **Vice-Diretor** centralizado embaixo.',
  '**QR code e código de verificação (SHA-256)**: leia o QR com o celular ou digite o código em Verificar documento.']));
add(P('Quando o documento tem **uma só assinatura**, o QR code passa para o **lado do carimbo**, e o código de verificação fica centralizado logo abaixo:'));
add(...FIG('pdf-ampl_detalhe_uma_assinatura', 'Documento com apenas uma assinatura (a do detalhista): o QR code fica ao lado do carimbo.'));
add(UL(['**Cabeçalho oficial** centralizado: brasão, MARINHA DO BRASIL, a OM e o título (“DETALHE DE SERVIÇO DE …”).',
  '**Carimbo** de cada autoridade que assinou: nome completo, NIP, data e hora (horário de Brasília). Quem ainda não assinou fica com a linha em branco.',
  'Os três primeiros papéis ficam lado a lado e o **Vice-Diretor** fica centralizado abaixo.',
  '**QR code e código de verificação** (SHA-256): com **uma só assinatura** o QR fica ao lado do carimbo; com **duas ou mais**, abaixo das assinaturas.']));

add(H2('6.5 Verificar a autenticidade'));
add(P('Qualquer pessoa pode conferir o documento: leia o **QR code** com o celular. A página de verificação abre **sem login** com o código já preenchido.'));
add(...FIG('17-verificar-publica', 'Verificação pública (aberta pelo QR code, sem login).'));
add(UL(['Mostra se a **assinatura é autêntica**, quem assinou (nome e papel), data e hora, a escala, o período e a OM.',
  'Por privacidade, a consulta pública **não mostra o NIP nem o conteúdo** do documento.',
  'Se o envio foi **cancelado, rejeitado ou substituído**, a página avisa em destaque que o documento não vale mais.']));
add(P('Quem tem conta usa **Documentos → Verificar documento** e vê também o **conteúdo assinado** (tabela de escalados, textos e observações) para comparar com o papel.'));
add(...FIG('16-verificar-logado', 'Verificar documento (usuário logado): mostra também o conteúdo assinado.'));
add(CAIXA('nota', 'A verificação prova que **o código foi emitido pelo sistema**, por quem e quando, e que o conteúdo gravado não foi alterado. Para saber se o PDF em mãos é o mesmo, compare-o com o conteúdo mostrado na verificação logada.'));
add(CAIXA('importante', 'Trata-se de **assinatura eletrônica simples** (conta + PIN), adequada a documentos internos e administrativos. Ela não substitui o certificado digital ICP-Brasil onde a norma o exigir.'));

add(H2('6.6 Detalhe unificado: várias escalas num só documento'));
add(P('É comum que o detalhe do dia reúna **várias escalas** (fiscal, sentinela, contramestre…) num único documento, com instruções, recomendações e regras **gerais**. Para isso existe **Documentos → Detalhe unificado**.'));
add(...FIG('12-detalhe-unificado', 'Detalhe unificado: escolha das escalas, textos gerais, quem assina e resumo.',
  ['Seletor do documento unificado.', 'Botão **Novo documento unificado**.', 'Escalas que o documento reúne (a ordem escolhida é a do documento).', 'Botão **Enviar para assinatura**.']));
add(...OL(['Clique em **Novo documento unificado**, dê um título (por exemplo, “Escala de Serviço do Dia”) e marque as escalas.', 'Preencha **OM**, **brasão** e os textos **gerais** (instruções, recomendações e regras).',
  'Em **Quem assina**, designe as contas do Auxiliar, do Encarregado e do Vice-Diretor e digite os nomes que saem impressos.', 'Clique em **Salvar documento**. Só depois de salvar o envio fica liberado.',
  'Escolha a **data e o período** no topo e clique em **Enviar para assinatura**. O restante (assinar, rejeitar, PDF parcial, QR code e verificação) é igual ao detalhe de uma escala.']));
add(...FIG('pdf-unificado', 'PDF do documento unificado de um dia: uma linha por escala, regras gerais e assinaturas.'));
add(UL(['**Um dia:** uma tabela com uma linha por escala (Serviço, Escalados e Retém). **Vários dias:** uma tabela por escala.',
  'O documento fica **salvo**: no dia seguinte basta mudar a data de início e enviar de novo.', 'Você só reúne escalas em que é **detalhista ou auxiliar**.']));

add(H2('6.7 Regras da escala'));
add(P('A página **Regras da escala** explica, em linguagem simples, **como a escala funciona**: quem entra, ordem da fila, descanso, quartos, retém, trocas e o que é configurável ou fixo no sistema. '
  + 'Há também o botão para baixar essas regras em PDF, útil para divulgar aos militares.'));
add(...FIG('18-regras', 'Página Regras da escala.'));

// 7 ---------------------------------------------------------------
add(H1('7. Gestão da escala (detalhista e auxiliar)'));
add(H2('7.1 Gerenciar escalas'));
add(...FIG('19-gerenciar-escalas', 'Gerenciar escalas: um cartão por escala, com as ações do detalhista.'));
add(UL(['**Nova escala:** informe nome, tipo, categoria, OM, modo (corrida, preta e vermelha, por evento), dias de funcionamento, quantos escalados e retém por dia, descanso mínimo (2×1), quartos e antecedência mínima da papeleta.',
  '**Editar** as regras, **Ponto de partida da fila** (diz ao sistema onde a escala está hoje e quem está de serviço), **Compartilhar** (dar acesso de leitura a outra conta) e **Excluir**.',
  '**Entregar o detalhe:** passa a responsabilidade a outra pessoa (é preciso designar o novo detalhista).']));
add(...FIG('20-nova-escala', 'Janela “Nova escala”.'));
add(CAIXA('importante', '**Detalhista × vínculo com um militar.** O **detalhista** é sempre a **conta** que responde pela escala (quem a criou): ela **não se remove**, só passa para outra pessoa em **Entregar o detalhe**. O **vínculo com um militar da lista** é **opcional** e só serve para o detalhista ficar fora da escala; “nenhum” não tira o detalhista, só diz que ele não é um dos militares listados.'));
add(H2('7.2 Militares da escala'));
add(...FIG('21-militares', 'Militares da escala e a ordem de antiguidade.'));
add(UL(['**Cadastrar e incluir:** cadastre um militar novo (só o nome é obrigatório) e ele já entra na escala.', '**Incluir quem já está cadastrado** em outra escala sua.',
  '**Antiguidade:** vale só dentro da escala (1 é o mais antigo). Arraste os nomes para reordenar.', '**Retirar da escala:** agora ou a partir de uma data; o militar continua cadastrado.']));
add(H2('7.3 Lançamentos: dispensas e impedimentos'));
add(P('Registre aqui o que tira um militar do serviço ou altera a escala: **férias, curso, dispensa, desembarque, destaque**, além de guarnecimento e eventos.'));
add(...FIG('22-lancamentos', 'Página Lançamentos.'));
add(...OL(['Escolha a **escala**, depois **o que lançar** e o **militar**.', 'Informe o **período** e o **motivo**. A **dispensa** com documento exige o arquivo/anexo; a justificada exige a justificativa do detalhista.',
  'Clique em **Salvar lançamento**: o militar passa a **Disp** (ou à situação escolhida), o retém avança e a prévia e o detalhe se reconfiguram.']));
add(UL(['A lista de lançamentos permite **editar** e **remover** (com confirmação). Cada lançamento guarda quem lançou e quando.', 'O auxiliar lança nas escalas em que auxilia, menos para si mesmo.']));
add(H2('7.4 Calendário da escala'));
add(...FIG('23-calendario', 'Calendário da escala: feriados, licenças e períodos roxos.'));
add(UL(['Cadastre **feriados, licenças administrativas, pontos facultativos e períodos roxos** e diga **como o dia conta** na fila: **preta** = dia útil · **vermelha** = sábado, domingo, feriado e dia sem expediente · **roxa** = período especial.',
  'O botão **Feriados oficiais e pontos facultativos do ano** sugere as datas para começar.']));
add(H2('7.5 Importar planilha'));
add(...FIG('24-importar', 'Importar planilha: envio, revisão e aplicação.'));
add(...OL(['Envie o arquivo **CSV ou XLSX**. Só o **nome de guerra** é obrigatório; as demais colunas (posto, especialidade, NIP, OM, escala, ordem) são opcionais.',
  'Indique a **ordem das linhas** (topo = mais antigo ou o contrário) e a **escala de destino**. Escolha **acrescentar** ou **substituir** os dados que já existem.',
  'Clique em **Revisar importação**, confira o relatório (quem entra, quem sai) e aplique.']));
add(H2('7.6 Pedidos de acesso e busca de escalas'));
add(...FIG('26-pedidos-acesso', 'Pedidos de acesso às suas escalas (detalhista).'));
add(UL(['**Buscar escalas** (qualquer usuário): encontre a escala da sua OM e clique em **Pedir acesso**, com uma mensagem ao detalhista.', '**Pedidos de acesso** (detalhista): **Aprovar (leitura)** ou **Rejeitar** (com motivo).']));
add(...FIG('25-buscar', 'Buscar escalas.'));

// 8 ---------------------------------------------------------------
add(H1('8. Administração do sistema'));
add(P('A página **Usuários** é exclusiva do administrador.'));
add(...FIG('29-usuarios', 'Página Usuários: cadastros pendentes, lista de contas e gerenciamento de uma conta.'));
add(TAB(['Ação', 'Para que serve'], [
  ['**Aprovar / rejeitar cadastro**', 'Todo cadastro novo fica pendente até a aprovação.'],
  ['**Bloquear / desbloquear conta**', 'Impede ou libera o acesso de uma pessoa.'],
  ['**Redefinir senha**', 'Define uma senha provisória; a pessoa é obrigada a trocá-la no próximo acesso.'],
  ['**Redefinir PIN (esqueceu)**', '**Apaga** o PIN da conta e avisa a pessoa; ela cadastra um novo em Minha conta, confirmando com a senha. O administrador nunca define nem vê o PIN.'],
  ['**Desvincular do militar**', 'Desfaz o vínculo da conta (a conta perde o PIN e deixa de assinar por aquele militar).'],
  ['**Editar dados / Excluir conta**', 'Corrige nome, NIP, OM e contato; excluir exige antes passar as escalas da conta a outra pessoa.'],
], [3200, 6438]));
add(SPACER());
add(CAIXA('dica', 'Boas práticas: aprove cadastros somente depois de conferir o NIP e a OM; ao redefinir o PIN de alguém, avise a pessoa por outro meio para que ela cadastre um novo logo.'));
add(H2('8.1 Configuração do sistema'));
add(UL(['**Administrador inicial:** criado automaticamente na primeira execução, com NIP e senha vindos da configuração do servidor.',
  '**Horário:** o sistema usa o horário de Brasília em todas as telas e documentos.', '**Endereço do QR code:** é o da própria página; se sair errado no seu servidor, o responsável técnico define o endereço fixo na configuração.',
  '**Dados:** ficam em uma planilha Google (ou arquivo, no ambiente de testes); alterações simultâneas de pessoas diferentes são detectadas e o sistema recarrega a versão mais recente.']));

// 9 ---------------------------------------------------------------
add(H1('9. Perguntas frequentes e solução de problemas'));
add(TAB(['Situação', 'O que fazer'], [
  ['Esqueci o **PIN**.', 'Em **Minha conta**, informe a senha da conta e cadastre outro PIN. Se esqueceu também a senha, peça ao administrador.'],
  ['Esqueci a **senha**.', 'Peça ao administrador para redefinir; no próximo acesso você escolhe uma nova.'],
  ['Não consigo **assinar**: o botão está desabilitado.', 'Cadastre o PIN em Minha conta. Para rejeitar, escreva o motivo.'],
  ['A conta está **bloqueada**.', 'Cinco erros seguidos de senha ou PIN bloqueiam por alguns minutos. Aguarde ou peça ao administrador para desbloquear.'],
  ['Não vejo **o meu nome** na lista de “Quem é você”.', 'O militar precisa estar na escala. O detalhista também aparece na lista, só para ele mesmo.'],
  ['**Cancelei o envio** e enviei de novo: preciso assinar outra vez?', 'Sim. Cada envio recomeça sem assinaturas, com ou sem mudança no documento.'],
  ['O sistema avisa que o documento **mudou depois do envio**.', 'Envie de novo. As assinaturas da versão antiga não valem para a nova.'],
  ['Uma autoridade **rejeitou** o documento.', 'Leia o motivo na notificação (ou na página do detalhe), corrija e envie de novo.'],
  ['O **QR code** não abre a página.', 'Verifique se a internet do celular alcança o servidor do SisEscala (rede interna ou VPN, se for o caso). Digite o código do rodapé na página **Verificar documento**.'],
  ['O **brasão** não carrega.', 'Use PNG, JPG, WEBP, BMP, GIF ou TIFF. Arquivos de edição (PSD, AI, CDR, SVG) devem ser exportados para PNG. Se aparecer “detalhes demais”, use uma versão mais simples.'],
  ['O **horário** está errado.', 'O sistema usa o horário de Brasília. Registros muito antigos podem ter sido gravados 3 horas adiantados.'],
  ['A prévia mostra **CONFLITO**.', 'Um militar está escalado em duas escalas no mesmo dia sem troca possível. Resolva manualmente (troca forçada, lançamento ou ajuste das escalas).'],
], [3600, 6038]));

add(H1('10. Glossário e atalhos'));
add(TAB(['Termo', 'Definição'], [
  ['**Antiguidade**', 'Ordem de precedência dos militares dentro de uma escala (1 = mais antigo).'],
  ['**Guarnecimento**', 'Se a escala funciona ou não em determinado dia.'],
  ['**Ponto de partida**', 'Informa ao sistema quem está de serviço hoje, para a fila continuar dali.'],
  ['**Troca forçada (TF)**', 'Troca feita pelo detalhista por necessidade do serviço.'],
  ['**Troca consensual (T)**', 'Troca combinada entre os militares por papeleta.'],
  ['**Snapshot / congelamento**', 'Cópia do documento no momento do envio para assinatura; é o que as autoridades assinam.'],
  ['**SHA-256**', 'Código de 64 caracteres que identifica o conteúdo de um documento; qualquer alteração muda o código.'],
  ['**Assinatura eletrônica simples**', 'Assinatura feita dentro do sistema, com login e PIN, registrando quem, quando e o quê.'],
], [3000, 6638]));
add(SPACER(200));
add(P('__Manual gerado a partir da versão atual do SisEscala. Em caso de dúvida, procure o detalhista da sua escala ou o administrador do sistema.__', { run: { color: CINZA, size: 18 } }));

// ------------------------------------------------------------------ capa e sumário
const hoje = new Date();
const meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const dataExtenso = `${meses[hoje.getMonth()]} de ${hoje.getFullYear()}`;
const capa = [
  new Paragraph({ spacing: { before: 600, after: 0 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 }, children: [new ImageRun({ type: 'png', data: fs.readFileSync(LOGO), transformation: { width: 300, height: 152 }, altText: { title: 'SisEscala', description: 'Logotipo do SisEscala', name: 'logo' } })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400, after: 120 }, children: [new TextRun({ text: 'MANUAL DO USUÁRIO', bold: true, size: 56, color: NAVY, font: FONTE })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, border: { top: { style: BorderStyle.SINGLE, size: 18, color: OURO, space: 8 } }, spacing: { before: 120, after: 200 },
    children: [new TextRun({ text: 'Sistema de Escalas de Serviço e Eventos', size: 30, color: CINZA, font: FONTE })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: 'Escalas · Papeletas · Detalhe de serviço · Assinatura eletrônica', size: 22, color: CINZA, font: FONTE })] }),
  new Paragraph({ spacing: { before: 2600 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Escalas e Eventos Sempre em Ordem', italics: true, size: 24, color: OURO, font: FONTE })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200 }, children: [new TextRun({ text: dataExtenso.charAt(0).toUpperCase() + dataExtenso.slice(1), size: 22, color: CINZA, font: FONTE })] }),
];
const sumario = [
  new Paragraph({ pageBreakBefore: true, spacing: { after: 240 }, children: [new TextRun({ text: 'Sumário', bold: true, size: 36, color: NAVY, font: FONTE })] }),
  ...titulos.map(([nivel, t]) => new Paragraph({
    spacing: { after: nivel === 1 ? 100 : 40, before: nivel === 1 ? 120 : 0 }, indent: { left: nivel === 1 ? 0 : 360 },
    tabStops: [{ type: TabStopType.RIGHT, position: LARG, leader: 'dot' }],
    children: [new TextRun({ text: t, bold: nivel === 1, size: nivel === 1 ? 22 : 20, font: FONTE }), new TextRun({ text: '\t' + (PAGINAS[t] ?? ''), size: nivel === 1 ? 22 : 20, font: FONTE })],
  })),
];

const doc = new Document({
  creator: 'SisEscala', title: 'Manual do Usuário – SisEscala', description: 'Manual do usuário do SisEscala',
  styles: {
    default: { document: { run: { font: FONTE, size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONTE, size: 36, bold: true, color: NAVY },
        paragraph: { spacing: { before: 0, after: 200 }, keepNext: true, outlineLevel: 0, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: OURO, space: 4 } } } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONTE, size: 28, bold: true, color: NAVY }, paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONTE, size: 24, bold: true, color: '2F5D8A' }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [
    { reference: 'marcadores', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } }, run: { color: OURO } } }] },
    ...numeracoes,
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 } }, titlePage: true },
    headers: { default: new Header({ children: [new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: OURO, space: 4 } },
      children: [new TextRun({ text: 'SisEscala — Manual do Usuário', size: 18, color: CINZA, font: FONTE })] })] }), first: new Header({ children: [new Paragraph({ children: [] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: 'Página ', size: 18, color: CINZA, font: FONTE }), new TextRun({ children: [PageNumber.CURRENT], size: 18, color: CINZA, font: FONTE })] })] }), first: new Footer({ children: [new Paragraph({ children: [] })] }) },
    children: [...capa, ...sumario, ...corpo],
  }],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(SAIDA, buf); console.log('ok', SAIDA, `${(buf.length / 1024 / 1024).toFixed(1)} MB`, 'títulos:', titulos.length, 'figuras:', nFig); fs.writeFileSync(SAIDA + '.titulos.json', JSON.stringify(titulos)); });

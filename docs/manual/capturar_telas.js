// Captura as telas do manual com o sistema rodando em http://localhost:8599 (dados de seed_manual.py).
// Uso: node docs/manual/capturar_telas.js <pasta_de_saida> <codigo_de_verificacao>
const { chromium } = require('playwright');
const fs = require('fs');
const SAIDA = process.argv[2] || 'telas';
const CODIGO = process.argv[3] || '';
const URL = 'http://localhost:8599';
const SENHA = 'Manual@2026';
fs.mkdirSync(SAIDA, { recursive: true });

async function entrar(page, nip) {
  await page.goto(URL); await page.waitForTimeout(4500);
  await page.getByLabel('NIP', { exact: true }).fill(nip);
  await page.getByLabel('Senha', { exact: true }).first().fill(SENHA);
  await page.getByRole('button', { name: 'Entrar' }).click(); await page.waitForTimeout(4500);
}
async function ir(page, texto) {
  await page.getByText(texto, { exact: false }).first().click(); await page.waitForTimeout(5000);
}
// números vermelhos sobre os elementos (legenda no texto do manual)
async function marcar(page, itens) {
  for (const [alvo, n, dx, dy] of itens) {
    let loc = typeof alvo === 'string' ? page.getByText(alvo, { exact: false }).first() : alvo;
    try {
      const box = await loc.boundingBox({ timeout: 2500 });
      if (!box) continue;
      await page.evaluate(([x, y, n]) => {
        const d = document.createElement('div');
        d.textContent = n; d.className = '__mk';
        d.style.cssText = `position:fixed;left:${x}px;top:${y}px;width:26px;height:26px;border-radius:50%;background:#D64545;color:#fff;
          font:700 15px Inter,Arial;display:flex;align-items:center;justify-content:center;z-index:99999;border:2px solid #fff;
          box-shadow:0 2px 6px rgba(0,0,0,.5)`;
        document.body.appendChild(d);
      }, [Math.max(2, box.x + (dx ?? -30)), Math.max(2, box.y + (dy ?? -12)), n]);
    } catch (e) { console.log('sem alvo', alvo, e.message.split('\n')[0]); }
  }
}
async function foto(page, nome) {
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${SAIDA}/${nome}.png` });
  await page.evaluate(() => document.querySelectorAll('.__mk').forEach(e => e.remove()));
  console.log('ok', nome);
}

(async () => {
  const b = await chromium.launch();
  const novo = async (alt = 1000) => { const ctx = await b.newContext({ viewport: { width: 1400, height: alt }, deviceScaleFactor: 1 }); return ctx.newPage(); };

  // ---------- sem login
  let p = await novo(820);
  await p.goto(URL); await p.waitForTimeout(5000);
  await marcar(p, [[p.getByLabel('NIP', { exact: true }), 1], [p.getByLabel('Senha', { exact: true }).first(), 2],
                   [p.getByRole('button', { name: 'Entrar' }), 3], [p.getByRole('tab', { name: 'Criar conta' }), 4]]);
  await foto(p, '01-login');
  await p.getByRole('tab', { name: 'Criar conta' }).click(); await p.waitForTimeout(1200);
  await foto(p, '02-criar-conta');
  await p.goto(`${URL}/verificar?codigo=${CODIGO}`); await p.waitForTimeout(6000);
  await foto(p, '17-verificar-publica');
  await p.context().close();

  // ---------- detalhista
  p = await novo(1500);
  await entrar(p, '20000001');
  await foto(p, '03-painel');
  await ir(p, 'Prévia da escala');
  await marcar(p, [[p.getByRole('button', { name: 'PDF' }).first(), 1], [p.getByText('Ritmo hoje'), 2], [p.getByText('Escala').first(), 3]]);
  await foto(p, '04-previa');
  await ir(p, 'Papeletas'); await foto(p, '06-papeletas');
  await ir(p, 'Devoluções'); await foto(p, '07-devolucoes');
  await ir(p, 'Vínculos'); await foto(p, '08-vinculos');
  await ir(p, 'Detalhe de serviço');
  await marcar(p, [[p.getByText('Brasão do documento'), 1], [p.getByRole('button', { name: /Instruções do serviço/ }).first(), 2],
                   [p.getByText('Quem assina com PIN'), 3], [p.getByRole('button', { name: /Salvar OM/ }), 4],
                   [p.getByRole('button', { name: 'PDF sem assinatura' }), 5]]);
  await foto(p, '09-detalhe-servico');
  await p.getByRole('button', { name: /Instruções do serviço/ }).first().click(); await p.waitForTimeout(3500);
  await foto(p, '10-editor');
  await p.locator('[data-testid="stDialog"] button[aria-label="Close"]').first().click(); await p.waitForTimeout(1000);
  await ir(p, 'Detalhe unificado');
  await marcar(p, [[p.getByText('Documento unificado').first(), 1], [p.getByText('Novo documento unificado'), 2],
                   [p.getByText('Escalas que o documento reúne'), 3], [p.getByRole('button', { name: 'Enviar para assinatura' }), 4]]);
  await foto(p, '12-detalhe-unificado');
  await ir(p, 'Regras da escala'); await foto(p, '18-regras');
  await ir(p, 'Assinar documentos'); await foto(p, '14-assinar-detalhista');
  await ir(p, 'Verificar documento');
  await p.getByLabel('Código').fill(CODIGO); await p.keyboard.press('Enter'); await p.waitForTimeout(3500);
  await foto(p, '16-verificar-logado');
  await ir(p, 'Gerenciar escalas'); await foto(p, '19-gerenciar-escalas');
  await p.getByRole('button', { name: /Nova escala/ }).first().click().catch(() => {}); await p.waitForTimeout(2500);
  await foto(p, '20-nova-escala'); await p.locator('[data-testid="stDialog"] button[aria-label="Close"]').first().click().catch(() => {}); await p.waitForTimeout(800);
  await ir(p, 'Militares'); await foto(p, '21-militares');
  await ir(p, 'Lançamentos'); await foto(p, '22-lancamentos');
  await ir(p, 'Calendário da escala'); await foto(p, '23-calendario');
  await ir(p, 'Importar planilha'); await foto(p, '24-importar');
  await ir(p, 'Buscar escalas'); await foto(p, '25-buscar');
  await ir(p, 'Pedidos de acesso'); await foto(p, '26-pedidos-acesso');
  await ir(p, 'Notificações'); await foto(p, '27-notificacoes');
  await ir(p, 'Minha conta'); await foto(p, '28-minha-conta');
  await p.context().close();

  // ---------- encarregado (autoridade que assina)
  p = await novo(1250);
  await entrar(p, '20000003');
  await ir(p, 'Assinar documentos');
  await marcar(p, [[p.getByText('Mostrar').first(), 1], [p.getByText('Conferir o conteúdo do documento'), 2],
                   [p.getByLabel('Seu PIN'), 3], [p.getByRole('button', { name: /Assinar como/ }), 4],
                   [p.getByRole('button', { name: /Rejeitar este documento/ }), 5]]);
  await foto(p, '13-assinar');
  await p.getByRole('button', { name: /Rejeitar este documento/ }).click(); await p.waitForTimeout(1500);
  await foto(p, '15-rejeitar');
  await p.keyboard.press('Escape');
  await p.getByText('Cancelados / rejeitados').first().click(); await p.waitForTimeout(3000);
  await foto(p, '15b-assinar-encerrados');
  await p.context().close();

  // ---------- militar
  p = await novo(1400);
  await entrar(p, '20000005');
  await ir(p, 'Prévia da escala'); await foto(p, '05-previa-militar');
  await p.context().close();

  // ---------- administrador
  p = await novo(1400);
  await entrar(p, 'admin');
  await ir(p, 'Usuários'); await foto(p, '29-usuarios');
  await p.context().close();
  await b.close();
})();

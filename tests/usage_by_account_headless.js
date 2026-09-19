// Drives the served landing page (tests/test_usage_by_account_served.py serves it) with playwright: hover the usage
// readout and read the panel's shape by ACCOUNT (plans/usage-panel-by-account.md): the blocks, each block's head, its
// window names, its machines line (names, dress, a lagging note), its updated-ago line, the not-reporting line, and the
// rail's own aggregate bars. Prints one JSON line of observations; screenshots when asked.
const { chromium } = require('playwright');
(async () => {
  const url = process.argv[2], shots = process.argv[3] || '';
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1280, height: 820 } });
  const errs = [];
  pg.on('pageerror', (e) => errs.push(String(e)));
  await pg.goto(url);
  await pg.waitForSelector('#rail-usage', { timeout: 20000 });
  await pg.evaluate(() => { const bt = document.getElementById('romp-boot'); if (bt) bt.remove(); });
  await pg.waitForFunction(() => document.getElementById('rail-usage').children.length > 0, null, { timeout: 20000 });
  const rail = await pg.evaluate(() => ({
    windows: Array.from(document.querySelectorAll('#rail-usage .ru-w:not(.ru-api) .ru-name-full, #rail-usage .ru-w:not(.ru-api) .ru-name')).map((e) => e.textContent.trim()).filter(Boolean),
    bars: document.querySelectorAll('#rail-usage .ru-w:not(.ru-api)').length,
    pcts: Array.from(document.querySelectorAll('#rail-usage .ru-w:not(.ru-api) .ru-pct')).map((e) => e.textContent),
    api: !!document.querySelector('#rail-usage .ru-api'),
  }));
  await pg.hover('#rail-usage');
  await pg.waitForFunction(() => { const t = document.getElementById('ru-tip'); return t && t.style.display === 'block'; }, null, { timeout: 5000 });
  const tip = await pg.evaluate(() => {
    const t = document.getElementById('ru-tip');
    const blocks = Array.from(t.querySelectorAll('.ru-tip-block')).map((bl) => ({
      head: (bl.querySelector('.ru-tip-acct') || {}).textContent || '',
      windows: Array.from(bl.querySelectorAll('.ru-tip-win .ru-tip-name > span:first-child')).map((e) => e.textContent),
      resets: Array.from(bl.querySelectorAll('.ru-tip-win .ru-tip-reset')).map((e) => e.textContent),
      used: Array.from(bl.querySelectorAll('.ru-tip-win .ru-tip-row')).filter((r) => /^(used|last known)$/.test(((r.querySelector('.ru-tip-k') || {}).textContent || '').trim())).map((r) => r.querySelector('.ru-tip-v').textContent),
      machines: Array.from(bl.querySelectorAll('.ru-tip-machines .ru-tip-machine')).map((e) => e.textContent),
      machinesLine: (bl.querySelector('.ru-tip-machines') || {}).textContent || '',
      lag: Array.from(bl.querySelectorAll('.ru-tip-lag')).map((e) => e.textContent),
      age: (bl.querySelector('.ru-tip-age') || {}).textContent || '',
      dress: (() => { const m = bl.querySelector('.ru-tip-machine'); if (!m) return null; const cs = getComputedStyle(m);
        return { style: cs.fontStyle, weight: cs.fontWeight, size: cs.fontSize, color: cs.color }; })(),
    }));
    const cols = t.querySelectorAll('.ru-tip-col').length;
    const noReport = Array.from(t.querySelectorAll('#ru-tip > .ru-tip-machines, #ru-tip .ru-tip-cols ~ .ru-tip-machines')).map((e) => e.textContent);
    return { blocks, cols, noReport, hosts: t.querySelectorAll('.ru-tip-host').length, accts: t.querySelectorAll('.ru-tip-acct').length,
             spend: !!t.querySelector('.ru-tip-fleetspend'), display: getComputedStyle(t).display, colsDisplay: (() => { const c = t.querySelector('.ru-tip-cols'); return c ? getComputedStyle(c).display : null; })() };
  });
  if (shots) { const tipEl = await pg.$('#ru-tip'); if (tipEl) await tipEl.screenshot({ path: shots + '-hover.png' }); }
  console.log(JSON.stringify({ rail, tip, errs }));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });

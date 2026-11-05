// ── 視圖路由與各視圖(標的分析 / 最佳策略 / 策略實驗室 / 市場環境)───────────────
// 設計原則:
//  1. 所有數字都來自既有 API(/api/analyze、/api/best_strategy、/api/deep_analysis、/api/market_character),前端不重算績效。
//  2. 切換視圖只是顯示/隱藏,不會自動多打 API、不會重跑回測;只有按「分析/開始」才會呼叫。
//  3. 結果類型分開標示:歷史回測 / 樣本外測試 / 即時技術訊號(未來紙上交易:尚未提供)。
const VIEW_NAMES = ['watchlist','symbol','best','lab','market'];
let currentView = 'watchlist';
const $id = id => document.getElementById(id);

function parseHash(){
  const h = location.hash.replace(/^#\/?/, '');
  const name = h.split('?')[0];
  return VIEW_NAMES.includes(name) ? name : 'watchlist';
}
function ensureWatchlistView(){
  if(currentView !== 'watchlist'){ location.hash = '#/watchlist'; return true; }
  return false;
}

function route(){
  const name = parseHash();
  VIEW_NAMES.forEach(v => { const el = $id('view-'+v); if(el) el.classList.toggle('active', v === name); });
  document.querySelectorAll('#mainNav a, #bottomTabs a').forEach(a => a.classList.toggle('active', a.dataset.view === name));
  if(name !== currentView) window.scrollTo(0, 0);
  currentView = name;
  if(name === 'watchlist'){ redrawStaleCharts(); updateExpandAllBtn(); }
  if(name === 'symbol'){ refreshViewSelects(); consumeSymbolPending(); }
  if(name === 'best' || name === 'lab') refreshViewSelects();
  if(name === 'market') loadMarketView(false);
}
window.addEventListener('hashchange', route);

// 卡片在隱藏的視圖中繪製時寬度為 0;回到自選清單時,把寬度不對的圖重畫。
function redrawStaleCharts(){
  stocks.forEach(s => {
    if(!s.expanded) return;
    const card = $id(`card-${s.id}`);
    if(!card || card.dataset.loaded !== '1' || card.style.display === 'none') return;
    const cont = card.querySelector('.chart-container');
    const charts = chartInsts[s.id];
    const w = cont ? cont.clientWidth : 0;
    if(!w) return;
    const first = charts && charts[0] && charts[0].chartElement ? charts[0].chartElement().clientWidth : 0;
    if(!charts || Math.abs(first - w) > 4){
      const data = JSON.parse(card.dataset.chartdata || 'null');
      if(data) drawCharts(s.id, data, s.indicators);
    }
  });
}

// ── 小提示 ────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg){
  let t = $id('toast');
  if(!t){ t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
  t.textContent = msg; t.classList.add('show');
  clearTimeout(_toastTimer); _toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

// ── 下拉選單 ───────────────────────────────────────────
function fillSelect(el, items, keep){
  if(!el) return;
  const prev = keep ? el.value : null;
  el.innerHTML = items.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
  if(prev && items.some(([v]) => v === prev)) el.value = prev;
}
function refreshViewSelects(){
  const byId = stocks.map(s => [String(s.id), `${s.name || s.symbol}（${s.symbol}）`]);
  const bySym = stocks.map(s => [s.symbol, `${s.name || s.symbol}（${s.symbol}）`]);
  fillSelect($id('symSel'), byId, true);
  fillSelect($id('bestSel'), bySym, true);
  fillSelect($id('labSel'), bySym, true);
  fillSelect($id('symStrat'), strategies.map(s => [s.v, s.l]), true);
  fillSelect($id('symPeriod'), PERIODS.map(p => [p, PERIOD_LABELS[p]]), true);
  fillSelect($id('symTf'), TFS.map(t => [t, TF_LABELS[t]]), true);
  fillSelect($id('bestPeriod'), PERIODS.map(p => [p, PERIOD_LABELS[p]]), true);
  fillSelect($id('bestTf'), TFS.map(t => [t, TF_LABELS[t]]), true);
  fillSelect($id('labTf'), TFS.map(t => [t, TF_LABELS[t]]), true);
}
function _stockById(id){ return stocks.find(s => String(s.id) === String(id)); }
function initViews(){
  refreshViewSelects();
  // 選到自選標的時,帶入它在清單裡的設定(使用者仍可改)
  $id('symSel').addEventListener('change', () => {
    const s = _stockById($id('symSel').value); if(!s) return;
    $id('symCustom').value = '';
    $id('symStrat').value = s.strat; $id('symPeriod').value = s.period || '2y'; $id('symTf').value = s.tf || '1d';
  });
  $id('bestSel').addEventListener('change', () => {
    const s = stocks.find(x => x.symbol === $id('bestSel').value); if(!s) return;
    $id('bestCustom').value = ''; $id('bestPeriod').value = s.period || '2y'; $id('bestTf').value = s.tf || '1d';
  });
  $id('labSel').addEventListener('change', () => {
    const s = stocks.find(x => x.symbol === $id('labSel').value); if(!s) return;
    $id('labCustom').value = ''; $id('labTf').value = s.tf || '1d';
  });
  const s0 = stocks[0];
  if(s0){
    $id('symStrat').value = s0.strat; $id('symPeriod').value = s0.period || '2y'; $id('symTf').value = s0.tf || '1d';
    $id('bestPeriod').value = s0.period || '2y'; $id('bestTf').value = s0.tf || '1d'; $id('labTf').value = s0.tf || '1d';
  }
  route();
}

// ── 標的分析 ───────────────────────────────────────────
let _symSeq = 0, symCharts = [], _symPending = null;
function symClear(){ symCharts.forEach(c => { try{ c.remove(); }catch(e){} }); symCharts = []; }

// 從卡片/排名結果進入:設定好選單後自動分析一次(使用者主動點擊,所以是一次明確的 API 呼叫)
function openSymbolView(id, strat, opts){
  _symPending = {id, strat, opts: opts || {}};
  if(location.hash === '#/symbol') route(); else location.hash = '#/symbol';
}
function consumeSymbolPending(){
  const p = _symPending; if(!p) return;
  _symPending = null;
  const s = p.id != null ? _stockById(p.id) : null;
  if(s){
    $id('symSel').value = String(s.id); $id('symCustom').value = '';
    $id('symStrat').value = p.strat || s.strat; $id('symPeriod').value = (p.opts.period || s.period || '2y'); $id('symTf').value = (p.opts.tf || s.tf || '1d');
  } else if(p.opts.symbol){
    $id('symCustom').value = p.opts.symbol;
    if(p.strat) $id('symStrat').value = p.strat;
    if(p.opts.period) $id('symPeriod').value = p.opts.period;
    if(p.opts.tf) $id('symTf').value = p.opts.tf;
  }
  runSymbolView();
}
function _symTarget(){
  const custom = normSymbol($id('symCustom').value);
  const stock = custom ? stocks.find(s => s.symbol === custom) : _stockById($id('symSel').value);
  const symbol = custom || (stock && stock.symbol);
  return {symbol, stock, name: stock ? (stock.name || symbol) : (symbol ? autoName(symbol) : '')};
}

async function runSymbolView(){
  const body = $id('symBody'), btn = $id('symRun');
  const t = _symTarget();
  if(!t.symbol){ body.innerHTML = '<div class="empty-state">請選擇標的，或輸入代號。</div>'; return; }
  const strat = $id('symStrat').value, period = $id('symPeriod').value, tf = $id('symTf').value;
  const seq = ++_symSeq; symClear();
  const unsup = tfUnsupported(t.symbol, tf);
  if(unsup){ body.innerHTML = `<div class="state-card warn"><b>此時框不支援</b>：${esc(unsup)}</div>`; return; }
  body.innerHTML = '<div class="empty-state"><span class="spinner"></span> 分析中…</div>';
  btn.disabled = true;
  try{
    const r = await fetch(`/api/analyze?symbol=${encodeURIComponent(t.symbol)}&strategy=${strat}&period=${period}&timeframe=${tf}`);
    const data = await r.json();
    if(seq !== _symSeq) return;
    if(data.error){
      const nodata = /不足/.test(data.error);
      body.innerHTML = `<div class="state-card ${nodata?'warn':'err'}"><b>${nodata?'資料不足':'分析失敗'}</b>：${esc(data.error)}<br><span class="vb-note">${nodata?'這個標的／時框的歷史資料不夠長,無法可靠回測;可改用日線或較短期間,或確認代號是否正確。':'請稍後再試,或確認代號是否正確。'}</span></div>`;
      return;
    }
    renderSymbolBody(body, data, {symbol: t.symbol, name: t.name, strat, period, tf, stock: t.stock});
  }catch(e){
    if(seq !== _symSeq) return;
    body.innerHTML = `<div class="state-card err"><b>連線失敗</b>：${esc(e.message)}。請確認本機伺服器仍在執行。</div>`;
  }finally{
    if(seq === _symSeq) btn.disabled = false;
  }
}

function kpiCard(label, valHtml, cls, tip){
  return `<div class="kpi-card"${tip?` data-tip="${tip}"`:''}><div class="kpi-label">${label}</div><div class="kpi-val ${cls||'neutral'}">${valHtml}</div></div>`;
}
function renderSymbolBody(body, data, ctx){
  const m = data.metrics, di = data.dataInfo, v = data.validation, bt = data.backtest;
  const sig = getSignalState(data);
  const intraday = !!(di && di.interval && di.interval !== '1d' && di.interval !== '1wk');
  const noTr = m.tradeCount === 0;
  const mk = getMarket(ctx.symbol);
  const bs = bt && bt.available ? bt.summary : null;

  const head = `<div class="sym-head">
      <div class="sym-title">${esc(ctx.name)} <span class="mk-badge">${MARKET_LABEL[mk]||mk}</span> <span style="font-size:13px;color:var(--text2);font-weight:400;">${esc(ctx.symbol)} · ${esc(getStratName(ctx.strat))} · ${TF_LABELS[ctx.tf]||ctx.tf} · ${PERIOD_LABELS[ctx.period]||ctx.period}</span></div>
      <div class="sym-meta">${esc(dataTimeText(di))}${di?` · 共 ${di.bars} 根已收盤 K 棒（最後一根未收盤的已排除）`:''}</div>
      <div class="sym-chips">
        <span class="chip"><span class="rtag live">即時技術訊號</span> ${esc(sig.label)}${sig.sub?`　<span style="color:var(--text3)">${esc(sig.sub)}</span>`:''}</span>
        <span class="chip" id="symRegime">市場性格：載入中…</span>
      </div>
    </div>`;

  const kpis = `<div class="kpi-grid">
      ${kpiCard('扣成本報酬', fmtPct(m.totalReturn), retClass(m.totalReturn), TIP.ret)}
      ${kpiCard('淨 PF', noTr?'—':(m.pf>=999?'∞':m.pf.toFixed(2)), noTr?'neutral':(m.pf>=1?'pos':'neg'), TIP.pf)}
      ${kpiCard('最大回撤', m.maxDD+'%', 'neg', TIP.dd)}
      ${kpiCard('勝率', noTr?'—':m.wr+'%', 'neutral', TIP.wr)}
      ${kpiCard('交易筆數', m.tradeCount+'筆', 'neutral', TIP.tc)}
      ${kpiCard('年化', fmtPct(m.cagr), retClass(m.cagr), TIP.cagr)}
      ${bs&&bs.buyHoldTotal!=null ? kpiCard('買進持有報酬', fmtPct(bs.buyHoldTotal), retClass(bs.buyHoldTotal), TIP.bh) : ''}
      ${bs&&bs.buyHoldMaxDD!=null ? kpiCard('買進持有回撤', bs.buyHoldMaxDD+'%', 'neg', TIP.bh) : ''}
    </div>`;

  let curves;
  if(bt && bt.available){
    curves = `<div class="curve-legend"><span><i style="background:#26a69a"></i>策略權益（已扣成本）</span><span><i style="background:#8b90a0"></i>買進持有（未計成本）</span><span><i style="background:rgba(239,83,80,0.7)"></i>策略回撤</span></div>
      <div class="curve-box" id="symEq"></div><div class="curve-box dd" id="symDd"></div>`;
  } else {
    curves = `<div class="state-card warn">${esc((bt && bt.reason) || data.extrasError || '權益曲線資料暫時無法取得')}</div>`;
  }
  const c = bt && bt.available ? bt.cost : null;
  const costBox = c ? `<div class="cost-box">每筆來回成本約 <b>${c.roundTripPct}%</b>（手續費 ${(c.commission*100).toFixed(4)}%×2＋滑價 ${(c.slippage*100).toFixed(4)}%×2${c.sellTax>0?`＋賣出證交稅 ${(c.sellTax*100).toFixed(2)}%`:''}）。
      此期間共 <b>${c.tradesInWindow}</b> 筆交易，累計成本約為期初權益的 <b>${c.paidPctOfEquity}%</b>。${esc(c.note)}</div>` : '';
  const period = bt && bt.available ? `${bt.period.start} → ${bt.period.end}（${bt.period.bars} 根，${bt.period.trades} 筆交易）` : '';

  body.innerHTML = head + `
    <div class="two-col" style="margin-top:8px;">
      <div class="panel"><div class="panel-h"><span class="rtag hist">歷史回測</span> <span style="color:var(--text2);font-size:12px;">${period}</span></div><div class="panel-b">${kpis}${costBox}</div></div>
      <div class="panel"><div class="panel-h"><span class="rtag oos">樣本內／樣本外</span></div><div class="panel-b">${validationTableHtml(v)}</div></div>
    </div>
    <div class="panel"><div class="panel-h"><span class="rtag hist">歷史回測</span> 權益曲線與回撤（以顯示期間起點為 0%）</div><div class="panel-b">${curves}</div></div>
    <div class="panel"><div class="panel-h">K 線與進出場<span class="vb-note" style="margin-left:8px;">▲▼ 為歷史回測的進出場點</span></div><div class="panel-b"><div id="symK"></div></div></div>
    <div class="panel"><div class="panel-h">進出場明細（已扣成本）</div><div class="panel-b">${tradesHtml(m.trades)}</div></div>
    <div class="vb-note" style="padding:4px 16px 16px;">未來紙上交易：<span class="rtag na">尚未提供</span>。本頁所有數字都是歷史模擬，不代表未來，也不是買賣建議。</div>`;

  if(bt && bt.available) symCharts.push(...drawBacktestCurves($id('symEq'), $id('symDd'), bt, intraday));
  const inds = (ctx.stock && ctx.stock.indicators) || {ema:true, kd:true, rsi:true, vol:true};
  symCharts.push(...buildChartsInContainer($id('symK'), data, inds, 320));

  // 市場性格(ADX):與卡片同一個 API,只做描述
  fetch(`/api/market_character?symbol=${encodeURIComponent(ctx.symbol)}&timeframe=${ctx.tf}`).then(r => r.json()).then(d => {
    const el = $id('symRegime'); if(!el) return;
    const icon = {up:'🔼', down:'🔽', range:'↔️', na:'⚪'}[d.code] || '⚪';
    el.textContent = `市場性格：${icon} ${d.label}${d.adx != null ? `（ADX ${d.adx}）` : ''}`;
  }).catch(() => { const el = $id('symRegime'); if(el) el.textContent = '市場性格：暫時無法取得'; });
}

function applySymbolToList(){
  const t = _symTarget();
  if(!t.stock){ alert('此標的不在自選清單，請先到「自選清單」加入後再套用。'); return; }
  const strat = $id('symStrat').value, period = $id('symPeriod').value, tf = $id('symTf').value;
  if(!confirm(`要把「${t.name}」在自選清單的設定改成：\n策略 ${getStratName(strat)}、期間 ${PERIOD_LABELS[period]}、時框 ${TF_LABELS[tf]} 嗎？`)) return;
  const s = t.stock; s.strat = strat; s.period = period; s.tf = tf; save();
  const set = (id, v) => { const el = $id(id); if(el) el.value = v; };
  set(`strat-sel-${s.id}`, strat); set(`period-sel-${s.id}`, period); set(`tf-sel-${s.id}`, tf);
  updateCardSub(s.id); reloadCard(s.id);
  showToast('已套用到自選清單');
}

// ── 最佳策略 / 策略實驗室(視圖版)────────────────────────────────
function viewUi(bodyId, btnId){
  const body = $id(bodyId), btn = $id(btnId);
  body.innerHTML = `<div class="panel"><div class="panel-b">
      <div class="progress-bar-wrap"><div class="progress-bar" data-pb style="width:0%"></div></div>
      <div class="progress-text" data-pt>準備中…</div>
      <div class="vb-note" data-sub style="margin-top:6px;"></div></div></div><div data-res></div>`;
  const q = s => body.querySelector(s);
  return {
    setProgress(p, text){ if(p == null){ q('[data-pb]').parentElement.style.display = 'none'; return; } q('[data-pb]').style.width = p + '%'; if(text) q('[data-pt]').textContent = text; },
    setSub(html){ q('[data-sub]').innerHTML = html; },
    setResults(html){ q('[data-res]').innerHTML = html; },
    busy(on){ btn.disabled = on; },
  };
}
async function runBestView(){
  const custom = normSymbol($id('bestCustom').value);
  const symbol = custom || $id('bestSel').value;
  if(!symbol){ $id('bestBody').innerHTML = '<div class="empty-state">請選擇標的，或輸入代號。</div>'; return; }
  const stock = stocks.find(s => s.symbol === symbol);
  const ctx = {symbol, period: $id('bestPeriod').value, tf: $id('bestTf').value, stockId: stock ? stock.id : null, useOos: $id('bestOos').checked};
  await rankingFlow('best', 'best', ctx, viewUi('bestBody', 'bestRun'));
}
async function runLabView(){
  if(isRender){ $id('labBody').innerHTML = '<div class="state-card warn">深度分析僅支援本機執行(雲端版有請求時間限制)。</div>'; return; }
  const custom = normSymbol($id('labCustom').value);
  const symbol = custom || $id('labSel').value;
  if(!symbol){ $id('labBody').innerHTML = '<div class="empty-state">請選擇標的，或輸入代號。</div>'; return; }
  const stock = stocks.find(s => s.symbol === symbol);
  const tf = $id('labTf').value;
  const ctx = {symbol, period: ['4h','1h'].includes(tf) ? '2y' : '5y', tf, stockId: stock ? stock.id : null, useOos: $id('labOos').checked};
  await rankingFlow('deep', 'lab', ctx, viewUi('labBody', 'labRun'));
}

// ── 市場環境 ───────────────────────────────────────────
const mkCache = {};            // `${symbol}|${tf}` → {t, d}
const MK_TTL = 10 * 60 * 1000;
let _mkSeq = 0;
async function loadMarketView(force){
  const tbl = $id('mkTable');
  const seq = ++_mkSeq;
  if(!stocks.length){ tbl.innerHTML = '<tbody><tr><td class="empty-state">自選清單是空的。</td></tr></tbody>'; return; }
  const rowHtml = s => {
    const key = `${s.symbol}|${s.tf||'1d'}`, c = mkCache[key];
    let ch = '<span style="color:var(--text3)">載入中…</span>', adx = '—', fit = '—';
    if(c){
      const d = c.d, icon = {up:'🔼', down:'🔽', range:'↔️', na:'⚪'}[d.code] || '⚪';
      ch = `${icon} ${esc(d.label)}`; adx = d.adx != null ? d.adx : '—';
      const msg = checkStratMismatch(d.code, getStratCat(s.strat));
      fit = d.code === 'na' ? '—' : (msg ? `<span style="color:#f5a623">${esc(msg.replace(/^⚠ /, ''))}</span>` : '類型相符');
    } else if(c === null){ ch = '<span style="color:var(--red)">暫時無法取得</span>'; }
    return `<tr><td>${esc(s.name||s.symbol)}<div class="vb-sub">${esc(s.symbol)}</div></td><td>${MARKET_LABEL[getMarket(s.symbol)]}</td><td>${TF_LABELS[s.tf]||'日線'}</td><td>${ch}</td><td>${adx}</td><td>${esc(getStratName(s.strat))}</td><td>${fit}</td></tr>`;
  };
  const draw = () => {
    tbl.innerHTML = `<thead><tr><th>標的</th><th>市場</th><th>時框</th><th>目前市場性格</th><th>ADX</th><th>自選策略</th><th>策略類型 vs 性格</th></tr></thead><tbody>${stocks.map(rowHtml).join('')}</tbody>`;
  };
  draw();
  const todo = stocks.filter(s => { const c = mkCache[`${s.symbol}|${s.tf||'1d'}`]; return force || !c || (Date.now() - c.t > MK_TTL); });
  let i = 0;
  const worker = async () => {
    while(i < todo.length){
      const s = todo[i++], key = `${s.symbol}|${s.tf||'1d'}`;
      try{
        const r = await fetch(`/api/market_character?symbol=${encodeURIComponent(s.symbol)}&timeframe=${s.tf||'1d'}`);
        mkCache[key] = {t: Date.now(), d: await r.json()};
      }catch(e){ mkCache[key] = null; }
      if(seq === _mkSeq) draw();
    }
  };
  await Promise.all([worker(), worker(), worker()]);     // 最多同時 3 個請求,不擠占卡片載入
  if(seq === _mkSeq) $id('mkStamp').textContent = `最後更新 ${new Date().toLocaleTimeString('zh-TW', {hour:'2-digit', minute:'2-digit'})}`;
}

// 視窗縮放時,標的分析頁的圖跟著容器寬度調整
let _rsz = null;
window.addEventListener('resize', () => {
  clearTimeout(_rsz);
  _rsz = setTimeout(() => symCharts.forEach(c => {
    try{ const el = c.chartElement().parentElement; if(el && el.clientWidth) c.applyOptions({width: el.clientWidth}); }catch(e){}
  }), 150);
});

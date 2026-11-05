// ── 多週期技術狀態 + 資料品質(市場環境頁) ──────────────────────────────────
// 原則:
//  1. 只是「已收盤 K 棒上技術指標目前的位置」的描述(EMA、ADX、±DI、ATR),不是價格預測,也不是買賣建議。
//  2. 每個週期各自抓自己的資料;某個週期沒有資料/不支援就明說,絕不用別的週期代替。最新一根未收盤的 K 棒一律排除。
//  3. 資料過期/異常要明確標示,不能顯示成最新狀態;休市(週末、假日)不算資料故障。
//  4. 數字全部來自 /api/mtf;前端不重算。進度只來自後端真實事件(Research Core),已快取的資料明確標示「使用快取」。
const mtfState = {pv: null, handle: null, data: null};
const MTF_SRC = {ccxt: '幣安公開行情', yfinance: 'Yahoo Finance'};

function dqClass(q){
  if(!q) return 'na';
  if(q.blocking) return 'bad';
  return q.status === 'forming' ? 'info' : 'ok';
}
// 資料品質徽章(卡片、標的分析、多週期共用)。q = API 的 dataQuality / quality。沒有就如實顯示「未檢查」,不假裝正常。
function dqBadge(q){
  if(!q) return `<span class="dq dq-na" title="這筆資料的品質檢查沒有結果">資料品質：未檢查</span>`;
  let text = q.label;
  if(q.status === 'ok' && q.marketClosed) text = '資料正常（休市中）';
  else if(q.status === 'ok' && q.marketState && ['weekend', 'holiday'].includes(q.marketState.code)) text = `資料正常（${q.marketState.label}）`;
  const icon = {ok: '✓', info: 'ℹ', bad: '⚠', na: '?'}[dqClass(q)];
  const tip = [q.detail, q.formingExcluded ? '最新一根尚未收盤的 K 棒已排除，只用已收盤的 K 棒。' : '', q.alsoFound ? '同時偵測到：' + Object.values(q.alsoFound).join('；') : ''].filter(Boolean).join(' ');
  return `<span class="dq dq-${dqClass(q)}" ${tip ? `title="${esc(tip)}"` : ''}>${icon} ${esc(text)}</span>`;
}

function mtfAgeText(sec){
  if(sec == null) return '';
  return sec >= 90 ? `${Math.round(sec / 60)} 分鐘前取得` : `${Math.round(sec)} 秒前取得`;
}
function mtfSourceText(d){
  if(!d) return '—';
  const src = MTF_SRC[d.source] || d.source || '—';
  const c = d.cached === true ? `<span class="dq-cache">使用快取（${esc(mtfAgeText(d.ageSec))}）</span>` : (d.cached === false ? '<span class="dq-cache fresh">重新取得</span>' : '');
  return `${esc(src)}${d.synth && !/合成/.test(src) ? '（由 1H 合成）' : ''}<div class="vb-sub">${c}</div>`;
}
function mtfTimeText(d){
  if(!d || !d.lastBarUtc) return '—';
  const local = d.lastBarLocal && d.lastBarLocal !== d.lastBarUtc ? `${esc(d.lastBarLocal)}（${esc(d.tzLabel)}）` : `${esc(d.lastBarUtc)}${/\d:\d/.test(d.lastBarUtc) ? ' UTC' : ''}`;
  const utc = d.lastBarLocal && d.lastBarLocal !== d.lastBarUtc ? `<div class="vb-sub">${esc(d.lastBarUtc)}${/\d:\d/.test(d.lastBarUtc) ? ' UTC' : ''}</div>` : '';
  return `${local}${utc}`;
}
function mtfTrendText(i){
  if(!i) return '—';
  const icon = {up: '🔼', down: '🔽', range: '↔️'}[i.trendCode] || '';
  return `${icon} ${esc(i.trendLabel || '—')}<div class="vb-sub">${esc(i.adxLabel || 'ADX (Wilder, 14)')} ${i.adx ?? '—'} · +DI ${i.plusDi ?? '—'} / −DI ${i.minusDi ?? '—'}</div>`;
}
function mtfPriceText(i){
  if(!i) return '—';
  const f = (name, v) => v == null ? `<span class="na">${name} —</span>` : `<span class="${v ? 'pos' : 'neg'}">${name} ${v ? '之上' : '之下'}</span>`;
  return `${f('EMA20', i.above.ema20)} · ${f('EMA50', i.above.ema50)} · ${f('EMA200', i.above.ema200)}<div class="vb-sub">收盤 ${i.close}</div>`;
}
const MTF_BIAS = {bull: ['偏多', 'pos'], bear: ['偏空', 'neg'], neutral: ['中性／分歧', 'neutral']};
function mtfBiasText(e){
  const i = e.indicators; if(!i) return '—';
  const [t, c] = MTF_BIAS[i.bias];
  const stale = e.quality && e.quality.blocking ? '<div class="vb-sub warn">資料過期，僅為歷史狀態</div>' : '';
  return `<span class="${c}" title="${esc(i.biasText)}">${t}</span>${stale}`;
}

function mtfRowHtml(e){
  if(!e.supported) return `<tr class="mtf-unsup"><td class="name"><b>${esc(e.label)}</b></td><td colspan="8" class="left"><span class="dq dq-na">資料來源不支援此週期</span> <span class="vb-note">${esc(e.reason)}</span></td></tr>`;
  const q = e.quality, i = e.indicators, d = e.data || {};
  const dim = q.blocking ? ' class="mtf-dim"' : '';
  return `<tr${dim}>
    <td class="name"><b>${esc(e.label)}</b><div class="vb-sub">${esc(e.tf)}${d.bars ? ` · ${d.bars} 根` : ''}</div></td>
    <td class="left">${dqBadge(q)}${q.detail ? `<div class="dq-detail">${esc(q.detail)}</div>` : ''}${d.formingExcluded && q.status !== 'forming' ? '<div class="vb-sub">已排除未收盤的最新 K 棒</div>' : ''}</td>
    <td>${mtfTimeText(d)}</td><td>${mtfSourceText(d)}</td>
    <td class="left">${mtfTrendText(i)}</td>
    <td class="left">${i ? esc(i.emaAlignText) : '—'}</td>
    <td class="left">${mtfPriceText(i)}</td>
    <td>${i && i.atrPct != null ? i.atrPct + '%' : '—'}</td>
    <td>${mtfBiasText(e)}</td></tr>`;
}
function mtfCardHtml(e){
  if(!e.supported) return `<div class="cmp-card mtf-unsup"><h4>${esc(e.label)} <span class="dq dq-na">不支援</span></h4><div class="vb-note">${esc(e.reason)}</div></div>`;
  const q = e.quality, i = e.indicators, d = e.data || {};
  const kv = (k, v) => `<div class="k">${k}</div><div class="v">${v}</div>`;
  return `<div class="cmp-card${q.blocking ? ' mtf-dim' : ''}">
    <h4>${esc(e.label)} ${dqBadge(q)}</h4>
    ${q.detail ? `<div class="dq-detail">${esc(q.detail)}</div>` : ''}
    <div class="cmp-grid">
      ${kv('最後已收盤 K 棒', mtfTimeText(d))}${kv('資料來源', mtfSourceText(d))}
      ${i ? kv('趨勢', mtfTrendText(i)) + kv('EMA 排列', esc(i.emaAlignText)) + kv('收盤 vs EMA', mtfPriceText(i)) + kv('ATR / 收盤', i.atrPct != null ? i.atrPct + '%' : '—') + kv('技術偏向', mtfBiasText(e)) : kv('技術指標', '<span class="na">沒有可用資料，不顯示指標</span>')}
    </div></div>`;
}

function mtfRender(d){
  const body = $id('mtfBody');
  const ms = d.marketState || {};
  const agree = {bull: 'pos', bear: 'neg', mixed: 'neutral', insufficient: 'neutral'}[d.summary.agreement];
  const head = `<div class="mtf-head">
      <b>${esc(d.symbol)}</b><span class="mk-badge">${esc(MARKET_LABEL[getMarket(d.symbol)] || d.market)}</span>
      <span class="vb-note">時區：${esc(d.tzLabel)} · 目前市場狀態：<b>${esc(ms.label || '—')}</b> · 檢查時間 ${esc(d.asOfUtc)} UTC</span>
    </div>
    <div class="mtf-sum"><span class="rtag na" title="只描述已收盤 K 棒上指標目前的位置">技術指標描述</span> <b class="${agree}">${esc(d.summary.text)}</b></div>`;
  const head2 = ['週期', '資料品質', '最後已收盤 K 棒', '資料來源', '趨勢（ADX / ±DI）', 'EMA 排列', '收盤 vs EMA', 'ATR%', '技術偏向'];
  body.innerHTML = head + `<div class="cmp-wrap"><table class="cmp-table mtf-table"><thead><tr>${head2.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${d.timeframes.map(mtfRowHtml).join('')}</tbody></table></div>
    <div class="cmp-cards">${d.timeframes.map(mtfCardHtml).join('')}</div>
    <div class="vb-note" style="padding:8px 2px;">${esc(d.disclaimer)} 週線／日線的 K 棒時間是交易所當地日期；日內週期同時顯示當地時間與 UTC。資料過期或異常的週期會變淡並標明原因，不會被當成最新狀態，也不列入「是否一致」的判斷。台股、美股沒有原生 4H，所以不提供，也不用別的週期代替。</div>`;
}

async function runMtfView(){
  const custom = normSymbol($id('mtfCustom').value);
  const symbol = custom || $id('mtfSel').value;
  const body = $id('mtfBody'), btn = $id('mtfRun');
  if(!symbol){ body.innerHTML = '<div class="empty-state">請選擇標的，或輸入代號。</div>'; return; }
  if(!mtfState.pv) mtfState.pv = RCJob.progressView($id('mtfProg'), {labels: {indicators: '品質檢查＋指標', summary: '多週期彙整'}});
  const pv = mtfState.pv;
  btn.disabled = true; body.innerHTML = '';
  const handle = RCJob.run({buildUrl: id => `/api/mtf?symbol=${encodeURIComponent(symbol)}&job=${id}`, onEvent: e => pv.event(e), onTick: ms => pv.tick(ms), onCancelling: () => pv.cancelling()});
  mtfState.handle = handle; pv.begin(handle);
  try{
    const res = await handle.done;
    if(res.cancelled){ pv.end('cancelled', {note: res.unconfirmed ? '已中斷連線，但沒有收到後端的停止確認。' : '已取消：後端確認已停止。'}); body.innerHTML = '<div class="state-card warn">已取消。</div>'; return; }
    if(res.error){ pv.end('stopped', {note: '連線中斷，沒有收到完整結果。'}); body.innerHTML = `<div class="state-card err">連線失敗：${esc(res.error)}。請確認本機伺服器仍在執行。</div>`; return; }
    if(!res.ok || !res.data || res.data.error){ pv.end('error', {note: (res.data && res.data.error) || '分析失敗'}); body.innerHTML = `<div class="state-card err">❌ ${esc((res.data && res.data.error) || '分析失敗')}</div>`; return; }
    const sup = res.data.timeframes.filter(t => t.supported), cachedN = sup.filter(t => t.data && t.data.cached === true).length,
          freshN = sup.filter(t => t.data && t.data.cached === false).length, unkN = sup.length - cachedN - freshN;
    pv.end('ok', {note: `完成：${sup.length} 個週期，其中 ${cachedN} 個使用快取（沒有重新下載）、${freshN} 個重新取得${unkN ? `、${unkN} 個來源不明` : ''}。`});
    mtfState.data = res.data; mtfRender(res.data);
  }catch(e){
    pv.end('stopped', {note: '處理結果時發生錯誤。'}); body.innerHTML = `<div class="state-card err">處理結果時發生錯誤：${esc(e.message)}。</div>`;
  }finally{
    btn.disabled = false; mtfState.handle = null;
  }
}

// ── C2:市場環境 × 策略歷史績效(市場環境頁) ───────────────────────────────
// 原則:
//  1. 環境分類只用「進場決策當下已收盤」的資料(後端 market_regime.py,與卡片上的市場性格同一套規則);績效是事後的歷史統計,兩者分開顯示,不是預測。
//  2. 數字全部來自 /api/regime_study;前端不重算績效。進度只來自後端真實事件(Research Core,不另外做動畫)。
//  3. 筆數少於 20 筆一律標「樣本不足」;樣本外預設不揭露,要先在樣本內決定條件,再按「查看樣本外」(會被計數,提醒不要反覆挑選)。
const regState = {pv: null, handle: null, data: null, basis: 'own', allow: new Set()};
const REG_ORDER = ['up', 'down', 'range', 'transition'];
const REG_ICON = {up: '🔼', down: '🔽', range: '↔️', transition: '🔀', na: '⚪'};
const REG_TIER = {insufficient: '樣本不足', preliminary: '初步觀察', evaluable: '可進一步評估'};

function regFillSelects(){
  const mk = $id('regMkt'); if(!mk) return;
  const want = mk.value;
  const list = stocks.filter(s => !want || getMarket(s.symbol) === want);
  fillSelect($id('regSel'), list.map(s => [s.symbol, `${s.name || s.symbol}（${s.symbol}）`]), true);
  fillSelect($id('regTf'), TFS.map(t => [t, TF_LABELS[t]]), true);
  fillSelect($id('regPeriod'), PERIODS.map(p => [p, PERIOD_LABELS[p]]), true);
  fillSelect($id('regStrat'), strategies.map(s => [s.v, s.l]), true);
  const per = $id('regPeriod'); if(per && !per.dataset.init){ per.value = '2y'; per.dataset.init = '1'; }
}
document.addEventListener('DOMContentLoaded', () => { const m = $id('regMkt'); if(m) m.addEventListener('change', regFillSelects); });

function regTier(n){
  const k = n < 20 ? 'insufficient' : (n < 50 ? 'preliminary' : 'evaluable');
  return `<span class="tier tier-${k}" title="只是樣本量分級（&lt;20 筆樣本不足；20–49 初步觀察；≥50 可進一步評估），不是統計顯著性，也不代表策略有效">${REG_TIER[k]}</span>`;
}
function regPf(s){
  if(s.pf == null) return '—';
  return fmtPF(s.pf) + (s.lossless ? '<span class="vb-sub" title="這組沒有虧損交易，PF 沿用本站算法（獲利總和），不是真正的比值"> 無虧損</span>' : '');
}
function regNum(v, d){ return v == null ? '—' : fmtPct(v, d == null ? 2 : d); }

function regRowDefs(bd, labels){
  const rows = [['all', '全部交易（整體）', '']];
  REG_ORDER.forEach(c => rows.push([c, labels[c], REG_ICON[c]]));
  if(bd.na && bd.na.n > 0) rows.push(['na', labels.na, REG_ICON.na]);
  return rows;
}
function regOfficial(o){ return o ? `<div class="vb-sub" title="和策略排名／標的分析同一份回測：含 1.5% 風險倉位與槓桿上限，用權益曲線計算">本站回測 ${fmtPct(o.total, 2)}</div>` : ''; }
function regOfficialDd(o){ return o ? `<div class="vb-sub">本站回測 ${o.mdd.toFixed(2)}%</div>` : ''; }
function regTableHtml(bd, labels, official){
  const head = ['環境（進場決策當下）', '交易筆數', '平均每筆（扣成本）', '合計報酬（各筆複利，扣成本）', '淨 PF', '勝率', '最大回撤（各筆複利）'];
  const body = regRowDefs(bd, labels).map(([k, name, icon]) => {
    const s = bd[k];
    if(!s || s.n === 0) return `<tr class="rg-low"><td>${icon} ${esc(name)}</td><td>0</td><td colspan="5" class="na">沒有交易，無資料</td></tr>`;
    return `<tr class="${k === 'all' ? 'rg-all' : (s.n < 20 ? 'rg-low' : '')}"><td>${icon} ${esc(name)}</td><td>${s.n}${k === 'all' ? '' : regTier(s.n)}</td><td>${regNum(s.avg, 2)}</td><td>${regNum(s.total, 2)}${k === 'all' ? regOfficial(official) : ''}</td><td>${regPf(s)}</td><td>${pctPlain(s.win, 1)}</td><td>${s.mdd == null ? '—' : s.mdd.toFixed(2) + '%'}${k === 'all' ? regOfficialDd(official) : ''}</td></tr>`;
  }).join('');
  return `<div class="cmp-wrap"><table class="cmp-table rg-tbl"><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>`;
}
function regCardsHtml(bd, labels, official){
  return `<div class="cmp-cards rg-cards">${regRowDefs(bd, labels).map(([k, name, icon]) => {
    const s = bd[k], kv = (a, b) => `<div class="k">${a}</div><div class="v">${b}</div>`;
    if(!s || s.n === 0) return `<div class="cmp-card"><h4>${icon} ${esc(name)}</h4><div class="vb-note">沒有交易，無資料。</div></div>`;
    return `<div class="cmp-card"><h4>${icon} ${esc(name)} ${k === 'all' ? '' : regTier(s.n)}</h4><div class="cmp-grid">${kv('交易筆數', s.n)}${kv('平均每筆（扣成本）', regNum(s.avg, 2))}${kv('合計報酬（各筆複利）', regNum(s.total, 2) + (k === 'all' ? regOfficial(official) : ''))}${kv('淨 PF', regPf(s))}${kv('勝率', pctPlain(s.win, 1))}${kv('最大回撤（各筆複利）', (s.mdd == null ? '—' : s.mdd.toFixed(2) + '%') + (k === 'all' ? regOfficialDd(official) : ''))}</div></div>`;
  }).join('')}</div>`;
}
function regShareHtml(sh, labels){
  if(!sh) return '';
  const order = [...REG_ORDER, 'na'];
  return `<div class="rg-share" role="img" aria-label="${order.map(c => `${labels[c]} ${sh[c].pct}%`).join('，')}">${order.map(c => sh[c].pct > 0 ? `<span class="rg-${c}" style="width:${sh[c].pct}%" title="${esc(labels[c])} ${sh[c].pct}%"></span>` : '').join('')}</div>
    <div class="rg-legend">${order.filter(c => sh[c].bars > 0).map(c => `<span><i class="rg-${c}"></i>${esc(labels[c])} ${sh[c].pct}%（${sh[c].bars} 根）</span>`).join('')}</div>`;
}

function regViewKey(d){ return `${d.symbol}|${d.timeframe}|${d.strategy}|${d.period}`; }
// 條件試驗紀錄:只存在「這個瀏覽器」的 localStorage,是給自己的提醒,不是可靠的防過度擬合機制(換瀏覽器/裝置、清除資料、直接呼叫 API 都會繞過;沒有帳號或伺服器端紀錄)。
function regTrialsAll(){ try{ return JSON.parse(localStorage.getItem('rgTrials') || '{}'); }catch(e){ return {}; } }
function regTrialsLoad(d){ return regTrialsAll()[regViewKey(d)] || []; }
function regRecordTrial(d, f){
  try{
    const all = regTrialsAll(), k = regViewKey(d); all[k] = all[k] || [];
    const cond = f.basis + ':' + f.allow.slice().sort().join(',');
    let t = all[k].find(x => x.cond === cond);
    if(!t){ t = {cond, basis: f.basis, allow: f.allow.slice(), at: new Date().toISOString(), revealed: false}; all[k].push(t); }
    t.isTrades = f.B.is.trades; t.isPf = f.B.is.pf;
    if(f.oos && f.oos.revealed) t.revealed = true;
    localStorage.setItem('rgTrials', JSON.stringify(all));
  }catch(e){ /* 沒有 localStorage 也不影響分析 */ }
}
function regTrialsHtml(d){
  const list = regTrialsLoad(d); if(!list.length) return '';
  const labels = d.labels, nRev = list.filter(t => t.revealed).length;
  const rows = list.map((t, i) => `<tr><td>${i + 1}</td><td>${esc(new Date(t.at).toLocaleString('zh-TW', {hour12: false}))}</td><td>${t.basis === 'market' ? '大盤' : '標的自身'}</td><td>${t.allow.map(c => esc(labels[c])).join('、')}</td><td>${t.isTrades}（PF ${fmtPF(t.isPf)}）</td><td>${t.revealed ? '<b>已揭露</b>' : '未揭露'}</td></tr>`).join('');
  let warn = '';
  if(list.length >= 3) warn += `<div class="rg-warn">⚠ 在這個「標的／週期／策略／期間」你已試過 ${list.length} 個不同條件。條件試得越多，越容易挑到「碰巧」在樣本內表現好的組合（多重比較）；樣本內的好結果不該直接當成有效。</div>`;
  if(nRev >= 2) warn += `<div class="rg-warn">⚠ 已對 ${nRev} 個不同條件揭露過樣本外：樣本外只有「事先決定一個條件、只看一次」時才有獨立性，現在它已經不再獨立。</div>`;
  return `<details class="rg-trials" ${warn ? 'open' : ''}><summary>本次研究流程的條件試驗紀錄（${list.length} 個條件）</summary>${warn}
    <div class="cmp-wrap"><table class="cmp-table rg-tbl"><thead><tr><th>#</th><th>時間</th><th>環境基準</th><th>允許進場的環境</th><th>樣本內（濾網後筆數）</th><th>樣本外</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="rg-sub">⚠ <b>這份紀錄只存在這個瀏覽器（localStorage）</b>：清除瀏覽器資料、換瀏覽器或裝置、或直接呼叫 API 都會繞過它，所以<b>不是可靠的防過度擬合機制</b>，只是提醒你自己；網站沒有帳號或伺服器端紀錄。</div></details>`;
}

function regCmpTable(title, seg, note){
  const head = ['版本', '交易筆數', '平均每筆（扣成本）', '合計報酬（權益曲線）', '淨 PF', '勝率', '最大回撤（權益曲線）'];
  const items = [['A　原始策略（無濾網）', seg.A], ['B　加入環境濾網', seg.B]];
  const rows = items.map(([n, s]) => `<tr><td>${n}</td><td>${s.trades}${regTier(s.trades)}</td><td>${regNum(s.avg, 2)}</td><td>${regNum(s.total, 2)}</td><td>${fmtPF(s.pf)}</td><td>${pctPlain(s.win, 1)}</td><td>${s.mdd.toFixed(2)}%</td></tr>`).join('');
  const cards = items.map(([n, s]) => `<div class="cmp-card"><h4>${n} ${regTier(s.trades)}</h4><div class="cmp-grid"><div class="k">交易筆數</div><div class="v">${s.trades}</div><div class="k">平均每筆</div><div class="v">${regNum(s.avg, 2)}</div><div class="k">合計報酬</div><div class="v">${regNum(s.total, 2)}</div><div class="k">淨 PF</div><div class="v">${fmtPF(s.pf)}</div><div class="k">勝率</div><div class="v">${pctPlain(s.win, 1)}</div><div class="k">最大回撤</div><div class="v">${s.mdd.toFixed(2)}%</div></div></div>`).join('');
  return `<div class="rg-sub"><b>${title}</b></div><div class="cmp-wrap"><table class="cmp-table rg-tbl"><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div><div class="cmp-cards">${cards}</div>${note ? `<div class="rg-warn">${esc(note)}</div>` : ''}`;
}
function regFilterResultHtml(d, f){
  let out = `<div class="rg-sub" style="margin-top:8px;">${esc(f.rule)}　所選環境：<b>${f.allowLabels.map(esc).join('、')}</b>（基準：${f.basis === 'market' ? '大盤' : '標的自身'}）</div>`;
  out += regCmpTable('樣本內（IS）', {A: f.A.is, B: f.B.is}, f.isNote);
  const o = f.oos;
  if(o.revealed){
    out += `<div class="rg-oos-box">${regCmpTable('樣本外（OOS）— 已揭露', {A: o.A, B: o.B}, o.note)}<div class="rg-sub">這個條件的樣本外已被揭露並記錄在下方「條件試驗紀錄」。若再換條件來看樣本外，樣本外就不再獨立。</div></div>`;
  } else out += `<div class="rg-oos-box"><div class="rg-sub">樣本外：${esc(o.note || '尚未揭露。')}</div></div>`;
  return out + regTrialsHtml(d);
}
function regFilterBlockHtml(d){
  const labels = d.labels, f = d.filter, cand = d.candidate;
  const checks = REG_ORDER.map(c => `<label><input type="checkbox" class="rg-allow" value="${c}" ${regState.allow.has(c) ? 'checked' : ''}> ${REG_ICON[c]} ${esc(labels[c])}</label>`).join('');
  const candTxt = cand ? (cand.regimes.length ? `樣本內候選環境：<b>${cand.regimes.map(c => esc(labels[c])).join('、')}</b>（${esc(cand.rule)}）<button class="linkbtn" type="button" onclick="regApplyCandidate()">套用候選</button>` : `樣本內候選：<b>無</b>。${esc(cand.note)}`) : '';
  let out = `<div class="rg-filter"><h4>濾網對照：假設只在所選環境允許新進場 <span class="rtag hist">歷史回測</span></h4>
    <div class="rg-sub">A = 原始策略（不加濾網）；B = 只在「進場決策當下」環境屬於所選環境時才允許新進場。出場邏輯、停損／停利、成本、初始資金、回測期間都和 A 相同。訊號被擋掉就不進場，不補進場。環境基準：<b>${regState.basis === 'market' ? '大盤' : '標的自身'}</b>（上方切換）。</div>
    <div class="rg-sub">${candTxt}</div>
    <div class="rg-checks" role="group" aria-label="允許新進場的環境">${checks}</div>
    <div class="ctrl-bar" style="padding:0;border:0;gap:8px;flex-wrap:wrap;"><button class="btn-primary" id="regCmp" type="button" onclick="regCompare(false)">比較（只看樣本內）</button>
      <button class="btn-secondary" id="regOos" type="button" onclick="regCompare(true)" ${f && f.status === 'ok' && d.split ? '' : 'disabled'} title="先按『比較』看樣本內；確定條件後才查看樣本外">查看樣本外（會被計數）</button></div>`;
  if(!f) out += '<div class="vb-note" style="margin-top:6px;">勾選要允許進場的環境後按「比較」。</div>';
  else if(f.status === 'unavailable') out += `<div class="state-card warn">資料不足：${esc(f.reason)}</div>`;
  else if(f.status !== 'ok') out += `<div class="state-card err">${esc(f.reason || '濾網對照失敗')}</div>`;
  else out += regFilterResultHtml(d, f);
  return out + '</div>';
}

function regApplyCandidate(){
  const d = regState.data; if(!d || !d.candidate) return;
  regState.allow = new Set(d.candidate.regimes); regRender(d);
}
function regReadAllow(){
  regState.allow = new Set([...document.querySelectorAll('#regBody .rg-allow:checked')].map(e => e.value));
}
function regSetBasis(b){ regState.basis = b; if(regState.data) regRender(regState.data); }

function regRender(d){
  const body = $id('regBody'), labels = d.labels, ref = d.reference || {};
  const bdAll = d.breakdown[regState.basis], split = d.split, mk = MARKET_LABEL[getMarket(d.symbol)] || d.market;
  const basisBtns = `<div class="rg-seg" role="group" aria-label="環境基準"><button type="button" class="${regState.basis === 'own' ? 'on' : ''}" onclick="regSetBasis('own')">標的自身環境</button><button type="button" class="${regState.basis === 'market' ? 'on' : ''}" onclick="regSetBasis('market')" ${ref.supported ? '' : 'disabled'}>大盤環境${ref.name ? '（' + esc(ref.name) + '）' : ''}</button></div>`;
  const dataTxt = d.data.cached === true ? `使用快取（${mtfAgeText(d.data.ageSec)}）` : (d.data.cached === false ? '重新取得' : '來源不明');
  let html = `<div class="rg-head"><b>${esc(d.symbol)}</b><span class="mk-badge">${esc(mk)}</span><span class="vb-note">${esc(d.strategyName)} · ${esc(TF_LABELS[d.timeframe] || d.timeframe)} · 近 ${esc(PERIOD_LABELS[d.period] || d.period)}（窗口自 ${esc(d.windowStart)}）· ${d.data.bars} 根 K 棒 · 資料：${esc(dataTxt)} · 檢查時間 ${esc(d.asOfUtc)} UTC</span></div>`;
  html += '<div id="sumBody">' + sumShellHtml() + '</div>';
  html += `<details class="rg-def"><summary>環境分類條件與歸屬規則</summary><table>${d.definition.rules.map(r => `<tr><td><b>${esc(r[0])}</b></td><td>${esc(r[1])}</td></tr>`).join('')}</table>
    <div>${esc(d.definition.attribution)}</div><div>${esc(d.definition.reference)}</div><div>ADX 沿用卡片的市場性格（${esc(d.definition.indicator)}，門檻 ${d.definition.trendThreshold} / ${d.definition.rangeThreshold}）。成本（單邊）：手續費 ${(d.costModel.commission * 100).toFixed(3)}%、滑價 ${(d.costModel.slippage * 100).toFixed(3)}%${d.costModel.sell_tax ? '、賣出稅 ' + (d.costModel.sell_tax * 100).toFixed(2) + '%' : ''}。</div></details>`;
  html += `<div class="rg-sub"><b>窗口內各環境佔比</b>（${regState.basis === 'market' ? '大盤環境' : '標的自身環境'}，只是歷史描述）</div>${regShareHtml(d.share[regState.basis], labels)}`;
  html += basisBtns;
  if(!ref.supported) html += `<div class="rg-sub">大盤環境：${esc(ref.reason || '不提供')}</div>`;
  if(ref.note) html += `<div class="rg-sub">${esc(ref.note)}</div>`;
  if(!bdAll) html += `<div class="state-card warn">資料不足：沒有可用的${regState.basis === 'market' ? '大盤' : ''}環境資料。</div>`;
  else {
    html += `<div class="rg-sub"><b>樣本內（IS）</b>　<span class="rtag hist">歷史回測</span>${split ? `（切分日 ${esc(split.boundary)} 之前）` : '（資料太短，沒有獨立樣本外，這裡等於整個窗口）'}</div>${regTableHtml(bdAll.is, labels, d.overall.is)}${regCardsHtml(bdAll.is, labels, d.overall.is)}`;
    if(split) html += `<div class="rg-sub" style="margin-top:10px;"><b>樣本外（OOS）</b>　<span class="rtag oos">樣本外測試</span>（切分日之後才進場的交易）</div>${regTableHtml(bdAll.oos, labels, d.overall.oos)}${regCardsHtml(bdAll.oos, labels, d.overall.oos)}`;
    else html += '<div class="state-card warn" style="margin-top:10px;">資料不足：沒有獨立的樣本外，所以不顯示樣本外結果。</div>';
  }
  html += regFilterBlockHtml(d);
  html += `<div class="vb-note" style="padding:8px 2px;">${esc(d.disclaimer)}</div><ul class="vb-note" style="padding-left:18px;">${d.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>`;
  body.innerHTML = html;
  body.querySelectorAll('.rg-allow').forEach(e => e.addEventListener('change', regReadAllow));
  if(regState.sumWanted) sumFromRegime(true);          // 已經產生過摘要:結果更新後自動重新整理(不重跑分析)
}

async function runRegimeView(opts){
  opts = opts || {};
  const custom = normSymbol($id('regCustom').value), symbol = custom || $id('regSel').value;
  const body = $id('regBody'), btn = $id('regRun');
  if(!symbol){ body.innerHTML = '<div class="empty-state">請選擇標的，或輸入代號。</div>'; return; }
  const tf = $id('regTf').value || '1d', strat = $id('regStrat').value, period = $id('regPeriod').value || '2y';
  if(!regState.pv) regState.pv = RCJob.progressView($id('regProg'), {labels: {indicators: '環境分類', backtest: '策略回測', validation: '樣本內／外切分', summary: '彙整'}});
  const pv = regState.pv;
  const allow = opts.allow ? [...opts.allow] : [];
  btn.disabled = true;
  ['regCmp', 'regOos'].forEach(i => { const e = $id(i); if(e) e.disabled = true; });
  if(!opts.keep) body.innerHTML = '';
  const q = `symbol=${encodeURIComponent(symbol)}&timeframe=${tf}&strategy=${encodeURIComponent(strat)}&period=${period}&basis=${regState.basis}${allow.length ? '&allow=' + allow.join(',') : ''}${opts.reveal ? '&reveal_oos=1' : ''}`;
  const handle = RCJob.run({buildUrl: id => `/api/regime_study?${q}&job=${id}`, onEvent: e => pv.event(e), onTick: ms => pv.tick(ms), onCancelling: () => pv.cancelling()});
  regState.handle = handle; pv.begin(handle);
  try{
    const res = await handle.done;
    if(res.cancelled){ pv.end('cancelled', {note: res.unconfirmed ? '已中斷連線，但沒有收到後端的停止確認。' : '已取消：後端確認已停止。'}); body.innerHTML = '<div class="state-card warn">已取消。</div>'; return; }
    if(res.error){ pv.end('stopped', {note: '連線中斷，沒有收到完整結果。'}); body.innerHTML = `<div class="state-card err">連線失敗：${esc(res.error)}。請確認本機伺服器仍在執行。</div>`; return; }
    if(!res.ok || !res.data || res.data.error){ pv.end('error', {note: (res.data && res.data.error) || '分析失敗'}); body.innerHTML = `<div class="state-card err">❌ ${esc((res.data && res.data.error) || '分析失敗')}</div>`; return; }
    const d = res.data;
    pv.end('ok', {note: `完成：${d.overall.all.trades} 筆交易，${d.data.cached === true ? '行情使用快取（沒有重新下載）' : '行情重新取得'}${d.reference && d.reference.cached === true ? '，大盤資料使用快取' : ''}。`});
    regState.data = d; if(d.filter && d.filter.allow) regState.allow = new Set(d.filter.allow);
    if(opts.allow && d.filter && d.filter.status === 'ok') regRecordTrial(d, d.filter);
    if(!d.reference.supported && regState.basis === 'market') regState.basis = 'own';
    regRender(d);
  }catch(e){
    pv.end('stopped', {note: '處理結果時發生錯誤。'}); body.innerHTML = `<div class="state-card err">處理結果時發生錯誤：${esc(e.message)}。</div>`;
  }finally{
    btn.disabled = false; regState.handle = null;
  }
}
function regCompare(reveal){
  regReadAllow();
  if(!regState.allow.size){ alert('請至少勾選一個要允許新進場的環境。'); return; }
  runRegimeView({allow: regState.allow, reveal: reveal, keep: true});
}

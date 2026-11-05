// ── 最佳策略 / 深度分析:共用的排名流程與比較表 ─────────────────────────
// 排名只用樣本內(IS)資料;樣本外(OOS)只對前幾名驗證一次、只標註,不影響排名(後端保證)。
// 這裡只負責「呈現」:所有數字直接取自 API,不在前端重算、不改變排名或通過與否的判斷。
let analysisStockId = null;
const MEDALS = ['🥇','🥈','🥉','4','5','6','7','8'];
const CAT_LABEL = {trend:'順勢', range:'均值回歸', breakout:'突破'};
const CAT_CLS   = {trend:'char-up', range:'char-range', breakout:'char-na'};
const rankStore = {};     // key → {stockId, symbol, tf, results}

function normSymbol(raw){
  const s = String(raw||'').trim().toUpperCase();
  return /^\d{4}$/.test(s) ? s + '.TW' : s;
}

function splitBannerHtml(data){
  const sp = data.split;
  if(data.oosAvailable && sp){
    return `<div class="split-banner">
      <span class="rtag hist">樣本內 IS</span> ${sp.windowStart} → ${sp.boundary}（<b>排名只用這段</b>）
      <span class="rtag oos">樣本外 OOS</span> ${sp.boundary} → ${sp.end}（只驗證前幾名，<b>不影響排名</b>）<br>
      OOS 展示分級（依筆數）：&lt;${sp.tierThresholds?sp.tierThresholds.preliminary:20} 筆＝樣本不足；${sp.tierThresholds?sp.tierThresholds.preliminary:20}～${sp.tierThresholds?sp.tierThresholds.evaluable-1:49} 筆＝初步觀察；≥${sp.tierThresholds?sp.tierThresholds.evaluable:50} 筆＝可進一步評估。
      這只是樣本量分級，<b>不是統計顯著性，也不代表策略有效或能獲利</b>。排名與所有績效皆已扣除成本。
    </div>`;
  }
  return `<div class="split-banner" style="color:#f5a623;">⚠ 這次沒有切出樣本外（資料太短或選了快速模式）：下列績效都是樣本內，<b>沒有獨立驗證</b>。</div>`;
}

function _c(v){ return v==null ? '' : (v>=0 ? 'pos' : 'neg'); }
function rankingHtml(key, data, ctx){
  const results = data.results || [];
  const ch = data.character;
  const fitCats = ch && (ch.code==='up'||ch.code==='down') ? ['trend','breakout'] : (ch && ch.code==='range' ? ['range'] : []);
  rankStore[key] = {stockId: ctx.stockId, symbol: ctx.symbol, tf: ctx.tf, period: ctx.period, results};
  const tfLabel = TF_LABELS[ctx.tf] || ctx.tf || '';
  const canApply = ctx.stockId != null;

  const catBadge = r => r.cat ? `<span class="char-badge show ${CAT_CLS[r.cat]}" style="margin-left:0;">${fitCats.includes(r.cat)?'✓ ':''}${CAT_LABEL[r.cat]||''}</span>` : '';
  const actions = i => (canApply
      ? `<button class="btn-apply" onclick="applyRankRow('${key}',${i})">套用</button> `
      : '') + `<button class="linkbtn" onclick="detailRankRow('${key}',${i})">詳細</button>`;
  const tierCell = r => {
    const o = r.oos;
    if(!o) return `${vbadge('unavailable')}`;
    return `${vbadge(r.oosTier || o.tier, o.trades)}<div class="vb-sub" title="${LEGACY_TIP}">舊版技術門檻：${legacyText(r.legacyTechPass != null ? r.legacyTechPass : o.legacyTechPass)}（非可信度）</div>`;
  };

  const head = `<tr>
      <th class="rank" rowspan="2">#</th><th class="name" rowspan="2">策略</th><th rowspan="2">時框</th>
      <th class="grp" colspan="3">樣本內 IS<br><small>排名用 · 歷史回測</small></th>
      <th class="grp" colspan="4"><span class="rtag oos">樣本外測試</span><br><small>排名時沒用到的後段</small></th>
      <th class="grp full" colspan="4">全期間（IS＋OOS）<br><small>僅供參考</small></th>
      <th class="grp left" rowspan="2">驗證分級</th><th class="left" rowspan="2">操作</th></tr>
    <tr><th class="sep">報酬</th><th>淨 PF</th><th>筆數</th>
      <th class="sep">報酬</th><th>淨 PF</th><th>筆數</th><th>回撤</th>
      <th class="sep full">報酬</th><th class="full">淨 PF</th><th class="full">回撤</th><th class="full">筆數</th></tr>`;

  const rows = results.map((r,i)=>{
    const is = r.is || {pf:r.pf,total:r.total,mdd:r.mdd,win:r.win,trades:r.trades};
    const o = r.oos, f = r.full;
    // OOS 欄位順序:報酬、PF、筆數、回撤(與表頭一致)
    const oosFixed = o ? (()=>{ const none=!o.trades; return `<td class="sep">${none?'—':`<span class="${_c(o.total)}">${fmtPct(o.total,1)}</span>`}</td><td>${none?'—':`<span class="${pfClass(o.pf,o.trades)}">${fmtPF(o.pf)}</span>`}</td><td>${o.trades}</td><td>${none?'—':pctPlain(o.mdd)}</td>`; })() : '<td colspan="4" class="sep full" style="text-align:center;">— 無樣本外驗證</td>';
    const isCells = (()=>{ const none=!is.trades; return `<td class="sep">${none?'—':`<span class="${_c(is.total)}">${fmtPct(is.total,1)}</span>`}</td><td>${none?'—':`<span class="${pfClass(is.pf,is.trades)}">${fmtPF(is.pf)}</span>`}</td><td>${is.trades}</td>`; })();
    const fullCells = (f && o) ? (()=>{ const none=!f.trades; return `<td class="sep full">${none?'—':fmtPct(f.total,1)}</td><td class="full">${none?'—':fmtPF(f.pf)}</td><td class="full">${none?'—':pctPlain(f.mdd)}</td><td class="full">${f.trades}</td>`; })() : '<td colspan="4" class="sep full" style="text-align:center;">—</td>';
    return `<tr class="${i===0?'top':''}">
      <td class="rank">${MEDALS[i]||i+1}</td>
      <td class="name"><b>${esc(r.name)}</b> ${catBadge(r)}<div class="vb-sub">綜合分數 ${r.score??''}（僅樣本內）</div></td>
      <td>${tfLabel}</td>${isCells}${oosFixed}${fullCells}
      <td class="left">${tierCell(r)}</td><td class="left">${actions(i)}</td></tr>`;
  }).join('');

  const cards = results.map((r,i)=>{
    const is = r.is || {pf:r.pf,total:r.total,mdd:r.mdd,win:r.win,trades:r.trades};
    const o = r.oos, f = r.full;
    const kv = (k,v)=>`<div class="k">${k}</div><div class="v">${v}</div>`;
    const ret = b => (!b||!b.trades) ? '—' : `<span class="${_c(b.total)}">${fmtPct(b.total,1)}</span>`;
    const pf  = b => (!b||!b.trades) ? '—' : `<span class="${pfClass(b.pf,b.trades)}">${fmtPF(b.pf)}</span>`;
    return `<div class="cmp-card">
      <h4>${MEDALS[i]||i+1} ${esc(r.name)} ${catBadge(r)}</h4>
      <div style="margin-bottom:6px;">${tierCell(r)}</div>
      <div class="cmp-grid">
        ${kv('樣本內 報酬 / 淨 PF / 筆數', `${ret(is)} / ${pf(is)} / ${is.trades}`)}
        ${o ? kv('樣本外 報酬 / 淨 PF', `${ret(o)} / ${pf(o)}`) + kv('樣本外 筆數 / 回撤', `${o.trades} / ${o.trades?pctPlain(o.mdd):'—'}`) : kv('樣本外','— 無')}
        ${(f&&o) ? kv('全期間(參考) 報酬 / 淨 PF', `${ret(f)} / ${pf(f)}`) + kv('全期間(參考) 回撤 / 筆數', `${f.trades?pctPlain(f.mdd):'—'} / ${f.trades}`) : ''}
      </div>
      <div style="margin-top:8px;display:flex;gap:8px;">${actions(i)}</div></div>`;
  }).join('');

  const note = `<div class="vb-note" style="padding:6px 2px;">排名前 ${results.length} 名（共測試 ${data.total_tested ?? '—'} 個策略）。<b>排名高不代表未來會賺</b>：我們從很多策略裡挑出歷史上表現最好的，本來就容易挑到湊巧的；請看樣本外的實際 PF、報酬、回撤與筆數，而不是只看分級。「舊版技術門檻」是程式內部舊條件（OOS ≥5 筆且 PF>1），不是研究可信度。</div>`;
  const dqWarn = (data.dataQuality && data.dataQuality.blocking) ? `<div class="state-card warn"><b>資料品質警告：${esc(data.dataQuality.label)}</b>　${esc(data.dataQuality.detail||'')}　以下排名是根據這份資料算的，不代表目前行情。</div>` : '';
  if(!results.length) return dqWarn + splitBannerHtml(data) + `<div class="empty-state">此標的在目前設定下，沒有策略在樣本內通過篩選條件。<br>可以換更長的期間，或改用深度分析。</div>`;
  return dqWarn + splitBannerHtml(data) + `<div class="cmp-wrap"><table class="cmp-table"><thead>${head}</thead><tbody>${rows}</tbody></table></div><div class="cmp-cards">${cards}</div>` + note;
}

function applyRankRow(key, i){
  const st = rankStore[key]; if(!st) return;
  const r = st.results[i]; if(!r || st.stockId == null) return;
  applyBestStrategy(st.stockId, r.strat, r.name);
  if(typeof showToast === 'function') showToast(`已套用「${r.name}」到自選清單`);
}
function detailRankRow(key, i){
  const st = rankStore[key]; if(!st) return;
  const r = st.results[i]; if(!r) return;
  closeAnalysis();
  if(typeof openSymbolView === 'function') openSymbolView(st.stockId, r.strat, {symbol: st.symbol, tf: st.tf, period: st.period});
}

// ── 共用流程:送出請求 → 以後端真實事件顯示進度 → 渲染結果 ───────────────────
// ui: {begin(handle), event(e), tick(ms), end(kind, {note,data,summary}), hideProgress(), setSub(html), setResults(html), busy(bool)}
// 進度只來自 /api/job_events 的真實事件(見 rc-job.js):後端知道『第 i 個/共 n 個』才顯示計數,不知道就顯示「處理中」。
// 這裡不再有依時間推算的百分比;也不會為了進度重跑策略或重新下載 K 線(輪詢端點不做任何運算)。
async function rankingFlow(kind, key, ctx, ui){
  const isDeep = kind === 'deep';
  const useOos = ctx.useOos !== false;
  const unsup = tfUnsupported(ctx.symbol, ctx.tf);
  if(unsup){ ui.setResults(`<div class="state-card warn"><b>此時框不支援</b>：${esc(unsup)}</div>`); ui.hideProgress(); return; }
  ui.busy(true); ui.setResults('');
  const buildUrl = jobId => isDeep
    ? `/api/deep_analysis?symbol=${encodeURIComponent(ctx.symbol)}&timeframe=${ctx.tf}&use_oos=${useOos?1:0}&job=${jobId}`
    : `/api/best_strategy?symbol=${encodeURIComponent(ctx.symbol)}&period=${ctx.period}&timeframe=${ctx.tf}&use_oos=${useOos?1:0}&job=${jobId}`;
  const handle = RCJob.run({buildUrl, onEvent: e => ui.event(e), onTick: ms => ui.tick(ms), onCancelling: () => ui.cancelling && ui.cancelling()});
  ui.begin(handle);
  try{
    const res = await handle.done;
    if(res.cancelled){
      ui.end('cancelled', {note: res.unconfirmed ? '已中斷連線，但 20 秒內沒有收到後端的停止確認（可能卡在行情下載）；後端會在下一個策略開始前停止。' : '已取消：後端確認已在下一個策略開始前停止，沒有產生半套結果。'});
      ui.setResults(`<div class="state-card warn">已取消分析。</div>`); return;
    }
    if(res.error){
      ui.end('stopped', {note: '連線中斷，沒有收到完整結果。', summary: '連線中斷'});
      ui.setResults(`<div class="state-card err">連線失敗：${esc(res.error)}。請確認本機伺服器仍在執行。</div>`); return;
    }
    const data = res.data;
    if(!res.ok || !data || data.error){
      ui.end('error', {note: (data && data.error) || '分析失敗', data});
      ui.setResults(`<div class="state-card err">❌ ${esc((data && data.error) || '分析失敗')}</div>`); return;
    }
    ui.end('ok', {data,
      note: (res.cancelRaced ? '你按了取消，但分析在後端收到取消前就已完成，以下是完整結果。　' : '') + `${isDeep?'深度分析':'分析'}完成！共測試 ${data.total_tested ?? '—'} 個策略；排名只看樣本內（IS），樣本外（OOS）只用來驗證`,
      summary: `共測試 ${data.total_tested ?? '—'} 個策略，入選 ${(data.results||[]).length} 名`});
    const ch = data.character;
    if(ch && ch.code && ch.code!=='na'){
      const icon={up:'🔼',down:'🔽',range:'↔️'}[ch.code]||'';
      const fit = (ch.code==='up'||ch.code==='down') ? ['順勢','突破'] : ch.code==='range' ? ['均值回歸'] : [];
      ui.setSub(`目前市場性格：<b>${icon} ${esc(ch.label)}</b>（${esc(ch.adxLabel||'ADX (Wilder, 14)')} ${ch.adx}）${fit.length?`　→ 通常 <b>${fit.join(' / ')}</b> 類策略較合（已標 ✓；這只是環境參考，不影響排名）`:''}`);
    }
    ui.setResults(rankingHtml(key, data, ctx));
  }catch(e){
    ui.end('stopped', {note: '處理結果時發生錯誤。'});
    ui.setResults(`<div class="state-card err">處理結果時發生錯誤：${esc(e.message)}。</div>`);
  }finally{
    ui.busy(false);
  }
}

// ── 彈窗版(自選清單卡片上的按鈕)──────────────────────────────────────
let modalHandle = null, modalPv = null;
function modalUi(){
  const $ = id => document.getElementById(id);
  return {
    begin(h){ modalHandle = h; const el = $('analysisProgress'); el.style.display = 'block'; modalPv = RCJob.progressView(el); modalPv.begin(h); },
    event(e){ if(modalPv) modalPv.event(e); },
    tick(ms){ if(modalPv) modalPv.tick(ms); },
    cancelling(){ if(modalPv) modalPv.cancelling(); },
    end(kind, o){ if(modalPv) modalPv.end(kind, o); modalHandle = null; },
    hideProgress(){ $('analysisProgress').style.display = 'none'; },
    setSub(html){ $('analysisSub').innerHTML = html; },
    setResults(html){ $('analysisResults').innerHTML = html; },
    busy(){},
  };
}
function openAnalysisModal(title, sub){
  document.getElementById('analysisBg').classList.add('open');
  document.getElementById('analysisTitle').textContent = title;
  document.getElementById('analysisSub').textContent = sub;
  document.getElementById('analysisProgress').style.display = 'block';
}

async function runBestStrategy(id, e){
  if(e) e.stopPropagation();
  const stock = stocks.find(s=>s.id===id);
  if(!stock) return;
  analysisStockId = id;
  openAnalysisModal(`🔍 ${stock.name||stock.symbol} — 最佳策略分析`,
    '前段資料為樣本內（IS）：只用它排名；後段為樣本外（OOS）：只對前 8 名各驗證一次，不影響排名。績效皆已扣除成本。');
  await rankingFlow('best', 'modal', {symbol: stock.symbol, period: stock.period||'2y', tf: stock.tf||'1d', stockId: id, useOos: true}, modalUi());
}

async function runDeepAnalysis(id, e){
  if(e) e.stopPropagation();
  const stock = stocks.find(s=>s.id===id);
  if(!stock) return;
  analysisStockId = id;
  const intra = ['4h','1h'].includes(stock.tf||'1d');
  openAnalysisModal(`🔬 ${stock.name||stock.symbol} — 深度分析`,
    (intra ? '加密貨幣：近 2 年。' : '台股/美股：近 5 年。') + '前段為樣本內（IS）用來排名，後段為樣本外（OOS）只驗證、不影響排名。績效皆已扣除成本。');
  await rankingFlow('deep', 'modal', {symbol: stock.symbol, period: intra?'2y':'5y', tf: stock.tf||'1d', stockId: id, useOos: true}, modalUi());
}

function applyBestStrategy(id, strat, name){
  const stock = stocks.find(s=>s.id===id);
  if(!stock) return;
  stock.strat = strat; save();
  closeAnalysis();
  // reloadCard 只重新載入資料,卡片外殼不重畫,所以要自己把選單與副標更新成新策略
  reloadCard(id);
  setTimeout(()=>{
    const sel = document.getElementById(`strat-sel-${id}`);
    if(sel) sel.value = strat;
    updateCardSub(id);
  }, 100);
}

// 關閉彈窗 = 不再需要這次結果 → 一併取消還在跑的分析,不讓它繼續耗用這台電腦的 CPU
function cancelModalJob(){ if(modalHandle){ modalHandle.cancel(); } }
function closeAnalysis(e){
  if(e&&e.target!==document.getElementById('analysisBg')) return;
  cancelModalJob();
  document.getElementById('analysisBg').classList.remove('open');
}
document.addEventListener('keydown',e=>{if(e.key==='Escape'){ cancelModalJob(); document.getElementById('analysisBg').classList.remove('open'); }});

function closeIntro(){
  const bar=document.getElementById('introBar');
  if(bar){bar.style.display='none';}
  localStorage.setItem('introSeen','1');
}
// 如果看過了就直接隱藏
if(localStorage.getItem('introSeen')==='1'){
  document.addEventListener('DOMContentLoaded',()=>{
    const bar=document.getElementById('introBar');
    if(bar) bar.style.display='none';
  });
}

const PRELOAD_COUNT = 5; // 預先載入前幾張

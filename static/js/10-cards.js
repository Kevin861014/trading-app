// ── 新增/刪除 ──────────────────────────────────────────
async function addStock(){
  const input=document.getElementById('addInput');
  const btn=document.querySelector('.btn-add');
  const raw=input.value.trim().toUpperCase();
  if(!raw) return;
  const symbol=/^\d{4}$/.test(raw)?raw+'.TW':raw;
  const strat=document.getElementById('addStrat').value||'diadx';

  // 先從固定清單找
  const dbEntry=(typeof STOCK_DB!=='undefined')?STOCK_DB.find(s=>s.s===symbol||s.s===symbol.toUpperCase()):null;

  let finalSymbol=symbol;
  let finalName=dbEntry?dbEntry.full:autoName(symbol);

  // 固定清單找不到 → 去後端驗證
  if(!dbEntry){
    btn.textContent='驗證中...';
    btn.disabled=true;
    try{
      const r=await fetch(`/api/validate?symbol=${encodeURIComponent(symbol)}`);
      const data=await r.json();
      if(!data.valid){
        alert(`❌ ${data.error}`);
        btn.textContent='＋ 加入';
        btn.disabled=false;
        return;
      }
      finalSymbol=data.symbol;
      finalName=data.name||finalSymbol;
      if(data.suggestion && data.suggestion !== symbol){
        input.value=data.suggestion;
      }
    }catch(e){
      alert('連線失敗，請稍後再試');
      btn.textContent='＋ 加入';
      btn.disabled=false;
      return;
    }
    btn.textContent='＋ 加入';
    btn.disabled=false;
  }

  const tf=dbEntry&&MARKET_TF?(MARKET_TF[dbEntry.market]||defaultTf(finalSymbol)):defaultTf(finalSymbol);
  const id=nextId++;
  const stock={id,symbol:finalSymbol,name:finalName,strat,period:'2y',tf,
    indicators:{ema:true,kd:true,rsi:true,vol:true}};
  stocks.push(stock);save();
  input.value='';
  hideRec();
  document.getElementById('searchDropdown').style.display='none';
  renderCard(stock);
  loadCard(id);
  updateNavBar();
  // 新加的股票如果跟目前分頁市場不同，自動切過去，不然會加了卻看不到
  const newMarket = getMarket(finalSymbol);
  if(activeMarketTab!=='all' && activeMarketTab!==newMarket){
    switchMarketTab(newMarket);
  } else {
    applyMarketFilter();
  }
  if(typeof refreshViewSelects==='function') refreshViewSelects();
}

function deleteStock(id,e){
  e.stopPropagation();
  if(!confirm('確定刪除？')) return;
  stocks=stocks.filter(s=>s.id!==id);save();
  destroyCard(id);
  document.getElementById(`card-${id}`)?.remove();
  updateNavBar();
  renderMarketTabs();
  if(typeof refreshViewSelects==='function') refreshViewSelects();
}

function destroyCard(id){
  if(chartInsts[id]){
    chartInsts[id].forEach(c=>{try{c.remove();}catch(e){}});
    delete chartInsts[id];
  }
}

// ── 展開 / 收合 ───────────────────────────────────────
// 卡片預設收合,只顯示重點。K 線與指標圖只在展開時才建立(收合時釋放),避免一次建立幾十張圖。
function isCardExpanded(id){ const s=stocks.find(s=>s.id===id); return !!(s && s.expanded); }
function setCardExpanded(id, on){
  const s=stocks.find(s=>s.id===id); if(!s) return;
  s.expanded=!!on; save();
  const card=document.getElementById(`card-${id}`); if(!card) return;
  const det=card.querySelector('.card-detail'); if(det) det.hidden=!on;
  const btn=card.querySelector('.card-expand'); if(btn){ btn.textContent=on?'收合 ▴':'展開詳細 ▾'; btn.setAttribute('aria-expanded', on?'true':'false'); }
  if(on){
    if(card.dataset.loaded==='1' && !chartInsts[id]){
      const data=JSON.parse(card.dataset.chartdata||'null');
      if(data) drawCharts(id,data,s.indicators);
    }
  } else {
    destroyCard(id);
    const cont=card.querySelector('.chart-container'); if(cont) cont.innerHTML='';
  }
  updateExpandAllBtn();
}
function toggleCardDetail(id){ setCardExpanded(id, !isCardExpanded(id)); }
function visibleStocks(){ return stocks.filter(s=>{ const c=document.getElementById(`card-${s.id}`); return c && c.style.display!=='none'; }); }
function toggleAllCards(){
  const vis=visibleStocks();
  const allOn=vis.length>0 && vis.every(s=>s.expanded);
  vis.forEach(s=>setCardExpanded(s.id, !allOn));
}
function updateExpandAllBtn(){
  const b=document.getElementById('expandAllBtn'); if(!b) return;
  const vis=visibleStocks();
  b.textContent=(vis.length>0 && vis.every(s=>s.expanded))?'全部收合':'全部展開';
}

// ── 設定變更 ──────────────────────────────────────────
function updateCardSub(id){
  const s=stocks.find(s=>s.id===id); if(!s) return;
  const card=document.getElementById(`card-${id}`); if(!card) return;
  const sub=card.querySelector('.card-sub'); if(!sub) return;
  // 注意：不能用 textContent 整個蓋掉，會把裡面的 char-badge <span> 一起砍掉，
  // 之後 loadCharacter() 就找不到那個 id、市場性格徽章跟策略對不對得上的警示都會停更。
  const badge = sub.querySelector('.char-badge');
  sub.textContent=`${s.symbol} · ${getStratName(s.strat)} · ${TF_LABELS[s.tf]||'1d'} `;
  if(badge) sub.appendChild(badge);
}
function changeStrat(id,val){const s=stocks.find(s=>s.id===id);if(s){s.strat=val;save();updateCardSub(id);updateMismatchWarn(id);}reloadCard(id);}
function changePeriod(id,val){const s=stocks.find(s=>s.id===id);if(s){s.period=val;save();}reloadCard(id);}
function changeTf(id,val){const s=stocks.find(s=>s.id===id);if(s){s.tf=val;save();updateCardSub(id);}reloadCard(id);}

function toggleIndicator(id,ind){
  const s=stocks.find(s=>s.id===id);
  if(!s) return;
  s.indicators[ind]=!s.indicators[ind];save();
  const btn=document.getElementById(`itoggle-${id}-${ind}`);
  if(btn) btn.classList.toggle('on',s.indicators[ind]);
  const card=document.getElementById(`card-${id}`);
  if(card&&card.dataset.loaded==='1'&&s.expanded){
    const data=JSON.parse(card.dataset.chartdata||'null');
    if(data) drawCharts(id,data,s.indicators);
  }
}

function toggleModalIndicator(ind){
  modalIndicators[ind]=!modalIndicators[ind];
  const btn=document.getElementById(`modal-itoggle-${ind}`);
  if(btn) btn.classList.toggle('on',modalIndicators[ind]);
  if(modalData) drawModalCharts(modalData,modalIndicators);
}

function reloadCard(id){
  destroyCard(id);
  const card=document.getElementById(`card-${id}`);
  if(card) card.dataset.loaded='0';
  loadCard(id);
}

// ── 載入資料 ──────────────────────────────────────────
let _loadSeq = 0;   // 同一張卡片連續重載時,只採用最後一次請求的結果
function setCardState(card, kind, msg){
  const color = (kind==='warn'||kind==='unsupported') ? 'var(--yellow,#f5a623)' : 'var(--red)';
  card.querySelector('.card-status').innerHTML=`<span style="color:${color};">⚠ ${esc(msg)}</span>`;
  const label = kind==='nodata' ? '— 資料不足' : (kind==='net' ? '— 連線失敗' : (kind==='unsupported' ? '— 此時框不支援' : '— 分析失敗'));
  card.querySelector('.signal-banner').innerHTML=`<span class="signal-big hold">${label}</span>`;
}

async function loadCard(id){
  const stock=stocks.find(s=>s.id===id);
  if(!stock) return;
  const card=document.getElementById(`card-${id}`);
  if(!card) return;
  const seq = ++_loadSeq; card.dataset.seq = seq;
  const unsup = tfUnsupported(stock.symbol, stock.tf||'1d');
  if(unsup){
    setMetrics(card,null); resetCardExtras(card); card.dataset.loaded='0';
    card.querySelector('.card-datatime').textContent='資料時間：—';
    setCardState(card,'unsupported',unsup); return;
  }
  card.querySelector('.card-status').innerHTML=`<span class="spinner"></span> 載入中...`;
  card.querySelector('.signal-banner').innerHTML='<span class="signal-big hold">— 載入中</span>';
  setMetrics(card,null);
  resetCardExtras(card);
  card.dataset.loaded='0';
  try{
    const r=await fetch(`/api/analyze?symbol=${encodeURIComponent(stock.symbol)}&strategy=${stock.strat}&period=${stock.period||'2y'}&timeframe=${stock.tf||'1d'}`);
    const data=await r.json();
    if(card.dataset.seq!==String(seq)) return;           // 已被較新的請求取代
    if(data.error){
      setCardState(card, /資料不足|不足/.test(data.error)?'nodata':'fail', data.error);
      return;
    }
    card.dataset.loaded='1';
    const {backtest, ...stored} = data;                  // 曲線資料只給「標的分析」用,不放進卡片
    card.dataset.chartdata=JSON.stringify(stored);
    setMetrics(card,data.metrics);
    setCardExtras(card,data);
    updateSignalBanner(card,data);
    if(stock.expanded) drawCharts(id,data,stock.indicators);
    drawTrades(card,data.metrics.trades);
    card.querySelector('.card-status').innerHTML=`<span style="color:var(--text3);">${new Date().toLocaleTimeString('zh-TW',{hour:'2-digit',minute:'2-digit'})} 已載入</span>`;
    updateNavBar();
    loadCharacter(id);
  }catch(e){
    if(card.dataset.seq!==String(seq)) return;
    setCardState(card,'net','連線失敗,請確認本機伺服器是否在執行');
  }
}

// 策略類型 vs 市場性格是否吃得上：跟「最佳策略」彈窗同一套判斷（trend/breakout 適合有方向、range 適合盤整）
function getStratCat(v){ const s=strategies.find(s=>s.v===v); return s?s.cat:''; }
function checkStratMismatch(marketCode, stratCat){
  if(!stratCat || !marketCode || marketCode==='na') return null; // 沒分類資訊就不判斷，別亂警告
  const fitCats = (marketCode==='up'||marketCode==='down') ? ['trend','breakout']
                : marketCode==='range' ? ['range'] : [];
  if(fitCats.includes(stratCat)) return null;
  const catLabel = {trend:'順勢', range:'均值回歸', breakout:'突破'};
  const marketLabel = {up:'上升趨勢', down:'下降趨勢', range:'盤整'}[marketCode];
  return `⚠ ${catLabel[stratCat]}策略遇上${marketLabel}，訊號可信度打折，非不能用，但要更小心`;
}

function updateMismatchWarn(id){
  const stock=stocks.find(s=>s.id===id);
  const el=document.getElementById(`mismatch-${id}`);
  if(!stock || !el) return;
  const msg = checkStratMismatch(stock._marketCode, getStratCat(stock.strat));
  if(msg){ el.textContent=msg; el.style.display='block'; }
  else{ el.style.display='none'; }
}

// 市場性格偵測（ADX）：在卡片標題列顯示趨勢/盤整徽章，並比對目前策略合不合
async function loadCharacter(id){
  const stock=stocks.find(s=>s.id===id);
  if(!stock) return;
  const el=document.getElementById(`char-${id}`);
  if(!el) return;
  try{
    const r=await fetch(`/api/market_character?symbol=${encodeURIComponent(stock.symbol)}&timeframe=${stock.tf||'1d'}`);
    const d=await r.json();
    const icon={up:'🔼',down:'🔽',range:'↔️',na:'⚪'}[d.code]||'⚪';
    const cls={up:'char-up',down:'char-down',range:'char-range',na:'char-na'}[d.code]||'char-na';
    el.className=`char-badge show ${cls}`;
    el.textContent=`${icon} ${d.label}${d.adx!=null?` ADX${d.adx}`:''}`;
    el.title=`${d.adxLabel||'ADX (Wilder, 14)'}${d.adx!=null?' = '+d.adx:''}`;
    stock._marketCode = d.code; // 記住，換策略時不用重打 API 就能重新比對
    updateMismatchWarn(id);
  }catch(e){ /* 靜默失敗，不影響卡片 */ }
}

function updateSignalBanner(card,data){
  const sig=getSignalState(data);
  const typeClass={'buy':'buy','sell':'sell','holding':'buy','expired':'hold','stale':'hold','exited':'sell','wait':'buy','bear':'sell','neutral':'hold'}[sig.type]||'hold';
  let html=`<span class="signal-big ${typeClass}">${sig.label}</span>`;
  if(sig.sub) html+=`<span class="sig-sub">${esc(sig.sub)}</span>`;
  html+=`<span class="rtag live" style="margin-left:auto;" title="策略『目前』的技術狀態,不是預測,也不是買賣建議">即時技術訊號</span>`;
  card.querySelector('.signal-banner').innerHTML=html;
}

// 指標 → 欄位。數字一律直接取自 API 的 metrics(不在前端重算)。
function setMetrics(card,m){
  const noTrades = m && m.tradeCount===0;
  [{k:'ret',fn:m=>(m.totalReturn>=0?'+':'')+m.totalReturn+'%',c:m=>m.totalReturn>=0?'up':'down'},
   {k:'cagr',fn:m=>(m.cagr>=0?'+':'')+m.cagr+'%',c:m=>m.cagr>=0?'up':'down'},
   {k:'pf',fn:m=>noTrades?'—':(m.pf>=999?'∞':m.pf.toFixed(2)),c:m=>noTrades?'neutral':(m.pf>=1?'up':'down')},
   {k:'dd',fn:m=>m.maxDD+'%',c:()=>'down'},
   {k:'wr',fn:m=>noTrades?'—':m.wr+'%',c:m=>'neutral'},
   {k:'tc',fn:m=>m.isPyramid&&m.totalAdds>0?`${m.tradeCount}筆<br><span style="font-size:10px;color:#f5a623;">(含${m.totalAdds}次加碼)</span>`:m.tradeCount+'筆',c:()=>'neutral'},
  ].forEach(d=>{
    const el=card.querySelector(`[data-m="${d.k}"]`);
    if(!el) return;
    const base = el.closest('.kpi') ? 'kpi-val' : 'metric-val';
    if(!m){ el.textContent='—'; el.className=base+' neutral'; return; }
    if(d.k==='tc') el.innerHTML=d.fn(m); else el.textContent=d.fn(m);
    el.className=base+' '+d.c(m);
  });
}

function resetCardExtras(card){
  const dt=card.querySelector('.card-datatime'); if(dt) dt.textContent='資料時間：載入中…';
  const o=card.querySelector('[data-oos]'); if(o) o.innerHTML=vbadge('unavailable')+'<span class="vb-sub">載入中…</span>';
  const v=card.querySelector('[data-vtable]'); if(v) v.innerHTML='';
  ['bh','cost'].forEach(k=>{ const el=card.querySelector(`[data-m="${k}"]`); if(el){ el.textContent='—'; el.className='metric-val neutral'; } });
  const n=card.querySelector('[data-costnote]'); if(n) n.textContent='';
}

// 資料時間、樣本外驗證、買進持有、成本:來自 /api/analyze 的 dataInfo / validation / backtest 區塊
function setCardExtras(card,data){
  const q=s=>card.querySelector(s);
  q('.card-datatime').innerHTML=esc(dataTimeText(data.dataInfo))+' '+dqBadge(data.dataQuality);
  if(data.extrasError){
    q('[data-oos]').innerHTML=vbadge('unavailable')+'<span class="vb-sub">進階資訊暫時無法取得</span>';
    q('[data-vtable]').innerHTML=`<div class="vb-note">進階資訊暫時無法取得(${esc(data.extrasError)}),基本績效不受影響。</div>`;
    return;
  }
  q('[data-oos]').innerHTML=oosKpiHtml(data.validation);
  q('[data-vtable]').innerHTML=validationTableHtml(data.validation);
  const bt=data.backtest;
  if(bt && bt.available){
    const s=bt.summary, c=bt.cost;
    const bh=q('[data-m="bh"]');
    if(bh && s.buyHoldTotal!=null){ bh.textContent=`${fmtPct(s.buyHoldTotal,1)}（回撤 ${s.buyHoldMaxDD}%）`; bh.className='metric-val '+retClass(s.buyHoldTotal); }
    const ct=q('[data-m="cost"]');
    if(ct){ ct.textContent=`${c.paidPctOfEquity}%`; ct.className='metric-val neutral'; }
    const n=q('[data-costnote]');
    if(n) n.textContent=`每筆來回成本約 ${c.roundTripPct}%（手續費＋滑價${c.sellTax>0?'＋賣出證交稅':''}）；期間 ${bt.period.start} → ${bt.period.end}，共 ${c.tradesInWindow} 筆交易，累計成本約為期初權益的 ${c.paidPctOfEquity}%。買進持有未計成本。`;
  }
}

function tradesHtml(trades){
  if(!trades||!trades.length) return '<div style="color:var(--text2);padding:8px 0;text-align:center;font-size:12px;">此期間無交易紀錄</div>';
  return trades.map(t=>`
    <div class="tm-row">
      <span style="color:var(--green);">▲${t.buyPrice}</span>
      <span style="color:var(--text3);margin:0 4px;">→</span>
      <span style="color:var(--red);">▼${t.sellPrice}</span>
      <span class="${t.ret>=0?'up':'down'}" style="font-weight:600;margin-left:8px;">${t.ret>=0?'+':''}${t.ret}%</span>
      <div class="tm-date">${t.buyDate||''} → ${t.sellDate||''}（已扣成本）</div>
    </div>`).join('');
}
function drawTrades(card,trades){
  card.querySelector('.trades-list').innerHTML=tradesHtml(trades);
}

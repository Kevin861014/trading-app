// ── 渲染卡片 ──────────────────────────────────────────
// 精簡卡片:標題 + 訊號 + 4 個重點指標(扣成本報酬 / 淨 PF / 最大回撤 / 樣本外驗證),其餘收在「展開詳細」。
const IND_DEFS=[
  {k:'ema',l:'EMA差距',tip:'EMA20（短期）和EMA50（長期）均線的差距百分比。綠柱代表短期均線在長期均線上方（多頭趨勢），紅柱反之（空頭）。接近0代表趨勢中立，是策略等待進場的時機。'},
  {k:'kd',l:'KD 線',tip:'隨機指標：K值（橘線）和D值（藍線），數值在0~100之間。KD>80進入超買區，可能回落；KD<20進入超賣區，可能反彈。K線從下往上穿越D線（黃金交叉）是買進參考，反之是賣出參考。'},
  {k:'rsi',l:'RSI',tip:'相對強弱指標，0~100之間。RSI>70 超買（漲太多），RSI<30 超賣（跌太多）。順勢策略中，RSI 回踩 50 後反彈是買進參考點；逆勢策略中，RSI<30 是進場時機。'},
  {k:'vol',l:'成交量',tip:'每根K棒的成交量。綠色代表收漲，紅色代表收跌。成交量放大且價格上漲，代表趨勢有動能支撐；成交量萎縮但價格繼續漲，可能是假突破。'},
];
const TIP = {
  ret:'這段期間策略的總報酬,已扣除手續費、滑價(台股另含賣出證交稅)。單看報酬不夠,要搭配淨 PF、最大回撤和交易筆數一起看。這是歷史回測,不是未來報酬。',
  pf:'淨獲利因子(扣成本後):總獲利 ÷ 總虧損。大於 1 代表這段歷史扣成本後仍有獲利。交易筆數少時 PF 很容易失真,請一併看筆數與樣本外結果。',
  dd:'最大回撤:這段時間資金從最高點最多跌了多少。越低越穩;回撤大代表過程會很煎熬,即使最終賺錢也很難抱住。',
  oos:TIER_TIP + ' 這裡顯示的是排名時沒用到的後段資料(樣本外)的實際績效。',
  cagr:'把總報酬換算成「每年」的基準,方便和其他標的比較。期間短時年化數字會被放大,請謹慎解讀。',
  wr:'勝率:幾成的交易是賺錢的。順勢策略通常只有 25~40%,靠賺的比虧的多撐起整體績效。',
  tc:'總交易筆數。筆數越少,PF、勝率越不穩定。',
  bh:'同一期間一直持有該標的的報酬與最大回撤(未計成本),用來對照策略有沒有比單純持有更好。',
  cost:'整段期間付出的手續費、滑價與稅,占期初權益的比例。',
};
function renderCard(stock){
  const div=document.createElement('div');
  div.className='card';div.id=`card-${stock.id}`;div.dataset.loaded='0';div.dataset.stockId=stock.id;
  const periodOpts=PERIODS.map(p=>`<option value="${p}" ${p===(stock.period||'2y')?'selected':''}>${PERIOD_LABELS[p]}</option>`).join('');
  const tfOpts=TFS.map(t=>`<option value="${t}" ${t===(stock.tf||'1d')?'selected':''}>${TF_LABELS[t]}${tfUnsupported(stock.symbol,t)?'（不支援）':''}</option>`).join('');
  const stratOpts=strategies.map(s=>`<option value="${s.v}" ${s.v===stock.strat?'selected':''}>${esc(s.l)}</option>`).join('');
  const inds=stock.indicators||{ema:true,kd:true,rsi:true,vol:true};
  const indToggles=IND_DEFS.map(o=>`<button id="itoggle-${stock.id}-${o.k}" class="itoggle ${inds[o.k]?'on':''}" onclick="toggleIndicator(${stock.id},'${o.k}')" data-tip="${o.tip}">${o.l}</button>`).join('');
  const mk=getMarket(stock.symbol);
  const open=!!stock.expanded;

  div.innerHTML=`
    <div class="card-top">
      <div class="card-id">
        <div class="card-name">${esc(stock.name||stock.symbol)} <span class="mk-badge">${MARKET_LABEL[mk]||mk}</span></div>
        <div class="card-sub">${esc(stock.symbol)} · ${esc(getStratName(stock.strat))} · ${TF_LABELS[stock.tf]||'1d'} <span id="char-${stock.id}" class="char-badge" data-tip="市場性格偵測（ADX）：判斷這支標的現在是在走趨勢還是盤整，幫你挑對應類型的策略。🔼上升/🔽下降趨勢→順勢策略；↔️盤整→均值回歸策略。"></span></div>
        <div class="card-datatime">資料時間：載入中…</div>
      </div>
      <div class="card-actions">
        <div class="act-main">
        <button class="btn-analyze" onclick="runBestStrategy(${stock.id},event)" title="跑所有策略並排名(僅用樣本內資料排名,再做樣本外驗證)">🔍 最佳策略</button>
        <button class="btn-analyze" id="deep-btn-${stock.id}" onclick="runDeepAnalysis(${stock.id},event)" title="深度分析:較長資料、較嚴筆數門檻,同樣樣本內排名、樣本外驗證(約 1~2 分鐘)" style="background:rgba(156,39,176,0.1);border-color:rgba(156,39,176,0.4);color:#b36fd0;">🔬 深度分析</button>
        </div>
        <div class="act-icons">
        <button class="btn-icon" onclick="openModal(${stock.id})" title="放大 K 線" aria-label="放大 K 線">⛶</button>
        <button class="btn-icon" onclick="reloadCard(${stock.id})" title="重新載入" aria-label="重新載入">↺</button>
        <button class="btn-icon del" onclick="deleteStock(${stock.id},event)" title="刪除" aria-label="刪除">✕</button>
        </div>
      </div>
    </div>
    <div id="mismatch-${stock.id}" class="mismatch-warn" style="display:none;" data-tip="策略分兩種：順勢/突破類適合有方向的行情，均值回歸類適合原地整理的行情。現在的市場性格跟選的策略類型對不上，訊號可信度要打折看，不是不能用，是要更小心。"></div>
    <div class="signal-banner" data-tip="目前策略狀態（即時技術訊號，不是預測）。▲買進訊號=現在符合進場條件；▼賣出訊號=現在符合出場條件；多頭趨勢=均線向上但尚未觸發訊號；空頭趨勢=不建議進場。"><span class="signal-big hold">— 等待載入</span></div>
    <div class="kpi-row">
      <div class="kpi" data-tip="${TIP.ret}"><div class="kpi-label">扣成本報酬 ⓘ</div><div class="kpi-val neutral" data-m="ret">—</div></div>
      <div class="kpi" data-tip="${TIP.pf}"><div class="kpi-label">淨 PF ⓘ</div><div class="kpi-val neutral" data-m="pf">—</div></div>
      <div class="kpi" data-tip="${TIP.dd}"><div class="kpi-label">最大回撤 ⓘ</div><div class="kpi-val neutral" data-m="dd">—</div></div>
      <div class="kpi kpi-oos" data-tip="${TIP.oos}"><div class="kpi-label">樣本外驗證 ⓘ</div><div data-oos>${vbadge('unavailable')}</div></div>
    </div>
    <div class="card-status"><span style="color:var(--text2);">等待載入...</span></div>
    <button class="card-expand" onclick="toggleCardDetail(${stock.id})" aria-expanded="${open}">${open?'收合 ▴':'展開詳細 ▾'}</button>
    <div class="card-detail" ${open?'':'hidden'}>
      <div class="metrics">
        <div class="metric" data-tip="${TIP.cagr}"><div class="metric-label">年化 ⓘ</div><div class="metric-val neutral" data-m="cagr">—</div></div>
        <div class="metric" data-tip="${TIP.wr}"><div class="metric-label">勝率 ⓘ</div><div class="metric-val neutral" data-m="wr">—</div></div>
        <div class="metric" data-tip="${TIP.tc}"><div class="metric-label">交易 ⓘ</div><div class="metric-val neutral" data-m="tc">—</div></div>
        <div class="metric" data-tip="${TIP.bh}"><div class="metric-label">買進持有 ⓘ</div><div class="metric-val neutral" data-m="bh">—</div></div>
        <div class="metric" data-tip="${TIP.cost}"><div class="metric-label">累計成本 ⓘ</div><div class="metric-val neutral" data-m="cost">—</div></div>
      </div>
      <div class="detail-note"><span class="rtag hist">歷史回測</span> <span data-costnote></span></div>
      <div class="detail-note"><span class="rtag oos">樣本外測試</span><div data-vtable style="margin-top:6px;"></div></div>
      <div class="chart-section">
        <div class="toolbar">
          <select class="sel-sm" id="strat-sel-${stock.id}" onchange="changeStrat(${stock.id},this.value)">${stratOpts}</select>
          <select class="sel-sm" id="period-sel-${stock.id}" onchange="changePeriod(${stock.id},this.value)">${periodOpts}</select>
          <select class="sel-sm" id="tf-sel-${stock.id}" onchange="changeTf(${stock.id},this.value)">${tfOpts}</select>
        </div>
        <div class="ind-toggles">${indToggles}</div>
        <div class="chart-container"></div>
        <div class="trades-section">
          <div class="trades-title">最近進出場</div>
          <div class="trades-list"></div>
        </div>
      </div>
      <div class="card-links">
        <button class="linkbtn" onclick="openSymbolView(${stock.id})">📊 標的分析（權益曲線／回撤／買進持有）</button>
      </div>
    </div>
  `;
  document.getElementById('grid').appendChild(div);
}

// ── 熱門選單 ──────────────────────────────────────────
let currentHotMarket = 'tw';

function switchHot(market){
  currentHotMarket = market;
  document.querySelectorAll('.htab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.htab').forEach(t => {
    if(t.textContent.includes(market==='tw'?'台股':market==='us'?'美股':market==='crypto'?'加密':'貴金屬'))
      t.classList.add('active');
  });
  renderHotStocks(market);
}

function renderHotStocks(market){
  const container = document.getElementById('hotStocks');
  if(!container || typeof STOCK_DB === 'undefined') return;
  const stocks = STOCK_DB.filter(s => s.market === market).slice(0, 20);
  container.innerHTML = stocks.map(s =>
    `<button class="hstock" onclick="quickAdd('${s.s}')" title="${s.full}">${s.n}</button>`
  ).join('');
}

function quickAdd(symbol){
  const dbEntry = STOCK_DB.find(s => s.s === symbol);
  if(!dbEntry) return;
  // 檢查有沒有重複
  if(stocks.find(s => s.symbol === symbol)){
    alert(`${dbEntry.full} 已經在清單裡了！`);
    return;
  }
  const strat = document.getElementById('addStrat').value || (dbEntry.rec && dbEntry.rec[0]) || 'diadx';
  const tf = MARKET_TF[dbEntry.market] || defaultTf(symbol);
  const id = nextId++;
  const stock = {id, symbol, name: dbEntry.full, strat, period: '2y', tf,
    indicators: {ema:true, kd:true, rsi:true, vol:true}};
  stocks.push(stock); save();
  renderCard(stock);
  loadCard(id);
  updateNavBar();
  // 捲動到新卡片
  setTimeout(() => scrollToCard(id), 300);
}

// ── 搜尋補全 ──────────────────────────────────────────
let searchActive = -1;
let currentRec = [];

function onSearchInput(){
  const q = document.getElementById('addInput').value.trim().toLowerCase();
  const dd = document.getElementById('searchDropdown');
  searchActive = -1;

  if(!q || q.length < 1){ dd.style.display='none'; hideRec(); return; }

  const results = STOCK_DB.filter(s =>
    s.n.toLowerCase().includes(q) ||
    s.s.toLowerCase().includes(q) ||
    s.full.toLowerCase().includes(q)
  ).slice(0, 12);

  if(!results.length){ dd.style.display='none'; hideRec(); return; }

  const mLabel = MARKET_LABEL;
  dd.innerHTML = results.map((s,i) => `
    <div class="search-item" data-idx="${i}" onclick="selectStock('${s.s}','${s.full}','${s.market}',${JSON.stringify(s.rec).replace(/"/g,"'")})">
      <span class="search-item-name">${s.full}</span>
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="search-item-code">${s.s}</span>
        <span class="search-item-market market-${s.market}">${mLabel[s.market]||s.market}</span>
      </div>
    </div>`).join('');
  dd.style.display = 'block';
}

function onSearchKey(e){
  const dd = document.getElementById('searchDropdown');
  const items = dd.querySelectorAll('.search-item');
  if(e.key === 'ArrowDown'){
    e.preventDefault();
    searchActive = Math.min(searchActive+1, items.length-1);
    items.forEach((el,i) => el.classList.toggle('active', i===searchActive));
  } else if(e.key === 'ArrowUp'){
    e.preventDefault();
    searchActive = Math.max(searchActive-1, -1);
    items.forEach((el,i) => el.classList.toggle('active', i===searchActive));
  } else if(e.key === 'Enter'){
    if(searchActive >= 0 && items[searchActive]){
      items[searchActive].click();
    } else {
      addStock();
    }
  } else if(e.key === 'Escape'){
    dd.style.display='none';
    hideRec();
  }
}

function selectStock(symbol, fullName, market, rec){
  document.getElementById('addInput').value = symbol;
  document.getElementById('searchDropdown').style.display = 'none';
  currentRec = rec || [];
  // 自動設定時框
  const tfMap = MARKET_TF || {tw:'1d',us:'1d',crypto:'4h',metal:'1d'};
  // 顯示推薦策略
  showRec(rec, fullName);
}

function showRec(rec, name){
  if(!rec || !rec.length){ hideRec(); return; }
  const bar = document.getElementById('recBar');
  const tags = document.getElementById('recTags');
  bar.style.display = 'flex';
  tags.innerHTML = rec.map((v,i) => {
    const label = STRAT_DESC[v] || v;
    return `<span class="rec-tag ${i===0?'best':''}" onclick="applyRec('${v}')" title="${i===0?'⭐ 最推薦':'推薦'}">${i===0?'⭐ ':''}${label}</span>`;
  }).join('');
}

function hideRec(){
  document.getElementById('recBar').style.display = 'none';
  currentRec = [];
}

function applyRec(stratVal){
  const sel = document.getElementById('addStrat');
  if(sel){
    for(let o of sel.options){
      if(o.value === stratVal){ sel.value = stratVal; break; }
    }
  }
  // 高亮選中的 tag
  document.querySelectorAll('.rec-tag').forEach(t => {
    t.style.fontWeight = t.getAttribute('onclick').includes(stratVal) ? '700' : '';
  });
}

// 點擊外部關閉下拉
document.addEventListener('click', e=>{
  if(!e.target.closest('.search-wrap')){
    document.getElementById('searchDropdown').style.display = 'none';
  }
});

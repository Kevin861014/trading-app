async function init(){
  await loadStrategies();
  stocks.forEach(s=>renderCard(s));
  applyNavState();
  applyMarketFilter();
  initViews();            // 路由 + 各視圖的下拉選單(不會呼叫任何 API)
  updateExpandAllBtn();

  // 1. 背景靜默載入所有股票輕量訊號 → 更新導覽列
  loadAllSignals();

  // 2. 前5張完整載入
  const preload = stocks.slice(0, PRELOAD_COUNT);
  preload.forEach(s => loadCard(s.id));

  // 3. 其餘卡片用 Intersection Observer 懶加載
  const lazyStocks = stocks.slice(PRELOAD_COUNT);
  if(lazyStocks.length > 0) setupLazyLoad(lazyStocks);
}

// 背景靜默載入輕量訊號（只更新導覽列，不渲染圖表）
async function loadAllSignals(){
  const results = await Promise.allSettled(
    stocks.map(s =>
      fetch(`/api/signal?symbol=${s.symbol}&strategy=${s.strat}&timeframe=${s.tf||'1d'}`)
        .then(r => r.json())
        .then(data => ({id: s.id, data}))
        .catch(() => null)
    )
  );
  // 把輕量訊號存到卡片上
  results.forEach(r => {
    if(r.status === 'fulfilled' && r.value) {
      const {id, data} = r.value;
      const card = document.getElementById(`card-${id}`);
      if(card && card.dataset.loaded !== '1') {
        card.dataset.signaldata = JSON.stringify(data);
      }
    }
  });
  updateNavBarFromSignals();
}

// 從輕量訊號更新導覽列（抽屜版）
function updateNavBarFromSignals(){
  updateNavDrawer();
}

function updateNavDrawer(){
  const body = document.getElementById('navDrawerBody');
  if(!body) return;
  const MARKET_LABELS = {tw:'📈 台股', us:'🇺🇸 美股', crypto:'₿ 加密貨幣', metal:'🥇 貴金屬', other:'📦 其他'};
  const groups = {tw:[], us:[], crypto:[], metal:[], other:[]};
  stocks.forEach(s => { const m = getMarket(s.symbol); (groups[m]=groups[m]||[]).push(s); });
  const colorMap = {buy:'#26a69a', sell:'#ef5350', expired:'#f5a623', hold:'#555a6e'};
  const sigMap = {buy:'▲ 買進！', sell:'▼ 賣出！', holding:'▲ 持有中',
    expired:'⚠ 已過期', stale:'⚠ 資料過期', exited:'▼ 已出場', wait:'多頭等待', bear:'▼ 空頭', neutral:'— 中立'};
  let html = '';
  ['tw','us','crypto','metal','other'].forEach(market => {
    const group = groups[market];
    if(!group||!group.length) return;
    html += `<div class="nav-group-label">${MARKET_LABELS[market]}</div>`;
    group.forEach(s => {
      const card = document.getElementById(`card-${s.id}`);
      let dot='hold', sigText='載入中...', itemClass='';
      if(card && card.dataset.loaded==='1'){
        const data = JSON.parse(card.dataset.chartdata||'null');
        if(data){ const sig=getSignalState(data); dot=sig.dot; sigText=sigMap[sig.type]||sig.label;
          if(sig.type==='buy'||sig.type==='holding') itemClass='sig-buy';
          else if(sig.type==='sell'||sig.type==='bear') itemClass='sig-sell'; }
      } else if(card && card.dataset.signaldata){
        const sig=JSON.parse(card.dataset.signaldata);
        dot=sig.dot||'hold'; sigText=sig.label||'— 載入中';
        if(dot==='buy') itemClass='sig-buy';
        else if(dot==='sell') itemClass='sig-sell';
      }
      html += `<div class="nav-item ${itemClass}" onclick="scrollToCard(${s.id});closeNav();">
        <div class="nav-dot ${dot}"></div>
        <div>
          <div class="nav-item-name">${s.name||s.symbol}</div>
          <div class="nav-item-sig" style="color:${colorMap[dot]||'#555a6e'}">${sigText}</div>
        </div>
      </div>`;
    });
  });
  body.innerHTML = html || '<div style="padding:16px;color:var(--text3);font-size:12px;">還沒有股票！</div>';
}

// Intersection Observer 懶加載
function setupLazyLoad(lazyStocks){
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if(entry.isIntersecting){
        const id = parseInt(entry.target.dataset.stockId);
        const card = document.getElementById(`card-${id}`);
        if(card && card.dataset.loaded !== '1' && card.dataset.loading !== '1'){
          card.dataset.loading = '1';
          loadCard(id);
          observer.unobserve(entry.target);
        }
      }
    });
  }, {rootMargin: '200px'}); // 提前 200px 開始載入

  lazyStocks.forEach(s => {
    const card = document.getElementById(`card-${s.id}`);
    if(card){
      card.dataset.stockId = s.id;
      observer.observe(card);
    }
  });
}
init();

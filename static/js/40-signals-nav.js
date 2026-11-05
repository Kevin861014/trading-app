// ── 訊號狀態判斷 ──────────────────────────────────────────
function getSignalState(data){
  const ps = data.posState || {};
  // C1:資料過期/異常時,不可以把舊資料顯示成『最新』交易訊號(只改顯示;策略與回測的計算完全不變)
  if(data.dataQuality && data.dataQuality.blocking){
    return {type:'stale', label:'⚠ 資料過期，不顯示最新訊號', sub:`${data.dataQuality.label}：${data.dataQuality.detail||''}`.slice(0,90), dot:'expired'};
  }
  const lastDiff = data.diff[data.diff.length-1];
  const hasBuyNow = data.buyPoints[data.buyPoints.length-1] !== null;
  const hasSellNow = data.sellPoints[data.sellPoints.length-1] !== null;
  if(hasBuyNow) return {type:'buy',label:'▲ 買進訊號！',sub:'',dot:'buy'};
  if(hasSellNow) return {type:'sell',label:'▼ 賣出訊號！',sub:'',dot:'sell'};
  if(ps.inPos){
    if(ps.signalExpired){
      const pnl=ps.floatPnl!=null?`(浮動 ${ps.floatPnl>=0?'+':''}${ps.floatPnl}%)`:'';
      return {type:'expired',label:'⚠ 訊號已過期',sub:`進場 ${ps.lastBuyPrice} ${pnl}`,dot:'expired'};
    }
    const days=ps.signalDaysAgo!=null?`第 ${ps.signalDaysAgo+1} 天`:'';
    const pnl=ps.floatPnl!=null?`${ps.floatPnl>=0?'+':''}${ps.floatPnl}%`:'';
    return {type:'holding',label:`▲ 策略建議持有中 ${days}`,sub:`進場 ${ps.lastBuyPrice}　浮動 ${pnl}`,dot:'buy'};
  }
  if(ps.lastSellDate) return {type:'exited',label:'▼ 策略已出場',sub:ps.lastSellDate||'',dot:'sell'};
  if(lastDiff>0.1) return {type:'wait',label:'▲ 多頭趨勢 · 等待訊號',sub:'',dot:'hold'};
  if(lastDiff<-0.1) return {type:'bear',label:'▼ 空頭趨勢 · 觀望',sub:'',dot:'sell'};
  return {type:'neutral',label:'— 中立 · 等待訊號',sub:'',dot:'hold'};
}

// ── 快速導覽列 ──────────────────────────────────────────
function updateNavBar(){
  updateNavBarFromSignals();
}

// ── 導覽列開關 ──────────────────────────────────────────
let navOpen = localStorage.getItem('navOpen') !== '0';

function toggleNav(){
  const drawer = document.getElementById('navDrawer');
  if(!drawer) return;
  drawer.classList.contains('open') ? closeNav() : openNav();
}
function openNav(){
  document.getElementById('navDrawer').classList.add('open');
  document.getElementById('navOverlay').classList.add('open');
  updateNavDrawer();
}
function closeNav(){
  document.getElementById('navDrawer').classList.remove('open');
  document.getElementById('navOverlay').classList.remove('open');
}
function applyNavState(){ updateNavDrawer(); }
function updateNavBar(){ updateNavDrawer(); }

function scrollToCard(id){
  if(typeof ensureWatchlistView==='function' && ensureWatchlistView()){ setTimeout(()=>scrollToCard(id), 60); return; }
  const card = document.getElementById(`card-${id}`);
  if(!card) return;
  const hdr = document.querySelector('.app-header');
  const offset = (hdr ? hdr.offsetHeight : 54) + 8;
  const top = card.getBoundingClientRect().top + window.scrollY - offset;
  window.scrollTo({top, behavior:'smooth'});
}

// ── 匯出股票清單 ──────────────────────────────────────────
function exportStocks(){
  const data = {
    version: '1.0',
    exportDate: new Date().toISOString().slice(0,10),
    stocks: stocks
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `trading-watchlist-${data.exportDate}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── 匯入股票清單 ──────────────────────────────────────────
function importStocks(event){
  const file = event.target.files[0];
  if(!file) return;
  const reader = new FileReader();
  reader.onload = async (e) => {
    try{
      const data = JSON.parse(e.target.result);
      const imported = data.stocks || data; // 支援舊格式
      if(!Array.isArray(imported)) throw new Error('格式錯誤');
      if(!confirm(`確定匯入 ${imported.length} 支股票？目前清單會被取代。`)) return;
      // 清除現有
      stocks.forEach(s => destroyCard(s.id));
      document.getElementById('grid').innerHTML = '';
      stocks = imported.map((s,i) => ({
        ...s,
        id: i+1,
        indicators: s.indicators || {ema:true,kd:true,rsi:true,vol:true}
      }));
      nextId = stocks.length + 1;
      save();
      stocks.forEach(s => renderCard(s));
      applyNavState();
      applyMarketFilter();
      loadAllSignals();
      stocks.slice(0, PRELOAD_COUNT).forEach(s => loadCard(s.id));
      setupLazyLoad(stocks.slice(PRELOAD_COUNT));
      if(typeof refreshViewSelects==='function') refreshViewSelects();
      alert(`✅ 成功匯入 ${stocks.length} 支股票！`);
    }catch(err){
      alert('匯入失敗：' + err.message);
    }
    event.target.value = '';
  };
  reader.readAsText(file);
}

// ── 導覽列分類顯示 ──────────────────────────────────────────
// getMarket() 已搬到 05-ui-helpers.js(與後端 classify_market 同一套規則)

const MARKET_GROUP_LABEL = {tw:'📈 台股', us:'美股', crypto:'₿ 加密', metal:'🥇 貴金屬'};

// ── 市場分頁：把自己追蹤的卡片依市場分開顯示 ──────────────────────
let activeMarketTab = localStorage.getItem('activeMarketTab') || 'all';

function renderMarketTabs(){
  const bar = document.getElementById('marketTabs');
  if(!bar) return;
  const counts = {all: stocks.length, tw:0, us:0, crypto:0, metal:0};
  stocks.forEach(s => { const m = getMarket(s.symbol); counts[m] = (counts[m]||0)+1; });
  const order = ['all','crypto','tw','us','metal'];
  const label = {all:'📋 全部', ...MARKET_GROUP_LABEL};
  bar.innerHTML = order
    .filter(m => m==='all' || counts[m]>0)
    .map(m => `<button class="mtab ${activeMarketTab===m?'active':''}" onclick="switchMarketTab('${m}')">${label[m]}<span class="mtab-count">${counts[m]||0}</span></button>`)
    .join('');
}

function applyMarketFilter(){
  // 分頁若失效（該市場已無卡片）就退回「全部」，避免畫面空白
  if(activeMarketTab!=='all' && !stocks.some(s=>getMarket(s.symbol)===activeMarketTab)){
    activeMarketTab='all';
    localStorage.setItem('activeMarketTab','all');
  }
  stocks.forEach(s => {
    const card = document.getElementById(`card-${s.id}`);
    if(!card) return;
    const show = activeMarketTab==='all' || getMarket(s.symbol)===activeMarketTab;
    card.style.display = show ? '' : 'none';
  });
  renderMarketTabs();
  if(typeof updateExpandAllBtn==='function') updateExpandAllBtn();
}

function switchMarketTab(m){
  activeMarketTab = m;
  localStorage.setItem('activeMarketTab', m);
  applyMarketFilter();
  window.scrollTo({top:0, behavior:'smooth'});
}

// ── 資料來源標示(網站在本機 Windows 執行)──────────────────────────
fetch('/api/config').then(r=>r.json()).then(data=>{
  const txt = data.ccxtAvailable ? '台股1D · 加密4H（ccxt）' : '台股1D · 加密4H（yfinance）';
  const tip = data.ccxtAvailable ? '加密貨幣使用 ccxt 幣安公開行情，支援真正 4H 和更長歷史' : '目前連不上幣安，加密貨幣改用 yfinance（4H 由 1H 合成，歷史較短）';
  document.querySelectorAll('.data-src-label').forEach(el=>{
    el.textContent = txt; el.title = tip;
    if(data.ccxtAvailable && el.id==='dataSourceLabel') el.style.color = '#26a69a';
  });
}).catch(()=>{});

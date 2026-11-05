// ── 常數 ──────────────────────────────────────────────
const PERIODS=['7d','1mo','3mo','6mo','1y','2y','3y','5y'];
const PERIOD_LABELS={'7d':'7天','1mo':'1月','3mo':'3月','6mo':'6月','1y':'1年','2y':'2年','3y':'3年','5y':'5年'};
const TFS=['1d','4h','1h'];
const TF_LABELS={'1d':'日線','4h':'4H','1h':'1H'};
const _isTouch = ('ontouchstart' in window) || navigator.maxTouchPoints > 0;
const CHART_OPTS={
  layout:{background:{color:'#0f1117'},textColor:'#8b90a0'},
  grid:{vertLines:{color:'rgba(255,255,255,0.04)'},horzLines:{color:'rgba(255,255,255,0.04)'}},
  crosshair:{
    mode:1,
    vertLine:{visible:true,labelVisible:true},
    horzLine:{visible:true,labelVisible:true},
  },
  rightPriceScale:{borderColor:'rgba(255,255,255,0.1)'},
  timeScale:{borderColor:'rgba(255,255,255,0.1)',timeVisible:true},
  handleScroll:{
    mouseWheel:true,
    pressedMouseMove:true,
    horzTouchDrag:true,
    vertTouchDrag:false,
  },
  handleScale:{
    mouseWheel:true,
    pinch:true,
    axisPressedMouseMove:true,
  },
  // 手機點擊直接觸發 crosshair
  kineticScroll:{touch:_isTouch, mouse:false},
};

function defaultTf(symbol){ return getMarket(symbol)==='crypto' ? '4h' : '1d'; }

// ── 計算指標 ──────────────────────────────────────────
function calcKD(prices,n=9){
  const K=[],D=[];let prevK=50,prevD=50;
  for(let i=0;i<prices.length;i++){
    const s=prices.slice(Math.max(0,i-n+1),i+1);
    const hi=Math.max(...s),lo=Math.min(...s);
    const rsv=hi===lo?50:(prices[i]-lo)/(hi-lo)*100;
    const k=prevK*(2/3)+rsv*(1/3),d=prevD*(2/3)+k*(1/3);
    K.push(parseFloat(k.toFixed(2)));D.push(parseFloat(d.toFixed(2)));
    prevK=k;prevD=d;
  }
  return{K,D};
}

function calcRSI(prices,n=14){
  const out=new Array(prices.length).fill(null);
  let ag=0,al=0;
  for(let i=1;i<prices.length;i++){
    const ch=prices[i]-prices[i-1],up=Math.max(ch,0),dn=Math.max(-ch,0);
    if(i<n){ag+=up/n;al+=dn/n;continue;}
    ag=(ag*(n-1)+up)/n;al=(al*(n-1)+dn)/n;
    out[i]=al>0?parseFloat((100-100/(1+ag/al)).toFixed(2)):100;
  }
  return out;
}

function calcEMADiff(ema20,ema50){
  return ema20.map((v,i)=>(v&&ema50[i]&&ema50[i]>0)?parseFloat(((v-ema50[i])/ema50[i]*100).toFixed(3)):0);
}

// ── 狀態 ──────────────────────────────────────────────
let strategies=[];
let stocks=JSON.parse(localStorage.getItem('stocks_v5')||'null')||[
  {id:1,symbol:'2330.TW',name:'台積電 2330',strat:'diadx',period:'2y',tf:'1d',indicators:{ema:true,kd:true,rsi:true,vol:true}},
  {id:2,symbol:'2317.TW',name:'鴻海 2317',strat:'diadx',period:'2y',tf:'1d',indicators:{ema:true,kd:true,rsi:true,vol:true}},
  {id:3,symbol:'2603.TW',name:'長榮 2603',strat:'diadx',period:'2y',tf:'1d',indicators:{ema:true,kd:true,rsi:true,vol:true}},
  {id:4,symbol:'0050.TW',name:'0050',strat:'sixline',period:'2y',tf:'1d',indicators:{ema:true,kd:true,rsi:true,vol:true}},
  {id:5,symbol:'PAXG-USD',name:'PAXG 黃金幣',strat:'supertrend',period:'2y',tf:'1d',indicators:{ema:true,kd:true,rsi:true,vol:true}},
  {id:6,symbol:'SOL-USD',name:'SOL',strat:'keltner',period:'2y',tf:'4h',indicators:{ema:true,kd:true,rsi:true,vol:true}},
  {id:7,symbol:'ETH-USD',name:'ETH',strat:'ttm',period:'2y',tf:'4h',indicators:{ema:true,kd:true,rsi:true,vol:true}},
];
let nextId=Math.max(...stocks.map(s=>s.id),0)+1;
let chartInsts={};
let modalChartInst=null;
let modalStockId=null;
let modalData=null;
let modalIndicators={ema:true,kd:true,rsi:true,vol:true};

const NAME_MAP={
  '2330.TW':'台積電 2330','2317.TW':'鴻海 2317','2603.TW':'長榮 2603',
  '2454.TW':'聯發科 2454','0050.TW':'0050','2308.TW':'台達電 2308',
  '3711.TW':'日月光 3711','2382.TW':'廣達 2382','3008.TW':'大立光 3008',
  '2891.TW':'中信金 2891','2412.TW':'中華電 2412',
  'AAPL':'Apple','MSFT':'Microsoft','NVDA':'NVIDIA','GOOGL':'Google',
  'AMZN':'Amazon','META':'Meta','TSLA':'Tesla','AMD':'AMD',
  'BTC-USD':'Bitcoin BTC','ETH-USD':'Ethereum ETH','BNB-USD':'BNB',
  'SOL-USD':'Solana SOL','XRP-USD':'XRP','PAXG-USD':'PAXG 黃金幣',
  'DOGE-USD':'Dogecoin','LINK-USD':'Chainlink',
};
function autoName(s){return NAME_MAP[s]||NAME_MAP[s.toUpperCase()]||s;}
function save(){localStorage.setItem('stocks_v5',JSON.stringify(stocks));}

// ── 策略載入 ──────────────────────────────────────────
async function loadStrategies(){
  try{const r=await fetch('/api/strategies');strategies=await r.json();}
  catch(e){strategies=[
    {v:'sixline',l:'六條線（最推薦）'},{v:'diadx',l:'DMI/ADX（台股最強）'},
    {v:'supertrend',l:'Supertrend'},{v:'keltner',l:'Keltner 突破'},
    {v:'volbreak',l:'波動突破'},{v:'ttm',l:'TTM 擠壓'},
    {v:'ema_cross',l:'EMA 快慢交叉'},{v:'donchian',l:'Donchian 突破'},
    {v:'trend',l:'順勢 EMA'},{v:'rsi',l:'RSI 逆勢'},
  ];}
  document.getElementById('addStrat').innerHTML=strategies.map(s=>`<option value="${s.v}">${s.l}</option>`).join('');
}
function getStratName(v){const s=strategies.find(s=>s.v===v);return s?s.l.split('（')[0].split('(')[0]:v;}


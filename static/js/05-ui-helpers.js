// ── 共用:格式、市場分類、驗證展示分級 ─────────────────────────────
// 市場分類規則與後端 sim.classify_market 一致(以 validation/stage3_ui 的對照測試驗證)。
const MARKET_LABEL = {tw:'台股', us:'美股', crypto:'加密', metal:'貴金屬'};
const BARE_CRYPTO = new Set(['BTC','ETH','BNB','SOL','XRP','DOGE','ADA','LINK','LTC','TRX','PAXG','DOT','XLM']);
const METAL_SET = new Set(['GLD','SLV','PPLT','PALL']);
function getMarket(symbol){
  const s = String(symbol||'').trim().toUpperCase();
  if(!s) return 'us';
  if(s.endsWith('.TW') || s.endsWith('.TWO')) return 'tw';
  if(s.endsWith('=F') || METAL_SET.has(s)) return 'metal';
  if(s.includes('/') || s.endsWith('-USD') || s.endsWith('-USDT') || (s.endsWith('USDT') && s.length > 4) || BARE_CRYPTO.has(s)) return 'crypto';
  return 'us';
}

function esc(s){
  return String(s==null?'':s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function fmtPF(v){ return v==null ? '—' : (v>=999 ? '∞' : Number(v).toFixed(2)); }
function fmtPct(v, d){ if(v==null || isNaN(v)) return '—'; d = (d==null?2:d); return (v>=0?'+':'') + Number(v).toFixed(d) + '%'; }
function pctPlain(v, d){ if(v==null || isNaN(v)) return '—'; return Number(v).toFixed(d==null?1:d) + '%'; }
function pfClass(pf, n){ if(n===0 || pf==null) return ''; return pf>=1 ? 'pos' : 'neg'; }
function retClass(v){ if(v==null) return ''; return v>=0 ? 'pos' : 'neg'; }

// OOS 筆數的「展示分級」:只是樣本量層級,不是統計顯著性判定,也不是通過/未通過,更不代表策略有效或會獲利。
const OOS_TIER_PRELIM = 20, OOS_TIER_EVAL = 50;
const TIER_LABEL = {insufficient:'樣本不足', preliminary:'初步觀察', evaluable:'可進一步評估', unavailable:'尚未驗證'};
const TIER_CLASS = {insufficient:'vb-low', preliminary:'vb-mid', evaluable:'vb-high', unavailable:'vb-na'};
const TIER_TIP = '展示分級（依樣本外交易筆數）：少於 20 筆＝樣本不足；20～49 筆＝初步觀察；50 筆以上＝可進一步評估。這只是樣本量分級，不是統計顯著性判定，也不代表策略有效或能獲利。';
function tierOf(n){ return n < OOS_TIER_PRELIM ? 'insufficient' : (n < OOS_TIER_EVAL ? 'preliminary' : 'evaluable'); }
function vbadge(tier, n){
  const t = TIER_LABEL[tier] ? tier : 'unavailable';
  const cnt = (t === 'unavailable' || n == null) ? '' : ` · OOS ${n} 筆`;
  return `<span class="vb ${TIER_CLASS[t]}" title="${TIER_TIP}">${TIER_LABEL[t]}${cnt}</span>`;
}
const LEGACY_TIP = '舊版技術門檻：樣本外至少 5 筆且淨 PF > 1。這只是程式內部的技術條件，不是研究可信度；筆數少時很容易湊巧達成。';
function legacyText(flag){
  if(flag == null) return '—';
  return flag ? '達成' : '未達成';
}

// 卡片上「樣本外驗證」那一格:分級 + 實際的 OOS 淨 PF / 報酬 / 回撤(不只靠筆數)
function oosKpiHtml(v){
  if(!v || v.available === false) return `${vbadge('unavailable')}<span class="vb-sub">${esc((v && v.reason) || '尚未驗證')}</span>`;
  const o = v.oos || {};
  if(!o.trades) return `${vbadge(o.tier || 'insufficient')}<span class="vb-sub">0 筆：樣本外期間沒有完成的交易</span>`;
  return `${vbadge(o.tier)}<span class="vb-sub">${o.trades} 筆 · 淨 PF <b class="${pfClass(o.pf, o.trades)}">${fmtPF(o.pf)}</b> · ${fmtPct(o.total,1)} · 回撤 ${pctPlain(o.mdd)}</span>`;
}

// 樣本內 / 樣本外 並排表(含日期)
function validationTableHtml(v){
  if(!v || v.available === false) return `<div class="vb-note">${esc((v && v.reason) || '尚未驗證')}</div>`;
  const s = v.split, a = v.is || {}, o = v.oos || {};
  const cell = (b, k) => {
    if(!b || (b.trades === 0 && k !== 'trades')) return '—';
    if(k === 'total') return `<span class="${retClass(b.total)}">${fmtPct(b.total)}</span>`;
    if(k === 'pf') return `<span class="${pfClass(b.pf, b.trades)}">${fmtPF(b.pf)}</span>`;
    if(k === 'mdd') return pctPlain(b.mdd, 2);
    if(k === 'win') return pctPlain(b.win, 1);
    return b.trades;
  };
  const row = (label, k) => `<tr><td>${label}</td><td>${cell(a,k)}</td><td>${cell(o,k)}</td></tr>`;
  return `<table class="vtable">
    <tr><th></th><th>樣本內 IS<br><small>${s.windowStart} → ${s.boundary}</small></th><th>樣本外 OOS<br><small>${s.boundary} → ${s.end}</small></th></tr>
    ${row('扣成本報酬','total')}${row('淨 PF','pf')}${row('最大回撤','mdd')}${row('勝率','win')}${row('交易筆數','trades')}
  </table>
  <div style="margin-top:8px;">${vbadge(o.tier, o.trades)} <span class="vb-note">跨越邊界的 ${o.carry||0} 筆交易兩邊都不算</span></div>
  <div class="vb-note" style="margin-top:6px;">舊版技術門檻（≥5 筆且 PF>1）：<b title="${LEGACY_TIP}">${legacyText(v.legacyTechPass)}</b>——僅為技術條件，<b>不是研究可信度</b>。
  分級只反映樣本量，不代表策略有效或能獲利；若這個策略是你看過排名或 OOS 結果後才選的，這段 OOS 就不再完全獨立。</div>`;
}

// 資料時間與時區(來自 API 的 dataInfo)
function dataTimeText(di){
  if(!di) return '資料時間：—';
  const src = di.source === 'ccxt' ? '幣安公開行情' : 'Yahoo Finance';
  if(di.interval === '1d' || di.interval === '1wk') return `資料至 ${di.lastBarLocal} 收盤 · ${di.tzLabel} · ${src}`;
  const loc = (di.tz !== 'UTC' && di.lastBarLocal) ? `（${di.lastBarLocal} ${di.tzLabel}）` : '';
  return `最後已收盤 K 棒 ${di.lastBarUtc} UTC${loc} · ${src}`;  // 日內時間以 UTC 顯示,括號內為交易所當地時間
}

// 台股/美股/貴金屬的 4H:資料來源只有 1H,合成 4H 的切點是 UTC 0/4/8/12/16/20 點(跟加密一樣),對不上這些市場的交易時段,
// 實測台股 4H 取不到任何完整區間、美股只剩少數完整區間——結果不可靠,所以標為不支援(日線與 1H 可用)。
function tfUnsupported(symbol, tf){
  if(tf === '4h' && getMarket(symbol) !== 'crypto')
    return '台股／美股／貴金屬不支援 4H：資料來源只有 1 小時資料，合成的 4H 區間對不上交易時段，結果不可靠。請改用日線或 1H。';
  return null;
}

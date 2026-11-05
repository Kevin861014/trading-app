// ── C3:規則式研究摘要(標的分析、市場環境) ───────────────────────────────
// 這不是 AI,也不是預測或買賣訊號:後端 rule_summary.py 只把「已經算好的」/api/regime_study 與 /api/mtf 回應,
// 套固定規則整理成中文說明;每一句話都附依據的 API 欄位(展開「判斷依據」查看),並可跳到對應數據。
// 前端不重算任何數字;摘要端點(/api/rule_summary)不下載資料、不跑回測。
const SUM_LEVEL_CLASS = {blocked: 'bad', insufficient: 'warn', notrades: 'na', descriptive: 'info'};

function sumEvidenceHtml(it){
  if(!it.evidence.length) return '<div class="vb-sub">這句沒有引用數據欄位（固定說明）。</div>';
  return `<table class="sum-ev-tbl"><thead><tr><th>項目</th><th>API 欄位</th><th>數值</th></tr></thead><tbody>${it.evidence.map(e => `<tr><td>${esc(e.label)}</td><td><code>${esc(e.path)}</code></td><td>${esc(e.display)}</td></tr>`).join('')}</tbody></table>`;
}
function sumItemHtml(it, view){
  const jump = it.jump ? `<button type="button" class="linkbtn sum-jump" data-view="${view}" data-target="${esc(it.jump.target)}">查看對應數據：${esc(it.jump.label)}</button>` : '';
  return `<li class="sum-item ${it.level ? 'sum-' + it.level : ''}"><div>${esc(it.text)}</div>
    <details class="sum-ev"><summary>判斷依據</summary>${sumEvidenceHtml(it)}<div class="vb-sub">此句由固定模板與上列欄位組成，沒有其他資料來源。</div></details>${jump}</li>`;
}
function sumRender(el, s, view){
  const h = s.headline, lv = SUM_LEVEL_CLASS[h.level] || 'info';
  el.innerHTML = `<div class="sum-head"><span class="dq dq-${lv}">${esc(h.levelLabel)}</span> <b>${esc(h.text)}</b></div>
    <div class="vb-note">規則式摘要：${esc(s.disclaimer)}</div>
    ${s.sections.map(sec => `<details class="sum-sec" open><summary>${esc(sec.title)}</summary><ul class="sum-list">${sec.items.map(it => sumItemHtml(it, view)).join('')}</ul></details>`).join('')}
    <details class="sum-rules"><summary>固定規則清單（摘要只依這些規則產生）</summary><ol>${s.rules.map(r => `<li>${esc(r)}</li>`).join('')}</ol></details>`;
  el.querySelectorAll('.sum-jump').forEach(b => b.addEventListener('click', () => sumJump(b.dataset.view, b.dataset.target)));
}
function sumFlash(node){
  if(!node) return false;
  node.scrollIntoView({block: 'start', behavior: 'auto'});
  node.classList.add('sum-flash'); setTimeout(() => node.classList.remove('sum-flash'), 1800);
  return true;
}
function sumJump(view, target){
  if(view === 'symbol'){
    // 標的分析頁自己有的數字(績效)就在本頁;多週期、環境分類、濾網在市場環境頁
    if(/rg-tbl|rg-head/.test(target) && sumFlash(document.querySelector('#symBody .kpi-grid'))) return;
    location.hash = '#/market';
    setTimeout(() => { if(!sumFlash(document.querySelector(target))) alert('這項數據要先在「市場環境」頁按對應的分析按鈕才會顯示。'); }, 250);
    return;
  }
  if(!sumFlash(document.querySelector(target))) alert('找不到對應的數據區塊，請先執行上方的分析。');
}

async function sumPost(study, mtf, trials){
  const r = await fetch('/api/rule_summary', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({study, mtf, trials})});
  const j = await r.json(); if(!r.ok || j.error) throw new Error(j.error || '摘要失敗'); return j;
}

// 市場環境頁:用「環境 × 策略歷史績效」面板已經拿到的結果(與多週期面板的結果),不重跑分析;多週期缺的話用既有的多週期流程(有進度列)補。
async function sumFromRegime(quiet){
  const d = regState.data, box = $id('sumBody'); if(!d || !box) return;
  regState.sumWanted = true;
  const out = box.querySelector('.sum-out'); const btn = box.querySelector('button.sum-run');
  if(btn) btn.disabled = true;
  try{
    if(!mtfState.data || mtfState.data.symbol !== d.symbol){ $id('mtfCustom').value = d.symbol; await runMtfView(); }
    const list = regTrialsLoad(d), trials = {count: list.length, revealed: list.filter(t => t.revealed).length};
    const s = await sumPost(d, mtfState.data && mtfState.data.symbol === d.symbol ? mtfState.data : null, trials);
    sumRender(out, s, 'market');
  }catch(e){ out.innerHTML = `<div class="state-card err">摘要失敗：${esc(e.message)}</div>`; }
  finally{ if(btn) btn.disabled = false; }
}
function sumShellHtml(){
  return `<div class="sum-box"><div class="sum-bar"><b>研究摘要</b><span class="rtag na" title="固定規則整理，沒有 AI、不是預測">規則式，不是 AI</span>
    <button type="button" class="btn-secondary sum-run" onclick="sumFromRegime()">產生／更新研究摘要</button></div>
    <div class="sum-out"><div class="vb-note">依固定規則，把上面的結果與多週期資料整理成中文說明，並列出每句話的依據欄位。資料過期、樣本不足或沒有交易時只會描述，不下結論。</div></div></div>`;
}

// 標的分析頁:用該頁目前的標的／策略／期間／時框,向既有 API 取(走快取)後整理。
async function sumForSymbol(){
  const ctx = _symLast && _symLast.ctx, box = $id('symSum'); if(!ctx || !box) return;
  const out = box.querySelector('.sum-out'), btn = box.querySelector('button.sum-run'); btn.disabled = true;
  out.innerHTML = '<div class="vb-note">整理中…（行情與回測多半已快取）</div>';
  try{
    const q = `symbol=${encodeURIComponent(ctx.symbol)}&timeframe=${ctx.tf}&strategy=${encodeURIComponent(ctx.strat)}&period=${ctx.period}&basis=own`;
    const [sr, mr] = await Promise.all([fetch(`/api/regime_study?${q}`), fetch(`/api/mtf?symbol=${encodeURIComponent(ctx.symbol)}`)]);
    const study = await sr.json(), mtf = await mr.json();
    if(!sr.ok || study.error) throw new Error(study.error || '環境研究失敗');
    const s = await sumPost(study, mr.ok && !mtf.error ? mtf : null, {});
    sumRender(out, s, 'symbol');
  }catch(e){ out.innerHTML = `<div class="state-card warn">無法產生摘要：${esc(e.message)}</div>`; }
  finally{ btn.disabled = false; }
}
function sumSymbolShellHtml(){ return `<div id="symSum">${sumShellHtml().replace('sumFromRegime()', 'sumForSymbol()')}</div>`; }

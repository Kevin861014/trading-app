// ── 策略實驗室:研究核心(U 型資訊布局)+ 全部策略分析結果 ───────────────────────
// 只出現在「策略實驗室」一處(整個網站只有一個球體);自選清單的卡片、彈窗、最佳策略頁都不渲染球體。
// 畫面完全由後端真實事件(rc-job.js)與最後的 API 回應驅動;沒有資料的欄位顯示「—」或「完成後顯示」,不自行推算。
// 左右六個區塊是『資訊摘要』,不是六個運算階段:實際只有 行情資料、策略回測(含篩選)、樣本外驗證 三個階段在執行;
// 指標計算、訊號判斷、風險與成本在這個流程不會執行(球體上的節點會標為『未涉及』)。
// 動畫引擎(rc-engine.js)與事件模型(rc-job.js)沒有任何修改。
const labState = {core: null, model: null, pv: null, data: null, selected: null, detailTimer: 0, handle: null, mode: 'u', running: false, userSet: false, t0: 0, ms: null, st: null, raf: 0, c3: null, c3Timer: 0};

function labFreshStats(){
  return {data: null, dataErr: null, bt: {n: null, i: 0, kept: 0, filtered: 0, noResult: 0, error: 0, pf: 0, trades: 0, mdd: 0, multi: 0, thr: null, started: false, done: false},
          val: {n: null, i: 0, skip: null, started: false, done: false}, final: null};
}

function labEnsure(){
  const body = $id('labBody');
  if(!body || labState.core) return;
  body.innerHTML = `
    <div class="panel rc-lab rc-m-u" id="labPanel"><div class="panel-b">
      <div class="rc-lab-head">
        <b>研究核心</b>
        <span class="vb-note rc-lab-note">左右六個區塊只是資訊摘要,數字全部來自這次分析的真實事件與結果;球體與光點只依後端真實事件亮起。實際執行的階段只有行情資料、策略回測(含篩選)、樣本外驗證。</span>
        <label class="lab3d-opt" id="lab3dOpt" title="只是裝飾,不代表運算;預設關閉"><input type="checkbox" id="lab3dAmb"> 裝飾旋轉</label>
        <button type="button" class="rc-toggle" id="labToggle" aria-expanded="false" aria-controls="labCoreWrap" onclick="labToggle()">展開研究核心 ▾</button>
      </div>
      <div class="rcu-grid">
        <div class="rcu-col rcu-left">
          <div class="rcu-blk" id="rcuData"><h5>行情資料</h5><div class="rcu-b"></div></div>
          <div class="rcu-blk" id="rcuBt"><h5>策略回測</h5><div class="rcu-b"></div></div>
          <div class="rcu-blk" id="rcuPass"><h5>篩選通過</h5><div class="rcu-b"></div></div>
        </div>
        <div class="rcu-center" id="labCoreWrap"><div id="labCore"></div>
          <div class="lab-flow" id="labFlow" role="group" aria-label="研究流程(只列出實際執行的階段)">
            <button type="button" class="lf-node idle" data-stage="data" title="行情資料"><i>1</i><span class="l">行情資料</span><span class="s">待機</span></button><span class="lf-link"></span>
            <button type="button" class="lf-node idle" data-stage="backtest"><i>2</i><span class="l" title="策略回測 + 篩選">回測篩選</span><span class="s">待機</span></button><span class="lf-link"></span>
            <button type="button" class="lf-node idle" data-stage="validation" title="樣本外驗證"><i>3</i><span class="l">樣本外驗證</span><span class="s">待機</span></button><span class="lf-link"></span>
            <button type="button" class="lf-node idle" data-stage="result" title="排名由回測結果整理而來,不是獨立的後端階段"><i>4</i><span class="l">排名結果</span><span class="s">待機</span></button>
          </div></div>
        <div class="rcu-col rcu-right">
          <div class="rcu-blk" id="rcuOos"><h5>樣本外驗證</h5><div class="rcu-b"></div></div>
          <div class="rcu-blk" id="rcuFail"><h5>未通過篩選</h5><div class="rcu-b"></div></div>
          <div class="rcu-blk" id="rcuRank"><h5>最終排名</h5><div class="rcu-b"></div></div>
        </div>
      </div>
      <div class="rcu-status" id="labStatus"><span class="rcu-idle" id="labIdle">待機中 · 選好標的後按「開始深度分析」</span><div id="labProg"></div></div>
      <div class="rcd" id="labDetail"></div>
    </div></div>
    <div class="vb-note" id="labSub"></div>
    <div id="labRes"><div class="empty-state">選好標的後按「開始深度分析」。</div></div>`;
  labState.model = new RCJob.Model();
  labState.pv = RCJob.progressView($id('labProg'), {model: labState.model});
  const now = $id('labProg').querySelector('.rcp-now'), seg = document.createElement('span'); seg.id = 'labSeg'; seg.className = 'rcu-seg'; now.after(seg);   // 狀態列:『策略回測 120/166 ｜ 已通過 42 ｜ 執行中 ｜ 5.2 秒』
  labState.core = RCEngine.create($id('labCore'), {model: labState.model, onNodeClick: id => { labState.selected = id; if(labState.mode !== 'full') labSetMode('full'); labRenderDetail(); }});
  document.querySelectorAll('#labCore .rc-node').forEach(n => { n.title = (n.querySelector('.l') ? n.querySelector('.l').textContent : '') + '(點擊展開並查看這個階段的細節)'; });
  labState.st = labFreshStats(); labRenderBlocks(); labRenderDetail(); labRenderFlow();
  document.querySelectorAll('#labFlow .lf-node').forEach(b => b.addEventListener('click', () => labFlowClick(b.dataset.stage)));
  const amb = $id('lab3dAmb'); try{ amb.checked = localStorage.getItem('rcAmbient') === '1'; }catch(e){}
  amb.addEventListener('change', () => { try{ localStorage.setItem('rcAmbient', amb.checked ? '1' : '0'); }catch(e){} if(labState.c3) labState.c3.setAmbient(amb.checked); });
  labTry3D();
}

// ── 版面狀態:u(預設,精簡 U 型)/ full(使用者展開:完整球體、選項、階段細節)──
function labSetMode(mode){
  const S = labState, panel = $id('labPanel'); if(!panel) return;
  S.mode = mode;
  panel.classList.remove('rc-m-u', 'rc-m-full'); panel.classList.add('rc-m-' + mode);
  const btn = $id('labToggle');
  if(btn){ btn.textContent = mode === 'full' ? '精簡研究核心 ▴' : '展開研究核心 ▾'; btn.setAttribute('aria-expanded', mode === 'full' ? 'true' : 'false'); }
  if(S.core) requestAnimationFrame(() => { S.core.resize(); if(S.c3) S.c3.resize(); });                // 區塊尺寸改變後讓球體依新尺寸重畫(只是重新量測)
  if(mode === 'full') labRenderDetail();
}
function labToggle(){ labState.userSet = true; labSetMode(labState.mode === 'full' ? 'u' : 'full'); }

// ── 資訊區塊 ──
const labNum = v => (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString('en-US');
function labSrcText(d){
  if(!d) return '—';
  if(d.source === 'ccxt') return '幣安 USDT-M 永續(ccxt)';
  if(d.source === 'yfinance') return 'Yahoo Finance';
  return d.source ? String(d.source) : '來源不明';
}
function labApplyEvent(e){
  const S = labState, st = S.st; if(!st) return;
  if(e.stage === 'data'){
    if(e.status === 'done') st.data = {bars: e.bars, source: e.source, venue: e.venue, missing: e.missingBars, first: e.firstBar, last: e.lastBar, cached: e.cached, ageSec: e.ageSec};
    else if(e.status === 'error') st.dataErr = e.message || '資料取得失敗';
  } else if(e.stage === 'backtest'){
    const b = st.bt;
    if(e.status === 'start'){ b.started = true; b.n = e.n; b.thr = {pfAbove: e.pfAbove, minTrades: e.minTrades, mddBelow: e.mddBelow, topN: e.topN}; }
    else if(e.status === 'progress'){
      b.i = e.i; b.n = e.n; b.kept = e.kept; b.last = {strat: e.strat, outcome: e.outcome, why: e.why};
      if(e.outcome === 'filtered'){ b.filtered++; const w = (e.why || '').split(',').filter(Boolean); w.forEach(c => { if(c in b) b[c]++; }); if(w.length > 1) b.multi++; }
      else if(e.outcome === 'no_result') b.noResult++;
      else if(e.outcome === 'error') b.error++;
    } else if(e.status === 'done') b.done = true;
  } else if(e.stage === 'validation'){
    const v = st.val;
    if(e.status === 'start'){ v.started = true; v.n = e.n; }
    else if(e.status === 'progress'){ v.i = e.i; v.n = e.n; }
    else if(e.status === 'done') v.done = true;
    else if(e.status === 'skip') v.skip = e.reason || '本次沒有進行樣本外驗證';
  }
  labScheduleBlocks();
}
function labScheduleBlocks(){ if(labState.raf) return; labState.raf = requestAnimationFrame(() => { labState.raf = 0; labRenderBlocks(); labRenderSeg(); labRenderFlow(); labRunner(); }); }

function labBlock(id, html, cls){ const el = document.querySelector('#' + id + ' .rcu-b'); if(el){ el.innerHTML = html; el.className = 'rcu-b' + (cls ? ' ' + cls : ''); } }
function labRenderBlocks(){
  const S = labState, st = S.st; if(!st) return;
  const f = st.final, b = st.bt, running = S.running, idle = !S.t0 && !running;
  const partial = !running && !f && !idle;                                          // 已取消/失敗/中斷:沒有完整結果,只剩中途數字
  const wait = '<span class="rcu-dim">' + (idle ? '尚未分析' : (running ? '分析中,完成後顯示' : '這次分析沒有完成,沒有結果')) + '</span>';
  const part = partial ? '<br><span class="rcu-bad">已中止:以上只是中途數字,不是完整結果</span>' : '';
  // 1 行情資料
  const d = st.data, q = S.data && S.data.dataQuality;
  if(st.dataErr) labBlock('rcuData', `<span class="rcu-bad">資料取得失敗</span>:${esc(st.dataErr)}`, 'bad');
  else if(!d) labBlock('rcuData', idle ? wait : '取得行情中…');
  else labBlock('rcuData', `${esc(labSrcText(d))} · <b>${labNum(d.bars)}</b> 根 · 缺棒 <b>${d.missing == null ? '—' : labNum(d.missing)}</b>${d.missing == null ? '(此來源沒有檢查)' : ''}<br>${d.first ? esc(d.first) + ' → ' + esc(d.last) + ' UTC' : '期間 —'} · 品質 ${q ? `<b class="${q.blocking ? 'rcu-bad' : ''}">${esc(q.label)}</b>` : '<span class="rcu-dim">完成後顯示</span>'}${d.cached === true ? ' · 使用快取' : ''}`);
  // 2 策略回測
  const cand = f ? f.candidates : b.n, ok = f ? f.backtested : (b.i - b.noResult - b.error), bad = f ? f.noResult + f.errors : b.noResult + b.error, done = f ? cand : b.i;
  if(cand == null) labBlock('rcuBt', wait);
  else labBlock('rcuBt', `候選 <b>${labNum(cand)}</b> · 成功回測 <b>${labNum(ok)}</b> · 失敗/跳過 <b class="${bad ? 'rcu-bad' : ''}">${labNum(bad)}</b><br>已處理 <b>${labNum(done)}</b> / ${labNum(cand)}${f && f.noResult ? ` · 無結果 ${f.noResult}` : ''}${f && f.errors ? ` · 例外 ${f.errors}` : ''}${part}`, bad ? 'warn' : '');
  // 3 篩選通過
  const thr = f ? f.thresholds : b.thr, passed = f ? f.passed : b.kept;
  if(!b.started && !f) labBlock('rcuPass', wait);
  else labBlock('rcuPass', `通過 <b>${labNum(passed)}</b> 個<br>門檻:樣本內 PF &gt; ${thr ? thr.pfAbove : '—'} · 筆數 ≥ ${thr ? thr.minTrades : '—'} · 回撤 &lt; ${thr ? thr.mddBelow : '—'}%${partial ? ' · <span class="rcu-bad">中途數字</span>' : ''}`);
  // 4 未通過篩選(原因會重疊)
  const rc = f ? f.reasonCounts : {pf: b.pf, trades: b.trades, mdd: b.mdd}, failed = f ? f.filtered : b.filtered, multi = f ? f.multiReason : b.multi;
  if(!b.started && !f) labBlock('rcuFail', wait);
  else labBlock('rcuFail', `未通過 <b>${labNum(failed)}</b> 個<br>PF 不足 ${labNum(rc.pf)} · 筆數不足 ${labNum(rc.trades)} · 回撤超標 ${labNum(rc.mdd)}<span class="rcu-dim">(原因會重疊,不可相加;同時多項 ${labNum(multi)} 個)</span>${partial ? ' <span class="rcu-bad">中途數字</span>' : ''}`);
  // 5 樣本外驗證
  const sp = S.data && S.data.split, o = f && f.oos;
  if(f && o){
    if(!o.available || !o.attempted) labBlock('rcuOos', `<b class="rcu-bad">未進行樣本外驗證</b>:${esc(o.skipReason || '資料不足')}`, 'warn');
    else labBlock('rcuOos', `驗證 <b>${o.attempted}</b> 個(只對前 ${f.top} 名)· 通過 <b>${o.pass}</b> · 未通過 <b>${o.fail}</b> · 證據不足 <b>${o.insufficient}</b>${o.unavailable ? ` · 驗證失敗 <b class="rcu-bad">${o.unavailable}</b>` : ''}<br>${sp ? `IS ${esc(sp.windowStart)}→${esc(sp.boundary)} · OOS ${esc(sp.boundary)}→${esc(sp.end)}` : ''}`);
  } else if(st.val.skip) labBlock('rcuOos', `<b class="rcu-bad">未進行樣本外驗證</b>:${esc(st.val.skip)}`, 'warn');
  else if(st.val.started) labBlock('rcuOos', `驗證中 ${st.val.i} / ${st.val.n}<span class="rcu-dim">(只對通過篩選且排名前 ${b.thr ? b.thr.topN : 8} 的策略)</span>`);
  else labBlock('rcuOos', running && b.started ? '<span class="rcu-dim">回測結束後才開始驗證</span>' : wait);
  // 6 最終排名
  if(f) labBlock('rcuRank', `前 <b>${f.top}</b> 名 · 通過但未進前 ${f.thresholds.topN} 名者 <b>${labNum(f.passedNotTop)}</b> 個<br><a href="javascript:labGoResults()" class="rcu-link">↓ 查看下方排名與全部策略結果</a>`);
  else labBlock('rcuRank', wait);
}

// 底部狀態列:策略回測 120/166 ｜ 已通過 42 ｜ 執行中 ｜ 5.2 秒(百分比只來自後端 i/n,沒有就顯示『處理中』)
function labRenderSeg(){
  const S = labState, seg = $id('labSeg'); if(!seg || !S.st || !S.running) return;
  const b = S.st.bt; seg.textContent = b.started ? ` ｜ 已通過 ${b.kept} ｜ 執行中` : ' ｜ 執行中';
}
function labFinishStatus(kind, o){
  const S = labState, now = $id('labProg').querySelector('.rcp-now'), seg = $id('labSeg'), f = S.st.final, wrap = $id('labProg');
  wrap.classList.remove('rcu-ok', 'rcu-warn', 'rcu-err');
  if(kind === 'ok'){
    if(f){
      const lost = f.noResult + f.errors;
      now.textContent = lost ? '分析完成(部分策略失敗)' : '分析完成';
      seg.textContent = ` ｜ ${f.candidates} 候選 ｜ ${f.passed} 通過 ｜ 前 ${f.top} 名` + (lost ? ` ｜ ${lost} 個策略回測失敗或無結果` : '');
      wrap.classList.add(lost ? 'rcu-warn' : 'rcu-ok');
    } else { now.textContent = '分析完成'; seg.textContent = ' ｜ 後端沒有提供全部策略統計'; wrap.classList.add('rcu-warn'); }
  } else {
    seg.textContent = ' ｜ ' + ({error: '沒有產生結果,原因見下方', cancelled: '沒有產生結果', stopped: '連線中斷,沒有收到完整結果'}[kind] || '沒有產生結果'); wrap.classList.add(kind === 'error' ? 'rcu-err' : 'rcu-warn');
  }
}

// ══════════════ 3D 研究核心(原型)+ 球體下方的研究流程列 ══════════════
// 3D 球體/星環(static/js/lab-core3d.js,改寫自 MIT 授權的開源專案,見 THIRD_PARTY_NOTICES.md)只是『視覺層』:顏色、光點、進度弧都來自上面的真實事件模型。
// 手機寬度、不支援 WebGL、省流量模式 → 不載入 3D,維持原本的 Canvas 球體(rc-engine.js)。載入失敗也退回 Canvas 球體。
// 流程列只列『實際執行』的三個階段(行情資料、策略回測+篩選、樣本外驗證)與由結果整理出的『排名結果』;指標/訊號/風險成本在這個流程不會執行,所以不列。
function labWebgl(){ try{ const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); }catch(e){ return false; } }
function labWant3D(){
  if(window.matchMedia('(max-width: 720px)').matches) return false;
  if(navigator.connection && navigator.connection.saveData) return false;
  try{ if(localStorage.getItem('lab3d') === '0') return false; }catch(e){}
  return labWebgl();
}
async function labTry3D(){
  if(!labWant3D()) return;
  const panel = $id('labPanel'); panel.classList.add('rc-3d'); labSetMode('full');         // 先保留版面,避免載入完成後跳動
  try{
    const m = await import('/static/js/lab-core3d.js');
    const box = document.querySelector('#labCore .rc-box'), host = document.createElement('div'); host.className = 'lab3d-host'; box.prepend(host);
    const stat = document.createElement('div'); stat.className = 'lab3d-stat'; stat.id = 'lab3dStat'; box.appendChild(stat);
    const c = m.createCore3D(host, {onDegrade: t => { stat.textContent = t; }});
    if(!c){ host.remove(); stat.remove(); throw new Error('webgl'); }
    labState.c3 = c; c.setAmbient($id('lab3dAmb').checked);
    labState.core.setMotion(false);                                                          // 3D 啟用後,隱藏的 Canvas 球體不再重畫(只保留它的事件模型與節點資料)
    labSync3D(); labStat3D();
  }catch(e){
    panel.classList.remove('rc-3d'); if(!labState.userSet) labSetMode('u');
    console.warn('3D 研究核心無法使用,改用 Canvas 球體:', e && e.message);
  }
}
function labStat3D(){
  const S = labState, el = $id('lab3dStat'); if(!el || !S.c3) return;
  const st = S.c3.stats(); el.textContent = st.forced ? '3D 已停止動畫(負擔過高)' : (st.loopOn ? `3D · ${st.fps} fps · ${st.frameCost} ms/幀` : (st.static ? '3D 靜態畫面' : '3D 待機(靜態,無動畫迴圈)'));
}
function labStatLoop(){ const S = labState; clearTimeout(S.c3Timer); labStat3D(); if(S.running) S.c3Timer = setTimeout(labStatLoop, 1000); }   // 只在分析進行中每秒更新一次讀數(自我排程的 setTimeout)
function labResultStatus(){ const S = labState; if(S.running) return 'idle'; if(S.model.state === 'ok') return S.st && S.st.final ? 'done' : 'skip'; return 'idle'; }
function labSync3D(){                                                                       // 依真實事件模型同步 3D 的顏色、錨點與進度弧
  const S = labState, c = S.c3, M = S.model; if(!c || !M) return;
  const stt = M.state;
  c.setState(stt === 'running' ? 'running' : stt === 'ok' ? 'done' : stt === 'error' ? 'error' : (stt === 'cancelling' || stt === 'cancelled' || stt === 'stopped') ? 'stopped' : 'idle');
  ['data', 'backtest', 'validation'].forEach(id => c.setStage(id, M.stages[id].status));
  c.setStage('result', labResultStatus());
  c.setProgress(labOverall()); labRunner();
}
// 整體進度(0~1):一條連續的賽道。各階段只是佔用賽道的一段『版面位置』(行情 0~6%、回測 6~96%、驗證 96~100%;依實際耗時比例配置,最後一段剛好接到 100%,完成時不會再多跑一截),
// 段落寬度是固定的畫面配置,不代表耗時;段落內的位置 = 後端真實的 i/n。換階段時只會接著往前跑,不會回到起點。
const LAB_SLOT = {data: [0, 0.06], backtest: [0.06, 0.96], validation: [0.96, 1]};
function labOverall(){
  const M = labState.model; if(!M || M.state === 'idle') return null; if(M.state === 'ok') return 1;
  let f = 0; Object.keys(LAB_SLOT).forEach(id => { const x = M.stages[id], a = LAB_SLOT[id][0], b = LAB_SLOT[id][1];
    if(x.status === 'done') f = Math.max(f, b); else if(x.status === 'running') f = Math.max(f, a + (b - a) * (x.prog && x.prog.n ? x.prog.i / x.prog.n : 0)); });
  return f;
}
// 小人與泡泡:位置與文字全部來自真實事件(目前階段、i/n、剛測完的策略與結果、最終統計),沒有任何預設台詞
const LAB_WHY = {pf: 'PF 不足', trades: '筆數不足', mdd: '回撤超標'};
function labRunnerInfo(){
  const S = labState, M = S.model, st = S.st, c = S.c3; if(!c || !M || !st) return null;
  const stt = M.state, f = st.final, ids = ['data', 'backtest', 'validation'];
  if(stt === 'ok') return {run: false, state: 'done', l1: '分析完成', l2: f ? `共測試 ${f.candidates} 個 · 通過 ${f.passed} · 入選 ${f.top} 名` : ''};
  const fail = ids.find(id => M.stages[id].status === 'error');
  if(stt === 'error') return {run: false, state: 'error', l1: '分析失敗', l2: st.dataErr || ''};
  if(stt === 'cancelling' || stt === 'cancelled' || stt === 'stopped'){ const cur = ids.slice().reverse().find(id => M.stages[id].status !== 'idle') || 'data'; return {run: false, state: 'stopped', l1: stt === 'cancelling' ? '正在取消…' : '已中止', l2: ''}; }
  if(stt !== 'running') return null;
  const act = ids.find(id => M.stages[id].status === 'running') || ids.slice().reverse().find(id => M.stages[id].status === 'done') || 'data', x = M.stages[act], pg = x.prog && x.prog.n ? x.prog : null;
  const base = {run: true, state: 'running'};
  if(act === 'data') return Object.assign(base, {l1: x.status === 'done' ? '行情資料就緒' : '取得行情資料…', l2: x.status === 'done' && st.data ? `${labNum(st.data.bars)} 根 K 棒` : ''});
  if(act === 'backtest'){ const b = st.bt, l = b.last; let l2 = '';
    if(l && l.strat){ const nm = (typeof getStratName === 'function' ? getStratName(l.strat) : l.strat), why = (l.why || '').split(',').filter(Boolean).map(k => LAB_WHY[k] || k).join('、');
      l2 = nm + ' → ' + (l.outcome === 'kept' ? '通過篩選' : l.outcome === 'filtered' ? '未通過' + (why ? '(' + why + ')' : '') : l.outcome === 'no_result' ? '無結果' : '錯誤'); }
    return Object.assign(base, {l1: pg ? `策略回測 ${pg.i} / ${pg.n} · 通過 ${b.kept}` : '策略回測準備中', l2}); }
  return Object.assign(base, {l1: pg ? `樣本外驗證 ${pg.i} / ${pg.n}` : '樣本外驗證', l2: ''});
}
function labRunner(){ const c = labState.c3; if(c) c.setRunner(labRunnerInfo()); }

const LF_LABEL = {idle: '待機', running: '進行中', done: '完成', error: '失敗', skip: '未進行', stopped: '已中止'};
function labFlowText(id){
  const S = labState, M = S.model, st = S.st, f = st && st.final, x = M.stages[id], ms = x && x.ms != null ? RCJob.fmtMs(x.ms) : '';
  if(id === 'result'){ const r = labResultStatus(); return {cls: r, txt: f ? `前 ${f.top} 名 · 通過 ${f.passed}` : (r === 'skip' ? '未提供統計' : (S.running ? '完成後顯示' : '待機'))}; }
  const cls = x.status; let t = LF_LABEL[cls] || cls;
  if(id === 'data'){ if(cls === 'done' && st.data) t = `${labNum(st.data.bars)} 根${ms ? ' · ' + ms : ''}`; }
  else if(id === 'backtest'){ if(cls === 'running' && x.prog && x.prog.n) t = `${x.prog.i}/${x.prog.n} · 通過 ${st.bt.kept}`; else if(cls === 'done') t = `${f ? f.candidates : st.bt.n} 個 · 通過 ${f ? f.passed : st.bt.kept}${ms ? ' · ' + ms : ''}`; }
  else if(id === 'validation'){ if(cls === 'running' && x.prog && x.prog.n) t = `${x.prog.i}/${x.prog.n}`; else if(cls === 'done') t = `${f && f.oos ? f.oos.attempted : (st.val.n != null ? st.val.n : '')} 個${ms ? ' · ' + ms : ''}`; }
  return {cls, txt: t};
}
function labRenderFlow(){
  const S = labState; if(!S.model || !S.st) return;
  document.querySelectorAll('#labFlow .lf-node').forEach(b => {
    const id = b.dataset.stage, r = labFlowText(id);
    b.className = 'lf-node ' + r.cls + (S.selected === id ? ' sel' : ''); b.querySelector('.s').textContent = r.txt;
    b.setAttribute('aria-label', b.querySelector('.l').textContent + ':' + r.txt);
  });
  labSync3D();
}
function labFlowClick(id){
  const S = labState;
  if(id === 'result'){ labGoResults(); return; }
  S.selected = id; if(S.mode !== 'full') labSetMode('full'); labRenderDetail(); labRenderFlow();
}

function labRenderDetail(){
  clearTimeout(labState.detailTimer); labState.detailTimer = 0;
  const el = $id('labDetail'); if(!el) return;
  const id = labState.selected;
  if(!id){ el.innerHTML = labState.model.state === 'idle' ? '' : '<div class="rcd-empty">點擊球體周圍的編號節點,查看該階段實際做了什麼、花了多久、產生了什麼結果。</div>'; return; }
  let html = RCJob.stageDetail(id, labState.model, labState.data);
  if((id === 'backtest' || id === 'validation') && labState.data && labState.data.results) html += `<button type="button" class="rcd-go" onclick="labGoResults()">跳到完整結果表</button>`;
  el.innerHTML = html;
}
function labScheduleDetail(stage){        // 事件很密時合併更新(最多每 250ms 一次),且只更新目前被選中的階段
  if(labState.selected !== stage || labState.detailTimer) return;
  labState.detailTimer = setTimeout(labRenderDetail, 250);
}
function labGoResults(){
  const el = $id('labRes'); if(!el) return;
  const reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  el.scrollIntoView({behavior: reduce ? 'auto' : 'smooth', block: 'start'});
}

function labUi(){
  labEnsure();
  const btn = $id('labRun'), S = labState;
  return {
    begin(h){ S.handle = h; S.data = null; S.selected = null; S.running = true; S.userSet = false; S.t0 = performance.now(); S.ms = null; S.st = labFreshStats();
      $id('labSub').innerHTML = ''; $id('labRes').innerHTML = ''; $id('labIdle').hidden = true; $id('labProg').classList.remove('rcu-ok', 'rcu-warn', 'rcu-err'); $id('labSeg').textContent = ' ｜ 執行中';
      if(S.mode === 'full' && !S.userSet && !S.c3) labSetMode('u');
      labRenderBlocks(); S.pv.begin(h); S.core.begin(); labRenderDetail();
      if(S.c3){ labRenderFlow(); labStatLoop(); } },
    event(e){ S.pv.event(e); S.core.event(e); labApplyEvent(e); labScheduleDetail(e.stage); if(S.c3) S.c3.event(e.stage, e.status, e.outcome); },
    tick(ms){ S.pv.tick(ms); },
    cancelling(){ S.pv.cancelling(); S.core.cancelling(); labRenderDetail(); labRenderFlow(); },
    end(kind, o){ o = o || {}; S.data = o.data || null; S.running = false; S.ms = performance.now() - S.t0;
      S.st.final = (o.data && o.data.strategyStats) || null;
      S.pv.end(kind, o); S.core.end(kind, o.summary); S.handle = null;
      labFinishStatus(kind, o); labRenderBlocks(); labRenderDetail(); labRenderFlow();
      if(S.c3){ clearTimeout(S.c3Timer); S.c3Timer = setTimeout(labStat3D, 1500); } },
    hideProgress(){},
    setSub(html){ $id('labSub').innerHTML = html; },
    setResults(html){ $id('labRes').innerHTML = html; },
    busy(on){ btn.disabled = on; },
  };
}

// ══════════════ 全部策略分析結果(前 8 名排行榜下方,預設收合)══════════════
// 資料來源:/api/deep_analysis 的 allStrategyResults(每個候選策略一列,後端在原本的樣本內回測迴圈裡順手留下,沒有重跑回測)與 strategyStats。
// 沒做過樣本外驗證的策略(未通過篩選、通過但未進前 8、回測無結果/錯誤)一律顯示『未進行樣本外驗證』,不顯示任何 OOS 數字。
const ALL_STATUS = {top: ['前 8 名', 'top'], passed: ['通過但未進前 8', 'passed'], filtered: ['未通過篩選', 'filtered'], no_result: ['回測無結果', 'noresult'], error: ['回測發生錯誤', 'error']};
const ALL_REASON = {pf: r => `PF 不足(${r.is ? fmtPF(r.is.pf) : '—'} ≤ 1)`, trades: (r, t) => `筆數不足(${r.is ? r.is.trades : '—'} < ${t ? t.minTrades : '—'})`, mdd: (r, t) => `回撤超標(${r.is ? pctPlain(r.is.mdd) : '—'} ≥ ${t ? t.mddBelow : 50}%)`};
const ALL_ORDER = {top: 0, passed: 1, filtered: 2, no_result: 3, error: 4};
const allStore = {};

function labAllRows(a){
  let rows = a.rows.slice();
  if(a.status !== 'all') rows = rows.filter(r => r.status === a.status);
  const q = a.q.trim().toLowerCase(); if(q) rows = rows.filter(r => (r.name + ' ' + r.strat).toLowerCase().includes(q));
  const num = (r, k) => r.is && r.is[k] != null ? r.is[k] : null, by = (k, dir) => (x, y) => { const p = num(x, k), s = num(y, k); if(p == null && s == null) return 0; if(p == null) return 1; if(s == null) return -1; return dir * (p - s); };
  const name = (x, y) => x.name.localeCompare(y.name, 'zh-Hant');
  const sorters = {default: (x, y) => (ALL_ORDER[x.status] - ALL_ORDER[y.status]) || ((x.rank || 1e9) - (y.rank || 1e9)) || by('pf', -1)(x, y) || name(x, y), total: by('total', -1), pf: by('pf', -1), mdd: by('mdd', 1), trades: by('trades', -1), win: by('win', -1), name};
  rows.sort(sorters[a.sort] || sorters.default); return rows;
}
function labAllCells(r, a){
  const t = a.stats && a.stats.thresholds, is = r.is, st = ALL_STATUS[r.status] || [r.status, ''];
  const why = r.status === 'filtered' ? r.reasons.map(c => `<span class="all-why">${esc(ALL_REASON[c](r, t))}</span>`).join('')
    : r.status === 'no_result' ? '<span class="all-why warn">回測無結果(資料不足,或策略需要的暖機根數不夠)</span>'
    : r.status === 'error' ? `<span class="all-why bad">回測發生錯誤${r.errorKind ? '(' + esc(r.errorKind) + ')' : ''}</span>` : '<span class="all-ok">通過全部篩選</span>';
  const oos = r.oosDone && r.oos ? `${{pass: '通過', fail: '未通過', insufficient: '證據不足'}[r.oos.status] || '—'} · ${r.oos.trades} 筆${r.oos.trades ? ` · PF ${fmtPF(r.oos.pf)} · ${fmtPct(r.oos.total, 1)}` : ''}`
    : (r.status === 'top' ? '<span class="all-dim">驗證失敗,沒有樣本外結果</span>' : '<span class="all-dim">未進行樣本外驗證</span>');
  const dash = '—';
  return {st, why, oos, ret: is ? `<span class="${retClass(is.total)}">${fmtPct(is.total, 1)}</span>` : dash, pf: is ? `<span class="${pfClass(is.pf, is.trades)}">${fmtPF(is.pf)}</span>` : dash, mdd: is ? pctPlain(is.mdd) : dash, n: is ? is.trades : dash, win: is ? pctPlain(is.win, 1) : dash,
          rank: r.rank != null ? `#${r.rank} · ${r.score}` : dash, top: r.status === 'top' ? '是' : '否'};
}
function labAllBody(key){
  const a = allStore[key]; if(!a) return '';
  const rows = labAllRows(a), per = a.per, pages = Math.max(1, Math.ceil(rows.length / per)); a.page = Math.min(Math.max(1, a.page), pages);
  const slice = rows.slice((a.page - 1) * per, a.page * per);
  const trs = slice.map(r => { const c = labAllCells(r, a); return `<tr class="all-${c.st[1]}"><td class="name"><b>${esc(r.name)}</b><span class="vb-sub">${esc(r.strat)}${r.cat ? ' · ' + esc({trend: '順勢', range: '均值回歸', breakout: '突破'}[r.cat] || r.cat) : ''}</span></td><td class="left"><span class="all-st ${c.st[1]}">${c.st[0]}</span></td><td>${c.ret}</td><td>${c.pf}</td><td>${c.mdd}</td><td>${c.n}</td><td>${c.win}</td><td class="left">${c.why}</td><td>${c.rank}</td><td>${c.top}</td><td class="left">${c.oos}</td></tr>`; }).join('');
  const cards = slice.map(r => { const c = labAllCells(r, a), kv = (k, v) => `<div class="k">${k}</div><div class="v">${v}</div>`; return `<div class="cmp-card"><h4>${esc(r.name)} <span class="all-st ${c.st[1]}">${c.st[0]}</span></h4><div class="vb-sub">${esc(r.strat)}</div><div class="cmp-grid">${kv('樣本內報酬', c.ret)}${kv('樣本內 PF', c.pf)}${kv('樣本內回撤', c.mdd)}${kv('樣本內筆數', c.n)}${kv('樣本內勝率', c.win)}${kv('名次 · 分數', c.rank)}</div><div class="all-cwhy">${c.why}</div><div class="vb-sub">樣本外:${c.oos}</div></div>`; }).join('');
  const head = ['策略', '狀態', '樣本內報酬', '樣本內 PF', '樣本內回撤', '樣本內筆數', '樣本內勝率', '未通過原因', '名次 · 分數', '前 8', '樣本外驗證'];
  const pager = `<div class="all-pager"><button type="button" class="linkbtn" onclick="labAllSet('${key}','page',${a.page - 1})" ${a.page <= 1 ? 'disabled' : ''}>‹ 上一頁</button><span>第 ${a.page} / ${pages} 頁 · 符合 ${rows.length} 個策略(每頁 ${per} 個)</span><button type="button" class="linkbtn" onclick="labAllSet('${key}','page',${a.page + 1})" ${a.page >= pages ? 'disabled' : ''}>下一頁 ›</button></div>`;
  if(!rows.length) return `<div class="empty-state">沒有符合條件的策略。</div>`;
  return pager + `<div class="cmp-wrap"><table class="cmp-table all-tbl"><thead><tr>${head.map((h, i) => `<th class="${i === 0 ? 'name' : (i === 1 || i === 7 || i === 10 ? 'left' : '')}">${h}</th>`).join('')}</tr></thead><tbody>${trs}</tbody></table></div><div class="cmp-cards">${cards}</div>` + pager;
}
function labAllSet(key, field, value){
  const a = allStore[key]; if(!a) return;
  if(field === 'page') a.page = Number(value); else { a[field] = value; a.page = 1; }
  const body = document.getElementById('all-body-' + key); if(body) body.innerHTML = labAllBody(key);
}
function labAllHtml(key, data){
  const rows = data && data.allStrategyResults, s = data && data.strategyStats;
  if(!Array.isArray(rows) || !s) return '';
  allStore[key] = {rows, stats: s, q: '', status: 'all', sort: 'default', page: 1, per: 20};
  const opt = (v, l) => `<option value="${v}">${l}</option>`;
  const cnt = st => rows.filter(r => r.status === st).length;
  const sumTxt = `${s.candidates} 個候選 · ${s.passed} 個通過篩選 · 前 ${s.top} 名`;
  const warn = (s.noResult || s.errors) ? `<div class="state-card warn"><b>有策略沒有跑出結果</b>:${s.noResult} 個回測無結果、${s.errors} 個回測發生錯誤。這些策略不在排名內,也不代表通過或未通過篩選。</div>` : '';
  return `<details class="all-box" id="all-${key}"><summary>全部策略分析結果<span class="vb-note">(${sumTxt};預設收合)</span></summary>
    <div class="all-in">
      <div class="vb-note">這裡列出本次<b>所有候選策略</b>的樣本內結果與篩選狀態,不限於前 ${s.top} 名。排名與分數只依樣本內結果;<b>只有前 ${s.top} 名做過樣本外驗證</b>,其餘顯示「未進行樣本外驗證」。「未通過原因」可能同時有多項,各項數量不可相加。
        狀態數量:前 8 名 ${cnt('top')}、通過但未進前 8 ${cnt('passed')}、未通過 ${cnt('filtered')}、無結果 ${cnt('no_result')}、錯誤 ${cnt('error')}(合計 ${rows.length})。</div>${warn}
      <div class="all-ctrl">
        <input type="search" class="all-q" placeholder="搜尋策略名稱或代碼" aria-label="搜尋策略" oninput="labAllSet('${key}','q',this.value)">
        <select aria-label="狀態篩選" onchange="labAllSet('${key}','status',this.value)">${opt('all', '全部狀態')}${opt('top', '前 8 名')}${opt('passed', '通過但未進前 8')}${opt('filtered', '未通過篩選')}${opt('no_result', '回測無結果')}${opt('error', '回測發生錯誤')}</select>
        <select aria-label="排序" onchange="labAllSet('${key}','sort',this.value)">${opt('default', '預設排序(名次)')}${opt('total', '樣本內報酬 高→低')}${opt('pf', '樣本內 PF 高→低')}${opt('mdd', '樣本內回撤 小→大')}${opt('trades', '樣本內筆數 多→少')}${opt('win', '樣本內勝率 高→低')}${opt('name', '名稱')}</select>
      </div>
      <div id="all-body-${key}">${labAllBody(key)}</div>
    </div></details>`;
}

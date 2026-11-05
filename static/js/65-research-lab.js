// ── 策略實驗室的 Research Core 面板 ─────────────────────────────────────
// 只出現在「策略實驗室」一處(整個網站只有一個球體);自選清單的卡片、彈窗、最佳策略頁都不渲染球體。
// 畫面完全由後端真實事件驅動(見 rc-job.js / rc-engine.js);沒有事件就是靜態畫面。
// 分析結果仍由既有的 rankingHtml() 顯示;這裡不重算任何績效,也不另外呼叫分析 API。
const labState = {core: null, model: null, pv: null, data: null, selected: null, detailTimer: 0, handle: null};

function labEnsure(){
  const body = $id('labBody');
  if(!body || labState.core) return;
  body.innerHTML = `
    <div class="panel rc-lab"><div class="panel-b">
      <div class="rc-lab-head"><b>研究核心</b><span class="vb-note">球體、路線與光點只依後端<b>真實的分析事件</b>亮起；點擊節點可查看該階段的實際結果。沒有分析時是靜態畫面。</span></div>
      <div id="labCore"></div>
      <div id="labProg" style="margin-top:10px;"></div>
      <div class="vb-note" id="labSub" style="margin-top:6px;"></div>
      <div class="rcd" id="labDetail"></div>
    </div></div>
    <div id="labRes"><div class="empty-state">選好標的後按「開始深度分析」。</div></div>`;
  labState.model = new RCJob.Model();
  labState.pv = RCJob.progressView($id('labProg'), {model: labState.model});
  labState.core = RCEngine.create($id('labCore'), {model: labState.model, onNodeClick: id => { labState.selected = id; labRenderDetail(); }});
  labRenderDetail();
}

function labRenderDetail(){
  clearTimeout(labState.detailTimer); labState.detailTimer = 0;
  const el = $id('labDetail'); if(!el) return;
  const id = labState.selected;
  if(!id){ el.innerHTML = labState.model.state === 'idle' ? '' : '<div class="rcd-empty">點擊上方任一節點，查看該階段實際做了什麼、花了多久、產生了什麼結果。</div>'; return; }
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
    begin(h){ S.handle = h; S.data = null; S.selected = null; $id('labSub').innerHTML = ''; $id('labRes').innerHTML = '';
      S.pv.begin(h); S.core.begin(); labRenderDetail(); },
    event(e){ S.pv.event(e); S.core.event(e); labScheduleDetail(e.stage); },
    tick(ms){ S.pv.tick(ms); },
    cancelling(){ S.pv.cancelling(); S.core.cancelling(); labRenderDetail(); },
    end(kind, o){ o = o || {}; S.data = o.data || null; S.pv.end(kind, o); S.core.end(kind, o.summary); S.handle = null; labRenderDetail(); },
    hideProgress(){},
    setSub(html){ $id('labSub').innerHTML = html; },
    setResults(html){ $id('labRes').innerHTML = html; },
    busy(on){ btn.disabled = on; },
  };
}

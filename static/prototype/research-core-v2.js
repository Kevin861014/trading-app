/* Research Core v2 原型頁(獨立、未接入正式網站的『重播』只存在於這裡)
 *
 * 畫面本體(球體、節點、光點)與事件追蹤(輪詢、狀態整理、節點詳情)和正式網站共用同一套程式:
 *   ../js/rc-job.js(RCJob)與 ../js/rc-engine.js(RCEngine)。這個檔案只負責:控制列、即時分析按鈕、重播錄製的真實紀錄、事件紀錄與階段卡片。
 *
 * 事件只來自兩個管道:
 *   - 即時:呼叫本機分析 API,並在請求進行中輪詢 /api/job_events(RCJob.run)。
 *   - 重播:traces/traces.js 內『這台電腦上實際跑出來』的事件紀錄(tools/record_trace.py 原樣存檔,未編輯)。
 * 沒有示範輪播、沒有計時器假進度、沒有編造的事件。
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var J = window.RCJob, STAGES = J.STAGES;
  var model = new J.Model(), core = null, handle = null, replayTimers = [], token = 0;

  function setNote(t) { $('rc-note').textContent = t || ''; }
  function modeText() {
    var m = $('rc-mode'), s = model.state;
    m.textContent = s === 'idle' ? '待機中 · 靜態畫面' : (s === 'running' ? (handle ? '即時分析中 · 光點來自後端真實事件' : '重播真實紀錄 · 光點來自當時的真實事件') : (s === 'cancelled' ? '已取消' : (s === 'error' ? '已結束(有錯誤)' : (s === 'stopped' ? '已中斷' : '已結束'))));
  }

  // ── 事件紀錄與階段卡片(皆由 model 與事件產生) ──
  var statusLabel = { start: '開始', progress: '進行', done: '完成', skip: '略過', error: '失敗' };
  function log(e) {
    var det = J.describe(e), row = document.createElement('div'); row.className = 'rc-log-row ' + e.status;
    row.innerHTML = '<span class="t">+' + (e.t / 1000).toFixed(2) + 's</span><b>' + J.esc(STAGES[J.IDX[e.stage]].label) + '</b><span class="st">' + statusLabel[e.status] + '</span><span class="d"></span>';
    row.querySelector('.d').textContent = det + (e.ms != null ? (det ? ' · ' : '') + J.fmtMs(e.ms) : '');
    var box = $('rc-log'); box.insertBefore(row, box.firstChild); while (box.childNodes.length > 160) box.removeChild(box.lastChild);
  }
  function cards() {
    STAGES.forEach(function (s) {
      var st = model.stages[s.id], card = $('rc-card-' + s.id); if (!card) return;
      card.className = 'rc-card ' + st.status;
      var line = st.status === 'idle' ? '尚未執行' : st.detail || J.STATUS_LABEL[st.status];
      if (st.prog && st.status === 'running') line = st.prog.i + ' / ' + st.prog.n;
      card.querySelector('.d').textContent = line;
      card.querySelector('.m').textContent = st.status === 'done' && st.ms != null ? J.fmtMs(st.ms) : J.STATUS_LABEL[st.status];
      card.querySelector('.bar i').style.width = (st.prog && st.prog.n ? st.prog.i / st.prog.n * 100 : (st.status === 'done' ? 100 : 0)) + '%';
    });
  }
  var last = {};
  function showDetail(id) { last.sel = id; $('rc-detail').innerHTML = J.stageDetail(id, model, last.data); }

  function onEvent(e) { model.apply(e); core.event(e); log(e); cards(); modeText(); if (last.sel === e.stage) showDetail(e.stage); }
  function begin() { stopAll(); model.reset(); core.begin(); $('rc-log').innerHTML = ''; $('rc-result').textContent = ''; $('rc-detail').innerHTML = ''; last = {}; setNote(''); cards(); modeText(); }
  function finish(kind, summary, data) { core.end(kind, summary); last.data = data; $('rc-result').textContent = summary || ''; $('rc-start').disabled = false; cards(); modeText(); if (last.sel) showDetail(last.sel); }
  function stopAll() { token++; replayTimers.forEach(clearTimeout); replayTimers = []; if (handle) { var h = handle; handle = null; h.cancel(); } }

  // ── 即時分析(真實 API + 真實事件輪詢) ──
  function summarize(kind, d) {
    if (d.error) return '失敗:' + d.error;
    if (kind === 'analyze') {
      var m = d.metrics, v = d.validation && d.validation.available ? d.validation.oos : null;
      return '扣成本報酬 ' + m.totalReturn + '% · 淨 PF ' + (m.tradeCount ? m.pf : '—') + ' · 最大回撤 ' + m.maxDD + '% · ' + m.tradeCount + ' 筆' + (v ? ' · 樣本外 ' + v.trades + ' 筆(' + (J.TIER_LABEL[v.tier] || v.tier) + ')' : '');
    }
    var t = (d.results || [])[0];
    return '共測試 ' + d.total_tested + ' 個策略,入選 ' + (d.results || []).length + ' 名' + (t ? ';第 1 名 ' + t.name + '(樣本外 ' + (t.oos ? t.oos.trades : 0) + ' 筆)' : '');
  }
  function startLive() {
    var kind = $('rc-kind').value, sym = ($('rc-symbol').value || '').trim(), tf = $('rc-tf').value;
    if (!sym) { setNote('請輸入代號'); return; }
    begin(); $('rc-start').disabled = true; var my = token;
    var base = ($('rc-base').value || '').replace(/\/$/, '');
    handle = J.run({
      base: base, onEvent: function (e) { if (my === token) onEvent(e); },
      buildUrl: function (id) {
        var q = '?symbol=' + encodeURIComponent(sym) + '&timeframe=' + tf + '&job=' + id;
        if (kind === 'analyze') return '/api/analyze' + q + '&strategy=' + encodeURIComponent($('rc-strat').value) + '&period=2y';
        if (kind === 'best') return '/api/best_strategy' + q + '&period=2y&use_oos=1';
        return '/api/deep_analysis' + q + '&use_oos=1';
      }
    });
    var h = handle;
    h.done.then(function (res) {
      if (my !== token) return; handle = null;
      if (res.cancelled) finish('cancelled', '已取消', null);
      else if (res.error) finish('stopped', '無法連線到分析服務(' + res.error + ')。請確認網站已在本機執行。', null);
      else if (!res.ok) finish('error', summarize(kind, res.data), res.data);
      else finish('ok', summarize(kind, res.data), res.data);
    });
  }

  // ── 重播(只在這個獨立原型):按錄製時的真實時間間隔,重放當時後端實測的事件 ──
  function startReplay() {
    var key = $('rc-trace').value, tr = (window.RC_TRACES || {})[key]; if (!tr) { setNote('沒有可重播的紀錄'); return; }
    begin(); var my = token, speed = parseFloat($('rc-speed').value) || 1;
    setNote('重播:' + tr.meta.label + '(錄製於 ' + tr.meta.recordedAt + ',後端實測時間,非即時)');
    tr.events.forEach(function (e) { replayTimers.push(setTimeout(function () { if (my === token) onEvent(e); }, e.t / speed)); });
    replayTimers.push(setTimeout(function () { if (my === token) finish(tr.result.ok ? 'ok' : 'error', tr.result.summary, null); }, (tr.events[tr.events.length - 1].t + 450) / speed));
  }
  function cancel() { if (model.state !== 'running') return; var wasLive = !!handle; stopAll(); finish('cancelled', '已取消', null); if (!wasLive) setNote('已停止重播'); }
  function reset() { stopAll(); model.reset(); core.reset(); $('rc-log').innerHTML = ''; $('rc-result').textContent = '尚未分析'; $('rc-detail').innerHTML = ''; last = {}; setNote(''); $('rc-start').disabled = false; cards(); modeText(); }

  function init() {
    var h = '';
    STAGES.forEach(function (s) { h += '<div class="rc-card idle" id="rc-card-' + s.id + '"><div class="h"><b>' + s.label + '</b><span class="m">待機</span></div><div class="s">' + s.sub + '</div><div class="d">尚未執行</div><div class="bar"><i></i></div></div>'; });
    $('rc-cards').innerHTML = h;
    var tr = $('rc-trace'); Object.keys(window.RC_TRACES || {}).forEach(function (k) { var o = document.createElement('option'); o.value = k; o.textContent = window.RC_TRACES[k].meta.label; tr.appendChild(o); });
    if (location.protocol === 'file:') $('rc-base').value = 'http://127.0.0.1:5000'; else { $('rc-base').value = ''; $('rc-base-wrap').style.display = 'none'; }
    core = window.RCEngine.create($('rc-host'), { model: model, onNodeClick: showDetail });
    $('rc-host').addEventListener('rc-note', function (ev) { setNote(ev.detail); });
    $('rc-start').addEventListener('click', startLive); $('rc-replay').addEventListener('click', startReplay);
    $('rc-cancel').addEventListener('click', cancel); $('rc-reset').addEventListener('click', reset);
    $('rc-kind').addEventListener('change', function () { $('rc-strat-wrap').style.display = this.value === 'analyze' ? '' : 'none'; });
    cards(); modeText();
    window.ResearchCoreV2 = { core: core, model: model, stats: function () { return core.stats(); }, applyEvent: onEvent, begin: begin, reset: reset };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

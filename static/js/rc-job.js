/* Research Core — 工作事件追蹤(正式網站與獨立原型共用)
 *
 * 這個檔案只做三件事,而且每一件都以『後端真實事件』為唯一依據:
 *   1. RCJob.run():送出一個帶 job 代號的分析請求,並在『請求進行中』輪詢 /api/job_events(只取新事件)。
 *   2. RCJob.Model:把事件整理成各階段的狀態(狀態、實測耗時、已完成/總數、細節),供球體畫面、進度列、節點詳情共用。
 *   3. RCJob.progressView():不含球體的精簡進度列(用在彈窗與「最佳策略」頁),取代過去依時間推算的假進度。
 *
 * 誠實規則:
 *   - 沒有事件就沒有進度數字。後端知道『第 i 個 / 共 n 個』才顯示 i / n;不知道就顯示「處理中」,絕不編造百分比。
 *   - 進度條的百分比 = 『目前這個階段』的真實完成比例(不是整個工作的推算值)。
 *   - 輪詢只在請求進行中存在;完成、失敗、取消、離開頁面後立即停止。不會為了進度重跑策略或重新下載 K 線(後端的輪詢端點不做任何運算)。
 *   - 這裡沒有重播功能,也沒有任何模擬事件的程式碼(重播只存在於獨立原型)。
 */
(function (root) {
  'use strict';

  // 與後端 research_events.STAGES 一致(有測試比對)
  var STAGES = [
    { id: 'data',       label: '行情資料',   sub: '下載已收盤 K 棒' },
    { id: 'indicators', label: '指標計算',   sub: 'EMA / 策略條件' },
    { id: 'backtest',   label: '策略回測',   sub: '含成本與停損' },
    { id: 'signal',     label: '訊號判斷',   sub: '目前持倉狀態' },
    { id: 'validation', label: '樣本外驗證', sub: 'IS / OOS 分開' },
    { id: 'summary',    label: '風險與成本', sub: '回撤 / 買進持有' }
  ];
  var IDX = {}; STAGES.forEach(function (s, i) { IDX[s.id] = i; });
  var STATUS_LABEL = { idle: '待機', running: '執行中', done: '完成', skip: '未涉及', error: '失敗', stopped: '已中止' };
  var TIER_LABEL = { insufficient: '樣本不足', preliminary: '初步觀察', evaluable: '可進一步評估', unavailable: '尚未驗證' };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function fmtMs(ms) { return ms == null ? '' : (ms >= 1000 ? (ms / 1000).toFixed(2) + ' 秒' : Math.round(ms) + ' ms'); }
  function fmtSec(ms) { return (ms / 1000).toFixed(1) + ' 秒'; }

  function newJobId() {
    var a = new Uint8Array(9);
    if (root.crypto && root.crypto.getRandomValues) root.crypto.getRandomValues(a);
    else for (var i = 0; i < a.length; i++) a[i] = Math.random() * 256;      // 只用來產生代號,與動畫、進度無關
    return 'rc-' + Array.prototype.map.call(a, function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
  }

  /* 把一筆事件寫成人看得懂的一行(全部是事件裡的真實欄位) */
  function describe(e) {
    var d = [];
    if (e.stage === 'data') { if (e.bars != null) d.push(e.bars + ' 根 K 棒'); if (e.source) d.push(e.source); if (e.interval) d.push(e.interval); }
    if (e.stage === 'indicators' && e.bars != null) d.push(e.bars + ' 根');
    if (e.stage === 'backtest') {
      if (e.i != null) d.push(e.i + ' / ' + e.n); if (e.strat) d.push(e.strat);
      if (e.tested != null) d.push('測試 ' + e.tested + ' 個、入選 ' + e.kept);
      if (e.trades != null) d.push(e.trades + ' 筆交易'); if (e.strategy) d.push(e.strategy);
    }
    if (e.stage === 'signal' && e.inPos != null) d.push(e.inPos ? '策略目前持有中' : '策略目前空手');
    if (e.stage === 'validation') {
      if (e.i != null) d.push(e.i + ' / ' + e.n); if (e.strat) d.push(e.strat);
      if (e.oosTrades != null) d.push('樣本外 ' + e.oosTrades + ' 筆'); if (e.tier) d.push(TIER_LABEL[e.tier] || e.tier);
      if (e.available === false) d.push('資料不足,切不出樣本外');
    }
    if (e.stage === 'summary' && e.points != null) d.push(e.points + ' 個權益點、' + e.trades + ' 筆');
    if (e.reason) d.push(e.reason); if (e.message) d.push(e.message);
    return d.join(' · ');
  }

  /* ───────────────── Model:事件 → 各階段狀態 ───────────────── */
  function Model() { this.reset(); }
  Model.prototype.reset = function () {
    var self = this; this.stages = {};
    STAGES.forEach(function (s) { self.stages[s.id] = { status: 'idle', ms: null, detail: '', prog: null, events: [], first: null }; });
    this.eventCount = 0; this.state = 'idle';      // idle | running | ok | error | cancelled | stopped
    this.lastEventAt = 0;
  };
  Model.prototype.begin = function () { this.reset(); this.state = 'running'; this.startedAt = (root.performance || Date).now(); };
  Model.prototype.apply = function (e) {
    var st = this.stages[e.stage]; if (!st) return null;
    this.eventCount++; this.lastEventAt = (root.performance || Date).now();
    var det = describe(e); st.events.push(e); if (st.events.length > 700) st.events.shift();
    if (st.first == null) st.first = e.t;
    if (e.status === 'start') { st.status = 'running'; st.ms = null; st.detail = det; st.prog = null; if (e.n != null) st.prog = { i: 0, n: e.n }; }
    else if (e.status === 'progress') { st.status = 'running'; if (e.i != null) st.prog = { i: e.i, n: e.n }; st.detail = det; }
    else if (e.status === 'done') { st.status = 'done'; st.ms = e.ms; st.detail = det || st.detail; if (st.prog && st.prog.n) st.prog.i = st.prog.n; }
    else if (e.status === 'skip') { st.status = 'skip'; st.detail = det || '本分析不含此階段'; }
    else if (e.status === 'error') { st.status = 'error'; st.ms = e.ms; st.detail = det; }
    return st;
  };
  /* 工作結束(完成/失敗/取消/連線中斷):仍停在『執行中』的階段不可能再有進展,改標為已中止(或失敗) */
  Model.prototype.end = function (kind) {
    this.state = kind;
    var self = this;
    STAGES.forEach(function (s) { var st = self.stages[s.id]; if (st.status === 'running') st.status = (kind === 'ok') ? 'done' : 'stopped'; });
  };
  Model.prototype.running = function () { var self = this; return STAGES.filter(function (s) { return self.stages[s.id].status === 'running'; }); };
  Model.prototype.errored = function () { var self = this; return STAGES.filter(function (s) { return self.stages[s.id].status === 'error'; }); };
  /* 目前『有計數』的階段(後端知道 i / n)。沒有就回傳 null,顯示端必須顯示「處理中」而不是編百分比 */
  Model.prototype.counted = function () {
    var r = this.running(); for (var k = r.length - 1; k >= 0; k--) { var p = this.stages[r[k].id].prog; if (p && p.n) return { stage: r[k], i: p.i, n: p.n }; }
    return null;
  };

  /* ───────────────── 工作執行器 ─────────────────
   * opts: { buildUrl(jobId) → '/api/...(含 job=)', base?: '', onEvent(e), onTick?(elapsedMs) }
   * 回傳 handle: { id, cancel(), done: Promise<{ok, status, data, cancelled, error}> }                                   */
  var active = {};
  function run(opts) {
    var base = opts.base || '', id = newJobId(), lastSeq = 0, stopped = false, timer = 0, interval = 300, fails = 0;
    var t0 = (root.performance || Date).now(), ac = root.AbortController ? new root.AbortController() : null, settled = false;
    var MAX_POLL_MS = 15 * 60 * 1000;
    var handle = { id: id, cancelled: false };
    active[id] = handle;

    function stop() { stopped = true; clearTimeout(timer); delete active[id]; }
    function delay() { return root.document && root.document.hidden ? 1500 : interval; }      // 分頁在背景時放慢(事件仍保留在後端,不會遺失)
    function poll(final) {
      return root.fetch(base + '/api/job_events?job=' + id + '&after=' + lastSeq, { cache: 'no-store' })
        .then(function (r) { return r.status === 404 ? { events: [] } : r.json(); })       // 404 = 後端還沒收到請求或工作已過期
        .then(function (j) {
          if (stopped && !final) return;
          var evs = (j && j.events) || [];
          for (var k = 0; k < evs.length; k++) { lastSeq = Math.max(lastSeq, evs[k].seq); opts.onEvent(evs[k]); }
          interval = evs.length ? 300 : Math.min(1000, Math.round(interval * 1.5));            // 有事件就密一點,沒事件逐步放慢
          fails = 0;
          if (opts.onTick) opts.onTick((root.performance || Date).now() - t0);
          if (!final && !stopped) {
            if ((root.performance || Date).now() - t0 > MAX_POLL_MS) { stop(); return; }
            timer = setTimeout(function () { poll(false); }, delay());
          }
        })
        .catch(function () {
          if (final || stopped) return;
          fails++; if (fails >= 5) { stop(); return; }                                         // 連續失敗就放棄輪詢,不會一直打
          timer = setTimeout(function () { poll(false); }, 1000);
        });
    }

    timer = setTimeout(function () { poll(false); }, 150);
    var req = root.fetch(base + opts.buildUrl(id), ac ? { signal: ac.signal } : undefined)
      .then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); });
    handle.done = req.then(function (res) {
      stop();
      return poll(true).then(function () {                                                      // 最後再取一次,確保尾端事件都收到
        settled = true;
        return { ok: res.status < 400 && !(res.data && res.data.error), status: res.status, data: res.data, cancelled: !!(res.data && res.data.cancelled) };
      });
    }).catch(function (err) {
      stop();
      if (handle.cancelled) return { ok: false, cancelled: true };
      return { ok: false, error: (err && err.message) || '連線失敗' };
    });
    handle.cancel = function () {
      if (settled || handle.cancelled) return;
      handle.cancelled = true; stop();
      try { if (ac) ac.abort(); } catch (e) { /* ignore */ }
      try { root.fetch(base + '/api/job_cancel?job=' + id, { method: 'POST', keepalive: true }); } catch (e) { /* ignore */ }
    };
    return handle;
  }
  /* 關閉分頁/離開網站時,通知後端停止還在跑的分析(不再為沒人看的結果耗用這台電腦的 CPU) */
  if (root.addEventListener) root.addEventListener('pagehide', function (ev) {
    if (ev && ev.persisted) return;                                                              // 只是進入 bfcache(之後可能回來)時不取消
    Object.keys(active).forEach(function (id) { try { if (root.navigator.sendBeacon) root.navigator.sendBeacon('/api/job_cancel?job=' + id); } catch (e) { /* ignore */ } });
  });

  /* ───────────────── 精簡進度列(彈窗、最佳策略頁) ─────────────────
   * 沒有球體、沒有動畫迴圈;只在事件到達時更新文字與寬度。                                                      */
  function progressView(el, opts) {
    opts = opts || {};
    var model = opts.model || new Model(), handle = null, t0 = 0, endInfo = null;
    el.classList.add('rcp'); el.innerHTML =
      '<div class="rcp-top"><span class="rcp-now" role="status" aria-live="polite">準備中…</span><span class="rcp-el"></span>' +
      '<button type="button" class="rcp-cancel btn-sm" hidden>取消</button></div>' +
      '<div class="progress-bar-wrap"><div class="progress-bar rcp-bar" style="width:0%"></div></div>' +
      '<ol class="rcp-stages">' + STAGES.map(function (s) { return '<li data-stage="' + s.id + '" class="idle"><i></i><span>' + s.label + '</span><em></em></li>'; }).join('') + '</ol>' +
      '<div class="rcp-note"></div>';
    var q = function (s) { return el.querySelector(s); }, now = q('.rcp-now'), elp = q('.rcp-el'), bar = q('.rcp-bar'), cancel = q('.rcp-cancel'), note = q('.rcp-note');
    cancel.addEventListener('click', function () { if (handle) { cancel.disabled = true; handle.cancel(); } });

    function setW(w) { if (bar.style.width !== w) bar.style.width = w; }
    function render() {
      el.style.display = model.state === 'idle' ? 'none' : '';          // 還沒開始分析:不顯示空的進度列
      STAGES.forEach(function (s) {
        var st = model.stages[s.id], li = q('[data-stage="' + s.id + '"]');
        li.className = st.status;
        li.querySelector('em').textContent = st.status === 'running' && st.prog && st.prog.n ? st.prog.i + '/' + st.prog.n : (st.status === 'done' && st.ms != null ? fmtMs(st.ms) : (st.status === 'idle' ? '' : STATUS_LABEL[st.status]));
      });
      var c = model.counted(), run = model.running(), err = model.errored();
      bar.classList.remove('indet', 'err', 'warn', 'ok');
      if (model.state === 'running') {
        if (c) { now.textContent = c.stage.label + ' ' + c.i + ' / ' + c.n; setW((c.n ? c.i / c.n * 100 : 0) + '%'); }
        else if (run.length) { now.textContent = run[run.length - 1].label + ':處理中'; setW('100%'); bar.classList.add('indet'); }
        else { now.textContent = model.eventCount ? '等待下一個階段…' : '連線中…'; setW('100%'); bar.classList.add('indet'); }
      } else if (model.state === 'ok') { now.textContent = '完成'; setW('100%'); bar.classList.add('ok'); }
      else if (model.state === 'cancelled') { now.textContent = '已取消'; bar.classList.add('warn'); }
      else if (model.state === 'error') { now.textContent = err.length ? '失敗:' + err[0].label : '失敗'; setW('100%'); bar.classList.add('err'); }
      else if (model.state === 'stopped') { now.textContent = '已中斷'; bar.classList.add('warn'); }
      cancel.hidden = model.state !== 'running'; if (model.state === 'running') cancel.disabled = false;
    }
    function tick(ms) { elp.textContent = (model.state === 'running' ? '已 ' : '共 ') + fmtSec(ms); }
    var view = {
      model: model,
      begin: function (h) { handle = h; model.begin(); t0 = (root.performance || Date).now(); endInfo = null; note.textContent = ''; render(); tick(0); },
      event: function (e) { model.apply(e); render(); },
      tick: function (ms) { tick(ms); },
      end: function (kind, o) { model.end(kind); render(); tick((root.performance || Date).now() - t0); if (o && o.note) note.textContent = o.note; handle = null; },
      hide: function () { el.style.display = 'none'; }
    };
    render();
    return view;
  }

  /* ───────────────── 節點詳情:點擊節點時顯示該階段『真實發生的事』 ─────────────────
   * 只使用 (1) 該階段收到的事件 (2) 這次 API 回應的資料。回傳已跳脫的 HTML。                                         */
  function stageDetail(stageId, model, data) {
    var s = STAGES[IDX[stageId]], st = model.stages[stageId], h = [];
    var pct = function (v) { return v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(1) + '%'; };
    var pf = function (v) { return v == null ? '—' : (v >= 999 ? '∞' : Number(v).toFixed(2)); };
    h.push('<div class="rcd-head"><b>' + esc(s.label) + '</b><span class="rcd-st ' + st.status + '">' + STATUS_LABEL[st.status] + '</span>' +
      (st.ms != null ? '<span class="rcd-ms">耗時 ' + fmtMs(st.ms) + '</span>' : '') + '<span class="rcd-n">事件 ' + st.events.length + ' 筆</span></div>');
    if (st.status === 'idle') h.push('<p class="rcd-p">尚未執行。開始分析後,這個階段實際做了什麼會顯示在這裡。</p>');
    else if (st.status === 'skip') h.push('<p class="rcd-p">這次分析的流程不含此階段(未涉及)' + (st.detail ? ':' + esc(st.detail) : '') + '。</p>');
    else if (st.detail) h.push('<p class="rcd-p">' + esc(st.detail) + '</p>');
    if (st.status === 'error') h.push('<p class="rcd-p rcd-err">失敗原因:' + esc(st.detail) + '</p>');
    if (st.status === 'stopped') h.push('<p class="rcd-p">工作在這個階段結束前就中止了(取消或連線中斷),沒有產生這個階段的結果。</p>');

    var results = data && data.results ? data.results : null;
    if (stageId === 'data') {
      var done = st.events.filter(function (e) { return e.status === 'done'; })[0], sp = data && data.split;
      if (done) h.push('<ul class="rcd-ul"><li>K 棒數:<b>' + done.bars + '</b></li></ul>');
      if (sp) h.push('<ul class="rcd-ul"><li>樣本內:' + esc(sp.windowStart) + ' → ' + esc(sp.boundary) + '(' + sp.isBars + ' 根)</li><li>樣本外:' + esc(sp.boundary) + ' → ' + esc(sp.end) + '(' + sp.oosBars + ' 根)</li></ul>');
    }
    if (stageId === 'backtest') {
      var prog = st.events.filter(function (e) { return e.status === 'progress' && e.ms != null; });
      if (prog.length) {
        var slow = prog.slice().sort(function (a, b) { return b.ms - a.ms; }).slice(0, 5), tot = prog.reduce(function (a, e) { return a + e.ms; }, 0);
        h.push('<p class="rcd-p">已回測 <b>' + prog.length + '</b> 個策略,合計 ' + fmtMs(tot) + '。耗時最長的 5 個:</p><ul class="rcd-ul">' +
          slow.map(function (e) { return '<li>' + esc(e.strat) + ' · ' + fmtMs(e.ms) + '</li>'; }).join('') + '</ul>');
      }
      if (results && results.length) {
        h.push('<p class="rcd-p">入選前 ' + results.length + ' 名(只看樣本內排名):</p><div class="rcd-tw"><table class="rcd-t"><thead><tr><th>#</th><th>策略</th><th>樣本內報酬</th><th>樣本內淨 PF</th><th>筆數</th></tr></thead><tbody>' +
          results.map(function (r, i) { var is = r.is || r; return '<tr><td>' + (i + 1) + '</td><td>' + esc(r.name) + '</td><td>' + pct(is.total) + '</td><td>' + pf(is.pf) + '</td><td>' + (is.trades != null ? is.trades : '—') + '</td></tr>'; }).join('') + '</tbody></table></div>');
      }
    }
    if (stageId === 'validation' && results && results.length && st.status !== 'skip') {
      h.push('<div class="rcd-tw"><table class="rcd-t"><thead><tr><th>#</th><th>策略</th><th>樣本外報酬</th><th>樣本外淨 PF</th><th>筆數</th><th>展示分級</th></tr></thead><tbody>' +
        results.map(function (r, i) { var o = r.oos; return '<tr><td>' + (i + 1) + '</td><td>' + esc(r.name) + '</td><td>' + (o && o.trades ? pct(o.total) : '—') + '</td><td>' + (o && o.trades ? pf(o.pf) : '—') + '</td><td>' + (o ? o.trades : '—') + '</td><td>' + esc(TIER_LABEL[r.oosTier] || '—') + '</td></tr>'; }).join('') +
        '</tbody></table></div><p class="rcd-p rcd-small">分級只依樣本外筆數(少於 20 筆=樣本不足,20–49=初步觀察,50 以上=可進一步評估),不是統計顯著性,也不代表策略有效。</p>');
    }
    if (stageId === 'summary' && data && data.backtest && data.backtest.available) {
      var c = data.backtest.cost;
      h.push('<ul class="rcd-ul"><li>權益曲線 ' + data.backtest.equity.length + ' 個點</li>' + (c ? '<li>每筆來回成本約 ' + esc(c.roundTripPct) + '%</li>' : '') + '</ul>');
    }
    var last = st.events.slice(-8).reverse();
    if (last.length) h.push('<details class="rcd-ev"' + (st.status === 'error' ? ' open' : '') + '><summary>此階段最近 ' + last.length + ' 筆事件</summary><ol>' +
      last.map(function (e) { return '<li><span>+' + (e.t / 1000).toFixed(2) + 's</span> ' + esc(e.status) + ' ' + esc(describe(e)) + (e.ms != null ? ' · ' + fmtMs(e.ms) : '') + '</li>'; }).join('') + '</ol></details>');
    return h.join('');
  }

  root.RCJob = { STAGES: STAGES, IDX: IDX, STATUS_LABEL: STATUS_LABEL, TIER_LABEL: TIER_LABEL, Model: Model, run: run, newJobId: newJobId,
    describe: describe, fmtMs: fmtMs, fmtSec: fmtSec, esc: esc, progressView: progressView, stageDetail: stageDetail };
})(typeof window !== 'undefined' ? window : this);

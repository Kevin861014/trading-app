/* Interactive strategy research core (prototype).
   Original design for this project: a tilted ring of five real pipeline stages with route lines and data particles.
   Canvas 2D only (no Three.js, no external assets, no network calls). State-driven: nothing animates unless a stage
   is actually running or handing data over. Pauses when hidden / off-screen / reduced-motion / low-power. */
(function () {
  'use strict';

  var STAGES = [
    { id: 'data',   name: '市場資料', sub: 'K 線與資料品質',  target: 'watchlist' },
    { id: 'tech',   name: '技術分析', sub: 'ADX・趨勢・EMA',  target: 'market' },
    { id: 'signal', name: '策略訊號', sub: '已收盤 K 棒訊號', target: 'symbol' },
    { id: 'valid',  name: '回測驗證', sub: 'IS / OOS 驗證',   target: 'best' },
    { id: 'risk',   name: '風險評估', sub: '回撤・成本',      target: 'symbol-risk' }
  ];
  var COLORS = { idle: '#6b7390', running: '#3fc1ff', done: '#26a69a', warn: '#f5a623', error: '#ef5350', skipped: '#444a60' };
  var STATUS_TEXT = { idle: '待命', running: '執行中', done: '完成', warn: '注意', error: '失敗', skipped: '略過' };

  var host, canvas, ctx, hub, nodeEls = [], mobileEl, statsEl;
  var state = {}, context = { symbol: '', tf: '', strategy: '' }, onNavigate = function () {};
  var W = 0, H = 0, dpr = 1, cx = 0, cy = 0, R = 0, F = 1100;
  var phi = 0, tilt = 0.55, rotating = true;
  var particles = [], PMAX = 90, spawnAcc = [0, 0, 0, 0, 0];
  var sprites = {};
  var raf = 0, last = 0, interval = 33, loopOn = false;
  var ambient = false, redrawQueued = false;
  var userEnabled = true, reduced = false, hidden = false, inView = true, mobile = false, lowPower = false, forcedStatic = false;
  var stats = { frames: 0, drawMs: 0, emaMs: 0, fps: 0, _t: 0, _n: 0, loopStarts: 0, particles: 0 };
  var NSEG = 5, SAMPLES = 24, RING_N = 96;
  var ringModel = [], segModel = [], nodeModel = [];
  var pointer = { x: 0, y: 0 };

  function now() { return (window.performance && performance.now) ? performance.now() : Date.now(); }
  function hex2rgb(h) { var n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }

  function glow(color, size) {
    var key = color + size;
    if (sprites[key]) return sprites[key];
    var c = document.createElement('canvas'); c.width = c.height = size;
    var g = c.getContext('2d'), rgb = hex2rgb(color);
    var gr = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gr.addColorStop(0, 'rgba(' + rgb.join(',') + ',0.95)');
    gr.addColorStop(0.25, 'rgba(' + rgb.join(',') + ',0.45)');
    gr.addColorStop(1, 'rgba(' + rgb.join(',') + ',0)');
    g.fillStyle = gr; g.fillRect(0, 0, size, size);
    return (sprites[key] = c);
  }

  function buildModel() {
    ringModel = []; nodeModel = []; segModel = [];
    var i, a;
    for (i = 0; i < RING_N; i++) { a = (i / RING_N) * Math.PI * 2; ringModel.push({ x: Math.cos(a) * R, y: 0, z: Math.sin(a) * R }); }
    for (i = 0; i < STAGES.length; i++) { a = Math.PI - (i / STAGES.length) * Math.PI * 2; nodeModel.push({ x: Math.cos(a) * R, y: 0, z: Math.sin(a) * R }); }
    for (i = 0; i < NSEG; i++) {
      var A = nodeModel[i], B = nodeModel[(i + 1) % STAGES.length], pts = [];
      for (var k = 0; k <= SAMPLES; k++) {
        var u = k / SAMPLES, lift = -Math.sin(Math.PI * u) * R * 0.28;
        pts.push({ x: A.x + (B.x - A.x) * u * 0.92 + (-A.x * 0.04) * Math.sin(Math.PI * u), y: lift, z: A.z + (B.z - A.z) * u * 0.92 });
      }
      segModel.push(pts);
    }
  }

  function xf(p) {
    var cp = Math.cos(phi), sp = Math.sin(phi), ct = Math.cos(tilt), st = Math.sin(tilt);
    var x = p.x * cp + p.z * sp, z = -p.x * sp + p.z * cp, y = p.y;
    var y2 = y * ct - z * st, z2 = y * st + z * ct;
    var s = F / (F + z2);
    return { x: cx + (x + pointer.x * 10) * s, y: cy + (y2 + pointer.y * 6) * s, s: s, z: z2 };
  }

  function edgeActive(i) {
    var a = state[STAGES[i].id], b = STAGES[i + 1] ? state[STAGES[i + 1].id] : null;
    if (!b) return false;
    return a.status === 'running' || ((a.status === 'done' || a.status === 'warn') && b.status === 'running');
  }
  function edgeTraveled(i) {
    var a = state[STAGES[i].id].status, b = STAGES[i + 1] ? state[STAGES[i + 1].id].status : 'idle';
    return (a === 'done' || a === 'warn') && b !== 'idle' && b !== 'skipped';
  }
  function anyRunning() { for (var i = 0; i < STAGES.length; i++) if (state[STAGES[i].id].status === 'running') return true; return false; }

  function resize() {
    var r = host.getBoundingClientRect();
    W = Math.max(320, Math.round(r.width)); H = Math.max(280, Math.round(r.height));
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx = W / 2; cy = H * 0.47; R = Math.min(W * 0.30, H * 0.44);
    buildModel(); drawFrame(0, true);
  }

  function spawn(seg) {
    for (var i = 0; i < PMAX; i++) if (!particles[i]) { particles[i] = { seg: seg, u: 0, v: 0.45 + Math.random() * 0.25 }; return; }
    for (var j = 0; j < PMAX; j++) if (particles[j] && particles[j].dead) { particles[j] = { seg: seg, u: 0, v: 0.45 + Math.random() * 0.25 }; return; }
  }

  function update(dt) {
    if (ambient && rotating && !anyRunning()) phi += dt * 0.00009;   // optional decorative rotation (off by default)
    var cap = lowPower ? Math.floor(PMAX / 3) : PMAX, active = 0, i;
    for (i = 0; i < NSEG; i++) {
      if (edgeActive(i)) { spawnAcc[i] += dt * (lowPower ? 0.006 : 0.012); while (spawnAcc[i] >= 1) { spawnAcc[i] -= 1; if (countP() < cap) spawn(i); } }
      else spawnAcc[i] = 0;
    }
    for (i = 0; i < particles.length; i++) {
      var p = particles[i]; if (!p || p.dead) continue;
      p.u += p.v * dt / 1000; if (p.u >= 1) p.dead = true; else active++;
    }
    stats.particles = active;
  }
  function countP() { var n = 0; for (var i = 0; i < particles.length; i++) if (particles[i] && !particles[i].dead) n++; return n; }

  function drawFrame(ts, staticDraw) {
    var t0 = now(), i, k;
    ctx.clearRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'source-over';
    // ring (depth-faded)
    var rp = [];
    for (i = 0; i < ringModel.length; i++) rp.push(xf(ringModel[i]));
    ctx.lineWidth = 1;
    for (i = 0; i < rp.length; i++) {
      var a = rp[i], b = rp[(i + 1) % rp.length], al = 0.10 + 0.22 * (1 - (a.z + R) / (2 * R));
      ctx.strokeStyle = 'rgba(120,150,210,' + al.toFixed(3) + ')';
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    var hubP = xf({ x: 0, y: -R * 0.08, z: 0 }), np = [], sp = [];
    for (i = 0; i < STAGES.length; i++) np.push(xf(nodeModel[i]));
    // spokes
    ctx.strokeStyle = 'rgba(100,130,190,0.10)'; ctx.setLineDash([3, 6]);
    for (i = 0; i < np.length; i++) { ctx.beginPath(); ctx.moveTo(hubP.x, hubP.y); ctx.lineTo(np[i].x, np[i].y); ctx.stroke(); }
    ctx.setLineDash([]);
    // route segments
    for (i = 0; i < NSEG; i++) {
      var pts = segModel[i], proj = [];
      for (k = 0; k < pts.length; k++) proj.push(xf(pts[k]));
      sp.push(proj);
      var act = edgeActive(i), trav = edgeTraveled(i);
      var col = act ? COLORS.running : (trav ? COLORS.done : '#4c5472');
      var rgb = hex2rgb(col), alpha = act ? 0.85 : (trav ? 0.55 : 0.28);
      ctx.strokeStyle = 'rgba(' + rgb.join(',') + ',' + alpha + ')'; ctx.lineWidth = act ? 2.2 : 1.4;
      ctx.beginPath(); ctx.moveTo(proj[0].x, proj[0].y);
      for (k = 1; k < proj.length; k++) ctx.lineTo(proj[k].x, proj[k].y);
      ctx.stroke();
    }
    // particles = data in flight (only on active edges)
    ctx.globalCompositeOperation = 'lighter';
    var gs = glow(COLORS.running, 32);
    for (i = 0; i < particles.length; i++) {
      var p = particles[i]; if (!p || p.dead) continue;
      var proj2 = sp[p.seg], f = p.u * SAMPLES, i0 = Math.min(SAMPLES - 1, Math.floor(f)), fr = f - i0;
      var q0 = proj2[i0], q1 = proj2[i0 + 1], px = q0.x + (q1.x - q0.x) * fr, py = q0.y + (q1.y - q0.y) * fr, sz = 14 * q0.s;
      ctx.globalAlpha = 0.85 * Math.sin(Math.PI * p.u);
      ctx.drawImage(gs, px - sz / 2, py - sz / 2, sz, sz);
    }
    ctx.globalAlpha = 1;
    // hub
    var hs = glow('#5a8dff', 96), hz = 120 * hubP.s;
    ctx.drawImage(hs, hubP.x - hz / 2, hubP.y - hz / 2, hz, hz);
    // nodes back-to-front
    var order = np.map(function (p, idx) { return idx; }).sort(function (a, b) { return np[b].z - np[a].z; });
    for (var oi = 0; oi < order.length; oi++) {
      var idx = order[oi], P = np[idx], st = state[STAGES[idx].id].status, c = COLORS[st];
      var pulse = (st === 'running' && !staticDraw) ? 1 + 0.12 * Math.sin(ts / 200) : 1;
      var gsz = (st === 'idle' || st === 'skipped' ? 54 : 88) * P.s * pulse, g2 = glow(c, 64);
      ctx.globalCompositeOperation = 'lighter';
      ctx.drawImage(g2, P.x - gsz / 2, P.y - gsz / 2, gsz, gsz);
      ctx.globalCompositeOperation = 'source-over';
      var r = 7 * P.s * pulse; ctx.fillStyle = c; ctx.beginPath(); ctx.arc(P.x, P.y, r, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.65)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(P.x, P.y, r + 3 * P.s, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.globalCompositeOperation = 'source-over';
    positionOverlays(np, hubP);
    var dtw = now() - t0;
    if (!staticDraw) {
      stats.frames++; stats.drawMs += dtw; stats.emaMs = stats.emaMs ? stats.emaMs * 0.9 + dtw * 0.1 : dtw;
    }
  }

  function positionOverlays(np, hubP) {
    for (var i = 0; i < nodeEls.length; i++) {
      var P = np[i], sc = 0.88 + 0.18 * P.s, below = P.y < cy ? -1 : 1;
      var tf = 'translate(' + Math.round(P.x) + 'px,' + Math.round(P.y) + 'px) translate(-50%,' + (below < 0 ? '-135%' : '35%') + ') scale(' + sc.toFixed(2) + ')';
      if (nodeEls[i]._tf !== tf) { nodeEls[i]._tf = tf; nodeEls[i].style.transform = tf; nodeEls[i].style.zIndex = String(Math.round(P.s * 100)); }
    }
    var ht = 'translate(' + Math.round(hubP.x) + 'px,' + Math.round(hubP.y) + 'px) translate(-50%,-50%)'; if (hub._tf !== ht) { hub._tf = ht; hub.style.transform = ht; }
  }

  // ---------- loop control ----------
  function shouldRun() { return userEnabled && !reduced && !hidden && inView && !mobile && !forcedStatic; }
  // the loop only exists while a stage is really running (or the optional decorative rotation is on)
  function wantLoop() { return shouldRun() && (anyRunning() || ambient); }
  function startLoop() {
    if (loopOn || !wantLoop()) return;
    loopOn = true; last = 0; stats.loopStarts++;
    raf = requestAnimationFrame(tick);
  }
  function stopLoop() {
    if (!loopOn) return;
    loopOn = false; cancelAnimationFrame(raf); particles = []; stats.particles = 0; drawFrame(0, true);   // no frozen particles after stopping
  }
  function tick(ts) {
    if (!loopOn) return;
    raf = requestAnimationFrame(tick);
    if (last && ts - last < interval) return;
    var dt = last ? ts - last : 16; last = ts;
    interval = (anyRunning() ? 33 : 66) * (lowPower ? 2 : 1);
    update(dt); drawFrame(ts, false);
    if (!wantLoop()) { stopLoop(); return; }
    stats._n++; if (ts - stats._t > 1000) { stats.fps = Math.round(stats._n * 1000 / (ts - stats._t)); stats._t = ts; stats._n = 0; renderStats(); }
    // adaptive guard: protect the machine (it also runs the trading bot)
    if (stats.frames > 60) {
      if (stats.emaMs > 22 && !forcedStatic) { forcedStatic = true; stopLoop(); note('動畫耗時過高,已自動停用動態效果(僅保留靜態圖)'); }
      else if (stats.emaMs > 10 && !lowPower) { lowPower = true; note('偵測到繪製較慢,已自動降為省電模式(降低幀率、減少光點)'); }
    }
  }
  function sync() { if (wantLoop()) startLoop(); else stopLoop(); renderMobile(); }

  // ---------- state API ----------
  function setStage(id, status, detail) {
    if (!state[id]) return;
    state[id].status = status; state[id].detail = detail || '';
    refreshText(); if (!loopOn) drawFrame(0, true); renderMobile(); sync();
  }
  function setContext(c) { context = c || context; refreshText(); }
  function reset() { STAGES.forEach(function (s) { state[s.id] = { status: 'idle', detail: '' }; }); particles = []; refreshText(); if (!loopOn && ctx) drawFrame(0, true); renderMobile(); }
  function overall() {
    var s = STAGES.map(function (x) { return state[x.id].status; });
    if (s.indexOf('error') >= 0) return ['失敗', 'error'];
    if (s.indexOf('running') >= 0) return ['分析中', 'running'];
    if (s.every(function (x) { return x === 'done'; })) return ['完成', 'done'];
    if (s.indexOf('warn') >= 0 && s.indexOf('idle') < 0) return ['完成(有注意事項)', 'warn'];
    return ['待命', 'idle'];
  }
  function refreshText() {
    if (!hub) return;
    var o = overall();
    hub.querySelector('.rc-hub-state').textContent = o[0];
    hub.querySelector('.rc-hub-state').style.color = COLORS[o[1]];
    hub.querySelector('.rc-hub-ctx').textContent = context.symbol ? (context.symbol + ' · ' + context.tf + ' · ' + context.strategy) : '尚未選擇標的';
    STAGES.forEach(function (s, i) {
      var st = state[s.id], el = nodeEls[i]; if (!el) return;
      el.querySelector('.rc-n-status').textContent = STATUS_TEXT[st.status];
      el.querySelector('.rc-n-status').style.color = COLORS[st.status];
      el.querySelector('.rc-n-detail').textContent = st.detail || s.sub;
      el.setAttribute('aria-label', s.name + ',' + STATUS_TEXT[st.status] + (st.detail ? ',' + st.detail : '') + ',按下前往相關功能');
      el.dataset.status = st.status;
    });
    hub.setAttribute('aria-label', '研究核心,' + o[0]);
  }
  function renderMobile() {
    if (!mobileEl) return;
    mobileEl.innerHTML = STAGES.map(function (s) {
      var st = state[s.id];
      return '<li><button type="button" class="rc-m-node" data-t="' + s.target + '" data-status="' + st.status + '">' +
        '<span class="rc-m-dot" style="background:' + COLORS[st.status] + '"></span><span class="rc-m-body"><b>' + s.name + '</b>' +
        '<small>' + (st.detail || s.sub) + '</small></span><span class="rc-m-st" style="color:' + COLORS[st.status] + '">' + STATUS_TEXT[st.status] + '</span></button></li>';
    }).join('');
  }
  function note(msg) { var n = host.parentNode.querySelector('.rc-note'); if (n) n.textContent = msg; }
  function renderStats() { if (statsEl) statsEl.textContent = 'fps ' + stats.fps + '  |  繪製 ' + stats.emaMs.toFixed(2) + ' ms/幀  |  光點 ' + stats.particles + '  |  迴圈 ' + (loopOn ? '運行' : '停止'); }

  // ---------- demo driver (prototype only: scripted, NOT real analysis) ----------
  var timers = [];
  function clearTimers() { timers.forEach(clearTimeout); timers = []; }
  function at(ms, fn) { timers.push(setTimeout(fn, ms)); }
  function simulate(kind) {
    clearTimers(); reset();
    setContext({ symbol: '2330.TW(示意)', tf: '日線', strategy: 'DMI/ADX' });
    var t = 200;
    var plan = {
      normal: [['data', 'done', '已收盤 K 棒 · 資料正常'], ['tech', 'done', '環境:盤整 · ADX 12.8'], ['signal', 'done', '目前:已出場'], ['valid', 'done', 'OOS 初步觀察(示意)'], ['risk', 'done', '回撤與成本已計算']],
      nodata: [['data', 'warn', '資料不足,不產生訊號'], ['tech', 'skipped', '略過'], ['signal', 'skipped', '略過'], ['valid', 'skipped', '略過'], ['risk', 'skipped', '略過']],
      weak: [['data', 'done', '已收盤 K 棒 · 資料正常'], ['tech', 'done', '環境:上升趨勢'], ['signal', 'done', '目前:持有中'], ['valid', 'warn', 'OOS 樣本不足'], ['risk', 'done', '回撤與成本已計算']],
      fail: [['data', 'error', '資料取得失敗'], ['tech', 'skipped', '略過'], ['signal', 'skipped', '略過'], ['valid', 'skipped', '略過'], ['risk', 'skipped', '略過']]
    }[kind] || [];
    plan.forEach(function (p, i) {
      at(t, function () { if (p[1] !== 'skipped') setStage(p[0], 'running', '處理中…'); });
      t += 1100;
      at(t, function () { setStage(p[0], p[1], p[2]); });
      t += 250;
    });
  }

  function mount(opts) {
    host = opts.host; onNavigate = opts.onNavigate || onNavigate; statsEl = opts.statsEl || null;
    reset();
    canvas = document.createElement('canvas'); canvas.setAttribute('aria-hidden', 'true'); canvas.className = 'rc-canvas';
    host.appendChild(canvas); ctx = canvas.getContext('2d');
    hub = document.createElement('div'); hub.className = 'rc-hub'; hub.setAttribute('role', 'status');
    hub.innerHTML = '<div class="rc-hub-title">研究核心</div><div class="rc-hub-state"></div><div class="rc-hub-ctx"></div>';
    host.appendChild(hub);
    STAGES.forEach(function (s) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'rc-node';
      b.innerHTML = '<span class="rc-n-name">' + s.name + '</span><span class="rc-n-status"></span><span class="rc-n-detail"></span>';
      b.addEventListener('click', function () { onNavigate(s.target, s.id); });
      host.appendChild(b); nodeEls.push(b);
    });
    mobileEl = opts.mobileEl || null;
    if (mobileEl) mobileEl.addEventListener('click', function (e) { var b = e.target.closest('.rc-m-node'); if (b) onNavigate(b.dataset.t); });
    var mqR = window.matchMedia('(prefers-reduced-motion: reduce)'), mqM = window.matchMedia('(max-width: 720px)');
    reduced = mqR.matches; mobile = mqM.matches;
    (mqR.addEventListener ? mqR.addEventListener('change', function (e) { reduced = e.matches; sync(); }) : mqR.addListener(function (e) { reduced = e.matches; sync(); }));
    (mqM.addEventListener ? mqM.addEventListener('change', function (e) { mobile = e.matches; sync(); }) : mqM.addListener(function (e) { mobile = e.matches; sync(); }));
    document.addEventListener('visibilitychange', function () { hidden = document.hidden; sync(); });
    if ('IntersectionObserver' in window) new IntersectionObserver(function (en) { inView = en[0].isIntersecting; sync(); }, { threshold: 0.05 }).observe(host);
    host.addEventListener('pointermove', function (e) {
      if (mobile || reduced || !userEnabled || forcedStatic) return;
      var r = host.getBoundingClientRect(); pointer.x = (e.clientX - r.left) / r.width - 0.5; pointer.y = (e.clientY - r.top) / r.height - 0.5;
      if (!loopOn && !redrawQueued) { redrawQueued = true; requestAnimationFrame(function () { redrawQueued = false; if (!loopOn) drawFrame(0, true); }); }   // event-driven parallax: one redraw per move, no loop
    });
    host.addEventListener('pointerenter', function () { rotating = false; });
    host.addEventListener('pointerleave', function () { rotating = true; pointer.x = pointer.y = 0; });
    if ('ResizeObserver' in window) new ResizeObserver(function () { resize(); }).observe(host); else window.addEventListener('resize', resize);
    resize(); refreshText(); renderMobile(); sync();
  }

  window.ResearchCore = {
    mount: mount, setStage: setStage, setContext: setContext, reset: reset, simulate: simulate,
    setAmbient: function (v) { ambient = !!v; sync(); },
    setEnabled: function (v) { userEnabled = !!v; if (v) { forcedStatic = false; lowPower = false; stats.emaMs = 0; stats.frames = 0; } sync(); },
    stats: function () { return { frames: stats.frames, avgDrawMs: stats.frames ? stats.drawMs / stats.frames : 0, emaMs: stats.emaMs, fps: stats.fps, loopOn: loopOn, loopStarts: stats.loopStarts, particles: stats.particles, lowPower: lowPower, forcedStatic: forcedStatic, mobile: mobile, reduced: reduced, inView: inView, hidden: hidden, ambient: ambient }; },
    _forceVisibility: function (h) { hidden = !!h; sync(); },
    STAGES: STAGES
  };
})();

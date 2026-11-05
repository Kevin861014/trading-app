/* Research Core v2 — own design (Canvas 2D). No third-party assets, no network calls except the site's own analysis API.
 *
 * HONESTY RULES (enforced by design, see docs/research_core_events.md):
 *  - "Working" lights (route particles, node pulses, spinners, progress numbers) are created ONLY from real events of a real job
 *    (live: polled from /api/job_events; replay: a recorded real trace). There is no demo loop, no timer-driven progress, no fake percentage.
 *  - Idle visuals (sphere rotation / slow morph / faint rings) are decorative and labelled as such; they never imply computation.
 *  - Loop runs only while: the page is visible AND the canvas is on-screen AND not prefers-reduced-motion AND not phone-sized.
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };

  // ---------------------------------------------------------------- stages (match backend research_events.STAGES)
  var STAGES = [
    { id: 'data',       label: '行情資料',   sub: '下載已收盤 K 棒' },
    { id: 'indicators', label: '指標計算',   sub: 'EMA / 策略條件' },
    { id: 'backtest',   label: '策略回測',   sub: '含成本與停損' },
    { id: 'signal',     label: '訊號判斷',   sub: '目前持倉狀態' },
    { id: 'validation', label: '樣本外驗證', sub: 'IS / OOS 分開' },
    { id: 'summary',    label: '風險與成本', sub: '回撤 / 買進持有' }
  ];
  var IDX = {}; STAGES.forEach(function (s, i) { IDX[s.id] = i; });
  var COLORS = { idle: [95, 125, 200], running: [79, 209, 255], done: [45, 212, 191], error: [255, 93, 115], skip: [120, 126, 150] };
  var BLUE = [60, 120, 235], VIOLET = [150, 100, 245], CYAN = [90, 215, 255];

  var state = {};            // per stage: {status, ms, detail, prog:{i,n}, lastAt, startedAt}
  var job = { mode: 'idle', id: null, t0: 0, lastSeq: 0, finished: false, events: 0 };
  var activity = 0;          // decays; bumped by REAL events only
  var particles = [];        // one per real progress/start/done event (capped)
  var pulses = [];           // node rings from real start/done/error events
  var logRows = [];

  function resetState() {
    STAGES.forEach(function (s) { state[s.id] = { status: 'idle', ms: null, detail: '', prog: null, lastAt: 0, startedAt: 0 }; });
    particles.length = 0; pulses.length = 0; activity = 0;
  }
  resetState();

  // ---------------------------------------------------------------- environment guards
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var phone = window.matchMedia('(max-width: 720px)');
  var visible = !document.hidden, onScreen = true, ambientOn = true, lowPower = false, forced = false;
  function staticMode() { return reduced.matches || phone.matches || forced; }

  // ---------------------------------------------------------------- canvas + geometry
  var canvas = $('rc-canvas'), ctx = canvas.getContext('2d', { alpha: true });
  var W = 0, H = 0, DPR = 1, CX = 0, CY = 0, R = 0;
  var NODE_POS = [];
  function resize() {
    var r = canvas.getBoundingClientRect();
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.max(280, r.width); H = Math.max(240, r.height);
    canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    CX = W / 2; CY = H / 2 - H * 0.02; R = Math.min(W * 0.2, H * 0.3);
    NODE_POS = STAGES.map(function (s, i) {
      var a = (-90 + i * 60) * Math.PI / 180;
      return { x: CX + Math.cos(a) * W * 0.40, y: CY + Math.sin(a) * H * 0.40 };
    });
    placeLabels(); draw(0, true);
  }
  function placeLabels() {
    STAGES.forEach(function (s, i) {
      var el = $('rc-node-' + s.id); if (!el) return;
      el.style.left = (NODE_POS[i].x / W * 100) + '%'; el.style.top = (NODE_POS[i].y / H * 100) + '%';
    });
  }

  // sphere network: Fibonacci points + nearest-neighbour edges (static topology, rotates and morphs)
  var N = 210, PTS = [], EDGES = [], DUST = [];
  (function build() {
    var ga = Math.PI * (3 - Math.sqrt(5));
    for (var i = 0; i < N; i++) {
      var y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), th = ga * i;
      PTS.push({ x: Math.cos(th) * r, y: y, z: Math.sin(th) * r, ph: (i * 2.399) % (Math.PI * 2), hue: (i % 7) / 6 });
    }
    var seen = {};
    for (var a = 0; a < N; a++) {
      var d = [];
      for (var b = 0; b < N; b++) if (b !== a) { var dx = PTS[a].x - PTS[b].x, dy = PTS[a].y - PTS[b].y, dz = PTS[a].z - PTS[b].z; d.push([dx * dx + dy * dy + dz * dz, b]); }
      d.sort(function (p, q) { return p[0] - q[0]; });
      for (var k = 0; k < 3; k++) { var bb = d[k][1], key = a < bb ? a + '-' + bb : bb + '-' + a; if (!seen[key]) { seen[key] = 1; EDGES.push([a, bb]); } }
    }
  })();
  (function () { var seed = 7; function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    for (var i = 0; i < 140; i++) { var th = rnd() * 6.283, ph = Math.acos(2 * rnd() - 1), rr = 1.45 + rnd() * 0.75; DUST.push({ x: Math.sin(ph) * Math.cos(th) * rr, y: Math.sin(ph) * Math.sin(th) * rr * 0.8, z: Math.cos(ph) * rr, k: rnd() }); } })();
  var RINGS = [];
  (function () { for (var i = 0; i < 5; i++) RINGS.push({ tilt: 0.5 + i * 0.55, spin: (i % 2 ? 1 : -1) * (0.05 + i * 0.012), rad: 1.12 + i * 0.07, hue: i / 4 }); })();

  // ---------------------------------------------------------------- glow sprites
  function sprite(rgb, size) {
    var c = document.createElement('canvas'); c.width = c.height = size; var g = c.getContext('2d');
    var gr = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gr.addColorStop(0, 'rgba(255,255,255,0.95)'); gr.addColorStop(0.18, 'rgba(' + rgb.join(',') + ',0.85)');
    gr.addColorStop(0.5, 'rgba(' + rgb.join(',') + ',0.22)'); gr.addColorStop(1, 'rgba(' + rgb.join(',') + ',0)');
    g.fillStyle = gr; g.fillRect(0, 0, size, size); return c;
  }
  var SP = { blue: sprite(BLUE, 32), violet: sprite(VIOLET, 32), cyan: sprite(CYAN, 32) };
  var SPN = {}; Object.keys(COLORS).forEach(function (k) { SPN[k] = sprite(COLORS[k], 64); });
  var SPP = { done: sprite(COLORS.done, 32), error: sprite(COLORS.error, 32), run: sprite(CYAN, 32), skip: sprite(COLORS.skip, 32) };

  function mix(a, b, t) { return [Math.round(a[0] + (b[0] - a[0]) * t), Math.round(a[1] + (b[1] - a[1]) * t), Math.round(a[2] + (b[2] - a[2]) * t)]; }

  // ---------------------------------------------------------------- routes (arc into stage i from stage i-1, or from the core for stage 0)
  var lastFrom = [-1, -1, -1, -1, -1, -1];
  function prevPerformed(i) { for (var j = i - 1; j >= 0; j--) { var st = state[STAGES[j].id].status; if (st === 'done' || st === 'running' || st === 'error') return j; } return -1; }
  function routePoint(i, u, from) {
    if (from === undefined) from = i - 1;
    var p0 = from < 0 ? { x: CX, y: CY } : NODE_POS[from], p1 = NODE_POS[i];
    var mx = (p0.x + p1.x) / 2, my = (p0.y + p1.y) / 2;
    var dx = mx - CX, dy = my - CY, L = Math.hypot(dx, dy) || 1;
    var bow = from < 0 ? 0 : 0.18;
    var cx = mx + dx / L * W * bow * 0.4, cy = my + dy / L * H * bow * 0.4;
    var a = (1 - u) * (1 - u), b = 2 * (1 - u) * u, c = u * u;
    return { x: a * p0.x + b * cx + c * p1.x, y: a * p0.y + b * cy + c * p1.y };
  }

  // ---------------------------------------------------------------- drawing
  var rotY = 0.6, tNow = 0, frameCost = 0, lastDraw = 0, frames = 0, fpsT = 0, fps = 0;
  function draw(ts, still) {
    var t0 = performance.now();
    var dt = still ? 0 : Math.min(0.1, (ts - lastDraw) / 1000); lastDraw = ts;
    tNow += dt;
    activity = Math.max(0, activity - dt * 0.9);
    var act = Math.min(1, activity);
    rotY += dt * (0.05 + act * 0.12);
    ctx.clearRect(0, 0, W, H);

    // (the soft background halo is plain CSS on .rc-box: no per-frame full-canvas gradient fill)
    ctx.globalCompositeOperation = 'lighter';
    var cosY = Math.cos(rotY), sinY = Math.sin(rotY), tilt = 0.42, cosX = Math.cos(tilt), sinX = Math.sin(tilt);
    var f = 3.2, P = new Array(N);
    for (var i = 0; i < N; i++) {
      var p = PTS[i], w = 1 + 0.07 * Math.sin(tNow * 0.45 + p.ph) + 0.04 * Math.sin(tNow * 0.27 + p.ph * 2.0);   // slow morph
      var x = p.x * w, y = p.y * w, z = p.z * w;
      var x1 = x * cosY + z * sinY, z1 = -x * sinY + z * cosY;
      var y2 = y * cosX - z1 * sinX, z2 = y * sinX + z1 * cosX;
      var s = f / (f - z2);
      P[i] = { x: CX + x1 * R * s, y: CY + y2 * R * s, z: z2, s: s };
    }
    // edges: 6 batched strokes (2 hues x 3 depth bands)
    for (var hue = 0; hue < 2; hue++) {
      for (var band = 0; band < 3; band++) {
        ctx.beginPath();
        for (var e = 0; e < EDGES.length; e++) {
          if ((e & 1) !== hue) continue;
          var A = P[EDGES[e][0]], B = P[EDGES[e][1]], zz = (A.z + B.z) / 2, bd = zz > 0.35 ? 2 : (zz > -0.3 ? 1 : 0);
          if (bd !== band) continue; ctx.moveTo(A.x, A.y); ctx.lineTo(B.x, B.y);
        }
        var col = hue ? VIOLET : BLUE, al = [0.10, 0.20, 0.38][band] * (1 + act * 0.9);
        ctx.strokeStyle = 'rgba(' + col.join(',') + ',' + Math.min(0.9, al) + ')'; ctx.lineWidth = band === 2 ? 1.1 : 0.7; ctx.stroke();
      }
    }
    // decorative filament rings (static decoration, not data)
    for (var r = 0; r < RINGS.length; r++) {
      var rg = RINGS[r], ang0 = tNow * rg.spin, ct = Math.cos(rg.tilt), st = Math.sin(rg.tilt);
      ctx.beginPath();
      for (var k = 0; k <= 72; k++) {
        var a = k / 72 * Math.PI * 2 + ang0, rx = Math.cos(a) * rg.rad, rz = Math.sin(a) * rg.rad, ry = 0;
        var yy = ry * ct - rz * st, zz2 = ry * st + rz * ct;
        var xx = rx * cosY + zz2 * sinY, zr = -rx * sinY + zz2 * cosY;
        var y3 = yy * cosX - zr * sinX, z3 = yy * sinX + zr * cosX, sc = f / (f - z3);
        var px = CX + xx * R * sc, py = CY + y3 * R * sc; if (k) ctx.lineTo(px, py); else ctx.moveTo(px, py);
      }
      var cc = mix(BLUE, VIOLET, rg.hue); ctx.strokeStyle = 'rgba(' + cc.join(',') + ',' + (0.13 + act * 0.1) + ')'; ctx.lineWidth = 0.8; ctx.stroke();
    }
    // faint outer dust (decoration)
    for (var di = 0; di < DUST.length; di++) {
      var dp = DUST[di], dx0 = dp.x * cosY + dp.z * sinY, dz0 = -dp.x * sinY + dp.z * cosY, dy0 = dp.y * cosX - dz0 * sinX, dz1 = dp.y * sinX + dz0 * cosX, ds = f / (f - dz1);
      var dpx = CX + dx0 * R * ds, dpy = CY + dy0 * R * ds, dsz = 3 + 4 * ds;
      ctx.globalAlpha = (0.12 + 0.3 * dp.k) * (0.6 + 0.4 * Math.sin(tNow * 0.6 + di)); ctx.drawImage(dp.k > 0.5 ? SP.cyan : SP.blue, dpx - dsz / 2, dpy - dsz / 2, dsz, dsz);
    }
    ctx.globalAlpha = 1;
    // points (depth shaded)
    for (var j = 0; j < N; j++) {
      var q = P[j], dep = (q.z + 1.2) / 2.4, sz = (5 + 9 * dep) * q.s * (0.8 + act * 0.25);
      ctx.globalAlpha = 0.25 + 0.75 * dep; ctx.drawImage(PTS[j].hue > 0.5 ? SP.violet : (PTS[j].hue > 0.15 ? SP.blue : SP.cyan), q.x - sz / 2, q.y - sz / 2, sz, sz);
    }
    ctx.globalAlpha = 1;
    // core glow (brightens only with recent REAL events)
    var cs = R * (0.55 + act * 0.25); ctx.globalAlpha = 0.5 + act * 0.4; ctx.drawImage(SP.violet, CX - cs, CY - cs, cs * 2, cs * 2); ctx.globalAlpha = 1;

    // routes + nodes
    var now = performance.now();
    for (var n = 0; n < STAGES.length; n++) {
      var st2 = state[STAGES[n].id], col2 = COLORS[st2.status] || COLORS.idle;
      var recent = Math.max(0, 1 - (now - st2.lastAt) / 900);            // lit only for ~0.9 s after a real event
      var base = st2.status === 'idle' ? 0.10 : (st2.status === 'skip' ? 0.07 : 0.22), a2 = base + recent * 0.7;
      ctx.beginPath(); for (var u = 0; u <= 20; u++) { var rp = routePoint(n, u / 20); if (u) ctx.lineTo(rp.x, rp.y); else ctx.moveTo(rp.x, rp.y); }
      ctx.strokeStyle = 'rgba(' + col2.join(',') + ',' + (base * 0.8) + ')'; ctx.lineWidth = 1; if (st2.status === 'skip') ctx.setLineDash([4, 6]); ctx.stroke(); ctx.setLineDash([]);
      if (recent > 0.02) {   // the route that REAL work just travelled (from the last stage that actually ran)
        ctx.beginPath(); for (var u2 = 0; u2 <= 20; u2++) { var rq = routePoint(n, u2 / 20, lastFrom[n]); if (u2) ctx.lineTo(rq.x, rq.y); else ctx.moveTo(rq.x, rq.y); }
        ctx.strokeStyle = 'rgba(' + col2.join(',') + ',' + (recent * 0.85) + ')'; ctx.lineWidth = 1 + recent * 2.2; ctx.stroke();
      }
      var ns = 46 + (st2.status === 'running' ? 12 * (0.5 + 0.5 * Math.sin(now / 280)) : 0) + recent * 10;
      ctx.globalAlpha = st2.status === 'idle' ? 0.45 : 0.95; ctx.drawImage(SPN[st2.status] || SPN.idle, NODE_POS[n].x - ns / 2, NODE_POS[n].y - ns / 2, ns, ns); ctx.globalAlpha = 1;
    }
    // pulses (from real start/done/error events)
    for (var pi = pulses.length - 1; pi >= 0; pi--) {
      var pu = pulses[pi], age = (now - pu.t) / 900; if (age >= 1) { pulses.splice(pi, 1); continue; }
      var rr = 22 + age * 46; ctx.beginPath(); ctx.arc(NODE_POS[pu.i].x, NODE_POS[pu.i].y, rr, 0, 6.283);
      ctx.strokeStyle = 'rgba(' + pu.c.join(',') + ',' + (0.7 * (1 - age)) + ')'; ctx.lineWidth = 2; ctx.stroke();
    }
    // particles: exactly one per real event, travelling along the route into that stage
    for (var qi = particles.length - 1; qi >= 0; qi--) {
      var pt = particles[qi]; pt.u += dt / pt.dur; if (still) pt.u = Math.min(pt.u, 0.999);
      if (pt.u >= 1) { particles.splice(qi, 1); continue; }
      for (var tr = 0; tr < 4; tr++) {
        var uu = Math.max(0, pt.u - tr * 0.045), pp = routePoint(pt.i, uu, pt.from), ps = (16 - tr * 3.2);
        ctx.globalAlpha = 1 - tr * 0.25; ctx.drawImage(pt.sp, pp.x - ps / 2, pp.y - ps / 2, ps, ps);
      }
    }
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';

    frameCost = frameCost * 0.9 + (performance.now() - t0) * 0.1;
    frames++; if (ts - fpsT > 1000) { fps = Math.round(frames * 1000 / Math.max(1, ts - fpsT)); frames = 0; fpsT = ts; if ($('rc-stats')) $('rc-stats').textContent = (loopOn ? 'fps ' + fps : '靜態') + ' · 繪製 ' + frameCost.toFixed(2) + ' ms/幀 · 光點 ' + particles.length + ' · 事件 ' + job.events; }
  }

  // ---------------------------------------------------------------- render loop (only while needed)
  var loopOn = false, raf = 0, lastFrame = 0;
  function working() { return job.mode !== 'idle' && !job.finished; }
  function wantLoop() {
    if (staticMode() || !visible || !onScreen) return false;
    return working() || particles.length > 0 || pulses.length > 0 || activity > 0.02 || ambientOn;
  }
  function targetFps() {
    if (working() || particles.length || pulses.length) return lowPower ? 16 : 24;
    return lowPower ? 6 : 10;                       // idle decoration: low frame rate on purpose
  }
  function tick(ts) {
    raf = 0; if (!loopOn) return;
    var iv = 1000 / targetFps();
    if (ts - lastFrame >= iv - 1) {
      lastFrame = ts; draw(ts, false);
      if (frameCost > 14 && !lowPower) lowPower = true;        // guard: expensive frames → lower fps
      if (frameCost > 26) { forced = true; stopLoop(); draw(performance.now(), true); setStatusNote('畫面負擔過高,已自動改為靜態'); return; }
    }
    if (!wantLoop()) { stopLoop(); draw(performance.now(), true); return; }
    raf = requestAnimationFrame(tick);
  }
  function startLoop() { if (loopOn) return; loopOn = true; lastFrame = 0; lastDraw = performance.now(); raf = requestAnimationFrame(tick); }
  function stopLoop() { loopOn = false; if (raf) cancelAnimationFrame(raf); raf = 0; if ($('rc-stats')) $('rc-stats').textContent = '靜態 · 事件 ' + job.events; }
  function sync() { if (wantLoop()) startLoop(); else if (loopOn) { stopLoop(); draw(performance.now(), true); } else draw(performance.now(), true); }
  document.addEventListener('visibilitychange', function () { visible = !document.hidden; sync(); });
  if ('IntersectionObserver' in window) new IntersectionObserver(function (en) { onScreen = en[0].isIntersecting; sync(); }).observe(canvas);
  [reduced, phone].forEach(function (m) { (m.addEventListener ? m.addEventListener('change', sync) : m.addListener(sync)); });
  window.addEventListener('resize', function () { resize(); sync(); });

  // ---------------------------------------------------------------- real events → state
  function fmtMs(ms) { return ms == null ? '' : (ms >= 1000 ? (ms / 1000).toFixed(2) + ' 秒' : Math.round(ms) + ' ms'); }
  function describe(e) {
    var d = [];
    if (e.stage === 'data') { if (e.bars != null) d.push(e.bars + ' 根 K 棒'); if (e.source) d.push(e.source); if (e.interval) d.push(e.interval); }
    if (e.stage === 'indicators' && e.bars != null) d.push(e.bars + ' 根');
    if (e.stage === 'backtest') { if (e.i != null) d.push(e.i + ' / ' + e.n); if (e.strat) d.push(e.strat); if (e.tested != null) d.push('測試 ' + e.tested + ' 個、入選 ' + e.kept); if (e.trades != null) d.push(e.trades + ' 筆交易'); if (e.strategy) d.push(e.strategy); }
    if (e.stage === 'signal' && e.inPos != null) d.push(e.inPos ? '策略目前持有中' : '策略目前空手');
    if (e.stage === 'validation') { if (e.i != null) d.push(e.i + ' / ' + e.n); if (e.strat) d.push(e.strat); if (e.oosTrades != null) d.push('樣本外 ' + e.oosTrades + ' 筆'); if (e.tier) d.push(e.tier); if (e.available === false) d.push('資料不足,切不出樣本外'); }
    if (e.stage === 'summary' && e.points != null) d.push(e.points + ' 個權益點、' + e.trades + ' 筆');
    if (e.reason) d.push(e.reason); if (e.message) d.push(e.message);
    return d.join(' · ');
  }
  var statusLabel = { start: '開始', progress: '進行', done: '完成', skip: '略過', error: '失敗' };
  function applyEvent(e) {
    var i = IDX[e.stage]; if (i == null) return;
    var s = state[e.stage], now = performance.now(); job.events++;
    s.lastAt = now; activity = Math.min(2, activity + (e.status === 'progress' ? 0.12 : 0.5));
    var det = describe(e);
    if (e.status === 'start') { s.status = 'running'; s.startedAt = now; s.ms = null; s.detail = det; pulses.push({ i: i, t: now, c: COLORS.running }); addParticle(i, 'run', 0.9); }
    else if (e.status === 'progress') { s.status = 'running'; if (e.i != null) s.prog = { i: e.i, n: e.n }; s.detail = det; if (e.ms != null) s.ms = e.ms; addParticle(i, 'run', 0.7); }
    else if (e.status === 'done') { s.status = 'done'; s.ms = e.ms; s.detail = det || s.detail; pulses.push({ i: i, t: now, c: COLORS.done }); addParticle(i, 'done', 0.9); }
    else if (e.status === 'skip') { s.status = 'skip'; s.detail = det || '本分析不含此階段'; addParticle(i, 'skip', 0.6); }
    else if (e.status === 'error') { s.status = 'error'; s.ms = e.ms; s.detail = det; pulses.push({ i: i, t: now, c: COLORS.error }); addParticle(i, 'error', 1.0); }
    log(e, det); refreshText(e); sync();
  }
  function addParticle(i, kind, dur) { lastFrom[i] = prevPerformed(i); if (staticMode()) return; if (particles.length > 90) particles.shift(); particles.push({ i: i, u: 0, dur: dur, sp: SPP[kind], from: lastFrom[i] }); }

  function log(e, det) {
    var row = document.createElement('div'); row.className = 'rc-log-row ' + e.status;
    row.innerHTML = '<span class="t">+' + (e.t / 1000).toFixed(2) + 's</span><b>' + STAGES[IDX[e.stage]].label + '</b><span class="st">' + statusLabel[e.status] + '</span><span class="d"></span>';
    row.querySelector('.d').textContent = (det || '') + (e.ms != null && e.status !== 'progress' ? ' · ' + fmtMs(e.ms) : (e.status === 'progress' && e.ms != null ? ' · ' + fmtMs(e.ms) : ''));
    var box = $('rc-log'); box.insertBefore(row, box.firstChild); while (box.childNodes.length > 160) box.removeChild(box.lastChild);
  }

  // ---------------------------------------------------------------- text (centre panel + stage cards): all from real state
  function refreshText(lastEvent) {
    STAGES.forEach(function (s) {
      var st = state[s.id], card = $('rc-card-' + s.id), node = $('rc-node-' + s.id); if (!card) return;
      card.className = 'rc-card ' + st.status; node.className = 'rc-node ' + st.status;
      var line = st.status === 'idle' ? '尚未執行' : st.detail || ({ running: '進行中', done: '完成', skip: '略過', error: '失敗' })[st.status];
      if (st.prog && st.status === 'running') line = st.prog.i + ' / ' + st.prog.n + (st.detail ? ' · ' + st.detail.replace(/^\d+ \/ \d+ · /, '') : '');
      card.querySelector('.d').textContent = line;
      card.querySelector('.m').textContent = st.status === 'done' && st.ms != null ? fmtMs(st.ms) : (st.status === 'running' ? '執行中' : (st.status === 'skip' ? '未涉及' : (st.status === 'error' ? '失敗' : '待機')));
      var bar = card.querySelector('.bar i'); bar.style.width = (st.prog && st.prog.n ? (st.prog.i / st.prog.n * 100) : (st.status === 'done' ? 100 : 0)) + '%';
      node.setAttribute('aria-label', s.label + ':' + (st.status === 'idle' ? '待機' : line));
    });
    var c = $('rc-center'), title, body;
    if (job.mode === 'idle') { title = '待機中'; body = '尚未開始分析。背景的球體旋轉是裝飾,不代表運算;只有真實的分析事件才會讓路線與光點亮起。'; }
    else {
      var running = STAGES.filter(function (s) { return state[s.id].status === 'running'; }), err = STAGES.filter(function (s) { return state[s.id].status === 'error'; });
      if (err.length) { title = '失敗:' + err[0].label; body = state[err[0].id].detail; }
      else if (running.length) { var cur = running[running.length - 1], cs = state[cur.id]; title = cur.label + '…'; body = cs.detail || cur.sub; }
      else if (job.finished) { title = job.ok === false ? '已結束(有錯誤)' : '完成'; body = job.summary || ''; }
      else { title = '等待下一個真實事件'; body = ''; }
    }
    $('rc-center-title').textContent = title; $('rc-center-body').textContent = body;
    c.className = 'rc-center ' + (job.mode === 'idle' ? 'idle' : (STAGES.some(function (s) { return state[s.id].status === 'error'; }) ? 'error' : (job.finished ? 'done' : 'running')));
    $('rc-mode').textContent = job.mode === 'idle' ? '待機中 · 背景為裝飾' : (job.mode === 'live' ? (job.finished ? '即時分析已結束' : '即時分析中 · 光點來自後端真實事件') : (job.finished ? '重播結束' : '重播真實紀錄 · 光點來自當時的真實事件'));
  }
  function setStatusNote(t) { $('rc-note').textContent = t || ''; }

  // ---------------------------------------------------------------- live job: real API call + real event polling (only while the call is in flight)
  var base = '';
  function apiBase() { return ($('rc-base').value || '').replace(/\/$/, ''); }
  function newJobId() { var a = new Uint8Array(9); (window.crypto || {}).getRandomValues ? crypto.getRandomValues(a) : a.forEach(function (_, i) { a[i] = Math.random() * 256; }); return 'rc-' + Array.prototype.map.call(a, function (b) { return b.toString(16).padStart(2, '0'); }).join(''); }
  var pollTimer = 0, runToken = 0;
  function begin(mode) { resetState(); $('rc-log').innerHTML = ''; job = { mode: mode, id: null, t0: performance.now(), lastSeq: 0, finished: false, events: 0, summary: '', ok: null }; $('rc-result').innerHTML = ''; setStatusNote(''); refreshText(); }
  function cancelAll() { runToken++; clearTimeout(pollTimer); replayTimers.forEach(clearTimeout); replayTimers = []; }

  function startLive() {
    cancelAll(); var token = runToken; begin('live');
    var kind = $('rc-kind').value, sym = ($('rc-symbol').value || '').trim(), tf = $('rc-tf').value;
    if (!sym) { setStatusNote('請輸入代號'); job.mode = 'idle'; refreshText(); return; }
    job.id = newJobId();
    var q = '?symbol=' + encodeURIComponent(sym) + '&timeframe=' + tf + '&job=' + job.id, url;
    if (kind === 'analyze') url = '/api/analyze' + q + '&strategy=' + encodeURIComponent($('rc-strat').value) + '&period=2y';
    else if (kind === 'best') url = '/api/best_strategy' + q + '&period=2y&use_oos=1';
    else url = '/api/deep_analysis' + q + '&use_oos=1';
    var b = apiBase(); $('rc-start').disabled = true; sync();
    function poll(final) {
      fetch(b + '/api/job_events?job=' + job.id + '&after=' + job.lastSeq).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (token !== runToken) return;
        if (j && j.events) { j.events.forEach(function (e) { job.lastSeq = Math.max(job.lastSeq, e.seq); applyEvent(e); }); }
        if (!final) pollTimer = setTimeout(function () { poll(false); }, 250);
      }).catch(function () { if (!final && token === runToken) pollTimer = setTimeout(function () { poll(false); }, 500); });
    }
    pollTimer = setTimeout(function () { poll(false); }, 120);
    fetch(b + url).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); }).then(function (res) {
      if (token !== runToken) return;
      clearTimeout(pollTimer); poll(true);
      setTimeout(function () { if (token !== runToken) return; finishJob(res.ok, res.d, kind); }, 350);
    }).catch(function (err) {
      if (token !== runToken) return; clearTimeout(pollTimer);
      job.finished = true; job.ok = false; job.summary = '無法連線到分析服務(' + err.message + ')。請確認網站已在本機執行。'; $('rc-start').disabled = false; refreshText(); sync();
    });
  }

  function summarize(kind, d) {
    if (d.error) return '失敗:' + d.error;
    if (kind === 'analyze') {
      var m = d.metrics, v = d.validation && d.validation.available ? d.validation.oos : null;
      return '扣成本報酬 ' + m.totalReturn + '% · 淨 PF ' + (m.tradeCount ? m.pf : '—') + ' · 最大回撤 ' + m.maxDD + '% · ' + m.tradeCount + ' 筆' + (v ? ' · 樣本外 ' + v.trades + ' 筆(' + ({ insufficient: '樣本不足', preliminary: '初步觀察', evaluable: '可進一步評估' }[v.tier] || v.tier) + ')' : '');
    }
    var t = (d.results || [])[0];
    return '共測試 ' + d.total_tested + ' 個策略,入選 ' + (d.results || []).length + ' 名' + (t ? ';第 1 名 ' + t.name + '(樣本外 ' + (t.oos ? t.oos.trades : 0) + ' 筆)' : '');
  }
  function finishJob(ok, d, kind) {
    job.finished = true; job.ok = ok; job.summary = summarize(kind, d); $('rc-start').disabled = false;
    $('rc-result').innerHTML = ''; var p = document.createElement('div'); p.textContent = job.summary; $('rc-result').appendChild(p);
    if (d.dataInfo) { var q = document.createElement('div'); q.className = 'sub'; q.textContent = '資料:' + d.dataInfo.bars + ' 根 · 最後已收盤 K 棒 ' + d.dataInfo.lastBarUtc + ' UTC · ' + d.dataInfo.tzLabel; $('rc-result').appendChild(q); }
    refreshText(); sync();
  }

  // ---------------------------------------------------------------- replay of a recorded REAL trace
  var replayTimers = [];
  function startReplay() {
    var key = $('rc-trace').value, tr = (window.RC_TRACES || {})[key]; if (!tr) { setStatusNote('沒有可重播的紀錄'); return; }
    cancelAll(); begin('replay'); var token = runToken, speed = parseFloat($('rc-speed').value) || 1;
    setStatusNote('重播:' + tr.meta.label + '(錄製於 ' + tr.meta.recordedAt + ',後端實測時間,非即時)'); sync();
    tr.events.forEach(function (e) { replayTimers.push(setTimeout(function () { if (token === runToken) { job.lastSeq = e.seq; applyEvent(e); } }, e.t / speed)); });
    replayTimers.push(setTimeout(function () { if (token !== runToken) return; job.finished = true; job.ok = tr.result.ok; job.summary = tr.result.summary; $('rc-result').textContent = tr.result.summary; refreshText(); sync(); }, (tr.events[tr.events.length - 1].t + 450) / speed));
  }
  function reset() { cancelAll(); job = { mode: 'idle', id: null, t0: 0, lastSeq: 0, finished: false, events: 0 }; resetState(); $('rc-log').innerHTML = ''; $('rc-result').innerHTML = ''; setStatusNote(''); $('rc-start').disabled = false; refreshText(); sync(); }

  // ---------------------------------------------------------------- wiring
  function init() {
    var h = '';
    STAGES.forEach(function (s) {
      h += '<div class="rc-card idle" id="rc-card-' + s.id + '"><div class="h"><b>' + s.label + '</b><span class="m">待機</span></div><div class="s">' + s.sub + '</div><div class="d">尚未執行</div><div class="bar"><i></i></div></div>';
    });
    $('rc-cards').innerHTML = h;
    var nodes = '';
    STAGES.forEach(function (s, i) { nodes += '<div class="rc-node idle" id="rc-node-' + s.id + '" role="img"><span class="n">' + (i + 1) + '</span><span class="l">' + s.label + '</span></div>'; });
    $('rc-nodes').innerHTML = nodes;
    var tr = $('rc-trace'); Object.keys(window.RC_TRACES || {}).forEach(function (k) { var o = document.createElement('option'); o.value = k; o.textContent = window.RC_TRACES[k].meta.label; tr.appendChild(o); });
    if (location.protocol === 'file:') { $('rc-base').value = 'http://127.0.0.1:5000'; } else { $('rc-base').value = ''; $('rc-base-wrap').style.display = 'none'; }
    $('rc-start').addEventListener('click', startLive); $('rc-replay').addEventListener('click', startReplay); $('rc-reset').addEventListener('click', reset);
    $('rc-ambient').addEventListener('change', function () { ambientOn = this.checked; sync(); });
    $('rc-kind').addEventListener('change', function () { $('rc-strat-wrap').style.display = this.value === 'analyze' ? '' : 'none'; });
    resize(); refreshText(); sync();
    window.ResearchCoreV2 = { stats: function () { return { loopOn: loopOn, fps: fps, frameCost: frameCost, particles: particles.length, pulses: pulses.length, events: job.events, mode: job.mode, lowPower: lowPower, forced: forced, static: staticMode() }; },
      applyEvent: applyEvent, begin: begin, reset: reset, setAmbient: function (v) { ambientOn = !!v; sync(); }, _forceVisibility: function (hidden) { visible = !hidden; sync(); } };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

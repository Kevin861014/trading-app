/* Research Core 球形網絡畫面(Canvas 2D,自行繪製,不含任何第三方素材,不發出任何網路請求)
 *
 * 效能與誠實原則:
 *   1. 預設是『靜態畫面』:沒有分析時完全沒有動畫迴圈(CPU/GPU 幾乎為 0)。裝飾旋轉預設關閉,可由使用者開啟。
 *   2. 只有真實的後端事件才會讓路線與光點亮起;每個事件最多一顆光點(同屏上限 60,超出只影響取樣,事件不會遺漏)。
 *   3. 工作完成、失敗、取消或中斷後,代表運算中的動畫立即停止(迴圈等光點播完就關閉)。
 *   4. 頁面在背景、畫布不在畫面內、prefers-reduced-motion、手機寬度、使用者關閉動態、單幀成本過高 → 靜態。
 *   5. 事件流動時最高 24 fps;有工作但暫時沒有新事件時降到 12 fps;裝飾旋轉(若開啟)10 fps。
 *   6. 這個檔案沒有任何『模擬事件/示範輪播/重播』的程式碼。
 */
(function (root) {
  'use strict';
  var J = root.RCJob, STAGES = J.STAGES, IDX = J.IDX;
  var COLORS = { idle: [95, 125, 200], running: [79, 209, 255], done: [45, 212, 191], error: [255, 93, 115], skip: [120, 126, 150], stopped: [245, 166, 35] };
  var BLUE = [60, 120, 235], VIOLET = [150, 100, 245], CYAN = [90, 215, 255];
  function mix(a, b, t) { return [Math.round(a[0] + (b[0] - a[0]) * t), Math.round(a[1] + (b[1] - a[1]) * t), Math.round(a[2] + (b[2] - a[2]) * t)]; }
  function store(k, v) { try { if (v === undefined) return root.localStorage.getItem(k); root.localStorage.setItem(k, v); } catch (e) { /* 私密模式等:忽略 */ } return null; }

  // 球體拓樸(固定、一次建立;所有實例共用)
  var N = 180, PTS = [], EDGES = [], DUST = [], RINGS = [];
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
    var seed = 7; function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    for (var m = 0; m < 120; m++) { var t2 = rnd() * 6.283, ph = Math.acos(2 * rnd() - 1), rr = 1.45 + rnd() * 0.75; DUST.push({ x: Math.sin(ph) * Math.cos(t2) * rr, y: Math.sin(ph) * Math.sin(t2) * rr * 0.8, z: Math.cos(ph) * rr, k: rnd() }); }
    for (var q = 0; q < 5; q++) RINGS.push({ tilt: 0.5 + q * 0.55, spin: (q % 2 ? 1 : -1) * (0.05 + q * 0.012), rad: 1.12 + q * 0.07, hue: q / 4 });
  })();

  var SPRITES = null;
  function sprite(rgb, size) {
    var c = document.createElement('canvas'); c.width = c.height = size; var g = c.getContext('2d');
    var gr = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gr.addColorStop(0, 'rgba(255,255,255,0.95)'); gr.addColorStop(0.18, 'rgba(' + rgb.join(',') + ',0.85)');
    gr.addColorStop(0.5, 'rgba(' + rgb.join(',') + ',0.22)'); gr.addColorStop(1, 'rgba(' + rgb.join(',') + ',0)');
    g.fillStyle = gr; g.fillRect(0, 0, size, size); return c;
  }
  function sprites() {
    if (SPRITES) return SPRITES;
    SPRITES = { blue: sprite(BLUE, 32), violet: sprite(VIOLET, 32), cyan: sprite(CYAN, 32), node: {}, part: {} };
    Object.keys(COLORS).forEach(function (k) { SPRITES.node[k] = sprite(COLORS[k], 64); SPRITES.part[k] = sprite(k === 'running' ? CYAN : COLORS[k], 32); });
    return SPRITES;
  }

  function create(host, opts) {
    opts = opts || {};
    var model = opts.model || new J.Model();
    var reduced = root.matchMedia('(prefers-reduced-motion: reduce)'), phone = root.matchMedia('(max-width: 720px)');
    var motionOn = store('rcMotion') !== '0';                     // 事件流動動畫(預設開)
    var ambientOn = store('rcAmbient') === '1';                    // 裝飾旋轉(預設關)
    var saveData = !!(root.navigator && root.navigator.connection && root.navigator.connection.saveData);
    if (saveData) ambientOn = false;
    var visible = !document.hidden, onScreen = true, lowPower = false, forced = false, destroyed = false;
    var summaryText = '';

    // ── DOM ──
    host.classList.add('rc-host');
    host.innerHTML =
      '<div class="rc-box"><canvas class="rc-canvas" aria-hidden="true"></canvas>' +
      '<div class="rc-nodes">' + STAGES.map(function (s, i) {
        var a = (-90 + i * 60) * Math.PI / 180;
        return '<button type="button" class="rc-node idle" data-stage="' + s.id + '" aria-label="' + s.label + ':待機" style="--x:' + (50 + Math.cos(a) * 40) + '%;--y:' + (48 + Math.sin(a) * 40) + '%">' +
          '<span class="n">' + (i + 1) + '</span><span class="l">' + s.label + '</span><span class="s">待機</span></button>';
      }).join('') + '</div>' +
      '<div class="rc-center idle" role="status" aria-live="polite"><div class="k">研究核心</div><div class="t">待機中</div><div class="b"></div></div></div>' +
      '<div class="rc-opts"><label><input type="checkbox" class="rc-o-motion"> 事件流動動畫</label><label class="rc-o-amb"><input type="checkbox" class="rc-o-ambient"> 裝飾旋轉(預設關閉,不代表運算)</label><span class="rc-stats"></span></div>';
    var box = host.querySelector('.rc-box'), canvas = host.querySelector('.rc-canvas'), ctx = canvas.getContext('2d', { alpha: true });
    var centerEl = host.querySelector('.rc-center'), statsEl = host.querySelector('.rc-stats');
    var nodeEls = {}; STAGES.forEach(function (s) { nodeEls[s.id] = host.querySelector('.rc-node[data-stage="' + s.id + '"]'); });
    var cbMotion = host.querySelector('.rc-o-motion'), cbAmb = host.querySelector('.rc-o-ambient');
    cbMotion.checked = motionOn; cbAmb.checked = ambientOn; if (saveData) { cbAmb.disabled = true; }
    var selected = null;

    // ── 視覺狀態 ──
    var vis = {}; STAGES.forEach(function (s) { vis[s.id] = { lastAt: 0 }; });
    var lastFrom = [-1, -1, -1, -1, -1, -1];
    var particles = [], pulses = [], activity = 0;
    var W = 0, H = 0, DPR = 1, CX = 0, CY = 0, R = 0, NODE_POS = [];
    var rotY = 0.6, tNow = 0, lastDraw = 0, frameCost = 0, frames = 0, fpsT = 0, fps = 0;

    function staticMode() { return reduced.matches || phone.matches || !motionOn || forced; }
    function working() { return model.state === 'running'; }

    function resize() {
      var r = canvas.getBoundingClientRect(); if (!r.width || !r.height) return;   // 隱藏中(display:none)不處理;以畫布實際顯示大小為準(手機版畫布比外框矮)
      DPR = Math.min(root.devicePixelRatio || 1, 1.5);
      W = Math.max(240, r.width); H = Math.max(160, r.height);
      canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR); ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      var ph = phone.matches;
      CX = W / 2; CY = ph ? H / 2 : H / 2 - H * 0.02; R = ph ? Math.min(W * 0.32, H * 0.38) : Math.min(W * 0.2, H * 0.3);
      NODE_POS = STAGES.map(function (s, i) { var a = (-90 + i * 60) * Math.PI / 180; return { x: CX + Math.cos(a) * W * 0.40, y: CY + Math.sin(a) * H * 0.40 }; });
      stillNow();
    }

    // ── 路線 ──
    function prevPerformed(i) { for (var j = i - 1; j >= 0; j--) { var st = model.stages[STAGES[j].id].status; if (st === 'done' || st === 'running' || st === 'error') return j; } return -1; }
    function routePoint(i, u, from) {
      if (from === undefined) from = i - 1;
      var p0 = from < 0 ? { x: CX, y: CY } : NODE_POS[from], p1 = NODE_POS[i];
      var mx = (p0.x + p1.x) / 2, my = (p0.y + p1.y) / 2, dx = mx - CX, dy = my - CY, L = Math.hypot(dx, dy) || 1, bow = from < 0 ? 0 : 0.18;
      var cx = mx + dx / L * W * bow * 0.4, cy = my + dy / L * H * bow * 0.4, a = (1 - u) * (1 - u), b = 2 * (1 - u) * u, c = u * u;
      return { x: a * p0.x + b * cx + c * p1.x, y: a * p0.y + b * cy + c * p1.y };
    }

    // ── 繪製 ──
    function draw(ts, still) {
      if (!W) return;
      var t0 = root.performance.now(), SP = sprites();
      var dt = still ? 0 : Math.min(0.1, (ts - lastDraw) / 1000); lastDraw = ts;
      activity = Math.max(0, activity - dt * 0.9);
      var act = Math.min(1, activity);
      if (ambientOn || act > 0.02) tNow += dt;
      rotY += dt * ((ambientOn ? 0.05 : 0) + act * 0.12);
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter';
      var cosY = Math.cos(rotY), sinY = Math.sin(rotY), tilt = 0.42, cosX = Math.cos(tilt), sinX = Math.sin(tilt), f = 3.2, P = new Array(N), i;
      for (i = 0; i < N; i++) {
        var p = PTS[i], w = 1 + 0.07 * Math.sin(tNow * 0.45 + p.ph) + 0.04 * Math.sin(tNow * 0.27 + p.ph * 2.0);
        var x = p.x * w, y = p.y * w, z = p.z * w, x1 = x * cosY + z * sinY, z1 = -x * sinY + z * cosY, y2 = y * cosX - z1 * sinX, z2 = y * sinX + z1 * cosX, s = f / (f - z2);
        P[i] = { x: CX + x1 * R * s, y: CY + y2 * R * s, z: z2, s: s };
      }
      for (var hue = 0; hue < 2; hue++) for (var band = 0; band < 3; band++) {
        ctx.beginPath();
        for (var e = 0; e < EDGES.length; e++) {
          if ((e & 1) !== hue) continue;
          var A = P[EDGES[e][0]], B = P[EDGES[e][1]], zz = (A.z + B.z) / 2, bd = zz > 0.35 ? 2 : (zz > -0.3 ? 1 : 0);
          if (bd !== band) continue; ctx.moveTo(A.x, A.y); ctx.lineTo(B.x, B.y);
        }
        var col = hue ? VIOLET : BLUE, al = [0.10, 0.20, 0.38][band] * (1 + act * 0.9);
        ctx.strokeStyle = 'rgba(' + col.join(',') + ',' + Math.min(0.9, al) + ')'; ctx.lineWidth = band === 2 ? 1.1 : 0.7; ctx.stroke();
      }
      if (!phone.matches) {                                               // 手機簡化:不畫裝飾環與塵點
        for (var r = 0; r < RINGS.length; r++) {
          var rg = RINGS[r], ang0 = tNow * rg.spin, ct = Math.cos(rg.tilt), st = Math.sin(rg.tilt);
          ctx.beginPath();
          for (var k = 0; k <= 60; k++) {
            var a = k / 60 * Math.PI * 2 + ang0, rx = Math.cos(a) * rg.rad, rz = Math.sin(a) * rg.rad, yy = -rz * st, zz2 = rz * ct;
            var xx = rx * cosY + zz2 * sinY, zr = -rx * sinY + zz2 * cosY, y3 = yy * cosX - zr * sinX, z3 = yy * sinX + zr * cosX, sc = f / (f - z3);
            var px = CX + xx * R * sc, py = CY + y3 * R * sc; if (k) ctx.lineTo(px, py); else ctx.moveTo(px, py);
          }
          var cc = mix(BLUE, VIOLET, rg.hue); ctx.strokeStyle = 'rgba(' + cc.join(',') + ',' + (0.13 + act * 0.1) + ')'; ctx.lineWidth = 0.8; ctx.stroke();
        }
        for (var di = 0; di < DUST.length; di++) {
          var dp = DUST[di], dx0 = dp.x * cosY + dp.z * sinY, dz0 = -dp.x * sinY + dp.z * cosY, dy0 = dp.y * cosX - dz0 * sinX, dz1 = dp.y * sinX + dz0 * cosX, ds = f / (f - dz1);
          var dpx = CX + dx0 * R * ds, dpy = CY + dy0 * R * ds, dsz = 3 + 4 * ds;
          ctx.globalAlpha = (0.12 + 0.3 * dp.k) * (0.6 + 0.4 * Math.sin(tNow * 0.6 + di)); ctx.drawImage(dp.k > 0.5 ? SP.cyan : SP.blue, dpx - dsz / 2, dpy - dsz / 2, dsz, dsz);
        }
      }
      ctx.globalAlpha = 1;
      for (var j = 0; j < N; j++) {
        var q = P[j], dep = (q.z + 1.2) / 2.4, sz = (5 + 9 * dep) * q.s * (0.8 + act * 0.25);
        ctx.globalAlpha = 0.25 + 0.75 * dep; ctx.drawImage(PTS[j].hue > 0.5 ? SP.violet : (PTS[j].hue > 0.15 ? SP.blue : SP.cyan), q.x - sz / 2, q.y - sz / 2, sz, sz);
      }
      ctx.globalAlpha = 1;
      var cs = R * (0.55 + act * 0.25); ctx.globalAlpha = 0.5 + act * 0.4; ctx.drawImage(SP.violet, CX - cs, CY - cs, cs * 2, cs * 2); ctx.globalAlpha = 1;

      if (!phone.matches) {                                               // 路線與節點(手機改由下方按鈕格呈現,資訊不減少)
        var now = root.performance.now();
        for (var n = 0; n < STAGES.length; n++) {
          var s2 = model.stages[STAGES[n].id], col2 = COLORS[s2.status] || COLORS.idle;
          var recent = still ? 0 : Math.max(0, 1 - (now - vis[STAGES[n].id].lastAt) / 900);       // 只在真實事件後約 0.9 秒內發亮
          var base = s2.status === 'idle' ? 0.10 : (s2.status === 'skip' ? 0.07 : 0.22);
          ctx.beginPath(); for (var u = 0; u <= 20; u++) { var rp = routePoint(n, u / 20); if (u) ctx.lineTo(rp.x, rp.y); else ctx.moveTo(rp.x, rp.y); }
          ctx.strokeStyle = 'rgba(' + col2.join(',') + ',' + (base * 0.8) + ')'; ctx.lineWidth = 1; if (s2.status === 'skip') ctx.setLineDash([4, 6]); ctx.stroke(); ctx.setLineDash([]);
          if (recent > 0.02) {
            ctx.beginPath(); for (var u2 = 0; u2 <= 20; u2++) { var rq = routePoint(n, u2 / 20, lastFrom[n]); if (u2) ctx.lineTo(rq.x, rq.y); else ctx.moveTo(rq.x, rq.y); }
            ctx.strokeStyle = 'rgba(' + col2.join(',') + ',' + (recent * 0.85) + ')'; ctx.lineWidth = 1 + recent * 2.2; ctx.stroke();
          }
          var pulse = (s2.status === 'running' && !still && working()) ? 12 * (0.5 + 0.5 * Math.sin(now / 280)) : 0;      // 只有『工作確實在進行中』才脈動
          var ns = 46 + pulse + recent * 10;
          ctx.globalAlpha = s2.status === 'idle' ? 0.45 : 0.95; ctx.drawImage(SP.node[s2.status] || SP.node.idle, NODE_POS[n].x - ns / 2, NODE_POS[n].y - ns / 2, ns, ns); ctx.globalAlpha = 1;
        }
        for (var pi = pulses.length - 1; pi >= 0; pi--) {
          var pu = pulses[pi], age = (now - pu.t) / 900; if (age >= 1) { pulses.splice(pi, 1); continue; }
          ctx.beginPath(); ctx.arc(NODE_POS[pu.i].x, NODE_POS[pu.i].y, 22 + age * 46, 0, 6.283);
          ctx.strokeStyle = 'rgba(' + pu.c.join(',') + ',' + (0.7 * (1 - age)) + ')'; ctx.lineWidth = 2; ctx.stroke();
        }
        for (var qi = particles.length - 1; qi >= 0; qi--) {
          var pt = particles[qi]; pt.u += dt / pt.dur;
          if (pt.u >= 1) { particles.splice(qi, 1); continue; }
          for (var tr = 0; tr < 3; tr++) {
            var uu = Math.max(0, pt.u - tr * 0.05), pp = routePoint(pt.i, uu, pt.from), ps = 16 - tr * 4;
            ctx.globalAlpha = 1 - tr * 0.3; ctx.drawImage(pt.sp, pp.x - ps / 2, pp.y - ps / 2, ps, ps);
          }
        }
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
      frameCost = frameCost * 0.9 + (root.performance.now() - t0) * 0.1;
      frames++; if (ts - fpsT > 1000) { fps = Math.round(frames * 1000 / Math.max(1, ts - fpsT)); frames = 0; fpsT = ts; if (loopOn) setStats(); }
    }
    function setStats() { statsEl.textContent = (loopOn ? 'fps ' + fps + ' · 繪製 ' + frameCost.toFixed(1) + ' ms/幀 · 光點 ' + particles.length : '靜態畫面(無動畫迴圈)') + ' · 事件 ' + model.eventCount; }

    // ── 繪製迴圈:只在需要時存在 ──
    var loopOn = false, raf = 0, lastFrame = 0, stillTimer = 0;
    function eventsFlowing() { return particles.length > 0 || pulses.length > 0 || activity > 0.05; }
    function wantLoop() { if (destroyed || staticMode() || !visible || !onScreen) return false; return working() || eventsFlowing() || ambientOn; }
    function targetFps() {
      if (eventsFlowing()) return lowPower ? 16 : 24;
      if (working()) return lowPower ? 8 : 12;
      return lowPower ? 6 : 10;
    }
    function tick(ts) {
      raf = 0; if (!loopOn) return;
      if (ts - lastFrame >= 1000 / targetFps() - 1) {
        lastFrame = ts; draw(ts, false);
        if (frameCost > 14 && !lowPower) lowPower = true;                     // 單幀成本偏高 → 降低幀率
        if (frameCost > 26) { forced = true; stopLoop(); stillNow(); setNote('畫面負擔過高,已自動改為靜態'); return; }
      }
      if (!wantLoop()) { stopLoop(); stillNow(); return; }
      raf = root.requestAnimationFrame(tick);
    }
    function startLoop() { if (loopOn) return; loopOn = true; lastFrame = 0; lastDraw = root.performance.now(); raf = root.requestAnimationFrame(tick); }
    function stopLoop() { loopOn = false; if (raf) root.cancelAnimationFrame(raf); raf = 0; setStats(); }
    function stillNow() { clearTimeout(stillTimer); stillTimer = 0; if (!destroyed && W) draw(root.performance.now(), true); setStats(); }
    // 靜態模式下的重畫:手機的畫布只有球體(狀態由下方按鈕格呈現),事件不需要重畫;桌面靜態(減少動態/關閉動畫)最多每 400ms 重畫一次
    function scheduleStill() { if (stillTimer || loopOn || phone.matches) return; stillTimer = setTimeout(function () { stillTimer = 0; if (!loopOn) stillNow(); }, 400); }
    function sync() { if (wantLoop()) startLoop(); else { if (loopOn) stopLoop(); scheduleStill(); } }
    function setNote(t) { host.dispatchEvent(new CustomEvent('rc-note', { detail: t })); }

    var onVis = function () { visible = !document.hidden; sync(); };
    document.addEventListener('visibilitychange', onVis);
    var io = null; if ('IntersectionObserver' in root) { io = new root.IntersectionObserver(function (en) { onScreen = en[en.length - 1].isIntersecting; if (onScreen && !W) resize(); sync(); }); io.observe(box); }
    var ro = null; if ('ResizeObserver' in root) { var rq2 = 0; ro = new root.ResizeObserver(function () { if (rq2) return; rq2 = root.requestAnimationFrame(function () { rq2 = 0; resize(); sync(); }); }); ro.observe(box); }
    else root.addEventListener('resize', function () { resize(); sync(); });
    var onMq = function () { resize(); sync(); }; [reduced, phone].forEach(function (m) { if (m.addEventListener) m.addEventListener('change', onMq); else m.addListener(onMq); });

    // ── 真實事件 → 視覺 ──
    function addParticle(i, kind, dur) {
      lastFrom[i] = prevPerformed(i);
      if (staticMode() || !onScreen || !visible) return;                  // 看不到/靜態時不累積光點
      if (particles.length > 60) particles.shift();
      particles.push({ i: i, u: 0, dur: dur, sp: sprites().part[kind] || sprites().part.running, from: lastFrom[i] });
    }
    function event(e) {                                                   // 呼叫前,事件必須已經 model.apply(e)
      var i = IDX[e.stage]; if (i == null) return;
      var now = root.performance.now(); vis[e.stage].lastAt = now;
      activity = Math.min(2, activity + (e.status === 'progress' ? 0.12 : 0.5));
      if (e.status === 'start') { pulses.push({ i: i, t: now, c: COLORS.running }); addParticle(i, 'running', 0.9); }
      else if (e.status === 'progress') addParticle(i, 'running', 0.7);
      else if (e.status === 'done') { pulses.push({ i: i, t: now, c: COLORS.done }); addParticle(i, 'done', 0.9); }
      else if (e.status === 'skip') addParticle(i, 'skip', 0.6);
      else if (e.status === 'error') { pulses.push({ i: i, t: now, c: COLORS.error }); addParticle(i, 'error', 1.0); }
      refresh(); sync();
    }
    function end(kind, summary) {                                         // kind: ok | error | cancelled | stopped
      model.end(kind); summaryText = summary || '';
      // 工作已結束:代表運算中的動畫立即停止。完成/失敗時,最後一個事件的光點與光環(<1 秒)讓它播完;取消/中斷則全部清掉。迴圈隨後關閉。
      activity = 0;
      if (kind === 'cancelled' || kind === 'stopped') { particles.length = 0; pulses.length = 0; }
      refresh(); sync();
    }
    function begin() { model.begin(); particles.length = 0; pulses.length = 0; activity = 0; lastFrom = [-1, -1, -1, -1, -1, -1]; summaryText = ''; refresh(); sync(); }
    function reset() { model.reset(); particles.length = 0; pulses.length = 0; activity = 0; summaryText = ''; refresh(); sync(); }

    function refresh() {
      STAGES.forEach(function (s) {
        var st = model.stages[s.id], el = nodeEls[s.id], sub = el.querySelector('.s');
        el.className = 'rc-node ' + st.status + (selected === s.id ? ' sel' : '');
        var txt = st.status === 'running' && st.prog && st.prog.n ? st.prog.i + '/' + st.prog.n : (st.status === 'done' && st.ms != null ? J.fmtMs(st.ms) : J.STATUS_LABEL[st.status]);
        sub.textContent = txt; el.setAttribute('aria-label', s.label + ':' + txt + ' — 點擊查看這個階段的結果'); el.setAttribute('aria-pressed', selected === s.id ? 'true' : 'false');
      });
      var title, body, cls;
      var run = model.running(), err = model.errored();
      if (model.state === 'idle') { title = '待機中'; body = '尚未開始分析。球體預設為靜態畫面;只有真實的分析事件才會讓路線與光點亮起。'; cls = 'idle'; }
      else if (err.length) { title = '失敗:' + err[0].label; body = model.stages[err[0].id].detail; cls = 'error'; }
      else if (model.state === 'cancelled') { title = '已取消'; body = '分析已停止,沒有產生結果。'; cls = 'stopped'; }
      else if (model.state === 'stopped') { title = '已中斷'; body = summaryText || '連線中斷,沒有收到完整結果。'; cls = 'stopped'; }
      else if (model.state === 'ok') { title = '完成'; body = summaryText; cls = 'done'; }
      else if (run.length) { var cur = run[run.length - 1], cs = model.stages[cur.id]; title = cur.label + '…'; body = cs.prog && cs.prog.n ? (cs.prog.i + ' / ' + cs.prog.n) : '處理中'; cls = 'running'; }
      else { title = '等待下一個真實事件'; body = ''; cls = 'running'; }
      centerEl.className = 'rc-center ' + cls; centerEl.querySelector('.t').textContent = title; centerEl.querySelector('.b').textContent = body;
    }
    function select(id) { selected = id; refresh(); }

    STAGES.forEach(function (s) { nodeEls[s.id].addEventListener('click', function () { select(s.id); if (opts.onNodeClick) opts.onNodeClick(s.id); }); });
    cbMotion.addEventListener('change', function () { motionOn = cbMotion.checked; store('rcMotion', motionOn ? '1' : '0'); if (!motionOn) { particles.length = 0; pulses.length = 0; } sync(); });
    cbAmb.addEventListener('change', function () { ambientOn = cbAmb.checked; store('rcAmbient', ambientOn ? '1' : '0'); sync(); });

    resize(); refresh(); setStats(); sync();
    return {
      model: model, begin: begin, event: event, end: end, reset: reset, select: select, resize: function () { resize(); sync(); },
      setAmbient: function (v) { ambientOn = !!v; cbAmb.checked = ambientOn; sync(); }, setMotion: function (v) { motionOn = !!v; cbMotion.checked = motionOn; sync(); },
      stats: function () { return { loopOn: loopOn, fps: fps, frameCost: frameCost, particles: particles.length, pulses: pulses.length, events: model.eventCount, state: model.state, lowPower: lowPower, forced: forced, static: staticMode(), ambient: ambientOn, motion: motionOn }; },
      _forceVisibility: function (hidden) { visible = !hidden; sync(); },
      destroy: function () { destroyed = true; stopLoop(); document.removeEventListener('visibilitychange', onVis); if (io) io.disconnect(); if (ro) ro.disconnect(); }
    };
  }

  root.RCEngine = { create: create, COLORS: COLORS };
})(typeof window !== 'undefined' ? window : this);

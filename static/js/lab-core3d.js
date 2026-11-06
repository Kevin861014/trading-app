/* 策略實驗室 3D 研究核心(原型 v2):電漿球體 + 四圈傾斜的粒子軌道環
 *
 * 視覺語彙(電漿球體的 shader 與弧光、藍紫青粒子配色、Bloom 參數、傾斜軌道環與流動光點的概念)改寫自開源專案
 *   JEV Trading Command Center  https://github.com/mars-tw/jev-trading-command-center  (檔案 web/three-viz.js 的 makePlasma / makeRing)
 *   以及 web/core-effects.js 的 createCinematicCore(軌道環)
 *   MIT License — Copyright (c) 2026 mars-tw and contributors(授權全文與修改說明見本專案根目錄 THIRD_PARTY_NOTICES.md)
 * 渲染函式庫 Three.js 0.186.1(MIT,Copyright © 2010-2026 three.js authors)自行託管於 static/vendor/three/(含 LICENSE 與 PROVENANCE.json,檔案雜湊與官方發佈一致)。
 *
 * 這個檔案『沒有』使用原專案的:AI 角色/寵物(LineWorkers)、決策圖(decision-graph)、window.LIVE、模型投票、風險決策、持倉、下單動畫。
 * 它只是一個純視覺元件,所有狀態都由外部餵入(來自本站真實的研究事件)。
 *
 * v2 設計(依使用者回饋重做):
 *   - 四圈細軌道環,半徑均勻、傾斜角度各不同,對應研究流程的四個階段(由內到外):行情資料 / 策略回測 / 樣本外驗證 / 排名結果。
 *     沒有其他裝飾線條(舊版的螺旋線、光帶、弧線管、光塵全部移除,避免線條擠成一團)。沒有懸浮的單點錨點。
 *   - 每圈環上有 3 條『流星』(亮頭、漸淡的尾巴)沿著環跑;環整個旋轉,所以看得到東西在環上流動。流星的顏色 = 該階段的真實狀態。
 *   - 小人:分析中以固定速度沿著環連續地跑,每跑完『完整的一圈』就沿弧線(固定 0.6 秒,有起跳與落地光圈)跳到另一圈隨機的環;停下的位置會保留、下一次分析從那裡接著跑;他的位置不綁進度(進度看泡泡與進度條);分析中整個畫面不自轉,他才站得穩;
 *   - 每一個真實的後端事件 = 一顆光點,從小人所在的位置發出(不會往球心聚集):
 *       策略回測 通過篩選 → 青綠,飛到最外圈累積成一顆亮點(下一次分析開始時清除);未通過篩選 → 玫紅,往外散掉熄滅;無結果/錯誤 → 琥珀/紅,往外飛散。
 *       行情資料 / 樣本外驗證 的進度事件 → 沿環往前噴出的一小段青/紫色火花。
 *   - 最外圈的細弧是進度弧(只用後端真實的 i/n),弧前端有一顆亮點。
 * 效能原則與 rc-engine.js 相同:沒有分析時不跑動畫迴圈(畫一張靜態畫面);頁面在背景、不在視窗內、減少動態偏好、單幀成本過高 → 停止迴圈。
 * 沒有任何『示範輪播/模擬事件』。
 */
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

const PLASMA_VERT = `
varying vec3 vPos; varying vec3 vNor;
void main(){ vPos=position; vNor=normalize(normalMatrix*normal);
  gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`;
const PLASMA_FRAG = `
uniform float uTime; uniform vec3 uColor; uniform float uIntensity;
varying vec3 vPos; varying vec3 vNor;
void main(){
  float n = sin(vPos.x*6.0+uTime)*0.34 + sin(vPos.y*8.0-uTime*1.3)*0.28
          + sin((vPos.z+vPos.x)*10.0+uTime*0.7)*0.22 + sin(length(vPos)*14.0-uTime*1.8)*0.16;
  n = n*0.5+0.5;
  float filaments = smoothstep(0.52, 0.95, n);
  vec3 viewDir = vec3(0.0,0.0,1.0);
  float fres = pow(1.0 - abs(dot(viewDir, normalize(vNor))), 2.0);
  vec3 col = uColor * (0.25 + filaments*1.6*uIntensity) + vec3(1.0)*filaments*0.35;
  col += uColor * fres * 1.2;
  gl_FragColor = vec4(col, 0.92);
}`;

const STATE_COLOR = { idle: 0x5f7dc8, running: 0x37e0ff, done: 0x2dd4bf, error: 0xff5d73, stopped: 0xf5a623 };
const STATE_POWER = { idle: 0.22, running: 0.75, done: 0.4, error: 0.5, stopped: 0.3 };
const STATE_INTENSITY = { idle: 0.55, running: 1.0, done: 0.7, error: 0.85, stopped: 0.6 };
const STAGE_COLOR = { idle: 0x5f7dc8, running: 0x37e0ff, done: 0x2dd4bf, error: 0xff5d73, skip: 0x6b7390, stopped: 0xf5a623 };
const STAGE_LINE = { idle: 0.2, running: 0.6, done: 0.42, error: 0.55, skip: 0.1, stopped: 0.3 };
const ANCHOR_IDS = ['data', 'backtest', 'validation', 'result'];             // 與球體下方流程列的四個節點一一對應(由內到外)
const RING_R = [1.75, 2.4, 3.05, 3.7];                                       // 半徑均勻遞增
const RING_TILT = [[0.18, 0.0], [-0.5, 0.22], [0.5, -0.22], [-0.24, -0.38]]; // 每圈的傾斜(x, z),各不同,避免全部疊在同一個平面
const RING_DIR = [1, -1, 1, -1];                                              // 相鄰的環反向旋轉
const PROG_R = 4.0;

export function webglAvailable() {
  try { const c = document.createElement('canvas'); const gl = c.getContext('webgl2') || c.getContext('webgl'); return !!gl; } catch (e) { return false; }
}

export function createCore3D(host, opts) {
  opts = opts || {};
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const canvas = document.createElement('canvas'); canvas.className = 'lab3d-canvas'; canvas.setAttribute('aria-hidden', 'true');
  host.appendChild(canvas);
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' }); }
  catch (e) { canvas.remove(); return null; }
  const w0 = host.clientWidth || 600;
  const budget = reduced.matches ? { dust: 120, streak: 12 } : (w0 <= 420 ? { dust: 380, streak: 40 } : { dust: 720, streak: 76 });   // 每圈的粒子數
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(46, 1.4, 0.1, 100);
  const world = new THREE.Group(); world.rotation.x = 0.34; scene.add(world);
  const addMat = m => { m.depthWrite = false; m.blending = THREE.AdditiveBlending; m.transparent = true; return m; };

  // 柔光貼圖(徑向漸層),避免方形點
  const spriteTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'); const g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.35, 'rgba(255,255,255,.6)'); g.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = g; x.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); })();

  // 偽亂數(固定種子:每次重新整理畫面一致,也避免兩個粒子雲長得一模一樣)
  const rnd = (() => { let s = 20261106; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; })();
  const tri = () => rnd() + rnd() - 1;                                          // -1..1,集中在 0 附近

  // ── 四圈軌道環:細線 + 帶疏密的粒子帶 + 3 條流星 ──
  const cBlue = new THREE.Color(0x1657ad), cPurp = new THREE.Color(0x6965bb), cCyan = new THREE.Color(0x75deef), cWhite = new THREE.Color(0xe8f6ff), tmp = new THREE.Color();
  const rings = ANCHOR_IDS.map((id, ri) => {
    const Rr = RING_R[ri], dir = RING_DIR[ri];
    const tilt = new THREE.Group(); tilt.rotation.set(RING_TILT[ri][0], 0, RING_TILT[ri][1]); world.add(tilt);
    const spin = new THREE.Group(); spin.rotation.y = ri * 1.3; tilt.add(spin);                // 整圈繞自己的法線旋轉 → 環上的東西會流動
    // 細線
    const lp = []; for (let i = 0; i < 160; i++) { const a = i / 160 * Math.PI * 2; lp.push(new THREE.Vector3(Math.cos(a) * Rr, 0, Math.sin(a) * Rr)); }
    const line = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(lp), addMat(new THREE.LineBasicMaterial({ color: STAGE_COLOR.idle, opacity: STAGE_LINE.idle })));
    spin.add(line);
    // 粒子帶:沿環分布,有疏密(密的地方成團,轉起來就看得到流動),整體很窄
    const n = budget.dust, pos = new Float32Array(n * 3), col = new Float32Array(n * 3), ph = ri * 1.7;
    for (let i = 0, got = 0; got < n && i < n * 20; i++) {
      const a = rnd() * Math.PI * 2, dens = 0.15 + 0.85 * Math.pow(0.5 + 0.5 * Math.sin(2 * a + ph), 2) * (0.6 + 0.4 * Math.sin(5 * a + ph * 2));
      if (rnd() > dens) continue;
      const r = Rr + tri() * 0.2, y = tri() * 0.12 + 0.1 * Math.sin(3 * a + ph);
      pos[got * 3] = Math.cos(a) * r; pos[got * 3 + 1] = y; pos[got * 3 + 2] = Math.sin(a) * r;
      const f = 0.5 + 0.5 * Math.sin(a * 2 + ri); tmp.copy(cBlue).lerp(cPurp, f).lerp(cCyan, rnd() * 0.35); if (rnd() < 0.04) tmp.copy(cWhite);
      col[got * 3] = tmp.r; col[got * 3 + 1] = tmp.g; col[got * 3 + 2] = tmp.b; got++;
    }
    const dg = new THREE.BufferGeometry(); dg.setAttribute('position', new THREE.BufferAttribute(pos, 3)); dg.setAttribute('color', new THREE.BufferAttribute(col, 3));
    const dustMat = addMat(new THREE.PointsMaterial({ size: 0.045, map: spriteTex, vertexColors: true, opacity: 0.78, sizeAttenuation: true }));
    const dust = new THREE.Points(dg, dustMat); spin.add(dust);
    // 流星:3 條,亮頭在前、尾巴漸淡(顏色 = 該階段的真實狀態)
    const m = budget.streak * 3, sp = new Float32Array(m * 3), sc = new Float32Array(m * 3), L = 0.5 + 1.5 / Rr * 0.9;
    for (let k = 0; k < 3; k++) {
      const head = k / 3 * Math.PI * 2 + ri * 0.7;
      for (let j = 0; j < budget.streak; j++) {
        const s = Math.pow(rnd(), 1.6), a = head + dir * L * s, r = Rr + tri() * 0.045, i = k * budget.streak + j, b = Math.pow(1 - s, 1.3);
        sp[i * 3] = Math.cos(a) * r; sp[i * 3 + 1] = tri() * 0.03; sp[i * 3 + 2] = Math.sin(a) * r; sc[i * 3] = sc[i * 3 + 1] = sc[i * 3 + 2] = 0.25 + 0.75 * b;
      }
    }
    const sg = new THREE.BufferGeometry(); sg.setAttribute('position', new THREE.BufferAttribute(sp, 3)); sg.setAttribute('color', new THREE.BufferAttribute(sc, 3));
    const streakMat = addMat(new THREE.PointsMaterial({ size: 0.085, map: spriteTex, vertexColors: true, color: STAGE_COLOR.idle, opacity: 0.0, sizeAttenuation: true }));
    const streaks = new THREE.Points(sg, streakMat); spin.add(streaks);
    return { id, Rr, dir, tilt, spin, line, dust, dustMat, streakMat, flash: 0, status: 'idle', n };
  });
  const ringIdx = {}; ANCHOR_IDS.forEach((id, i) => { ringIdx[id] = i; });
  const centerGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: spriteTex, color: 0x6a5cff, transparent: true, opacity: 0.30, blending: THREE.AdditiveBlending, depthWrite: false }));
  centerGlow.scale.set(4.4, 4.4, 1); world.add(centerGlow);

  // ── 電漿球體(中心)──
  const sphereGroup = new THREE.Group(); world.add(sphereGroup);
  const mat = new THREE.ShaderMaterial({ uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(STATE_COLOR.idle) }, uIntensity: { value: 0.55 } }, vertexShader: PLASMA_VERT, fragmentShader: PLASMA_FRAG, transparent: true });
  sphereGroup.add(new THREE.Mesh(new THREE.SphereGeometry(1.05, 48, 48), mat));
  const coreMesh = new THREE.Mesh(new THREE.SphereGeometry(0.22, 24, 24), new THREE.MeshBasicMaterial({ color: STATE_COLOR.idle })); sphereGroup.add(coreMesh);
  sphereGroup.add(new THREE.Mesh(new THREE.SphereGeometry(1.18, 48, 48), new THREE.MeshPhysicalMaterial({ color: 0x88ccff, transparent: true, opacity: 0.10, roughness: 0.1, metalness: 0 })));
  const arcMat = new THREE.LineBasicMaterial({ color: 0xbfefff, transparent: true, opacity: 0.9 }), arcs = [];
  for (let i = 0; i < 11; i++) { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(8 * 3), 3)); const line = new THREE.Line(g, arcMat); sphereGroup.add(line); arcs.push(line); }
  const coreRings = [];
  for (let i = 0; i < 2; i++) { const ring = new THREE.Mesh(new THREE.TorusGeometry(1.26 + i * 0.13, 0.012, 8, 90), new THREE.MeshBasicMaterial({ color: i ? 0x8b5cff : 0x37e0ff, transparent: true, opacity: 0.75 })); ring.rotation.x = Math.PI / 2.4 + i * 0.5; sphereGroup.add(ring); coreRings.push(ring); }
  function regenArcs() {
    for (const line of arcs) {
      const a = Math.random() * Math.PI * 2, b = Math.acos(2 * Math.random() - 1), end = new THREE.Vector3(Math.sin(b) * Math.cos(a), Math.cos(b), Math.sin(b) * Math.sin(a)).multiplyScalar(1.12), pos = line.geometry.attributes.position;
      for (let s = 0; s < 8; s++) { const t = s / 7, p = end.clone().multiplyScalar(t); if (s > 0 && s < 7) { p.x += (Math.random() - .5) * .16; p.y += (Math.random() - .5) * .16; p.z += (Math.random() - .5) * .16; } pos.setXYZ(s, p.x, p.y, p.z); }
      pos.needsUpdate = true;
    }
  }
  regenArcs();

  // ── 進度弧:最外圈,只用後端真實的 i/n ──
  const PROG_N = 160, progPts = []; for (let i = 0; i <= PROG_N; i++) { const u = Math.PI * 2 * (i / PROG_N) - Math.PI / 2; progPts.push(new THREE.Vector3(Math.cos(u) * PROG_R, 0, Math.sin(u) * PROG_R)); }
  const progGeo = new THREE.BufferGeometry().setFromPoints(progPts), progMat = addMat(new THREE.LineBasicMaterial({ color: STATE_COLOR.running, opacity: 0.95 }));
  const progLine = new THREE.Line(progGeo, progMat); progLine.visible = false; world.add(progLine);

  // ── 資料封包:每一個真實的後端事件 = 一顆光點(全部來自真實事件,沒有任何模擬) ──
  const packets = [], pending = [], packetPool = [], shocks = [], shockPool = [];
  let coreFlash = 0, rate = 0, progFrac = null;
  const PKT_COLOR = { kept: 0x2dd4bf, filtered: 0xff6f91, no_result: 0xffb020, error: 0xff3b5c, data: 0x37e0ff, validation: 0xb69bff, result: 0x2dd4bf };
  const mkSprite = () => new THREE.Sprite(new THREE.SpriteMaterial({ map: spriteTex, color: 0x37e0ff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
  const tv = new THREE.Vector3();
  function ringPoint(r, ang, lift) {                                             // 該圈環上某個角度的位置(含目前的旋轉與傾斜),換算成 world 座標
    r.spin.updateMatrix(); r.tilt.updateMatrix();
    return tv.set(Math.cos(ang) * r.Rr, lift, Math.sin(ang) * r.Rr).applyMatrix4(r.spin.matrix).applyMatrix4(r.tilt.matrix).clone();
  }
  function ringStatic(r, ang, lift) {                                            // 該圈環上某角度的位置(只含傾斜,不含旋轉;小人與累積的亮點都在這個不轉的座標上)
    r.tilt.updateMatrix(); return tv.set(Math.cos(ang) * r.Rr, lift, Math.sin(ang) * r.Rr).applyMatrix4(r.tilt.matrix).clone();
  }
  const beads = [], beadPool = [];                                                // 通過篩選的策略:累積在最外圈(排名結果的環)的亮點,下一次分析開始時清除
  function clearBeads() { while (beads.length) { const b = beads.pop(); b.visible = false; world.remove(b); beadPool.push(b); } }
  function addBead(pos) {
    if (beads.length >= 160) return; const b = beadPool.pop() || mkSprite(); b.material.color.set(PKT_COLOR.kept); b.material.opacity = 0.9; b.scale.setScalar(0.2); b.position.copy(pos); b.visible = true; world.add(b); beads.push(b);
  }
  function spawnPacket(ev) {
    const i = ringIdx[ev.stage]; if (i == null || packets.length >= 64) return;
    const start = runner.on ? runnerSp.position.clone().add(new THREE.Vector3(0, 0.35, 0)) : ringStatic(rings[i], Math.random() * Math.PI * 2, 0.12);       // 光點從『小人所在的位置』發出
    let kind = 'spark', col = PKT_COLOR[ev.stage] || PKT_COLOR.data, size = 0.34, dur = 0.7, end;
    if (ev.stage === 'backtest') {
      size = 0.26; dur = 0.8;
      if (ev.outcome === 'kept') { kind = 'collect'; col = PKT_COLOR.kept; dur = 1.0; end = ringStatic(rings[3], -Math.PI / 2 + beads.length * 2.399, tri() * 0.08); }   // 通過 → 飛到最外圈累積起來
      else if (ev.outcome === 'filtered') { kind = 'fizzle'; col = PKT_COLOR.filtered; end = start.clone().multiplyScalar(1.06).add(new THREE.Vector3(0, 0.7, 0)); }                                          // 淘汰 → 往外散掉熄滅
      else if (ev.outcome === 'no_result' || ev.outcome === 'error') { kind = 'out'; col = PKT_COLOR[ev.outcome]; end = start.clone().multiplyScalar(1.1).add(new THREE.Vector3(0, 1.1, 0)); }               // 無結果/錯誤 → 往外飛散
      else col = PKT_COLOR.data;
    }
    if (!end) end = runner.on ? runner.ahead.clone().add(new THREE.Vector3(0, 0.35, 0)) : start.clone().multiplyScalar(1.1);                          // 行情資料/樣本外驗證的進度:沿環往前噴出一小段火花
    const sp = []; for (let k = 0; k < 4; k++) { const x = packetPool.pop() || mkSprite(); x.material.color.set(col); x.visible = true; world.add(x); sp.push(x); }
    packets.push({ sp, t: 0, dur, a: start, b: end, kind, size, lift: kind === 'collect' ? 0.35 + Math.random() * 0.3 : (Math.random() - 0.5) * 0.5, big: ev.stage !== 'backtest' });
  }
  function spawnShock(color, grow, pos) {
    const sp = shockPool.pop() || mkSprite(); sp.material.color.set(color); if (pos) sp.position.copy(pos); else sp.position.set(0, 0, 0); sp.visible = true; world.add(sp); shocks.push({ sp, t: 0, grow });
  }
  const headSp = mkSprite(); headSp.visible = false; headSp.material.opacity = 1; world.add(headSp);        // 進度弧前端的亮點(位置 = 後端真實 i/n)

  // ── 小人(研究進度的化身):站在『目前執行中階段的環』上,位置 = 後端真實的 i/n;頭上的泡泡只顯示真實事件的內容 ──
  //   不會思考也不會判斷:它只是把『現在跑到哪、剛測完哪個策略、結果如何』用一個角色說出來。沒有資料時不會出現。
  const RUN_FRAMES = 6, FW = 128;                                              // 0-3 跑步循環、4 站立揮手、5 站立
  const runnerTex = (() => {
    const c = document.createElement('canvas'); c.width = FW * RUN_FRAMES; c.height = FW; const x = c.getContext('2d');
    const limb = (x0, y0, x1, y1, x2, y2, w, col) => { x.strokeStyle = col; x.lineWidth = w; x.lineCap = 'round'; x.lineJoin = 'round'; x.beginPath(); x.moveTo(x0, y0); x.lineTo(x1, y1); x.lineTo(x2, y2); x.stroke(); };
    const rrect = (a, b, w, h, r) => { x.beginPath(); x.moveTo(a + r, b); x.arcTo(a + w, b, a + w, b + h, r); x.arcTo(a + w, b + h, a, b + h, r); x.arcTo(a, b + h, a, b, r); x.arcTo(a, b, a + w, b, r); x.closePath(); };
    for (let f = 0; f < RUN_FRAMES; f++) {
      const run = f < 4, ph = run ? f / 4 * Math.PI * 2 : 0, sw = run ? Math.sin(ph) : 0, bob = run ? Math.abs(Math.cos(ph)) * 4 : 0;
      x.save(); x.translate(f * FW + 64, 0);
      const hipY = 92 - bob, bodyTop = 66 - bob;
      for (const sg of [1, -1]) {                                              // 腿:鞋子是橘色,大步前後擺動、膝蓋彎曲
        const a = sw * 0.95 * sg, kx = Math.sin(a) * 15, ky = hipY + 11, fx = kx + Math.sin(a * 1.2 - (run ? 0.55 * sg : 0)) * 13, fy = Math.min(120, ky + 14 - (run && sg * sw > 0 ? 7 : 0));
        limb(sg * 6, hipY, kx + sg * 6, ky, fx + sg * 6, fy, 11, '#eaf6ff'); x.fillStyle = '#ff9a3c'; x.beginPath(); x.ellipse(fx + sg * 6 + 3, fy + 2, 9, 6, 0, 0, Math.PI * 2); x.fill();
      }
      x.fillStyle = '#37e0ff'; rrect(-19, bodyTop, 38, 34, 12); x.fill();                                          // 身體(青色外套)
      x.fillStyle = '#0b1b3a'; x.fillRect(-4, bodyTop + 6, 8, 20); x.fillStyle = '#ff6f91'; x.beginPath(); x.arc(0, bodyTop + 30, 4, 0, Math.PI * 2); x.fill();   // 拉鍊與小徽章
      for (const sg of [1, -1]) {                                              // 手臂與腿反向擺動;站立時右手揮手
        const wave = f === 4 && sg === 1, a = -sw * 1.0 * sg;
        if (wave) limb(sg * 19, bodyTop + 8, sg * 30, bodyTop - 4, sg * 28, bodyTop - 20, 9, '#eaf6ff');
        else limb(sg * 19, bodyTop + 8, sg * 24 + Math.sin(a) * 10, bodyTop + 22, sg * 22 + Math.sin(a * 1.4) * 14, bodyTop + 32 + Math.cos(a) * 3, 9, '#eaf6ff');
      }
      const hy = 38 - bob * 0.6;                                               // 大頭(Q 版比例:頭幾乎和身體一樣大)
      x.strokeStyle = '#7fe9ff'; x.lineWidth = 3; x.beginPath(); x.moveTo(0, hy - 30); x.lineTo(0, hy - 42); x.stroke(); x.fillStyle = '#ff6f91'; x.beginPath(); x.arc(0, hy - 45, 5, 0, Math.PI * 2); x.fill();   // 天線
      x.fillStyle = '#eaf6ff'; x.beginPath(); x.arc(0, hy, 33, 0, Math.PI * 2); x.fill(); x.strokeStyle = '#37e0ff'; x.lineWidth = 3; x.stroke();
      x.fillStyle = '#0b1b3a'; rrect(-25, hy - 12, 50, 28, 13); x.fill();                                          // 護目鏡
      x.fillStyle = '#7ff3ff'; const blink = f === 5 ? 1.5 : 7; x.beginPath(); x.ellipse(-10, hy + 2, 5, blink, 0, 0, Math.PI * 2); x.fill(); x.beginPath(); x.ellipse(10, hy + 2, 5, blink, 0, 0, Math.PI * 2); x.fill();
      x.strokeStyle = '#7ff3ff'; x.lineWidth = 2.5; x.beginPath(); x.arc(0, hy + 9, 5, 0.15 * Math.PI, 0.85 * Math.PI); x.stroke();   // 微笑
      x.fillStyle = 'rgba(255,111,145,.55)'; x.beginPath(); x.ellipse(-22, hy + 12, 5, 3, 0, 0, Math.PI * 2); x.fill(); x.beginPath(); x.ellipse(22, hy + 12, 5, 3, 0, 0, Math.PI * 2); x.fill();   // 腮紅
      x.restore();
    }
    const t = new THREE.CanvasTexture(c); t.repeat.set(1 / RUN_FRAMES, 1); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  const runnerSp = new THREE.Sprite(new THREE.SpriteMaterial({ map: runnerTex, color: 0xffffff, transparent: true, depthTest: false, depthWrite: false }));
  runnerSp.center.set(0.5, 0.04); runnerSp.scale.set(0.01, 0.01, 1); runnerSp.visible = false; runnerSp.renderOrder = 10; world.add(runnerSp);
  const runnerGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: spriteTex, color: STATE_COLOR.running, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false }));
  runnerGlow.visible = false; world.add(runnerGlow);                          // 腳下的光暈,顏色 = 整體真實狀態
  const bubble = document.createElement('div'); bubble.className = 'lab3d-bubble'; bubble.style.display = 'none';
  const bubL1 = document.createElement('b'), bubL2 = document.createElement('span'); bubble.appendChild(bubL1); bubble.appendChild(bubL2); host.appendChild(bubble);
  // 小人:分析進行中,他以固定的速度沿著環連續地跑;每跑完『完整的一圈』,就沿著弧線跳到另一圈(隨機挑)環,換方向繼續跑。
  //   停下來(分析結束/取消/失敗)的位置會保留,下一次分析從那裡接著跑。他的位置『不』綁進度:進度與細節看頭上的泡泡和進度條(成批抵達的進度若直接拿來當位置,小人會一段一段地瞬移)。
  const RUN_SPEED = 6, HOP_T = 0.6;                                              // 奔跑速度(單位/秒,每圈環上的實際速度相同)、跳環固定花 0.6 秒(實際時間)
  const runner = { on: false, init: false, ring: 0, ang: 0, dir: 1, lapLeft: Math.PI * 2, hop: null, run: false, moving: false, pop: 0, flip: 1, ahead: new THREE.Vector3(), l1: '', l2: '', bw: 120, bh: 40 };
  const ringAngle = (ri, a, lift, out) => { const r = rings[ri]; r.tilt.updateMatrix(); return out.set(Math.cos(a) * r.Rr, lift, Math.sin(a) * r.Rr).applyMatrix4(r.tilt.matrix); };   // 第 ri 圈環上角度 a 的位置;不含環自己的旋轉
  const tv2 = new THREE.Vector3();
  const tv3 = new THREE.Vector3();
  function placeBubble() {                                                       // 泡泡跟著小人(投影到畫面座標)
    if (!runner.on || !runnerSp.visible) { if (bubble.style.display !== 'none') bubble.style.display = 'none'; return; }
    const w = host.clientWidth, h = host.clientHeight; if (!w || !h) return;
    world.updateMatrixWorld(); tv3.copy(runner.ahead).applyMatrix4(world.matrixWorld).project(camera); const ax = tv3.x;       // 前方一點點的位置 → 判斷小人在畫面上是往左還是往右跑
    runnerSp.getWorldPosition(tv2); const dist = camera.position.distanceTo(tv2), th = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2), pxH = 1.25 * runner.pop / (dist * th) * h / 2;
    tv2.project(camera); if (Math.abs(ax - tv2.x) > 1e-4) runner.flip = ax >= tv2.x ? 1 : -1;
    let x = (tv2.x * 0.5 + 0.5) * w, y = (-tv2.y * 0.5 + 0.5) * h;
    x = Math.min(w - runner.bw / 2 - 4, Math.max(runner.bw / 2 + 4, x)); y = Math.max(runner.bh + 10, y - pxH - 12);
    bubble.style.display = 'block'; bubble.style.opacity = '1'; bubble.style.transform = 'translate(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px) translate(-50%,-100%)';
  }

  // ── 後處理 ──
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(600, 400), 0.62, 0.38, 0.36); composer.addPass(bloom);

  // ── 狀態 ──
  let state = 'idle', activity = 0, tNow = 0, yaw = 0.0, vx = 0, vy = 0, ambientOn = false, destroyed = false, visible = !document.hidden, onScreen = true;
  let loopOn = false, raf = 0, lastFrame = 0, frames = 0, fpsT = 0, fps = 0, frameCost = 0, lowPower = false, forced = false, renderedFrames = 0, arcTick = 0, dragging = false;
  const colTarget = new THREE.Color(STATE_COLOR.idle); let intensity = 0.55, intensityTarget = 0.55;
  const staticOnly = () => reduced.matches || forced;

  function resize() {
    const w = host.clientWidth, h = host.clientHeight; if (!w || !h) return;
    renderer.setSize(w, h, false); composer.setSize(w, h); bloom.setSize(w, h); camera.aspect = w / h;
    const th = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2), d = Math.max(7.3, 4.25 / (th * camera.aspect), 3.7 / th);   // 水平與垂直都要容得下最外圈
    const sc = Math.min(2.2, Math.max(1, 560 / h)); rings.forEach(r => { r.dustMat.size = 0.045 * sc; r.streakMat.size = 0.085 * sc; });   // 畫面較矮時放大粒子,讓環不會變得稀疏
    camera.position.set(0, 2.1 * d / 7.6, d); camera.lookAt(0, 0, 0); camera.updateProjectionMatrix(); renderNow();
  }
  function frame(dt) {
    tNow += dt; activity = Math.max(0, activity - dt * 0.9); coreFlash = Math.max(0, coreFlash - dt * 2.4);
    if (dt > 0) {                                                       // 後端事件常成批抵達:排隊後在約 0.3 秒內平均放出,畫面才是連續的『資料流』(事件數量不變,不會多也不會少)
      let n = 0; if (pending.length) { n = Math.min(pending.length, Math.max(1, Math.ceil(pending.length * dt / 0.3))); for (let q = 0; q < n; q++) spawnPacket(pending.shift()); }
      rate += (n / dt - rate) * Math.min(1, dt * 3);
      for (let q = packets.length - 1; q >= 0; q--) {
        const pk = packets[q]; pk.t += dt / pk.dur;
        if (pk.t >= 1.12) { pk.sp.forEach(x => { x.visible = false; x.material.opacity = 0; world.remove(x); packetPool.push(x); }); if (pk.kind === 'collect') addBead(pk.b); packets.splice(q, 1); continue; }
        pk.sp.forEach((x, j) => {
          const u = Math.min(1, Math.max(0, pk.t - j * 0.05)), e = u * u * (3 - 2 * u);
          x.position.lerpVectors(pk.a, pk.b, e); x.position.y += Math.sin(Math.PI * u) * pk.lift;
          const fade = pk.kind === 'collect' ? (u > 0.9 ? 1 : 1) : (pk.kind === 'out' ? 1 - u * 0.9 : 1 - u);
          x.material.opacity = pk.t < j * 0.05 ? 0 : Math.max(0, fade) * (1 - j * 0.2) * 0.85; x.scale.setScalar(pk.size * (1 - j * 0.16) * (pk.big ? 1.25 : 1));
        });
      }
      for (let q = shocks.length - 1; q >= 0; q--) {
        const sh = shocks[q]; sh.t += dt / 0.9;
        if (sh.t >= 1) { sh.sp.visible = false; world.remove(sh.sp); shockPool.push(sh.sp); shocks.splice(q, 1); continue; }
        sh.sp.scale.setScalar(0.6 + sh.t * sh.grow); sh.sp.material.opacity = 0.7 * (1 - sh.t) * (1 - sh.t);
      }
      if (progFrac != null) { const u = Math.PI * 2 * progFrac - Math.PI / 2; headSp.position.set(Math.cos(u) * PROG_R, 0, Math.sin(u) * PROG_R); headSp.scale.setScalar(0.5 + 0.16 * Math.sin(tNow * 9)); }
    }
    sphereGroup.scale.setScalar(1 + coreFlash * 0.07); bloom.strength = 0.62 + Math.min(0.3, rate * 0.01) + coreFlash * 0.18;
    const k = Math.min(1, dt * 4); mat.uniforms.uColor.value.lerp(colTarget, k); coreMesh.material.color.copy(mat.uniforms.uColor.value);
    intensity += (intensityTarget + Math.min(0.6, activity * 0.5) + coreFlash * 0.6 - intensity) * k; mat.uniforms.uIntensity.value = intensity; mat.uniforms.uTime.value = tNow;
    const power = (STATE_POWER[state] || 0.22) + Math.min(0.3, activity * 0.25), moving = dt > 0 && (state === 'running' || ambientOn || activity > 0.05 || packets.length > 0);
    const spd = (state === 'running' ? 1 : 0.35) + activity * 0.9 + Math.min(3.5, rate * 0.1);        // 事件越密(後端每秒處理的策略越多),環轉得越快
    rings.forEach((r, i) => {
      r.flash = Math.max(0, r.flash - dt * 1.1);
      const base = STAGE_LINE[r.status] != null ? STAGE_LINE[r.status] : 0.2, lit = r.status === 'running' || r.flash > 0.02;
      r.line.material.opacity = Math.min(0.95, base + r.flash * 0.4); r.streakMat.opacity = r.status === 'idle' || r.status === 'skip' ? 0.0 : Math.min(1, 0.25 + base * 0.8 + r.flash * 0.4);
      r.dustMat.opacity = 0.5 + 0.3 * Math.min(1, power) + (lit ? 0.12 : 0);
      if (moving) r.spin.rotation.y += r.dir * dt * (0.22 + i * 0.07) * 0.6 * (0.5 + spd * (r.status === 'running' ? 1.8 : 1));   // 該階段執行中時,那一圈轉得最快
    });
    if (runner.on) {                                                    // 小人:分析中等速奔跑;跑完一整圈才跳環(固定 0.6 秒的弧線);沒在分析就站著
      runner.pop = Math.min(1, runner.pop + dt * 4); let lift = 0, jumping = false; runner.moving = false;
      if (runner.hop) {
        const h = runner.hop; h.t += dt / HOP_T; jumping = true; const u = Math.min(1, h.t), e = u * u * (3 - 2 * u); lift = Math.sin(Math.PI * u) * 1.6;
        runnerSp.position.lerpVectors(h.a, h.b, e); runnerSp.position.y += lift;
        if (h.t >= 1) { runner.ring = h.to; runner.ang = h.ang; runner.dir = -RING_DIR[h.to]; runner.lapLeft = Math.PI * 2; runner.hop = null; spawnShock(STATE_COLOR.running, 2.4, runnerSp.position); }      // 落地的光圈
      } else {
        if (runner.run && dt > 0) {
          const da = RUN_SPEED / RING_R[runner.ring] * dt; runner.ang += runner.dir * da; runner.lapLeft -= da; runner.moving = true;
          if (runner.lapLeft <= 0) {                                    // 這一圈跑完了 → 起跳:隨機挑另一圈環
            let to = Math.floor(Math.random() * (rings.length - 1)); if (to >= runner.ring) to++;
            const ang2 = runner.ang + (Math.random() - 0.5) * 1.2, a = ringAngle(runner.ring, runner.ang, 0, new THREE.Vector3()), b = ringAngle(to, ang2, 0, new THREE.Vector3());
            runner.hop = { t: 0, to, ang: ang2, a, b }; spawnShock(STATE_COLOR.running, 2.4, a);                                      // 起跳的光圈
          }
        }
        ringAngle(runner.ring, runner.ang, runner.moving ? Math.abs(Math.sin(tNow * 9)) * 0.06 : 0, runnerSp.position);
      }
      if (jumping) runner.moving = true;
      ringAngle(runner.ring, runner.ang + runner.dir * 0.15, 0, runner.ahead);
      const sz = 1.1 * (1 - Math.pow(1 - runner.pop, 3)) * (jumping ? 1.15 : 1);
      runnerSp.scale.set(sz * runner.flip, sz, 1); runnerGlow.position.set(runnerSp.position.x, runnerSp.position.y - lift + 0.02, runnerSp.position.z); runnerGlow.scale.setScalar(sz * (jumping ? 1.5 : 1.1));
      runnerTex.offset.x = (jumping ? 4 : (runner.moving ? Math.floor(tNow * 10) % 4 : (Math.floor(tNow * 0.6) % 3 === 0 ? 4 : 5))) / RUN_FRAMES;       // 跳躍時舉起手;跑步;停下來偶爾揮手、眨眼
    }
    const spin = ambientOn ? 0.15 : 0;                                  // 只有使用者開啟『裝飾旋轉』才會整個轉(分析中不轉,否則環上的小人會跟著晃)
    yaw += (spin * dt) + vx; vx *= 0.94; if (Math.abs(vx) < 1e-5) vx = 0;
    world.rotation.y = yaw; sphereGroup.rotation.y = -yaw * 0.6 + tNow * 0.12; sphereGroup.rotation.x += (state === 'running' ? 0.2 : 0.05) * dt + vy; vy *= 0.94; if (Math.abs(vy) < 1e-5) vy = 0;
    coreRings[0].rotation.z = tNow * 0.5; coreRings[1].rotation.z = -tNow * 0.35;
    if (state === 'running' && ++arcTick % 8 === 0) regenArcs();
    arcMat.opacity = 0.5 + Math.min(0.5, intensity * 0.4); centerGlow.material.opacity = 0.22 + Math.min(0.4, activity * 0.2 + coreFlash * 0.25 + (state === 'running' ? 0.06 : 0)); centerGlow.material.color.copy(mat.uniforms.uColor.value).lerp(new THREE.Color(0x6a5cff), 0.5);
  }
  let nRender = 0;
  function renderNow() { if (destroyed) return; const t0 = performance.now(); composer.render(); placeBubble(); if (++nRender > 4) frameCost = frameCost * 0.85 + (performance.now() - t0) * 0.15; }   // 前幾次含 shader 編譯,不計入
  // 迴圈:只在有真實工作、光點在飛、拖曳慣性或使用者開啟裝飾旋轉時存在
  const busy = () => state === 'running' || packets.length > 0 || pending.length > 0 || shocks.length > 0 || coreFlash > 0.02 || activity > 0.05 || ambientOn || dragging || vx !== 0 || vy !== 0;
  const wantLoop = () => !destroyed && !staticOnly() && visible && onScreen && busy();
  const targetFps = () => (lowPower ? 20 : 30);
  function tick(ts) {
    raf = 0; if (!loopOn) return;
    if (ts - lastFrame >= 1000 / targetFps() - 1) {
      const dt = Math.min(0.1, lastFrame ? (ts - lastFrame) / 1000 : 0.033); lastFrame = ts; frame(dt); renderNow(); renderedFrames++;
      frames++; if (ts - fpsT > 1000) { fps = Math.round(frames * 1000 / Math.max(1, ts - fpsT)); frames = 0; fpsT = ts; }
      if (frameCost > 18 && !lowPower) { lowPower = true; rings.forEach(r => { r.dust.geometry.setDrawRange(0, r.n >> 1); }); }
      if (frameCost > 34 && renderedFrames > 30) { forced = true; stopLoop(); renderNow(); if (opts.onDegrade) opts.onDegrade('3D 畫面負擔過高,已停止動畫(保留靜態畫面)'); return; }
    }
    if (!wantLoop()) { stopLoop(); frame(0); renderNow(); return; }
    raf = requestAnimationFrame(tick);
  }
  function startLoop() { if (loopOn) return; loopOn = true; lastFrame = 0; fpsT = performance.now(); frames = 0; raf = requestAnimationFrame(tick); }
  function stopLoop() { loopOn = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
  function sync() { if (wantLoop()) startLoop(); else { if (loopOn) stopLoop(); settle(); } }
  let settleT = 0;
  function settle() { if (settleT || destroyed) return; settleT = setTimeout(() => { settleT = 0; for (let i = 0; i < 24; i++) frame(1 / 12); renderNow(); }, 30); }   // 靜態:讓顏色與強度走到目標值,畫一張

  const onVis = () => { visible = !document.hidden; sync(); }; document.addEventListener('visibilitychange', onVis);
  const io = 'IntersectionObserver' in window ? new IntersectionObserver(en => { onScreen = en[en.length - 1].isIntersecting; sync(); }) : null; if (io) io.observe(host);
  const ro = 'ResizeObserver' in window ? new ResizeObserver(() => { resize(); }) : null; if (ro) ro.observe(host);
  // 拖曳旋轉(滑鼠/觸控筆;原專案是 OrbitControls,這裡只留最簡單的拖曳慣性,不攔截頁面捲動)
  let drag = null;
  canvas.style.touchAction = 'pan-y';
  canvas.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY }; dragging = true; canvas.setPointerCapture(e.pointerId); sync(); });
  canvas.addEventListener('pointermove', e => { if (!drag) return; vx = (e.clientX - drag.x) * 0.004; vy = (e.clientY - drag.y) * 0.002; drag = { x: e.clientX, y: e.clientY }; yaw += vx; sync(); });
  const endDrag = () => { drag = null; dragging = false; sync(); }; canvas.addEventListener('pointerup', endDrag); canvas.addEventListener('pointercancel', endDrag);

  resize(); settle();
  const api = {
    setState(s) {
      s = STATE_COLOR[s] ? s : 'idle'; if (s === state) return; if (s === 'running') clearBeads();
      state = s; colTarget.set(STATE_COLOR[state]); intensityTarget = STATE_INTENSITY[state]; if (state !== 'running') progMat.color.set(STATE_COLOR[state] || STATE_COLOR.running);
      if (state === 'running') activity = 0.5;
      sync();
    },
    setStage(id, status) {                                              // 四圈環的顏色與亮度 = 該階段的真實狀態
      const i = ringIdx[id]; if (i == null) return; const r = rings[i]; if (r.status === status) return;
      r.status = status; const c = STAGE_COLOR[status] || STAGE_COLOR.idle; r.line.material.color.set(c); r.streakMat.color.set(c); if (!busy()) settle();
    },
    event(stage, status, outcome) {                                     // 呼叫端保證每一次呼叫對應一個真實後端事件
      const i = ringIdx[stage]; if (i == null) return;
      activity = Math.min(2, activity + (status === 'progress' ? 0.12 : 0.5)); rings[i].flash = status === 'progress' ? 0.5 : 1;
      const live = !staticOnly() && visible && onScreen;
      if (live && status === 'progress') { pending.push({ stage, outcome }); if (pending.length > 400) pending.shift(); sync(); return; }
      if (live && (status === 'done' || status === 'start')) spawnShock(status === 'done' ? STAGE_COLOR.done : (STATE_COLOR[state] || STATE_COLOR.running), status === 'done' ? 6 : 5);
      sync();
    },
    setProgress(f) { progFrac = f == null ? null : Math.min(1, Math.max(0, f)); headSp.visible = false; headSp.material.color.set(state === 'running' ? STATE_COLOR.running : STATE_COLOR[state]); if (f == null) { progLine.visible = false; } else { progLine.visible = true; progGeo.setDrawRange(0, Math.max(2, Math.round(Math.min(1, Math.max(0, f)) * PROG_N) + 1)); progMat.color.set(f >= 1 ? STATE_COLOR.done : (state === 'running' ? STATE_COLOR.running : STATE_COLOR[state] || STATE_COLOR.running)); } if (!busy()) settle(); },
    setRunner(info) {                                                   // info = {run, state, l1, l2};null = 隱藏(沒有真實分析時不顯示)。小人停下來的位置會保留,下一次分析從那裡接著跑
      if (!info) { runner.on = false; runnerSp.visible = false; runnerGlow.visible = false; bubble.style.display = 'none'; if (!busy()) settle(); return; }
      if (!runner.init) { runner.init = true; runner.ring = Math.floor(Math.random() * rings.length); runner.ang = Math.random() * Math.PI * 2; runner.dir = -RING_DIR[runner.ring]; runner.lapLeft = Math.PI * 2; }
      if (!runner.on) { runner.on = true; runner.pop = 0; }
      runner.run = !!info.run; runnerSp.visible = true; runnerGlow.visible = true; runnerGlow.material.color.set(STATE_COLOR[info.state] || STATE_COLOR.running);
      if (info.l1 !== runner.l1 || info.l2 !== runner.l2) { runner.l1 = info.l1; runner.l2 = info.l2; bubL1.textContent = info.l1 || ''; bubL2.textContent = info.l2 || ''; bubL2.style.display = info.l2 ? 'block' : 'none'; bubble.style.display = 'block'; runner.bw = bubble.offsetWidth || 120; runner.bh = bubble.offsetHeight || 40; }
      sync(); if (!busy()) settle();
    },
    setAmbient(v) { ambientOn = !!v; sync(); },
    resize, sync,
    stats() { return { loopOn, fps, frameCost: +frameCost.toFixed(2), calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, particles: rings.length * (budget.dust + budget.streak * 3), packets: packets.length, pending: pending.length, eventRate: +rate.toFixed(1), runner: { on: runner.on, ring: runner.ring, ang: +runner.ang.toFixed(3), lapLeft: +runner.lapLeft.toFixed(3), moving: runner.moving, hop: !!runner.hop }, state, lowPower, forced, static: staticOnly(), ambient: ambientOn, pixelRatio: renderer.getPixelRatio(), size: [host.clientWidth, host.clientHeight] }; },
    _forceVisibility(hidden) { visible = !hidden; sync(); },
    destroy() { destroyed = true; stopLoop(); document.removeEventListener('visibilitychange', onVis); if (io) io.disconnect(); if (ro) ro.disconnect(); renderer.dispose(); bubble.remove(); canvas.remove(); },
  };
  return api;
}

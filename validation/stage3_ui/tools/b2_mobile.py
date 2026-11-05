# -*- coding: utf-8 -*-
"""B2: iPhone-size screenshots + REAL touch tests (CDP Input.synthesize*Gesture) + audits (tap-target size, font size, overflow, PWA).
usage: python b2_mobile.py <base_url> <outdir> [--device iphone14|se|landscape] [--long]"""
import asyncio, base64, json, os, sys, time, argparse, shutil
import aiohttp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import CDP, launch, kill_tree

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
DEVICES = {'iphone14': (390, 844), 'se': (375, 667), 'promax': (430, 932), 'landscape': (844, 390)}


async def shot(c, path, full=False, maxh=7000):
    p = {'format': 'png'}
    if full:
        m = await c.call('Page.getLayoutMetrics')
        p.update({'captureBeyondViewport': True, 'clip': {'x': 0, 'y': 0, 'width': m['cssContentSize']['width'], 'height': min(m['cssContentSize']['height'], maxh), 'scale': 1}})
    r = await c.call('Page.captureScreenshot', p)
    open(path, 'wb').write(base64.b64decode(r['data'])); return os.path.basename(path)


async def wait_js(c, expr, timeout=90, step=0.8):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = await c.js(expr)
        if v: return v
        await asyncio.sleep(step)
    return None


CENTER_JS = """((sel, nth) => { const els = [...document.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }); const e = els[nth||0]; if (!e) return null;
  e.scrollIntoView({block: 'center', inline: 'nearest'}); const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height}; })"""


async def raw_tap(c, x, y, hold=0.06):
    await c.call('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
    await asyncio.sleep(hold)
    await c.call('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})


async def swipe(c, x0, y0, x1, y1, steps=12, dt=0.016):
    await c.call('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x0, 'y': y0}]})
    for i in range(1, steps + 1):
        await asyncio.sleep(dt)
        await c.call('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x0 + (x1 - x0) * i / steps, 'y': y0 + (y1 - y0) * i / steps}]})
    await c.call('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})


async def tap(c, sel, nth=0, dur=60):
    pt = await c.js(f"({CENTER_JS})({json.dumps(sel)},{nth})")
    if not pt: return None
    await asyncio.sleep(0.25)
    pt = await c.js(f"({CENTER_JS})({json.dumps(sel)},{nth})")      # re-measure after scroll settles
    try:
        await raw_tap(c, pt['x'], pt['y'], dur / 1000.0)
    except RuntimeError as e:
        print('TAP FAILED', sel, nth, pt, e); return None
    await asyncio.sleep(0.5); return pt


AUDIT_JS = r"""(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && !e.closest('[hidden]') && !e.closest('.view:not(.active)') && !e.closest('.modal-bg:not(.open)') && !e.closest('.analysis-modal-bg:not(.open)') && !e.closest('.card-detail[hidden]') && !(e.closest('.nav-drawer') && !e.closest('.nav-drawer.open')); };
  const small = [];
  document.querySelectorAll('button, a[href], select, input:not([type=hidden]):not([type=file]), label.nav-toggle-btn, [role=button], .search-item, .nav-item, .mtab, .htab, .hstock, .itoggle, .rec-tag').forEach(e => {
    if (!vis(e)) return; let r = e.getBoundingClientRect();
    if (e.type === 'checkbox' && e.closest('label')) r = e.closest('label').getBoundingClientRect();   // the whole label is the tap target
    if (r.width < 43.5 || r.height < 43.5) small.push({tag: e.tagName.toLowerCase(), cls: e.className.toString().slice(0, 30), text: (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 18), w: Math.round(r.width), h: Math.round(r.height)});
  });
  const fs = {}; let lt12 = [], lt14 = 0, total = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode; const t = n.textContent.trim(); if (!t) continue; const p = n.parentElement; if (!p || ['SCRIPT', 'STYLE', 'OPTION'].includes(p.tagName) || !vis(p)) continue;
    if (p.closest('canvas, .tv-lightweight-charts')) continue;
    const s = parseFloat(getComputedStyle(p).fontSize); total++; if (s < 14) lt14++; if (s < 12) lt12.push({t: t.slice(0, 24), s, cls: p.className.toString().slice(0, 24)});
  }
  const inputs = [...document.querySelectorAll('input:not([type=checkbox]):not([type=file]), select, textarea')].filter(vis).map(e => ({id: e.id || e.className, fs: parseFloat(getComputedStyle(e).fontSize)})).filter(x => x.fs < 16);
  const sc = document.scrollingElement;
  return {smallTargets: small.slice(0, 40), nSmall: small.length, textNodes: total, lt14, lt12: lt12.slice(0, 25), nLt12: lt12.length, inputsUnder16: inputs, overflowX: sc.scrollWidth > innerWidth + 1, scrollW: sc.scrollWidth, innerW: innerWidth};
})()"""


async def run(base, outdir, device, long_run):
    os.makedirs(outdir, exist_ok=True)
    W, H = DEVICES[device]
    proc, tmp, wsurl = await launch(9361)
    R = {'device': device, 'viewport': [W, H], 'shots': [], 'touch': {}, 'audit': {}}
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.ws_connect(wsurl, max_msg_size=0) as ws:
                c = CDP(ws); pump = asyncio.ensure_future(c.pump())
                for dom in ('Page', 'Runtime', 'Log', 'Network'): await c.call(dom + '.enable')
                await c.call('Network.setCacheDisabled', {'cacheDisabled': True})
                await c.call('Emulation.setDeviceMetricsOverride', dict(width=W, height=H, deviceScaleFactor=2, mobile=True, screenWidth=W, screenHeight=H))
                await c.call('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 5})
                await c.call('Emulation.setUserAgentOverride', {'userAgent': UA})
                await c.call('Page.navigate', {'url': base}); await asyncio.sleep(3)
                await c.js("try{closeIntro()}catch(e){} 1")
                await c.js("(async()=>{for(let y=0;y<document.body.scrollHeight;y+=500){window.scrollTo(0,y);await new Promise(r=>setTimeout(r,200));} window.scrollTo(0,0);return 1;})()")
                R['cards_loaded'] = await wait_js(c, "(()=>{const cs=[...document.querySelectorAll('.card')]; return cs.length && cs.every(x=>x.dataset.loaded==='1') ? cs.length : 0;})()", 120)
                await asyncio.sleep(1.2)
                R['media'] = await c.js("({coarse: matchMedia('(pointer:coarse)').matches, hoverNone: matchMedia('(hover:none)').matches, touchPoints: navigator.maxTouchPoints, mobileBP: matchMedia('(max-width:720px)').matches})")
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_01_watchlist_top.png')))
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_02_watchlist_full.png'), full=True, maxh=5200))
                R['audit']['watchlist'] = await c.js(AUDIT_JS)

                # ---- touch: bottom tabs navigate
                T = R['touch']
                T['dbg'] = []
                EXP = "stocks.map(s=>s.expanded?1:0).join('')"
                T['dbg'].append(('start', await c.js(EXP)))
                await tap(c, '#bottomTabs a[data-view=symbol]')
                T['tab_symbol_hash'] = await c.js("location.hash")
                await tap(c, '#bottomTabs a[data-view=watchlist]')
                T['dbg'].append(('after tabs', await c.js(EXP)))
                T['tab_watchlist_hash'] = await c.js("location.hash")
                T['bottom_tabs_box'] = await c.js("(()=>{const r=document.getElementById('bottomTabs').getBoundingClientRect(); return {top:Math.round(r.top), h:Math.round(r.height), bottom:Math.round(r.bottom), vh:innerHeight}})()")
                # ---- touch: tap KPI → tip sheet; tap elsewhere → hide
                await c.js("window.scrollTo(0,0); 1")
                await tap(c, '.card .kpi[data-tip]')
                T['dbg'].append(('after kpi tap', await c.js(EXP)))
                T['tip_after_tap'] = await c.js("(()=>{const s=document.getElementById('tipSheet'); return {shown:!s.hidden, text:s.innerText.slice(0,40)}})()")
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_03_tip_sheet.png')))
                await tap(c, '.card-datatime')
                T['tip_after_tap_elsewhere'] = await c.js("document.getElementById('tipSheet').hidden")
                # ---- touch: expand card → charts
                T['before_expand'] = await c.js("({exp: stocks.map(s=>s.expanded), btn: document.querySelector('.card-expand').textContent, tipHidden: document.getElementById('tipSheet').hidden})")
                T['expand_tap_hit'] = await c.js("(()=>{const e=document.querySelector('.card-expand'); e.scrollIntoView({block:'center'}); const b=e.getBoundingClientRect(); const h=document.elementFromPoint(b.left+b.width/2,b.top+b.height/2); return h.className+'|'+h.tagName})()")
                await tap(c, '.card-expand')
                await asyncio.sleep(1.5)
                T['expanded_charts'] = await c.js("(()=>{const id=stocks[0].id; return {expanded:stocks[0].expanded, charts:(chartInsts[id]||[]).length, canvases:document.querySelectorAll('#card-'+id+' canvas').length}})()")
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_04_card_expanded_chart.png')))
                R['audit']['card_expanded'] = await c.js(AUDIT_JS)
                # ---- touch: vertical swipe on the chart must scroll the page (not get trapped); horizontal swipe pans; pinch zooms
                pt = await c.js(f"({CENTER_JS})('#card-'+stocks[0].id+' .chart-container canvas',0)")
                if pt:
                    y0 = await c.js("scrollY")
                    await swipe(c, pt['x'], pt['y'] + 120, pt['x'], pt['y'] - 120)
                    await asyncio.sleep(0.6)
                    T['chart_vertical_swipe_scrolled_page'] = {'before': y0, 'after': await c.js("scrollY")}
                    pt = await c.js(f"({CENTER_JS})('#card-'+stocks[0].id+' .chart-container canvas',0)")
                    r0 = await c.js("(()=>{const r=chartInsts[stocks[0].id][0].timeScale().getVisibleLogicalRange(); return [r.from, r.to]})()")
                    await swipe(c, pt['x'] - 80, pt['y'], pt['x'] + 80, pt['y'])
                    await asyncio.sleep(0.6)
                    r1 = await c.js("(()=>{const r=chartInsts[stocks[0].id][0].timeScale().getVisibleLogicalRange(); return [r.from, r.to]})()")
                    T['chart_horizontal_swipe_panned'] = {'before': r0, 'after': r1, 'changed': abs(r0[0] - r1[0]) > 0.5}
                    pt = await c.js(f"({CENTER_JS})('#card-'+stocks[0].id+' .chart-container canvas',0)")
                    await c.call('Input.synthesizePinchGesture', {'x': pt['x'], 'y': pt['y'], 'scaleFactor': 2.0, 'relativeSpeed': 300, 'gestureSourceType': 'touch'})
                    await asyncio.sleep(0.6)
                    r2 = await c.js("(()=>{const r=chartInsts[stocks[0].id][0].timeScale().getVisibleLogicalRange(); return [r.from, r.to]})()")
                    T['chart_pinch'] = {'span_before': round(r1[1] - r1[0], 1), 'span_after': round(r2[1] - r2[0], 1), 'zoomed_in': (r2[1] - r2[0]) < (r1[1] - r1[0]) - 1}
                # ---- touch: long-press indicator toggle shows tip WITHOUT toggling
                before = await c.js("stocks[0].indicators.kd")
                pt = await c.js(f"({CENTER_JS})('#itoggle-'+stocks[0].id+'-kd',0)")
                await asyncio.sleep(0.3)
                pt = await c.js(f"({CENTER_JS})('#itoggle-'+stocks[0].id+'-kd',0)")
                if pt:
                    await raw_tap(c, pt['x'], pt['y'], 0.8)
                    await asyncio.sleep(0.6)
                    T['longpress_indicator'] = {'tip_shown': await c.js("!document.getElementById('tipSheet').hidden"), 'toggled': (await c.js("stocks[0].indicators.kd")) != before}
                else:
                    T['longpress_indicator'] = 'ELEMENT NOT FOUND; state=' + json.dumps(await c.js("({exp:stocks[0].expanded, hidden:document.querySelector('#card-'+stocks[0].id+' .card-detail').hidden, hash:location.hash, view:document.querySelector('.view.active').id})"))
                await c.js("document.getElementById('tipSheet').hidden=true; 1")
                # ---- touch: plain tap on the toggle still toggles
                await tap(c, '#itoggle-' + str(await c.js("stocks[0].id")) + '-kd')
                T['tap_indicator_toggles'] = (await c.js("stocks[0].indicators.kd")) != before
                await tap(c, '#itoggle-' + str(await c.js("stocks[0].id")) + '-kd')   # restore
                # ---- touch: enlarge chart → full-screen modal
                await tap(c, '#card-' + str(await c.js("stocks[0].id")) + ' .btn-icon[aria-label="放大 K 線"]')
                await asyncio.sleep(1.5)
                T['chart_modal'] = await c.js("(()=>{const m=document.querySelector('#modalBg .modal').getBoundingClientRect(); return {open:document.getElementById('modalBg').classList.contains('open'), w:Math.round(m.width), h:Math.round(m.height), vw:innerWidth, vh:innerHeight, bodyLocked:document.body.classList.contains('modal-open'), charts:(modalChartInst||[]).length}})()")
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_05_chart_modal.png')))
                R['audit']['chart_modal'] = await c.js(AUDIT_JS)
                await tap(c, '#modalBg .btn-close')
                T['chart_modal_closed'] = await c.js("!document.getElementById('modalBg').classList.contains('open')")
                # ---- touch: nav drawer
                await c.js("window.scrollTo(0,0); 1")
                await tap(c, '#navToggleBtn')
                await asyncio.sleep(0.5)
                T['drawer_open'] = await c.js("document.getElementById('navDrawer').classList.contains('open')")
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_06_nav_drawer.png')))
                R['audit']['drawer'] = await c.js(AUDIT_JS)
                await tap(c, '#navDrawerBody .nav-item', 3)
                await asyncio.sleep(1.2)
                T['drawer_item_closes_and_scrolls'] = await c.js("({closed:!document.getElementById('navDrawer').classList.contains('open'), scrollY:Math.round(scrollY)})")
                # ---- touch: search + add bar (keyboard zoom guard = font-size ≥16)
                await c.js("window.scrollTo(0,0); 1")
                await tap(c, '#addInput')
                await c.call('Input.insertText', {'text': 'NV'}); await asyncio.sleep(0.8)
                T['search_dropdown_items'] = await c.js("document.querySelectorAll('#searchDropdown .search-item').length")
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_07_search.png')))
                await c.js("document.getElementById('addInput').value=''; document.getElementById('searchDropdown').style.display='none'; document.getElementById('addInput').blur(); 1")
                # ---- 最佳策略 bottom sheet
                await c.js("window.scrollTo(0,0); 1")
                await tap(c, '.act-main .btn-analyze', 0)   # first card → 最佳策略
                await wait_js(c, "/完成|失敗|❌/.test((document.getElementById('progressText')||{}).textContent||'')||document.querySelector('#analysisResults .state-card')?1:0", 180, 2)
                await asyncio.sleep(1.5)
                T['analysis_sheet'] = await c.js("(()=>{const m=document.querySelector('#analysisBg .analysis-modal').getBoundingClientRect(); return {open:document.getElementById('analysisBg').classList.contains('open'), w:Math.round(m.width), h:Math.round(m.height), bottom:Math.round(m.bottom), vh:innerHeight, bodyLocked:document.body.classList.contains('modal-open'), cards:document.querySelectorAll('#analysisResults .cmp-card').length, tableVisible:getComputedStyle(document.querySelector('#analysisResults .cmp-wrap')||document.body).display}})()")
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_08_analysis_sheet.png')))
                R['audit']['analysis_sheet'] = await c.js(AUDIT_JS)
                # parity: every number in the (hidden) desktop table must also be present in the phone cards
                R['parity'] = await c.js(r"""(() => {
                  const rows = [...document.querySelectorAll('#analysisResults .cmp-table tbody tr')]; const cards = [...document.querySelectorAll('#analysisResults .cmp-card')];
                  const out = {tableRows: rows.length, cards: cards.length, mismatches: []};
                  rows.forEach((tr, i) => { const tds = [...tr.children].map(td => td.innerText.replace(/\s+/g, ' ').trim()); const name = tds[1].split('\n')[0]; const ct = cards[i] ? cards[i].innerText.replace(/\s+/g, ' ') : '';
                    // numbers shown in the table cells (IS ret/pf/n, OOS ret/pf/n/mdd, full ret/pf/mdd/n)
                    const nums = [tds[3], tds[4], tds[5], tds[6], tds[7], tds[8], tds[9], tds[10], tds[11], tds[12], tds[13]];
                    nums.forEach((v, k) => { if (v && v !== '—' && !ct.includes(v)) out.mismatches.push({row: i, col: k, v}); });
                    if (!ct.includes(name.slice(0, 8))) out.mismatches.push({row: i, name}); });
                  return out; })()""")
                # touch: tap 詳細 → go to symbol view
                await c.js("document.getElementById('analysisResults').scrollTop=0; 1")
                await tap(c, '#analysisResults .cmp-card .linkbtn', 0)
                await asyncio.sleep(0.8)
                T['detail_button_opens_symbol_view'] = await c.js("location.hash")
                await wait_js(c, "document.querySelector('#symBody .sym-head, #symBody .state-card')?1:0", 90)
                await asyncio.sleep(2)
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_09_symbol_view_top.png')))
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_10_symbol_view_full.png'), full=True, maxh=6500))
                R['audit']['symbol_view'] = await c.js(AUDIT_JS)
                T['sheet_closed_after_detail'] = await c.js("!document.getElementById('analysisBg').classList.contains('open')")
                # symbol view for the other two markets (touch: select + tap 分析)
                for sym, strat, per, tf, tag in [('AAPL', 'tsmom', '2y', '1d', 'us'), ('SOL-USD', 'keltner', '1y', '4h', 'crypto')]:
                    await c.js(f"document.getElementById('symCustom').value={json.dumps(sym)}; document.getElementById('symStrat').value={json.dumps(strat)}; document.getElementById('symPeriod').value={json.dumps(per)}; document.getElementById('symTf').value={json.dumps(tf)}; 1")
                    await tap(c, '#symRun')
                    await wait_js(c, "document.querySelector('#symBody .sym-head, #symBody .state-card')?1:0", 90)
                    await asyncio.sleep(2)
                    R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_11_symbol_{tag}.png'), full=True, maxh=6500))
                    R['touch'][f'symbol_{tag}_panels'] = await c.js("document.querySelectorAll('#symBody .panel').length + '/' + document.querySelectorAll('#symBody canvas').length")
                # market view + lab/best views
                await tap(c, '#bottomTabs a[data-view=market]')
                await wait_js(c, "document.querySelectorAll('#mkTable tbody tr').length && !document.querySelector('#mkTable').innerText.includes('載入中')?1:0", 90)
                await asyncio.sleep(1)
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_12_market.png'), full=True, maxh=5000))
                await tap(c, '#bottomTabs a[data-view=lab]')
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_13_lab_top.png')))
                await tap(c, '#bottomTabs a[data-view=best]')
                R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_14_best_top.png')))
                R['audit']['best_view'] = await c.js(AUDIT_JS)
                if long_run:
                    await c.js("document.getElementById('bestCustom').value='AAPL'; document.getElementById('bestTf').value='1d'; document.getElementById('bestPeriod').value='2y'; 1")
                    await tap(c, '#bestRun')
                    await wait_js(c, "document.querySelector('#bestBody .cmp-card, #bestBody .state-card')?1:0", 240, 2)
                    await asyncio.sleep(1.5)
                    R['shots'].append(await shot(c, os.path.join(outdir, f'b2_{device}_15_best_view_AAPL.png'), full=True, maxh=6500))
                # PWA checks
                R['pwa'] = await c.js("""(async()=>{const out={}; out.manifestLink=!!document.querySelector('link[rel=manifest]'); out.appleIcon=!!document.querySelector('link[rel=apple-touch-icon]'); out.metaCapable=!!document.querySelector('meta[name=apple-mobile-web-app-capable]'); out.themeColor=(document.querySelector('meta[name=theme-color]')||{}).content; out.viewport=(document.querySelector('meta[name=viewport]')||{}).content;
                  const regs = navigator.serviceWorker ? await navigator.serviceWorker.getRegistrations() : []; out.serviceWorkers = regs.length; out.hasSWScript=[...document.scripts].some(s=>/sw|service/i.test(s.src));
                  const m = await fetch('/manifest.webmanifest'); out.manifestStatus=m.status; out.manifestType=m.headers.get('content-type'); const j=await m.json(); out.manifest={name:j.name,display:j.display,start_url:j.start_url,icons:j.icons.map(i=>i.sizes+' '+i.purpose)};
                  out.icons={}; for (const u of ['/apple-touch-icon.png','/static/pwa/icon-192.png','/static/pwa/icon-512.png','/static/pwa/icon-maskable-512.png','/favicon.ico']) { const r=await fetch(u); out.icons[u]=r.status+' '+r.headers.get('content-type'); }
                  return out;})()""")
                R['console_errors'] = c.console[:20]
                pump.cancel()
    finally:
        kill_tree(proc)
        shutil.rmtree(tmp, ignore_errors=True)
    return R


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('outdir'); ap.add_argument('--device', default='iphone14'); ap.add_argument('--long', action='store_true')
    a = ap.parse_args()
    res = asyncio.run(run(a.base, a.outdir, a.device, a.long))
    json.dump(res, open(os.path.join(a.outdir, f'b2_report_{a.device}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ('audit', 'shots')}, ensure_ascii=False, indent=1)[:6000])
    for k, v in res['audit'].items():
        print('AUDIT', k, 'smallTargets', v['nSmall'], 'text<14:', v['lt14'], '/', v['textNodes'], 'text<12:', v['nLt12'], 'inputs<16:', len(v['inputsUnder16']), 'overflowX', v['overflowX'])

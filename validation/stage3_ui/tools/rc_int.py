# -*- coding: utf-8 -*-
"""Research Core 正式整合的瀏覽器驗證(無頭 Edge + CDP,只用 aiohttp 與 Pillow)。

usage: python rc_int.py <base_url> <outdir> <scenario> [--profile desktop|mobile] [--symbol SOL-USD] [--tf 4h]
scenarios:
  smoke       載入實驗室,檢查無錯誤、待機為靜態
  live_deep   真實深度分析(實驗室):逐步截圖、事件到達時間線、節點點擊、GIF、與無 job 結果比對
  cancel      真實分析中按取消:前端停止、後端停止
  modal       自選清單彈窗的最佳策略(真實進度列);含『關閉彈窗即取消』
  best_view   最佳策略頁(進度列、無球體)
  phone       iPhone 尺寸:實驗室待機/分析中/完成、觸控點節點、取消鈕、尺寸稽核
  resources   CPU 負載量測(待機/裝飾/分析中/背景分頁)
"""
import asyncio, base64, io, json, os, subprocess, sys, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aiohttp
from shot import CDP, launch, kill_tree, PROFILES

PORT = 9355


async def open_page(url, profile, port=PORT, wait=2.5):
    proc, tmp, ws_url = await launch(port)
    sess = aiohttp.ClientSession(); ws = await sess.ws_connect(ws_url, max_msg_size=0)
    c = CDP(ws); asyncio.get_event_loop().create_task(c.pump())
    p = PROFILES[profile]
    await c.call('Page.enable'); await c.call('Runtime.enable'); await c.call('Log.enable')
    await c.call('Emulation.setDeviceMetricsOverride', dict(width=p['width'], height=p['height'], deviceScaleFactor=p['dsf'], mobile=p['mobile']))
    if p['mobile']:
        await c.call('Emulation.setTouchEmulationEnabled', dict(enabled=True, maxTouchPoints=5))
        await c.call('Emulation.setUserAgentOverride', dict(userAgent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1'))
    await c.call('Page.navigate', dict(url=url)); await asyncio.sleep(wait)
    proc._tmp = tmp
    return proc, tmp, sess, c


async def rect(c, sel):
    return await c.js("(()=>{const e=document.querySelector(%s);if(!e)return null;const b=e.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,w:b.width,h:b.height,vx:b.x,vy:b.y}})()" % json.dumps(sel))


async def shot(c, path, sel=None, full=False, fmt='png', quality=70, scroll=True):
    params = {'format': fmt}
    if fmt == 'jpeg': params['quality'] = quality
    if sel:
        if scroll:
            await c.js("document.querySelector(%s).scrollIntoView({block:'start'})" % json.dumps(sel)); await asyncio.sleep(0.25)
        r = await rect(c, sel)
        params['clip'] = dict(x=r['x'], y=r['y'], width=r['w'], height=r['h'], scale=1); params['captureBeyondViewport'] = True
    elif full:
        params['captureBeyondViewport'] = True
    res = await c.call('Page.captureScreenshot', params)
    data = base64.b64decode(res['data'])
    if path: open(path, 'wb').write(data)
    return data


async def until(c, expr, timeout=240, step=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if await c.js(expr): return True
        except Exception: pass
        await asyncio.sleep(step)
    return False


async def tap(c, x, y):
    await c.call('Input.dispatchTouchEvent', dict(type='touchStart', touchPoints=[dict(x=x, y=y)])); await asyncio.sleep(0.06)
    await c.call('Input.dispatchTouchEvent', dict(type='touchEnd', touchPoints=[])); await asyncio.sleep(0.25)


async def click(c, x, y):
    for t in ('mousePressed', 'mouseReleased'):
        await c.call('Input.dispatchMouseEvent', dict(type=t, x=x, y=y, button='left', clickCount=1)); await asyncio.sleep(0.05)
    await asyncio.sleep(0.25)


def make_gif(frames, path, width=760, ms=140):
    from PIL import Image
    ims = []
    for b in frames:
        im = Image.open(io.BytesIO(b)).convert('RGB'); h = int(im.height * width / im.width); ims.append(im.resize((width, h)).convert('P', palette=Image.ADAPTIVE, colors=96))
    if ims: ims[0].save(path, save_all=True, append_images=ims[1:], duration=ms, loop=0, optimize=True, disposal=2)


TIMELINE_JS = """
window.__tl = []; window.__tl0 = performance.now();
window.__tlTimer = setInterval(() => { try { const m = labState.model, c = m.counted();
  window.__tl.push({t: Math.round(performance.now() - window.__tl0), ec: m.eventCount, st: m.state, stage: c ? c.stage.id : null, i: c ? c.i : null, n: c ? c.n : null}); } catch (e) {} }, 250);
"""   # 這只是測試用的取樣器(量測事件何時到達),不屬於網站程式


async def set_lab_target(c, symbol, tf):
    await c.js("document.getElementById('labCustom').value=%s; document.getElementById('labTf').value=%s; 1" % (json.dumps(symbol), json.dumps(tf)))


async def run(a):
    rep = {}; out = a.out; os.makedirs(out, exist_ok=True)
    start = a.base + ('/#/best' if a.scenario == 'best_view' else ('/' if a.scenario == 'modal' else '/#/lab'))
    proc, tmp, sess, c = await open_page(start, a.profile)
    try:
        sc = a.scenario; P = a.profile
        if sc == 'smoke':
            rep['labCore'] = await c.js("!!document.querySelector('#labCore .rc-box')")
            rep['stats'] = await c.js("JSON.stringify(labState.core.stats())")
            rep['rcpHiddenWhenIdle'] = await c.js("getComputedStyle(document.getElementById('labProg')).display")
            await shot(c, os.path.join(out, 'smoke_%s.png' % P))

        elif sc == 'live_deep':
            await c.js(TIMELINE_JS)
            await set_lab_target(c, a.symbol, a.tf)
            await shot(c, os.path.join(out, 'live_00_standby.png'), '.rc-lab')
            t0 = time.time(); await c.js("runLabView(); 1")
            frames = []; seen = set(); shots = {}
            async def snap(name):
                await shot(c, os.path.join(out, 'live_%s.png' % name), '.rc-lab', scroll=False)
            await c.js("document.querySelector('.rc-lab').scrollIntoView({block:'start'})")
            while time.time() - t0 < 400:
                st = json.loads(await c.js("JSON.stringify((()=>{const m=labState.model,c=m.counted();return {state:m.state,ec:m.eventCount,stage:c?c.stage.id:null,i:c?c.i:null,n:c?c.n:null,stat:Object.fromEntries(Object.entries(m.stages).map(([k,v])=>[k,v.status]))}})())"))
                frames.append(await shot(c, None, '.rc-lab', fmt='jpeg', quality=55, scroll=False))
                if st['stage'] == 'backtest' and st['i'] and st['n'] and 'bt_early' not in shots and st['i'] >= 12: shots['bt_early'] = 1; await snap('01_backtest_early')
                if st['stage'] == 'backtest' and st['i'] and st['n'] and 'bt_mid' not in shots and st['i'] >= st['n'] * 0.5: shots['bt_mid'] = 1; await snap('02_backtest_mid')
                if st['stat'].get('validation') == 'running' and 'val' not in shots: shots['val'] = 1; await snap('03_validation')
                if st['state'] != 'running' and st['ec'] > 0: break
                await asyncio.sleep(0.03)
            rep['elapsedSec'] = round(time.time() - t0, 1)
            await asyncio.sleep(1.2)
            await snap('04_done')
            frames.append(await shot(c, None, '.rc-lab', fmt='jpeg', quality=55, scroll=False))
            make_gif(frames[::3], os.path.join(out, 'live_deep_run.gif'), width=720, ms=140); rep['gifFrames'] = len(frames)
            rep['final'] = await c.js("JSON.stringify({state: labState.model.state, stages: Object.fromEntries(Object.entries(labState.model.stages).map(([k,v])=>[k,{status:v.status,ms:v.ms,events:v.events.length,prog:v.prog}])), stats: labState.core.stats()})")
            tl = json.loads(await c.js("JSON.stringify(window.__tl)")); rep['timeline_samples'] = len(tl)
            # 事件逐步到達:時間線上事件數必須隨時間遞增,而不是結束時一次到齊
            ecs = [x['ec'] for x in tl]; steps = sum(1 for i in range(1, len(ecs)) if ecs[i] > ecs[i - 1])
            rep['timeline'] = {'first_event_ms': next((x['t'] for x in tl if x['ec'] > 0), None), 'last_ms': tl[-1]['t'] if tl else None, 'increments': steps, 'total_events': ecs[-1] if ecs else 0,
                               'ec_at_25pct': ecs[len(ecs) // 4] if ecs else 0, 'ec_at_50pct': ecs[len(ecs) // 2] if ecs else 0, 'ec_at_75pct': ecs[3 * len(ecs) // 4] if ecs else 0}
            json.dump(tl, open(os.path.join(out, 'live_timeline.json'), 'w'))
            # 節點點擊:檢視各階段真實結果
            for stage in ('data', 'backtest', 'validation', 'indicators'):
                r = await rect(c, '.rc-node[data-stage="%s"]' % stage)
                await c.js("document.querySelector('.rc-node[data-stage=\"%s\"]').scrollIntoView({block:'center'})" % stage); await asyncio.sleep(0.3)
                r = await rect(c, '.rc-node[data-stage="%s"]' % stage)
                await click(c, r['vx'] + r['w'] / 2, r['vy'] + r['h'] / 2); await asyncio.sleep(0.3)
                rep['detail_' + stage] = (await c.js("document.getElementById('labDetail').innerText"))[:600]
                await shot(c, os.path.join(out, 'live_node_%s.png' % stage), '.rc-lab')
            # 與沒帶 job 的同一請求比對(真實資料):結果必須相同
            same = await c.js("""(async()=>{const m=labState.data; const per=['4h','1h'].includes('%s')?'2y':'5y';
              const r=await fetch('/api/deep_analysis?symbol=%s&timeframe=%s&use_oos=1'); const d=await r.json();
              return JSON.stringify({sameResults: JSON.stringify(d.results)===JSON.stringify(m.results), sameTested: d.total_tested===m.total_tested, n: (d.results||[]).length});})()""" % (a.tf, a.symbol, a.tf), timeout=400)
            rep['equalToNoJobRun'] = json.loads(same)
            # 輪詢成本
            rep['pollRequests'] = json.loads(await c.js("""JSON.stringify((()=>{const es=performance.getEntriesByType('resource').filter(e=>e.name.includes('/api/job_events'));
              return {count: es.length, transferBytes: es.reduce((s,e)=>s+(e.transferSize||0),0), avgMs: es.length?Math.round(es.reduce((s,e)=>s+e.duration,0)/es.length*10)/10:0}})())"""))
            rep['percentTextSeen'] = await c.js("/\\d+\\s*%/.test(document.getElementById('labProg').innerText)")
            await shot(c, os.path.join(out, 'live_full_page.png'), full=True)

        elif sc == 'cancel':
            await c.js(TIMELINE_JS); await set_lab_target(c, a.symbol, a.tf)
            await c.js("runLabView(); 1")
            ok = await until(c, "(()=>{const c=labState.model.counted();return c && c.stage.id==='backtest' && c.i>=6})()", 180)
            rep['reachedBacktest'] = ok
            before = json.loads(await c.js("JSON.stringify({i: labState.model.counted().i, n: labState.model.counted().n})"))
            await shot(c, os.path.join(out, 'cancel_01_running.png'), '.rc-lab')
            r = await rect(c, '.rcp-cancel'); await c.js("document.querySelector('.rcp-cancel').scrollIntoView({block:'center'})"); await asyncio.sleep(0.3)
            r = await rect(c, '.rcp-cancel'); await click(c, r['vx'] + r['w'] / 2, r['vy'] + r['h'] / 2)
            await asyncio.sleep(1.5)
            rep['before'] = before
            rep['afterClick'] = json.loads(await c.js("JSON.stringify({state: labState.model.state, now: document.querySelector('.rcp-now').textContent, stages: Object.fromEntries(Object.entries(labState.model.stages).map(([k,v])=>[k,v.status])), loopOn: labState.core.stats().loopOn, cancelHidden: document.querySelector('.rcp-cancel').hidden, results: document.getElementById('labRes').innerText.slice(0,80)})"))
            await shot(c, os.path.join(out, 'cancel_02_cancelled.png'), '.rc-lab')
            # 後端:工作狀態為 cancelled,且事件不再增加(代表真的停止運算)
            jid = await c.js("(performance.getEntriesByType('resource').filter(e=>e.name.includes('/api/job_events')).pop()||{}).name.match(/job=([^&]+)/)[1]")
            j1 = await c.js("fetch('/api/job_events?job=%s&after=0').then(r=>r.json()).then(j=>JSON.stringify({status:j.status,last:j.lastSeq}))" % jid)
            await asyncio.sleep(4)
            j2 = await c.js("fetch('/api/job_events?job=%s&after=0').then(r=>r.json()).then(j=>JSON.stringify({status:j.status,last:j.lastSeq}))" % jid)
            rep['server_after_cancel'] = [json.loads(j1), json.loads(j2)]
            rep['serverStoppedGrowing'] = json.loads(j1)['last'] == json.loads(j2)['last']

        elif sc == 'cancel_phases':
            await set_lab_target(c, a.symbol, a.tf)
            await c.js("window.__ph=[]; window.__phT=setInterval(()=>{const m=labState.model; window.__ph.push([Math.round(performance.now()), m.state, document.querySelector('.rcp-now').textContent, document.querySelector('.rcp-cancel').textContent, labState.core.stats().loopOn])},30); runLabView(); 1")
            await until(c, "(()=>{const k=labState.model.counted();return k && k.stage.id==='backtest' && k.i>=6})()", 180, 0.1)
            await c.js("document.querySelector('.rcp-cancel').click(); 1")
            await asyncio.sleep(0.12)
            await shot(c, os.path.join(out, 'cancel_phase_cancelling.png'), '.rc-lab', scroll=False)
            await until(c, "labState.model.state==='cancelled'", 30, 0.1); await asyncio.sleep(0.5)
            ph = json.loads(await c.js("clearInterval(window.__phT); JSON.stringify(window.__ph)"))
            seq = []
            for t, st, txt, btn, loop in ph:
                if not seq or seq[-1][0] != st: seq.append((st, txt, btn, loop))
            rep['phase_sequence'] = seq
            await shot(c, os.path.join(out, 'cancel_phase_cancelled.png'), '.rc-lab', scroll=False)

        elif sc == 'modal':
            await c.js("window.__tl=[];1")
            sid = await c.js("(()=>{const s=stocks[0]; s.symbol='SOL-USD'; s.name='Solana'; s.tf='4h'; s.period='2y'; return s.id})()")   # 只改記憶體中的測試資料,不存檔
            sym = await c.js("(stocks.find(s=>s.id===%s)||{}).symbol" % json.dumps(sid)); rep['symbol'] = sym
            await c.js("runBestStrategy(%s); 1" % json.dumps(sid))
            ok = await until(c, "(()=>{const c=document.querySelector('#analysisProgress .rcp-now');return c && /策略回測 \\d+ \\/ \\d+/.test(c.textContent)})()", 120)
            rep['countShown'] = ok
            rep['text_mid'] = await c.js("document.querySelector('#analysisProgress').innerText.replace(/\\n+/g,' | ')")
            await shot(c, os.path.join(out, 'modal_%s_01_running.png' % P))
            await until(c, "document.querySelector('#analysisProgress .rcp-now').textContent==='完成'", 200)
            rep['text_done'] = await c.js("document.querySelector('#analysisProgress').innerText.replace(/\\n+/g,' | ')")
            await asyncio.sleep(0.5); await shot(c, os.path.join(out, 'modal_%s_02_done.png' % P))
            rep['hasPercentText'] = await c.js("/分析中…|約需|\\d+\\s*%/.test(document.getElementById('analysisProgress').innerText)")
            rep['sphereInModal'] = await c.js("document.querySelectorAll('#analysisBg canvas').length")
            # 關閉彈窗 = 取消
            await c.js("closeAnalysis(); 1"); await asyncio.sleep(0.5)
            await c.js("runBestStrategy(%s); 1" % json.dumps(sid))
            await until(c, "(()=>{const k=modalPv && modalPv.model.counted(); return !!(modalHandle && k && k.stage.id==='backtest' && k.i>=5)})()", 120, 0.1)
            jid = await c.js("modalHandle ? modalHandle.id : null"); rep['cancelJobId'] = jid
            await c.js("closeAnalysis(); 1"); await asyncio.sleep(1.5)
            j1 = json.loads(await c.js("fetch('/api/job_events?job=%s').then(r=>r.json()).then(j=>JSON.stringify({status:j.status,last:j.lastSeq}))" % jid)); await asyncio.sleep(3)
            j2 = json.loads(await c.js("fetch('/api/job_events?job=%s').then(r=>r.json()).then(j=>JSON.stringify({status:j.status,last:j.lastSeq}))" % jid))
            rep['closeModalCancel'] = {'after1.5s': j1, 'after4.5s': j2}

        elif sc == 'best_view':
            await c.js("document.getElementById('bestCustom').value=%s; document.getElementById('bestTf').value=%s; document.getElementById('bestPeriod').value='2y'; runBestView(); 1" % (json.dumps(a.symbol), json.dumps(a.tf)))
            await until(c, "(()=>{const c=document.querySelector('#bestBody .rcp-now');return c && /策略回測 \\d+ \\/ \\d+/.test(c.textContent)})()", 120)
            rep['text_mid'] = await c.js("document.querySelector('#bestBody .rcp').innerText.replace(/\\n+/g,' | ')")
            await shot(c, os.path.join(out, 'best_view_%s_01_running.png' % P), '#bestBody')
            await until(c, "document.querySelector('#bestBody .rcp-now').textContent==='完成'", 200)
            await asyncio.sleep(0.5); await shot(c, os.path.join(out, 'best_view_%s_02_done.png' % P), '#bestBody')
            rep['canvasInBestView'] = await c.js("document.querySelectorAll('#view-best canvas').length")
            rep['bodyHasResults'] = await c.js("!!document.querySelector('#bestBody .cmp-table, #bestBody .cmp-cards')")

        elif sc == 'phone':
            rep['idle'] = json.loads(await c.js("JSON.stringify({stats: labState.core.stats(), overflowX: document.documentElement.scrollWidth > innerWidth, canvasH: document.querySelector('.rc-canvas').getBoundingClientRect().height})"))
            await shot(c, os.path.join(out, 'phone_01_lab_idle.png'), '.rc-lab')
            await set_lab_target(c, a.symbol, a.tf); await c.js("runLabView(); 1")
            await until(c, "(()=>{const c=labState.model.counted();return c && c.stage.id==='backtest' && c.i>=8})()", 180)
            await shot(c, os.path.join(out, 'phone_02_lab_running.png'), '.rc-lab')
            rep['running'] = json.loads(await c.js("JSON.stringify({stats: labState.core.stats(), now: document.querySelector('.rcp-now').textContent})"))
            # 觸控稽核:節點與取消鈕的尺寸
            rep['targets'] = json.loads(await c.js("""JSON.stringify([...document.querySelectorAll('.rc-node,.rcp-cancel,.rcd-go,.rc-opts input')].map(e=>{const b=e.getBoundingClientRect();return {cls:e.className.split(' ')[0],w:Math.round(b.width),h:Math.round(b.height)}}))"""))
            rep['fonts'] = json.loads(await c.js("""JSON.stringify([...document.querySelectorAll('.rc-lab *, .rcp *')].filter(e=>e.children.length===0&&e.textContent.trim()&&e.offsetParent!==null).map(e=>parseFloat(getComputedStyle(e).fontSize)).reduce((a,v)=>{a.min=Math.min(a.min,v);return a},{min:99}))"""))
            rep['smallFontEls'] = json.loads(await c.js("""JSON.stringify([...document.querySelectorAll('.rc-lab *, .rcp *')].filter(e=>e.children.length===0&&e.textContent.trim()&&e.offsetParent!==null&&parseFloat(getComputedStyle(e).fontSize)<12).map(e=>e.className+':'+e.textContent.slice(0,12)))"""))
            # 觸控:點節點 → 詳情
            await c.js("document.querySelector('.rc-node[data-stage=\"backtest\"]').scrollIntoView({block:'center'})"); await asyncio.sleep(0.3)
            r = await rect(c, '.rc-node[data-stage="backtest"]'); await tap(c, r['vx'] + r['w'] / 2, r['vy'] + r['h'] / 2)
            rep['detailAfterTap'] = (await c.js("document.getElementById('labDetail').innerText"))[:240]
            await shot(c, os.path.join(out, 'phone_03_node_tapped.png'), '.rc-lab')
            # 觸控:取消
            await c.js("document.querySelector('.rcp-cancel').scrollIntoView({block:'center'})"); await asyncio.sleep(0.3)
            r = await rect(c, '.rcp-cancel'); await tap(c, r['vx'] + r['w'] / 2, r['vy'] + r['h'] / 2); await asyncio.sleep(1.2)
            rep['afterCancel'] = json.loads(await c.js("JSON.stringify({state: labState.model.state, now: document.querySelector('.rcp-now').textContent, overflowX: document.documentElement.scrollWidth > innerWidth, stats: labState.core.stats()})"))
            await shot(c, os.path.join(out, 'phone_04_cancelled.png'), '.rc-lab')

        rep['console'] = c.console
        json.dump(rep, open(os.path.join(out, 'report_%s_%s.json' % (a.scenario, a.profile)), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(json.dumps(rep, ensure_ascii=False, indent=1)[:6000])
    finally:
        await sess.close(); kill_tree(proc)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('out'); ap.add_argument('scenario')
    ap.add_argument('--profile', default='desktop'); ap.add_argument('--symbol', default='SOL-USD'); ap.add_argument('--tf', default='4h')
    asyncio.run(run(ap.parse_args()))

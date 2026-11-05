# -*- coding: utf-8 -*-
"""Screenshot tool: drives a headless Edge/Chrome through the Chrome DevTools Protocol using only aiohttp (already a ccxt
dependency). No new packages. Saves PNG files and reports console errors.

usage: python shot.py <base_url> <outdir> <prefix> [--profile desktop|mobile|both] [--scenarios a,b,c]
scenarios: watchlist | best | deep
"""
import asyncio, json, os, sys, shutil, subprocess, tempfile, time, argparse
import aiohttp

EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
BROWSER = EDGE if os.path.exists(EDGE) else CHROME
PROFILES = {'desktop': dict(width=1440, height=900, mobile=False, dsf=1),
            'mobile': dict(width=390, height=844, mobile=True, dsf=2)}


class CDP:
    def __init__(self, ws):
        self.ws = ws; self.i = 0; self.pending = {}; self.events = []; self.console = []

    async def pump(self):
        async for msg in self.ws:
            if msg.type != aiohttp.WSMsgType.TEXT: continue
            d = json.loads(msg.data)
            if 'id' in d and d['id'] in self.pending:
                self.pending.pop(d['id']).set_result(d)
            else:
                self.events.append(d)
                m = d.get('method')
                if m == 'Runtime.consoleAPICalled' and d['params']['type'] in ('error', 'warning'):
                    self.console.append((d['params']['type'], ' '.join(str(a.get('value', a.get('description', ''))) for a in d['params']['args'])[:300]))
                elif m == 'Runtime.exceptionThrown':
                    self.console.append(('exception', d['params']['exceptionDetails'].get('text', '') + ' ' + str(d['params']['exceptionDetails'].get('exception', {}).get('description', ''))[:300]))
                elif m == 'Log.entryAdded' and d['params']['entry']['level'] in ('error',):
                    self.console.append(('log-error', d['params']['entry']['text'][:300] + ' ' + d['params']['entry'].get('url', '')))

    async def call(self, method, params=None, timeout=60):
        self.i += 1; fut = asyncio.get_event_loop().create_future(); self.pending[self.i] = fut
        await self.ws.send_str(json.dumps({'id': self.i, 'method': method, 'params': params or {}}))
        d = await asyncio.wait_for(fut, timeout)
        if 'error' in d: raise RuntimeError('%s: %s' % (method, d['error']))
        return d.get('result', {})

    async def js(self, expr, timeout=60):
        r = await self.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, timeout)
        if 'exceptionDetails' in r: raise RuntimeError('js error: ' + (json.dumps(r['exceptionDetails'], ensure_ascii=False)[:300] + ' || ' + str(r['exceptionDetails'].get('exception',{}).get('description',''))[:600]))
        return r['result'].get('value')


def kill_tree(proc):
    """Edge re-spawns itself as a detached browser process, so killing only our PID leaves browsers behind (and a later run on the same
    port reconnects to the OLD browser with its old localStorage). Kill every msedge whose command line has our debugging port."""
    port = getattr(proc, '_port', None)
    if port:
        ps = "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -match 'remote-debugging-port=%d ' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" % port
        try: subprocess.run(['powershell', '-NoProfile', '-Command', ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        except Exception: pass
    try: proc.terminate()
    except Exception: pass


async def launch(port):
    tmp = tempfile.mkdtemp(prefix='shot_profile_')
    proc = subprocess.Popen([BROWSER, '--headless=new', '--remote-debugging-port=%d' % port, '--user-data-dir=' + tmp, '--no-first-run',
                             '--disable-extensions', '--disable-gpu', '--disk-cache-size=1', '--aggressive-cache-discard', '--hide-scrollbars', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    async with aiohttp.ClientSession() as s:
        for _ in range(60):
            try:
                async with s.get('http://127.0.0.1:%d/json/version' % port) as r:
                    if r.status == 200: break
            except Exception: pass
            await asyncio.sleep(0.5)
        async with s.get('http://127.0.0.1:%d/json' % port) as r:
            targets = await r.json()
    page = next(t for t in targets if t.get('type') == 'page')
    proc._port = port
    return proc, tmp, page['webSocketDebuggerUrl']


async def run(base, outdir, prefix, profiles, scenarios):
    os.makedirs(outdir, exist_ok=True)
    report = {}
    for pname in profiles:
        p = PROFILES[pname]
        proc, tmp, wsurl = await launch(9333 if pname == 'desktop' else 9334)
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.ws_connect(wsurl, max_msg_size=0) as ws:
                    c = CDP(ws); pump = asyncio.ensure_future(c.pump())
                    for dom in ('Page', 'Runtime', 'Log'): await c.call(dom + '.enable')
                    await c.call('Emulation.setDeviceMetricsOverride', dict(width=p['width'], height=p['height'], deviceScaleFactor=p['dsf'], mobile=p['mobile']))
                    if p['mobile']:
                        await c.call('Emulation.setTouchEmulationEnabled', {'enabled': True})
                        await c.call('Emulation.setUserAgentOverride', {'userAgent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'})
                    await c.call('Page.navigate', {'url': base})
                    await asyncio.sleep(3)
                    await c.js("(()=>{try{if(typeof closeIntro==='function')closeIntro();}catch(e){} const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('我知道了')); if(b)b.click(); return 1;})()")
                    # trigger lazy loading of every card by scrolling, then wait until they report loaded
                    await c.js("(async()=>{for(let y=0;y<document.body.scrollHeight;y+=500){window.scrollTo(0,y);await new Promise(r=>setTimeout(r,250));} window.scrollTo(0,0);return 1;})()")
                    t0 = time.time()
                    while time.time() - t0 < 90:
                        n = await c.js("(()=>{const cs=[...document.querySelectorAll('.card')]; return cs.length? cs.filter(x=>x.dataset.loaded==='1').length+'/'+cs.length : '0/0';})()")
                        a, b = n.split('/')
                        if b != '0' and a == b: break
                        await asyncio.sleep(1.5)
                    await asyncio.sleep(2)
                    report[pname] = {'cards_loaded': n}
                    for sc in scenarios:
                        if sc == 'watchlist':
                            m = await c.call('Page.getLayoutMetrics')
                            h = int(min(m['cssContentSize']['height'], 7000))
                            r = await c.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True, 'clip': {'x': 0, 'y': 0, 'width': p['width'], 'height': h, 'scale': 1}})
                            fn = os.path.join(outdir, '%s_%s_watchlist.png' % (prefix, pname)); open(fn, 'wb').write(__import__('base64').b64decode(r['data'])); report[pname]['watchlist'] = fn
                            r = await c.call('Page.captureScreenshot', {'format': 'png'})
                            fn = os.path.join(outdir, '%s_%s_firstscreen.png' % (prefix, pname)); open(fn, 'wb').write(__import__('base64').b64decode(r['data'])); report[pname]['firstscreen'] = fn
                        elif sc in ('best', 'deep'):
                            fnname = 'runBestStrategy' if sc == 'best' else 'runDeepAnalysis'
                            sid = await c.js("(()=>{const s=(stocks||[]).find(x=>x.symbol.includes('SOL'))||stocks[0]; return s.id;})()")
                            await c.js("%s(%s,{stopPropagation(){}}); 1" % (fnname, sid))
                            t0 = time.time()
                            while time.time() - t0 < 180:
                                txt = await c.js("document.getElementById('progressText')?document.getElementById('progressText').textContent:''")
                                if '完成' in (txt or '') or '❌' in (txt or '') or '失敗' in (txt or ''): break
                                await asyncio.sleep(2)
                            await asyncio.sleep(1.5)
                            r = await c.call('Page.captureScreenshot', {'format': 'png'})
                            fn = os.path.join(outdir, '%s_%s_%s.png' % (prefix, pname, sc)); open(fn, 'wb').write(__import__('base64').b64decode(r['data'])); report[pname][sc] = fn
                            await c.js("try{closeAnalysis();}catch(e){} 1")
                    report[pname]['console_errors'] = c.console[:20]
                    pump.cancel()
        finally:
            kill_tree(proc)
            shutil.rmtree(tmp, ignore_errors=True)
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('base'); ap.add_argument('outdir'); ap.add_argument('prefix')
    ap.add_argument('--profile', default='both'); ap.add_argument('--scenarios', default='watchlist,best')
    a = ap.parse_args()
    profiles = ['desktop', 'mobile'] if a.profile == 'both' else [a.profile]
    rep = asyncio.run(run(a.base, a.outdir, a.prefix, profiles, a.scenarios.split(',')))
    print(json.dumps(rep, ensure_ascii=False, indent=1))

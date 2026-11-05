# -*- coding: utf-8 -*-
"""Research Core v1 vs v2: screenshots, short GIFs (PIL) and CPU measurements via CDP.
usage: python rc_shots.py <site_base_url> <outdir> [--perf]"""
import asyncio, base64, io, json, os, sys, time, pathlib, argparse
import aiohttp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import CDP, launch, kill_tree
ROOT = pathlib.Path(__file__).resolve().parents[3]
V1 = (ROOT / 'static/prototype/research-core.html').as_uri()
V2 = (ROOT / 'static/prototype/research-core-v2.html').as_uri()
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'


async def new_browser(port, w, h, mobile=False):
    proc, tmp, ws_url = await launch(port)
    sess = aiohttp.ClientSession(); ws = await sess.ws_connect(ws_url, max_msg_size=0)
    c = CDP(ws); c._pump = asyncio.ensure_future(c.pump())
    for d in ('Page', 'Runtime', 'Log', 'Performance', 'Network'): await c.call(d + '.enable')
    await c.call('Network.setCacheDisabled', {'cacheDisabled': True})
    await c.call('Emulation.setDeviceMetricsOverride', dict(width=w, height=h, deviceScaleFactor=2 if mobile else 1, mobile=mobile))
    if mobile:
        await c.call('Emulation.setTouchEmulationEnabled', {'enabled': True}); await c.call('Emulation.setUserAgentOverride', {'userAgent': UA})
    return proc, sess, ws, c


async def close(proc, sess, ws, c):
    c._pump.cancel(); await ws.close(); await sess.close(); kill_tree(proc)


async def png(c, path, scale=1.0):
    r = await c.call('Page.captureScreenshot', {'format': 'png'}); open(path, 'wb').write(base64.b64decode(r['data'])); return os.path.basename(path)


async def frames(c, n, interval=0.0, scale=0.5):
    from PIL import Image
    out = []
    for _ in range(n):
        r = await c.call('Page.captureScreenshot', {'format': 'jpeg', 'quality': 70})
        im = Image.open(io.BytesIO(base64.b64decode(r['data']))).convert('P', palette=Image.ADAPTIVE)
        im = im.resize((int(im.width * scale), int(im.height * scale))); out.append(im)
        if interval: await asyncio.sleep(interval)
    return out


def save_gif(fr, path, ms=180):
    fr[0].save(path, save_all=True, append_images=fr[1:], duration=ms, loop=0, optimize=True); return os.path.basename(path)


async def metrics(c):
    return {m['name']: m['value'] for m in (await c.call('Performance.getMetrics'))['metrics']}


async def measure(c, seconds, label, js_stats):
    m0 = await metrics(c); t0 = time.time(); await asyncio.sleep(seconds); m1 = await metrics(c); wall = time.time() - t0
    d = lambda k: m1.get(k, 0) - m0.get(k, 0)
    st = await c.js(js_stats) if js_stats else None
    return {'scenario': label, 'seconds': round(wall, 1), 'main_thread_busy_pct': round(100 * d('TaskDuration') / wall, 2), 'script_pct': round(100 * d('ScriptDuration') / wall, 2), 'stats': st}


async def main(site, out, perf):
    os.makedirs(out, exist_ok=True); rep = {'shots': [], 'perf': []}
    live = site.rstrip('/') + '/static/prototype/research-core-v2.html'
    # ---------- v1 (original) desktop
    P = await new_browser(9401, 1440, 900); c = P[3]
    await c.call('Page.navigate', {'url': V1}); await asyncio.sleep(2.5)
    rep['shots'].append(await png(c, os.path.join(out, 'rc_v1_idle.png')))
    await c.js("document.getElementById('b-normal').click(); 1"); await asyncio.sleep(2.0)
    rep['shots'].append(await png(c, os.path.join(out, 'rc_v1_running.png')))
    g1 = await frames(c, 24, 0.0, 0.5); save_gif(g1, os.path.join(out, 'rc_v1_running.gif'), 200)
    await asyncio.sleep(5); rep['shots'].append(await png(c, os.path.join(out, 'rc_v1_done.png')))
    rep['v1_console'] = c.console[:5]; await close(*P)

    # ---------- v2 desktop (file:// — also proves the page works when opened by double-click)
    P = await new_browser(9402, 1440, 900); c = P[3]
    await c.call('Page.navigate', {'url': V2}); await asyncio.sleep(2.5)
    rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_idle.png')))
    g = await frames(c, 14, 0.12, 0.5); save_gif(g, os.path.join(out, 'rc_v2_idle_ambient.gif'), 140)
    await c.js("document.getElementById('rc-trace').value='best-sol-4h'; document.getElementById('rc-speed').value='1'; document.getElementById('rc-replay').click(); 1")
    await asyncio.sleep(1.2); rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_replay_backtest.png')))
    g2 = await frames(c, 30, 0.0, 0.5); save_gif(g2, os.path.join(out, 'rc_v2_replay_best.gif'), 170)
    await asyncio.sleep(2.5); rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_replay_done.png')))
    rep['replay_state'] = await c.js("ResearchCoreV2.stats()")
    await c.js("document.getElementById('rc-trace').value='analyze-2330'; document.getElementById('rc-replay').click(); 1"); await asyncio.sleep(3.2)
    rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_replay_analyze_done.png')))
    await c.js("document.getElementById('rc-trace').value='error-bad-symbol'; document.getElementById('rc-replay').click(); 1"); await asyncio.sleep(2.0)
    rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_replay_error.png')))
    rep['v2_console_file'] = c.console[:5]; await close(*P)

    # ---------- v2 LIVE against the real server (real API call + real polling)
    P = await new_browser(9403, 1440, 900); c = P[3]
    await c.call('Page.navigate', {'url': live}); await asyncio.sleep(2.5)
    await c.js("document.getElementById('rc-kind').value='best'; document.getElementById('rc-symbol').value='SOL-USD'; document.getElementById('rc-tf').value='4h'; document.getElementById('rc-start').click(); 1")
    await asyncio.sleep(2.4); rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_live_best_mid.png')))
    live_log = []
    for _ in range(40):
        s = await c.js("({mode: document.getElementById('rc-mode').textContent, rows: document.querySelectorAll('#rc-log .rc-log-row').length, st: ResearchCoreV2.stats()})"); live_log.append(s)
        if '結束' in s['mode']: break
        await asyncio.sleep(0.5)
    await asyncio.sleep(0.8); rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_live_best_done.png')))
    rep['live_final'] = live_log[-1]; rep['live_log_rows_seen'] = [x['rows'] for x in live_log]
    rep['live_result'] = await c.js("document.getElementById('rc-result').innerText")
    await c.js("document.getElementById('rc-kind').value='analyze'; document.getElementById('rc-symbol').value='AAPL'; document.getElementById('rc-tf').value='1d'; document.getElementById('rc-strat').value='tsmom'; document.getElementById('rc-start').click(); 1")
    await asyncio.sleep(6.0); rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_live_analyze_done.png')))
    rep['live_analyze_result'] = await c.js("document.getElementById('rc-result').innerText"); rep['live_console'] = c.console[:5]
    await close(*P)

    # ---------- v2 reduced-motion + phone
    P = await new_browser(9404, 1440, 900); c = P[3]
    await c.call('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
    await c.call('Page.navigate', {'url': V2}); await asyncio.sleep(2.0)
    await c.js("document.getElementById('rc-trace').value='best-sol-4h'; document.getElementById('rc-speed').value='4'; document.getElementById('rc-replay').click(); 1"); await asyncio.sleep(2.6)
    rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_reduced_motion.png'))); rep['reduced_stats'] = await c.js("ResearchCoreV2.stats()"); await close(*P)
    P = await new_browser(9405, 390, 844, mobile=True); c = P[3]
    await c.call('Page.navigate', {'url': V2}); await asyncio.sleep(2.0)
    rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_phone_idle.png')))
    await c.js("document.getElementById('rc-trace').value='best-sol-4h'; document.getElementById('rc-speed').value='4'; document.getElementById('rc-replay').click(); 1"); await asyncio.sleep(2.2)
    rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_phone_running.png'))); rep['phone_stats'] = await c.js("ResearchCoreV2.stats()")
    await asyncio.sleep(2.0); rep['shots'].append(await png(c, os.path.join(out, 'rc_v2_phone_done.png'))); await close(*P)

    if perf:
        S = "(()=>{return window.ResearchCoreV2?ResearchCoreV2.stats():null})()"
        P = await new_browser(9406, 1440, 900); c = P[3]
        await c.call('Page.navigate', {'url': V2}); await asyncio.sleep(2.0)
        await c.js("document.getElementById('rc-ambient').checked=false; document.getElementById('rc-ambient').dispatchEvent(new Event('change')); 1"); await asyncio.sleep(1.0)
        rep['perf'].append(await measure(c, 5, 'v2 baseline: decorative animation OFF (page only)', S))
        await c.js("document.getElementById('rc-ambient').checked=true; document.getElementById('rc-ambient').dispatchEvent(new Event('change')); 1"); await asyncio.sleep(1.0)
        rep['perf'].append(await measure(c, 7, 'v2 idle with decorative animation ON (12 fps cap)', S))
        await c.js("document.getElementById('rc-trace').value='best-sol-4h'; document.getElementById('rc-speed').value='1'; document.getElementById('rc-replay').click(); 1")
        rep['perf'].append(await measure(c, 6, 'v2 while real events stream (replay of a real 6.5 s ranking; 30 fps cap)', S))
        await asyncio.sleep(3)
        await c.call('Emulation.setCPUThrottlingRate', {'rate': 4})
        await c.js("document.getElementById('rc-replay').click(); 1")
        rep['perf'].append(await measure(c, 6, 'v2 streaming events with 4x CPU slowdown', S))
        await c.call('Emulation.setCPUThrottlingRate', {'rate': 1}); await asyncio.sleep(8)
        await c.js("window.scrollTo(0, 99999); 1"); await asyncio.sleep(1)
        await c.js("ResearchCoreV2._forceVisibility(true); 1")
        rep['perf'].append(await measure(c, 4, 'v2 tab hidden', S)); await c.js("ResearchCoreV2._forceVisibility(false); 1")
        await close(*P)
        # v1 reference numbers measured the same way
        P = await new_browser(9407, 1440, 900); c = P[3]
        await c.call('Page.navigate', {'url': V1}); await asyncio.sleep(2.0)
        S1 = "(()=>ResearchCore.stats())()"
        rep['perf'].append(await measure(c, 5, 'v1 (original) idle', S1))
        await c.js("document.getElementById('b-normal').click(); 1")
        rep['perf'].append(await measure(c, 6, 'v1 (original) running simulated pipeline', S1)); await close(*P)
    json.dump(rep, open(os.path.join(out, 'rc_report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != 'shots'}, ensure_ascii=False, indent=1)[:5000]); print(rep['shots'])

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('site'); ap.add_argument('out'); ap.add_argument('--perf', action='store_true'); a = ap.parse_args()
    asyncio.run(main(a.site, a.out, a.perf))

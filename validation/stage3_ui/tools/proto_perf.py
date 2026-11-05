# -*- coding: utf-8 -*-
"""Screenshots + performance measurements of the research-core prototype via CDP (aiohttp only, no new packages).
usage: python proto_perf.py <url> <outdir>"""
import asyncio, base64, json, os, sys, time
import aiohttp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import CDP, launch, kill_tree
import shutil


async def metrics(c):
    r = await c.call('Performance.getMetrics')
    return {m['name']: m['value'] for m in r['metrics']}


async def measure(c, seconds, label, setup=None):
    if setup: await setup()
    m0 = await metrics(c); t0 = time.time(); s0 = await c.js('ResearchCore.stats()')
    await asyncio.sleep(seconds)
    m1 = await metrics(c); t1 = time.time(); s1 = await c.js('ResearchCore.stats()')
    wall = t1 - t0
    d = lambda k: m1.get(k, 0) - m0.get(k, 0)
    frames = s1['frames'] - s0['frames']
    return {'scenario': label, 'seconds': round(wall, 1),
            'main_thread_busy_pct': round(100 * d('TaskDuration') / wall, 2),
            'script_pct': round(100 * d('ScriptDuration') / wall, 2),
            'layout_style_pct': round(100 * (d('LayoutDuration') + d('RecalcStyleDuration')) / wall, 2),
            'frames_drawn': frames, 'fps': round(frames / wall, 1),
            'avg_draw_ms': round(s1['emaMs'], 2), 'heap_mb': round(m1.get('JSHeapUsedSize', 0) / 1e6, 2),
            'loopOn': s1['loopOn'], 'particles_max_seen': s1['particles'], 'lowPower': s1['lowPower'], 'forcedStatic': s1['forcedStatic']}


async def shot(c, path, clip=None):
    p = {'format': 'png'}
    if clip: p['clip'] = clip
    r = await c.call('Page.captureScreenshot', p)
    open(path, 'wb').write(base64.b64decode(r['data'])); return path


async def run(url, outdir):
    os.makedirs(outdir, exist_ok=True)
    out = {'perf': [], 'shots': []}
    for prof in ('desktop', 'mobile'):
        proc, tmp, wsurl = await launch(9341 if prof == 'desktop' else 9342)
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.ws_connect(wsurl, max_msg_size=0) as ws:
                    c = CDP(ws); pump = asyncio.ensure_future(c.pump())
                    for dom in ('Page', 'Runtime', 'Log', 'Performance'): await c.call(dom + '.enable')
                    if prof == 'desktop':
                        await c.call('Emulation.setDeviceMetricsOverride', dict(width=1440, height=900, deviceScaleFactor=1, mobile=False))
                    else:
                        await c.call('Emulation.setDeviceMetricsOverride', dict(width=390, height=844, deviceScaleFactor=2, mobile=True))
                        await c.call('Emulation.setTouchEmulationEnabled', {'enabled': True})
                    await c.call('Page.navigate', {'url': url}); await asyncio.sleep(2.5)
                    if prof == 'mobile':
                        out['perf'].append(await measure(c, 4, 'mobile (390px): simplified 2D route list'))
                        out['shots'].append(await shot(c, os.path.join(outdir, 'proto_mobile_idle.png')))
                        await c.js("document.getElementById('b-normal').click()"); await asyncio.sleep(2.2)
                        out['shots'].append(await shot(c, os.path.join(outdir, 'proto_mobile_running.png')))
                        await asyncio.sleep(6)
                        out['shots'].append(await shot(c, os.path.join(outdir, 'proto_mobile_done.png')))
                        out['console_mobile'] = c.console[:10]; pump.cancel(); continue
                    # ---- desktop screenshots
                    out['shots'].append(await shot(c, os.path.join(outdir, 'proto_desktop_idle.png'), {'x': 0, 'y': 0, 'width': 1440, 'height': 900, 'scale': 1}))
                    await c.js("document.getElementById('b-normal').click()"); await asyncio.sleep(1.9)
                    out['shots'].append(await shot(c, os.path.join(outdir, 'proto_desktop_running.png')))
                    await asyncio.sleep(7)
                    out['shots'].append(await shot(c, os.path.join(outdir, 'proto_desktop_done.png')))
                    await c.js("document.getElementById('b-weak').click()"); await asyncio.sleep(8)
                    out['shots'].append(await shot(c, os.path.join(outdir, 'proto_desktop_weak.png')))
                    await c.js("document.getElementById('b-nodata').click()"); await asyncio.sleep(3)
                    out['shots'].append(await shot(c, os.path.join(outdir, 'proto_desktop_nodata.png')))
                    # ---- performance
                    await c.js("document.getElementById('b-reset').click()"); await asyncio.sleep(1)
                    async def motion_off(): await c.js("(()=>{const e=document.getElementById('motion'); e.checked=false; e.dispatchEvent(new Event('change')); return 1})()")
                    async def motion_on(): await c.js("(()=>{const e=document.getElementById('motion'); e.checked=true; e.dispatchEvent(new Event('change')); return 1})()")
                    out['perf'].append(await measure(c, 5, 'baseline: motion OFF (page only, no animation loop)', motion_off))
                    out['perf'].append(await measure(c, 6, 'standby (default): static, no animation loop', motion_on))
                    async def amb_on(): await c.js("(()=>{const e=document.getElementById('ambient'); e.checked=true; e.dispatchEvent(new Event('change')); return 1})()")
                    async def amb_off(): await c.js("(()=>{const e=document.getElementById('ambient'); e.checked=false; e.dispatchEvent(new Event('change')); return 1})()")
                    out['perf'].append(await measure(c, 8, 'standby with OPTIONAL decorative rotation ON (15 fps)', amb_on))
                    await amb_off(); await asyncio.sleep(1)
                    async def go(): await c.js("document.getElementById('b-normal').click()")
                    out['perf'].append(await measure(c, 6.5, 'running pipeline: rotation paused, particles flowing', go))
                    await asyncio.sleep(1.5)
                    await c.call('Emulation.setCPUThrottlingRate', {'rate': 4})
                    out['perf'].append(await measure(c, 6.5, 'running pipeline with 4x CPU slowdown', go))
                    await c.call('Emulation.setCPUThrottlingRate', {'rate': 1})
                    await asyncio.sleep(2)
                    # off-screen: scroll the core out of view
                    async def scroll_away(): await c.js("window.scrollTo(0, document.body.scrollHeight); 1"); await asyncio.sleep(1)
                    out['perf'].append(await measure(c, 4, 'core scrolled OFF-SCREEN (IntersectionObserver pause)', scroll_away))
                    await c.js("window.scrollTo(0,0); 1"); await asyncio.sleep(1)
                    # hidden tab (visibility handler)
                    async def hide(): await c.js("ResearchCore._forceVisibility(true); 1")
                    out['perf'].append(await measure(c, 3, 'tab hidden (visibilitychange handler)', hide))
                    await c.js("ResearchCore._forceVisibility(false); 1"); await asyncio.sleep(1)
                    # reduced motion
                    await c.call('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
                    await asyncio.sleep(1)
                    out['reduced_state_after_media_change'] = await c.js('ResearchCore.stats()')
                    async def go2(): await c.js("document.getElementById('b-normal').click()")
                    out['perf'].append(await measure(c, 7.5, 'prefers-reduced-motion: reduce, full simulated analysis', go2))
                    out['shots'].append(await shot(c, os.path.join(outdir, 'proto_desktop_reduced_motion.png')))
                    out['console_desktop'] = c.console[:10]
                    pump.cancel()
        finally:
            kill_tree(proc)
            shutil.rmtree(tmp, ignore_errors=True)
    return out

if __name__ == '__main__':
    res = asyncio.run(run(sys.argv[1], sys.argv[2]))
    json.dump(res, open(os.path.join(sys.argv[2], 'proto_perf.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(res['perf'], ensure_ascii=False, indent=1)); print('reduced:', res.get('reduced_state_after_media_change')); print('console:', res.get('console_desktop'), res.get('console_mobile')); print(res['shots'])

# -*- coding: utf-8 -*-
"""iPhone landscape (844x390) screenshots: watchlist, expanded card, symbol view. usage: python landscape.py <base> <outdir>"""
import asyncio, base64, os, sys
import aiohttp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import CDP, launch, kill_tree
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'


async def main(base, out):
    os.makedirs(out, exist_ok=True)
    proc, tmp, ws_url = await launch(9381)
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.ws_connect(ws_url, max_msg_size=0) as ws:
                c = CDP(ws); pump = asyncio.ensure_future(c.pump())
                for d in ('Page', 'Runtime', 'Network'): await c.call(d + '.enable')
                await c.call('Network.setCacheDisabled', {'cacheDisabled': True})
                await c.call('Emulation.setDeviceMetricsOverride', dict(width=844, height=390, deviceScaleFactor=2, mobile=True))
                await c.call('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 5})
                await c.call('Emulation.setUserAgentOverride', {'userAgent': UA})
                await c.call('Page.navigate', {'url': base}); await asyncio.sleep(9)
                await c.js("try{closeIntro()}catch(e){} 1")

                async def snap(name):
                    r = await c.call('Page.captureScreenshot', {'format': 'png'}); open(os.path.join(out, name), 'wb').write(base64.b64decode(r['data'])); print(name)
                await snap('b2_landscape_01_watchlist.png')
                await c.js("toggleCardDetail(stocks[0].id); document.getElementById('card-'+stocks[0].id).scrollIntoView(); window.scrollBy(0,-60); 1"); await asyncio.sleep(1.5)
                await snap('b2_landscape_02_card_expanded.png')
                await c.js("openModal(stocks[0].id); 1"); await asyncio.sleep(1.5)
                await snap('b2_landscape_03_chart_modal.png')
                print(await c.js("({bottomTabs:getComputedStyle(document.getElementById('bottomTabs')).display, nav:getComputedStyle(document.getElementById('mainNav')).display, overflowX:document.scrollingElement.scrollWidth>innerWidth+1})"))
                print('console', c.console[:5])
                pump.cancel()
    finally:
        kill_tree(proc)

asyncio.run(main(sys.argv[1], sys.argv[2]))

# -*- coding: utf-8 -*-
"""Extract reference frames from a local video using headless Edge (no ffmpeg/opencv needed). Study use only; frames are not committed.
usage: python video_frames.py <video.mp4> <outdir> [n_frames]"""
import asyncio, base64, os, sys, json, pathlib
import aiohttp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import CDP, launch, kill_tree


async def main(video, out, n):
    os.makedirs(out, exist_ok=True)
    url = pathlib.Path(video).resolve().as_uri()
    proc, tmp, ws_url = await launch(9391)
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.ws_connect(ws_url, max_msg_size=0) as ws:
                c = CDP(ws); pump = asyncio.ensure_future(c.pump())
                for d in ('Page', 'Runtime'): await c.call(d + '.enable')
                await c.call('Emulation.setDeviceMetricsOverride', dict(width=1280, height=720, deviceScaleFactor=1, mobile=False))
                await c.call('Page.navigate', {'url': url})
                await asyncio.sleep(2.5)
                info = await c.js("new Promise(r=>{const v=document.querySelector('video'); const done=()=>r({d:v.duration,w:v.videoWidth,h:v.videoHeight,err:v.error&&v.error.code}); if(v.readyState>=1) done(); else {v.onloadedmetadata=done; v.onerror=done; setTimeout(done,8000);}})")
                print('video info', info)
                if not info or not info.get('d'): print('cannot decode video'); return
                dur = info['d']
                for i in range(n):
                    t = dur * (i + 0.5) / n
                    await c.js("new Promise(r=>{const v=document.querySelector('video'); v.onseeked=()=>setTimeout(r,250); v.currentTime=%f;})" % t)
                    r = await c.call('Page.captureScreenshot', {'format': 'jpeg', 'quality': 80})
                    open(os.path.join(out, 'f%02d_%05.1fs.jpg' % (i, t)), 'wb').write(base64.b64decode(r['data']))
                print('saved', n)
                pump.cancel()
    finally:
        kill_tree(proc)

asyncio.run(main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12))

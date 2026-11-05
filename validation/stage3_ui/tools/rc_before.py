# -*- coding: utf-8 -*-
"""整合『前』截圖:對 99fd0e0(整合前)的網站跑同樣的真實分析,拍下依時間推算的假進度條。

usage: python rc_before.py <base_url_of_old_site> <outdir> [--profile desktop|mobile]
"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rc_int import open_page, shot, until, rect
from shot import kill_tree


async def main():
    base, out = sys.argv[1], sys.argv[2]; prof = sys.argv[3] if len(sys.argv) > 3 else 'desktop'
    os.makedirs(out, exist_ok=True); rep = {}
    proc, tmp, sess, c = await open_page(base + '/#/lab', prof, port=9370)
    try:
        await c.js("document.getElementById('labCustom').value='SOL-USD'; document.getElementById('labTf').value='1h'; runLabView(); 1")
        await asyncio.sleep(4)
        rep['progress_text_t4s'] = await c.js("document.querySelector('#labBody [data-pt]').textContent")
        await shot(c, os.path.join(out, 'before_%s_lab_running_t4s.png' % prof), '#labBody')
        await asyncio.sleep(8)
        rep['progress_text_t12s'] = await c.js("document.querySelector('#labBody [data-pt]').textContent")
        rep['bar_width_t12s'] = await c.js("document.querySelector('#labBody [data-pb]').style.width")
        await shot(c, os.path.join(out, 'before_%s_lab_running_t12s.png' % prof), '#labBody')
        await until(c, "/完成/.test(document.querySelector('#labBody [data-pt]').textContent)", 200)
        await shot(c, os.path.join(out, 'before_%s_lab_done.png' % prof), '#labBody')
        rep['console'] = c.console
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        json.dump(rep, open(os.path.join(out, 'before_report_%s.json' % prof), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    finally:
        await sess.close(); kill_tree(proc)

asyncio.run(main())

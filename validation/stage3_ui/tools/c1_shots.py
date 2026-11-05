# -*- coding: utf-8 -*-
"""C1 截圖與畫面檢查(無頭 Edge + CDP)。

usage: python c1_shots.py <base_url> <outdir> <scenario> [--profile desktop|mobile] [--prefix real]
scenarios:
  mtf      市場環境 → 多週期:5 個標的各跑一次(再重跑一次 BTC 以顯示『使用快取』)
  cards    自選清單:資料過期的卡片與導覽列(用狀態範例伺服器)
  audit    手機尺寸稽核(觸控目標、字級、橫向溢出)
"""
import asyncio, json, os, sys, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rc_int import open_page, shot, until, click, tap, rect

SYMS = ['BTC/USDT', 'SOL/USDT', '2330.TW', 'AAPL', 'NVDA']


async def run_one(c, sym, out, prefix, profile, tag=''):
    await c.js("document.getElementById('mtfCustom').value=%s; runMtfView(); 1" % json.dumps(sym))
    t0 = time.time(); mid = None
    while time.time() - t0 < 90:
        st = await c.js("JSON.stringify({running: !document.getElementById('mtfRun').disabled ? false : true, now: (document.querySelector('#mtfProg .rcp-now')||{}).textContent||''})")
        st = json.loads(st)
        if st['running'] and mid is None and time.time() - t0 > 0.8:
            mid = await c.js("document.getElementById('mtfProg').innerText.replace(/\\n+/g,' | ')")
        if not st['running'] and await c.js("!!document.querySelector('#mtfBody .mtf-table')"): break
        await asyncio.sleep(0.25)
    name = sym.replace('/', '-')
    await asyncio.sleep(0.5)
    await shot(c, os.path.join(out, '%s_%s_%s%s.png' % (prefix, profile, name, tag)), '#mtfPanel')
    rows = json.loads(await c.js("""JSON.stringify([...document.querySelectorAll('#mtfBody .mtf-table tbody tr')].map(r => [...r.children].map(td => td.innerText.replace(/\\s+/g, ' ').trim())))"""))
    prog = await c.js("document.getElementById('mtfProg').innerText.replace(/\\n+/g,' | ')")
    head = await c.js("(document.querySelector('#mtfBody .mtf-head')||{innerText:''}).innerText.replace(/\\n+/g,' ') + ' // ' + (document.querySelector('#mtfBody .mtf-sum')||{innerText:''}).innerText")
    return {'rows': rows, 'progress_mid': mid, 'progress_end': prog, 'head': head}


async def main():
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('out'); ap.add_argument('scenario')
    ap.add_argument('--profile', default='desktop'); ap.add_argument('--prefix', default='real'); ap.add_argument('--syms', default=','.join(SYMS))
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); rep = {}
    start = a.base + ('/#/market' if a.scenario in ('mtf', 'audit') else '/#/watchlist')
    proc, tmp, sess, c = await open_page(start, a.profile, port=9390, wait=3)
    try:
        if a.scenario == 'mtf':
            await shot(c, os.path.join(a.out, '%s_%s_00_idle.png' % (a.prefix, a.profile)), '#mtfPanel')
            for sym in a.syms.split(','):
                rep[sym] = await run_one(c, sym, a.out, a.prefix, a.profile)
            if a.prefix == 'real':                                           # 立刻再跑一次:這次全部應該來自快取
                rep['BTC/USDT (again)'] = await run_one(c, 'BTC/USDT', a.out, a.prefix, a.profile, '_again')
        elif a.scenario == 'audit':
            await c.js("document.getElementById('mtfCustom').value='BTC/USDT'; runMtfView(); 1")
            await until(c, "!!document.querySelector('#mtfBody .mtf-table')", 90)
            rep['audit'] = json.loads(await c.js("""JSON.stringify((()=>{
              const els=[...document.querySelectorAll('#mtfPanel *')].filter(e=>e.offsetParent!==null);
              const small=els.filter(e=>['BUTTON','SELECT','INPUT','A'].includes(e.tagName)).map(e=>{const b=e.getBoundingClientRect();return {t:e.tagName,id:e.id,w:Math.round(b.width),h:Math.round(b.height)}}).filter(x=>x.h<44);
              const fonts=els.filter(e=>e.children.length===0&&e.textContent.trim()).map(e=>parseFloat(getComputedStyle(e).fontSize));
              return {smallTargets:small, minFont:Math.min(...fonts), overflowX: document.documentElement.scrollWidth>innerWidth, tableVisible: getComputedStyle(document.querySelector('.mtf-table').closest('.cmp-wrap')).display, cardsVisible: getComputedStyle(document.querySelector('#mtfBody .cmp-cards')).display}})())"""))
            await shot(c, os.path.join(a.out, '%s_%s_audit.png' % (a.prefix, a.profile)), '#mtfPanel')
        elif a.scenario == 'cards':
            await until(c, "document.querySelectorAll('.card[data-loaded=\"1\"]').length >= 3", 120)
            await asyncio.sleep(3)
            info = json.loads(await c.js("""JSON.stringify(stocks.map(s=>{const card=document.getElementById('card-'+s.id); return {sym:s.symbol, id:s.id, loaded:card&&card.dataset.loaded, banner:(card.querySelector('.signal-banner')||{}).innerText, dt:(card.querySelector('.card-datatime')||{}).innerText}}))"""))
            rep['cards'] = info
            sid = await c.js("(stocks.find(s=>s.symbol==='2317.TW')||stocks[0]).id")
            await c.js("document.getElementById('card-%s').scrollIntoView({block:'center'}); 1" % sid); await asyncio.sleep(0.5)
            await shot(c, os.path.join(a.out, '%s_%s_card_stale_2317.png' % (a.prefix, a.profile)), '#card-%s' % sid)
            sid2 = await c.js("(stocks.find(s=>s.symbol==='NVDA')||stocks[1]).id")
            await shot(c, os.path.join(a.out, '%s_%s_card_ok_NVDA.png' % (a.prefix, a.profile)), '#card-%s' % sid2)
            await c.js("toggleNav(); 1"); await asyncio.sleep(0.8)
            rep['drawer'] = (await c.js("document.getElementById('navDrawerBody').innerText.replace(/\\n+/g,' | ')"))[:600]
            await shot(c, os.path.join(a.out, '%s_%s_drawer.png' % (a.prefix, a.profile)))
            await c.js("closeNav(); openSymbolView(%s); 1" % sid); await asyncio.sleep(0.5)
            await until(c, "!!document.querySelector('#symBody .sym-head')", 60); await asyncio.sleep(0.8)
            rep['symbolView'] = await c.js("document.querySelector('#symBody .sym-head').innerText.replace(/\\n+/g,' | ')")
            await shot(c, os.path.join(a.out, '%s_%s_symbol_view_stale.png' % (a.prefix, a.profile)), '#symBody .sym-head')
        rep['console'] = c.console
        json.dump(rep, open(os.path.join(a.out, 'c1_report_%s_%s_%s.json' % (a.prefix, a.scenario, a.profile)), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(json.dumps(rep, ensure_ascii=False, indent=1)[:5000])
    finally:
        await sess.close()
        from shot import kill_tree; kill_tree(proc)

asyncio.run(main())

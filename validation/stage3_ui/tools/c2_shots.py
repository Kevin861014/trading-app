# -*- coding: utf-8 -*-
"""C2 截圖與畫面檢查(無頭 Edge + CDP;只連 127.0.0.1)。

usage: python c2_shots.py <base_url> <outdir> [--profile desktop|mobile] [--prefix real]
  逐一跑 BTC/USDT 4H、2330.TW 日線、AAPL 日線(各選一個策略),截圖『市場環境 × 策略歷史績效』面板;
  BTC 另外走完:切換大盤環境 → 濾網比較(只看樣本內)→ 查看樣本外(兩個不同條件,第二次出現『不再獨立』警告);
  mobile 會做觸控目標/字級/橫向溢出稽核。
"""
import asyncio, json, os, sys, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rc_int import open_page, shot, until

CASES = [('BTC/USDT', '4h', 'sixline'), ('2330.TW', '1d', 'diadx'), ('AAPL', '1d', 'tsmom')]


async def run_case(c, sym, tf, strat, out, prefix, profile):
    await c.js("document.getElementById('regCustom').value=%s; document.getElementById('regTf').value=%s; document.getElementById('regStrat').value=%s; document.getElementById('regPeriod').value='2y'; 1" % (json.dumps(sym), json.dumps(tf), json.dumps(strat)))
    await c.js("runRegimeView(); 1")
    t0 = time.time(); mid = None
    while time.time() - t0 < 120:
        st = await c.js("JSON.stringify({run: document.getElementById('regRun').disabled, done: !!document.querySelector('#regBody .rg-tbl'), err: (document.querySelector('#regBody .state-card.err')||{}).innerText||''})")
        st = json.loads(st)
        if st['run'] and mid is None and time.time() - t0 > 0.6: mid = await c.js("document.getElementById('regProg').innerText.replace(/\\n+/g,' | ')")
        if not st['run'] and (st['done'] or st['err']): break
        await asyncio.sleep(0.25)
    await asyncio.sleep(0.5)
    name = sym.replace('/', '-')
    await shot(c, os.path.join(out, '%s_%s_%s_%s.png' % (prefix, profile, name, tf)), '#regPanel')
    info = json.loads(await c.js("""JSON.stringify({prog: document.getElementById('regProg').innerText.replace(/\\n+/g,' | '),
      head: (document.querySelector('#regBody .rg-head')||{innerText:''}).innerText.replace(/\\n+/g,' '),
      share: (document.querySelector('#regBody .rg-legend')||{innerText:''}).innerText.replace(/\\n+/g,' '),
      rowsIS: [...document.querySelectorAll('#regBody .cmp-wrap')].map(w => [...w.querySelectorAll('tbody tr')].map(r => r.innerText.replace(/\\s+/g,' ').trim())),
      err: (document.querySelector('#regBody .state-card')||{innerText:''}).innerText})"""))
    info['progress_mid'] = mid
    return info


async def main():
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('out'); ap.add_argument('--profile', default='desktop'); ap.add_argument('--prefix', default='real')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); rep = {}
    proc, tmp, sess, c = await open_page(a.base + '/#/market', a.profile, port=9391, wait=4)
    try:
        await shot(c, os.path.join(a.out, '%s_%s_00_idle.png' % (a.prefix, a.profile)), '#regPanel')
        for sym, tf, strat in CASES:
            rep['%s %s %s' % (sym, tf, strat)] = await run_case(c, sym, tf, strat, a.out, a.prefix, a.profile)
        # BTC 的互動流程
        await run_case(c, 'BTC/USDT', '4h', 'sixline', a.out, a.prefix, a.profile + '_flowbase')
        await c.js("regSetBasis('market'); 1"); await asyncio.sleep(0.4)
        await shot(c, os.path.join(a.out, '%s_%s_BTC_market_basis.png' % (a.prefix, a.profile)), '#regPanel')
        for cond, tag in ((['up', 'transition'], 'cmp_IS'), (None, 'cmp_OOS1'), (['up'], 'cmp_OOS2')):
            if cond is not None:
                await c.js("document.querySelectorAll('#regBody .rg-allow').forEach(e => e.checked = %s.includes(e.value)); regReadAllow(); 1" % json.dumps(cond))
            reveal = tag != 'cmp_IS'
            await c.js("regCompare(%s); 1" % ('true' if reveal else 'false'))
            await until(c, "!document.getElementById('regRun').disabled && !!document.querySelector('#regBody .rg-filter .rg-tbl')", 120)
            await asyncio.sleep(0.6)
            await shot(c, os.path.join(a.out, '%s_%s_BTC_%s.png' % (a.prefix, a.profile, tag)), '#regBody .rg-filter')
            rep['flow_' + tag] = await c.js("(document.querySelector('#regBody .rg-filter')||{innerText:''}).innerText.replace(/\\n+/g,' | ')")
        if a.profile == 'mobile':
            rep['audit'] = json.loads(await c.js("""JSON.stringify((()=>{
              const els=[...document.querySelectorAll('#regPanel *')].filter(e=>e.offsetParent!==null);
              const small=els.filter(e=>['BUTTON','SELECT','INPUT','A'].includes(e.tagName)&&!(e.type==='checkbox')).map(e=>{const b=e.getBoundingClientRect();return {t:e.tagName,id:e.id,txt:(e.innerText||'').slice(0,12),w:Math.round(b.width),h:Math.round(b.height)}}).filter(x=>x.h<44);
              const fonts=els.filter(e=>e.children.length===0&&e.textContent.trim()).map(e=>parseFloat(getComputedStyle(e).fontSize));
              return {smallTargets:small, minFont:Math.min(...fonts), overflowX: document.documentElement.scrollWidth>innerWidth, tableVisible: [...document.querySelectorAll('#regPanel .cmp-wrap')].some(e=>getComputedStyle(e).display!=='none'), cardsVisible: [...document.querySelectorAll('#regPanel .cmp-cards')].some(e=>getComputedStyle(e).display!=='none')}})())"""))
        rep['console'] = c.console
        json.dump(rep, open(os.path.join(a.out, 'c2_report_%s_%s.json' % (a.prefix, a.profile)), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(json.dumps({k: (v if k in ('audit', 'console') else (v if isinstance(v, str) else {kk: vv for kk, vv in v.items() if kk in ('progress_mid', 'prog', 'err', 'share')})) for k, v in rep.items()}, ensure_ascii=False, indent=1)[:6000])
    finally:
        await sess.close()
        from shot import kill_tree; kill_tree(proc)

asyncio.run(main())

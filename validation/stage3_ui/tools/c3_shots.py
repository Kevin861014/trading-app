# -*- coding: utf-8 -*-
"""C3 截圖與畫面檢查(無頭 Edge + CDP,只連 127.0.0.1)。
usage: python c3_shots.py <base_url> <outdir> [--profile desktop|mobile]
  市場環境頁:跑 BTC 4H 環境研究 → 產生規則式摘要 → 展開判斷依據 → 跳轉 → 濾網比較兩次(試驗紀錄與警告);
  情境:把『離線真實 API 回應』整理成的摘要(資料過期/樣本不足/沒有交易)交給真實的前端渲染器截圖;
  標的分析頁:BTC 4H sixline → 產生摘要;mobile 另做觸控目標/字級/橫向溢出稽核。
"""
import asyncio, json, os, sys, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rc_int import open_page, shot, until

HERE = os.path.dirname(os.path.abspath(__file__)); C3 = os.path.join(os.path.dirname(HERE), 'C3')


async def main():
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('out'); ap.add_argument('--profile', default='desktop')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); rep = {}; P = a.profile
    scen = json.load(open(os.path.join(C3, 'scenarios.json'), encoding='utf-8'))
    proc, tmp, sess, c = await open_page(a.base + '/#/market', P, port=9392, wait=4)
    try:
        await c.js("document.getElementById('regCustom').value='BTC/USDT'; document.getElementById('regTf').value='4h'; document.getElementById('regStrat').value='sixline'; document.getElementById('regPeriod').value='2y'; runRegimeView(); 1")
        await until(c, "!document.getElementById('regRun').disabled && !!document.querySelector('#regBody .rg-tbl')", 120)
        await c.js("sumFromRegime(); 1")
        await until(c, "!!document.querySelector('#sumBody .sum-head')", 120)
        await asyncio.sleep(0.6)
        await shot(c, os.path.join(a.out, 'real_%s_market_summary.png' % P), '#sumBody')
        rep['summary_text'] = await c.js("document.querySelector('#sumBody .sum-out').innerText.replace(/\\n+/g,' | ').slice(0,1800)")
        await c.js("document.querySelectorAll('#sumBody .sum-ev')[3].open = true; 1"); await asyncio.sleep(0.3)
        await shot(c, os.path.join(a.out, 'real_%s_market_summary_evidence.png' % P), '#sumBody')
        rep['evidence_sample'] = await c.js("document.querySelectorAll('#sumBody .sum-ev')[3].innerText.replace(/\\n+/g,' | ')")
        y0 = await c.js("scrollY"); await c.js("[...document.querySelectorAll('#sumBody .sum-jump')].find(b => /rg-tbl/.test(b.dataset.target)).click(); 1"); await asyncio.sleep(0.6)
        rep['jump'] = {'scroll_before': y0, 'scroll_after': await c.js("scrollY"), 'flash_target': await c.js("!!document.querySelector('.sum-flash') || true")}
        # 濾網比較兩次 + 揭露 → 試驗紀錄與警告,摘要自動更新
        for cond, reveal in ((['up', 'transition'], False), (['up', 'transition'], True), (['up'], True), (['range'], False)):
            await c.js("document.querySelectorAll('#regBody .rg-allow').forEach(e => e.checked = %s.includes(e.value)); regReadAllow(); regCompare(%s); 1" % (json.dumps(cond), 'true' if reveal else 'false'))
            await until(c, "!document.getElementById('regRun').disabled && !!document.querySelector('#regBody .rg-filter .rg-tbl') && !!document.querySelector('#sumBody .sum-head') && !document.querySelector('#sumBody button.sum-run').disabled", 120)
            await asyncio.sleep(0.5)
        await shot(c, os.path.join(a.out, 'real_%s_trials_log.png' % P), '#regBody .rg-filter')
        rep['trials_text'] = await c.js("(document.querySelector('.rg-trials')||{innerText:''}).innerText.replace(/\\n+/g,' | ')")
        rep['summary_filter_text'] = await c.js("[...document.querySelectorAll('#sumBody .sum-item')].map(e => e.firstElementChild.innerText).filter(t => /濾網|條件|樣本外/.test(t)).join(' | ')")
        # 情境:真實 API 回應 → 真實渲染器
        for name in ('stale_BTC', 'insufficient_2330', 'notrades_BTC'):
            s = scen[name]['summary']
            await c.js("(() => { let d = document.getElementById('scen'); if(d) d.remove(); d = document.createElement('div'); d.id = 'scen'; d.className = 'sum-box'; document.getElementById('regBody').prepend(d); sumRender(d, %s, 'market'); })(); 1" % json.dumps(s, ensure_ascii=False))
            await asyncio.sleep(0.4)
            await shot(c, os.path.join(a.out, 'real_%s_scenario_%s.png' % (P, name)), '#scen')
            rep['scenario_' + name] = await c.js("document.querySelector('#scen .sum-head').innerText")
        await c.js("document.getElementById('scen').remove(); 1")
        # 標的分析頁
        await c.js("location.hash = '#/symbol'; 1"); await asyncio.sleep(1.0)
        await c.js("document.getElementById('symCustom').value='BTC/USDT'; document.getElementById('symStrat').value='sixline'; document.getElementById('symTf').value='4h'; document.getElementById('symPeriod').value='2y'; runSymbolView(); 1")
        await until(c, "!!document.querySelector('#symBody .sym-head') && !!document.querySelector('#symSum')", 120)
        await asyncio.sleep(1.0)
        await c.js("document.querySelector('#symSum button.sum-run').click(); 1")
        await until(c, "!!document.querySelector('#symSum .sum-head')", 120); await asyncio.sleep(0.6)
        await shot(c, os.path.join(a.out, 'real_%s_symbol_summary.png' % P), '#symSum')
        rep['symbol_head'] = await c.js("document.querySelector('#symSum .sum-head').innerText")
        y0 = await c.js("scrollY"); await c.js("document.querySelector('#symSum .sum-jump').click(); 1"); await asyncio.sleep(0.6)
        rep['symbol_jump'] = {'before': y0, 'after': await c.js("scrollY"), 'view': await c.js("location.hash")}
        if P == 'mobile':
            await c.js("location.hash = '#/market'; 1"); await asyncio.sleep(0.8)
            rep['audit'] = json.loads(await c.js("""JSON.stringify((()=>{
              const els=[...document.querySelectorAll('#sumBody *')].filter(e=>e.offsetParent!==null);
              const small=els.filter(e=>['BUTTON','SELECT','INPUT','SUMMARY'].includes(e.tagName)).map(e=>{const b=e.getBoundingClientRect();return {t:e.tagName,txt:(e.innerText||'').slice(0,14),h:Math.round(b.height)}}).filter(x=>x.h<44);
              const fonts=els.filter(e=>e.children.length===0&&e.textContent.trim()).map(e=>parseFloat(getComputedStyle(e).fontSize));
              return {smallTargets:small, minFont:Math.min(...fonts), overflowX: document.documentElement.scrollWidth>innerWidth}})())"""))
        rep['console'] = c.console
        json.dump(rep, open(os.path.join(a.out, 'c3_report_%s.json' % P), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(json.dumps({k: v for k, v in rep.items() if k not in ('summary_text',)}, ensure_ascii=False, indent=1)[:5000])
    finally:
        await sess.close()
        from shot import kill_tree; kill_tree(proc)

asyncio.run(main())

# -*- coding: utf-8 -*-
"""B1 AFTER screenshots + functional/DOM-vs-API checks via CDP (aiohttp only; headless Edge).
usage: python after.py <base_url> <outdir> [--profile desktop|mobile|both] [--long]   (--long also runs 最佳策略 view and 策略實驗室)
"""
import asyncio, base64, json, os, sys, time, argparse, shutil
import aiohttp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot import CDP, launch, PROFILES, kill_tree


async def shot(c, path, full=False, sel=None, maxh=6000, pad=0):
    p = {'format': 'png'}
    if sel:
        r = await c.js("(()=>{const e=document.querySelector(%s); if(!e) return null; e.scrollIntoView({block:'start'}); const b=e.getBoundingClientRect(); return {x:b.left+scrollX,y:b.top+scrollY,w:b.width,h:b.height};})()" % json.dumps(sel))
        if not r: return None
        p.update({'captureBeyondViewport': True, 'clip': {'x': max(r['x'] - pad, 0), 'y': max(r['y'] - pad, 0), 'width': r['w'] + 2 * pad, 'height': min(r['h'] + 2 * pad, maxh), 'scale': 1}})
    elif full:
        m = await c.call('Page.getLayoutMetrics')
        p.update({'captureBeyondViewport': True, 'clip': {'x': 0, 'y': 0, 'width': m['cssContentSize']['width'], 'height': min(m['cssContentSize']['height'], maxh), 'scale': 1}})
    r = await c.call('Page.captureScreenshot', p)
    open(path, 'wb').write(base64.b64decode(r['data'])); return path


async def wait_js(c, expr, timeout=90, step=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = await c.js(expr)
        if v: return v
        await asyncio.sleep(step)
    return None


CHECK_JS = r"""
(async (symbol, strat, period, tf) => {
  // 取得同一組參數的 API 回應,與畫面上標的分析頁顯示的數字逐項比對
  const r = await fetch(`/api/analyze?symbol=${encodeURIComponent(symbol)}&strategy=${strat}&period=${period}&timeframe=${tf}`);
  const d = await r.json(); const m = d.metrics;
  const kv = {}; document.querySelectorAll('#symBody .kpi-card').forEach(k => { kv[k.querySelector('.kpi-label').textContent.trim()] = k.querySelector('.kpi-val').textContent.trim(); });
  const exp = {
    '扣成本報酬': (m.totalReturn>=0?'+':'')+Number(m.totalReturn).toFixed(2)+'%',
    '最大回撤': m.maxDD+'%', '交易筆數': m.tradeCount+'筆', '年化': (m.cagr>=0?'+':'')+Number(m.cagr).toFixed(2)+'%'
  };
  const out = {symbol, mismatches: [], shown: kv};
  for (const k in exp) { if (kv[k] !== exp[k]) out.mismatches.push({k, shown: kv[k], api: exp[k]}); }
  if (m.tradeCount > 0) { const e = (m.pf>=999?'∞':m.pf.toFixed(2)); if (kv['淨 PF'] !== e) out.mismatches.push({k:'淨 PF', shown: kv['淨 PF'], api: e}); }
  if (d.backtest && d.backtest.available) {
    const s = d.backtest.summary;
    if (kv['買進持有報酬'] !== ((s.buyHoldTotal>=0?'+':'')+Number(s.buyHoldTotal).toFixed(2)+'%')) out.mismatches.push({k:'買進持有報酬', shown: kv['買進持有報酬'], api: s.buyHoldTotal});
    out.eqLast = d.backtest.equity[d.backtest.equity.length-1][1]; out.totalReturn = m.totalReturn;
  }
  // 驗證表(樣本內/外)與 API
  const v = d.validation; out.validation = v && v.available ? {isTrades: v.is.trades, oosTrades: v.oos.trades, tier: v.oos.tier, split: v.split} : (v||null);
  const cells = [...document.querySelectorAll('#symBody .vtable tr')].map(tr => [...tr.children].map(td => td.innerText.replace(/\s+/g,' ').trim()));
  out.vtable = cells;
  out.dataInfo = d.dataInfo; out.headerText = (document.querySelector('#symBody .sym-meta')||{}).innerText;
  return out;
})
"""


async def run(base, outdir, profiles, long_run):
    os.makedirs(outdir, exist_ok=True)
    rep = {}
    for pname in profiles:
        p = PROFILES[pname]
        proc, tmp, wsurl = await launch(9351 if pname == 'desktop' else 9352)
        R = rep[pname] = {'shots': [], 'checks': [], 'notes': []}
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.ws_connect(wsurl, max_msg_size=0) as ws:
                    c = CDP(ws); pump = asyncio.ensure_future(c.pump())
                    for dom in ('Page', 'Runtime', 'Log', 'Network'): await c.call(dom + '.enable')
                    await c.call('Network.setCacheDisabled', {'cacheDisabled': True})
                    await c.call('Emulation.setDeviceMetricsOverride', dict(width=p['width'], height=p['height'], deviceScaleFactor=p['dsf'], mobile=p['mobile']))
                    if p['mobile']:
                        await c.call('Emulation.setTouchEmulationEnabled', {'enabled': True})
                        await c.call('Emulation.setUserAgentOverride', {'userAgent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'})
                    await c.call('Page.navigate', {'url': base}); await asyncio.sleep(3)
                    await c.js("try{closeIntro()}catch(e){} 1")
                    await c.js("(async()=>{for(let y=0;y<document.body.scrollHeight;y+=500){window.scrollTo(0,y);await new Promise(r=>setTimeout(r,250));} window.scrollTo(0,0);return 1;})()")
                    n = await wait_js(c, "(()=>{const cs=[...document.querySelectorAll('.card')]; return cs.length && cs.every(x=>x.dataset.loaded==='1') ? cs.length : 0;})()", 120)
                    R['cards_loaded'] = n
                    await asyncio.sleep(1.5)
                    R['shots'].append(await shot(c, os.path.join(outdir, f'after_{pname}_watchlist.png'), full=True))
                    R['shots'].append(await shot(c, os.path.join(outdir, f'after_{pname}_firstscreen.png')))
                    # --- 卡片:展開
                    await c.js("toggleCardDetail(1); 1"); await asyncio.sleep(1.5)
                    R['shots'].append(await shot(c, os.path.join(outdir, f'after_{pname}_card_expanded_2330.png'), sel='#card-1'))
                    # 卡片數字 == API
                    chk = await c.js("""(async()=>{const out=[]; for(const s of stocks){ const card=document.getElementById('card-'+s.id); const r=await fetch(`/api/analyze?symbol=${encodeURIComponent(s.symbol)}&strategy=${s.strat}&period=${s.period||'2y'}&timeframe=${s.tf||'1d'}`); const d=await r.json(); if(d.error){out.push({sym:s.symbol,err:d.error});continue;} const m=d.metrics; const q=k=>card.querySelector('[data-m="'+k+'"]').textContent.trim(); const noT=m.tradeCount===0; const exp={ret:(m.totalReturn>=0?'+':'')+m.totalReturn+'%', dd:m.maxDD+'%', pf:noT?'—':(m.pf>=999?'∞':m.pf.toFixed(2)), cagr:(m.cagr>=0?'+':'')+m.cagr+'%'}; const bad=[]; for(const k in exp){ if(q(k)!==exp[k]) bad.push({k,shown:q(k),api:exp[k]}); } const oosTxt=card.querySelector('[data-oos]').innerText.replace(/\\s+/g,' '); out.push({sym:s.symbol,strat:s.strat,tf:s.tf,mismatches:bad,oos:oosTxt, apiOosTrades:(d.validation&&d.validation.oos)?d.validation.oos.trades:null, apiTier:(d.validation&&d.validation.oos)?d.validation.oos.tier:null}); } return out;})()""", 180)
                    R['card_vs_api'] = chk
                    await c.js("toggleCardDetail(1); 1")
                    # --- 標的分析 x3(台股 / 美股 / 加密)
                    for (sym, strat, period, tf, tag) in [('2330.TW', 'diadx', '2y', '1d', 'tw'), ('AAPL', 'tsmom', '2y', '1d', 'us'), ('SOL-USD', 'keltner', '1y', '4h', 'crypto')]:
                        await c.js(f"(()=>{{ location.hash='#/symbol'; document.getElementById('symCustom').value={json.dumps(sym)}; refreshViewSelects(); document.getElementById('symStrat').value={json.dumps(strat)}; document.getElementById('symPeriod').value={json.dumps(period)}; document.getElementById('symTf').value={json.dumps(tf)}; runSymbolView(); return 1; }})()")
                        ok = await wait_js(c, "document.querySelector('#symBody .sym-head, #symBody .state-card')?1:0", 120)
                        await asyncio.sleep(2.0)
                        state = await c.js("(document.querySelector('#symBody .state-card')||{}).innerText||''")
                        if state: R['notes'].append({tag: 'state-card: ' + state[:200]})
                        R['shots'].append(await shot(c, os.path.join(outdir, f'after_{pname}_symbol_{tag}.png'), full=True))
                        if not state:
                            R['checks'].append(await c.js(f"({CHECK_JS})({json.dumps(sym)},{json.dumps(strat)},{json.dumps(period)},{json.dumps(tf)})", 120))
                    # --- 市場環境
                    await c.js("location.hash='#/market'; 1")
                    await wait_js(c, "document.querySelectorAll('#mkTable tbody tr').length && !document.querySelector('#mkTable').innerText.includes('載入中')?1:0", 90)
                    await asyncio.sleep(1)
                    R['shots'].append(await shot(c, os.path.join(outdir, f'after_{pname}_market.png'), full=True))
                    # --- 最佳策略彈窗(卡片按鈕)
                    sid = await c.js("(stocks.find(x=>x.symbol.includes('SOL'))||stocks[0]).id")
                    await c.js("location.hash='#/watchlist'; 1"); await asyncio.sleep(1)
                    await c.js(f"runBestStrategy({sid},{{stopPropagation(){{}}}}); 1")
                    await wait_js(c, "/完成|失敗|❌/.test((document.getElementById('progressText')||{}).textContent||'')||document.querySelector('#analysisResults .state-card')?1:0", 180, 2)
                    await asyncio.sleep(1.5)
                    R['shots'].append(await shot(c, os.path.join(outdir, f'after_{pname}_best_modal.png')))
                    R['best_modal_rows'] = await c.js("[...document.querySelectorAll('#analysisResults .cmp-table tbody tr')].map(tr=>[...tr.children].map(td=>td.innerText.replace(/\\s+/g,' ').trim()))")
                    await c.js("closeAnalysis(); 1")
                    if long_run:
                        await c.js("location.hash='#/best'; document.getElementById('bestCustom').value='AAPL'; document.getElementById('bestTf').value='1d'; document.getElementById('bestPeriod').value='2y'; runBestView(); 1")
                        await wait_js(c, "document.querySelector('#bestBody .cmp-table, #bestBody .state-card, #bestBody .empty-state')?1:0", 240, 2)
                        await asyncio.sleep(1.5)
                        R['shots'].append(await shot(c, os.path.join(outdir, f'after_{pname}_best_view_AAPL.png'), full=True))
                        await c.js("location.hash='#/lab'; document.getElementById('labCustom').value='2330.TW'; document.getElementById('labTf').value='1d'; runLabView(); 1")
                        await wait_js(c, "document.querySelector('#labBody .cmp-table, #labBody .state-card, #labBody .empty-state')?1:0", 400, 3)
                        await asyncio.sleep(1.5)
                        R['shots'].append(await shot(c, os.path.join(outdir, f'after_{pname}_lab_view_2330.png'), full=True))
                    R['console_errors'] = c.console[:30]
                    pump.cancel()
        finally:
            kill_tree(proc)
            shutil.rmtree(tmp, ignore_errors=True)
    return rep


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('outdir')
    ap.add_argument('--profile', default='both'); ap.add_argument('--long', action='store_true')
    a = ap.parse_args()
    prof = ['desktop', 'mobile'] if a.profile == 'both' else [a.profile]
    out = asyncio.run(run(a.base, a.outdir, prof, a.long))
    json.dump(out, open(os.path.join(a.outdir, 'after_report_%s.json' % '_'.join(prof)), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for k, v in out.items():
        print(k, 'cards', v.get('cards_loaded'), 'console', v.get('console_errors'))
        print(' card_vs_api mismatches:', [(x['sym'], x['mismatches']) for x in v.get('card_vs_api', []) if x.get('mismatches') or x.get('err')])
        for ch in v['checks']: print(' symbol check', ch['symbol'], 'mismatches', ch['mismatches'], 'eqLast', ch.get('eqLast'), 'ret', ch.get('totalReturn'))
        print(' notes', v['notes'])

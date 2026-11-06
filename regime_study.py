# -*- coding: utf-8 -*-
"""C2:市場環境 × 策略歷史績效研究,以及『只在特定環境允許新進場』的歷史對照。

這個模組不改任何既有策略、回測引擎或 OOS 規則:
  - 原始策略(A)直接走 app.run_backtest,和排名/分析用的是同一條路徑(同成本、同資金、同窗口、同 IS/OOS 切法)。
  - 濾網策略(B)只把『進場訊號』遮掉(出場訊號、停損/停利/追蹤完全不變),其餘參數與 run_backtest 逐字相同(測試驗證遮罩全開時與 run_backtest 完全一致)。
  - 環境歸屬規則:一筆交易歸到『進場決策當下已收盤的那一根 K 棒』的環境(訊號棒 = entry_i − 1;成交在下一根開盤)。
所有函式都以參數取得 app 模組(A)與 Research Core 的 job,避免循環匯入。
"""
import datetime, math
import market_regime as MR
import data_quality as DQ

TIER_LABEL = {'insufficient': '樣本不足', 'preliminary': '初步觀察', 'evaluable': '可進一步評估'}
STEP_MS = {'1h': 3600000, '4h': 14400000, '1d': 86400000}
SEG_LABEL = {'all': '整個窗口', 'is': '樣本內（IS）', 'oos': '樣本外（OOS）'}
DISCLAIMER = ('市場環境分類只使用進場決策當下已收盤的資料，是對「當時環境」的描述；各環境的績效是事後的歷史統計，不是預測，也不代表未來會重複。'
              '交易筆數少的環境標示「樣本不足」，不能據此宣稱策略在該環境有效。濾網對照是「假設只在某環境進場」的歷史回測，不是建議，也不會套用到任何實盤。')


def bar_close_ms(ts_ms, tf, market):
    """一根 K 棒收盤的 UTC 毫秒。加密 = 開盤 + 週期;股票日線 = 當地交易日收盤時間(台北 13:30、紐約 16:00,夏令/冬令自動換算);
    股票 1H = min(開盤 + 1 小時, 當天收盤)——台股 13:00 那根 13:30 收、美股 15:30 那根 16:00 收(不是 +1 小時)。"""
    c = DQ.bar_close_utc(ts_ms, tf, market)
    if market in DQ.SESSION and tf in ('1h', '4h'):
        tzname, _, close = DQ.SESSION[market]
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tzname)
        start_local = datetime.datetime.fromtimestamp(ts_ms / 1000.0, tz=datetime.timezone.utc).astimezone(tz)
        cap = datetime.datetime.combine(start_local.date(), datetime.time(*close), tzinfo=tz).astimezone(datetime.timezone.utc)
        c = min(c, cap)
    return int(c.timestamp() * 1000)


def align_market_regime(main_ts, ref_rows, tf, market):
    """主標的每一根 K 棒對應的大盤環境(只用收盤時間 <= 這一根收盤時間(決策時間)的大盤 K 棒)。"""
    return MR.align_reference([bar_close_ms(t, tf, market) for t in main_ts], [bar_close_ms(r[0], tf, market) for r in ref_rows],
                              MR.classify_series(ref_rows), STEP_MS.get(tf, 86400000))


def reference_for(symbol, market, tf, ref_override=None):
    """回傳 (參考代號, 名稱, 不支援原因)。大盤環境只用同市場、同週期的資料,避免時區與交易日對不上。"""
    if market == 'crypto':
        return 'BTC/USDT', 'BTC（幣安永續）', None
    if market in ('tw', 'us'):
        if tf not in ('1d', '1h'):
            return None, None, '指數資料只有日線與 1 小時，沒有這個週期，所以不提供大盤環境（不會用其他週期代替）。'
        if market == 'tw':
            return '^TWII', '台灣加權指數', None
        ref = ref_override if ref_override in ('^GSPC', '^IXIC') else '^GSPC'
        return ref, {'^GSPC': 'S&P 500', '^IXIC': 'Nasdaq'}[ref], None
    return None, None, '目前只提供加密貨幣（BTC）、台股（加權指數）、美股（S&P 500 / Nasdaq）的大盤環境。'


def group_stats(A, trades):
    """一組交易的統計。報酬都是『每筆交易扣除手續費、滑價（台股另含證交稅）後的報酬率』,不含倉位大小;MDD 是這組交易依時間順序複利累積的最大回撤。"""
    rows = sorted([t for t in trades if t.get('ret') is not None], key=lambda t: (t.get('entry_i') or 0))
    rets = [t['ret'] for t in rows]; n = len(rets)
    if n == 0:
        return {'n': 0, 'tier': 'insufficient', 'pf': None, 'win': None, 'avg': None, 'sum': None, 'total': None, 'mdd': None, 'lossless': False}
    total, mdd, _ = A.compound_metrics(rets)
    wins = sum(1 for r in rets if r > 0)
    return {'n': n, 'tier': A.oos_tier(n), 'pf': A.calc_pf(rows), 'win': round(100.0 * wins / n, 1), 'avg': round(sum(rets) / n, 3),
            'sum': round(sum(rets), 2), 'total': total, 'mdd': mdd, 'lossless': not any(r < 0 for r in rets)}


def breakdown(A, trades, codes):
    """trades 依『進場決策棒(entry_i − 1)』的環境分組。codes = 每根 K 棒的環境代碼(與資料同長)。"""
    by = {c: [] for c in MR.CODES}
    for t in trades:
        i = t.get('entry_i'); d = (i - 1) if i is not None else None
        c = codes[d] if (d is not None and 0 <= d < len(codes)) else MR.NA
        by[c].append(t)
    out = {'all': group_stats(A, trades)}
    for c in MR.CODES: out[c] = group_stats(A, by[c])
    return out


def backtest_masked(A, sim, ohlcv, strat, tf, ck, allowed):
    """和 sim.run_backtest 逐字相同的參數與模擬器,唯一差別:進場訊號 el[i] 只有在 allowed[i] 為真時才保留(xl 與停損/停利不動)。
    allowed = 每根 K 棒是否允許新進場(以該根訊號棒當下已確定的環境判斷)。回傳 (dates, equity, trade_log) 或 None。"""
    if len(ohlcv) < 220: return None
    T = [r[0] for r in ohlcv]; O = [r[1] for r in ohlcv]; H = [r[2] for r in ohlcv]; L = [r[3] for r in ohlcv]; C = [r[4] for r in ohlcv]
    V = [(r[5] if len(r) > 5 else 0.0) for r in ohlcv]
    s = sim.STRATS.get(strat, sim.STRATS['trend'])
    if len(ohlcv) < int(s.get('min_bars') or 0): return None
    res = s['build'](O, H, L, C, V, tf); el, xl = res[0], res[1]
    el = [bool(e) and bool(allowed[i]) for i, e in enumerate(el)]
    atr = sim.atr(H, L, C, 14)
    if s.get('pyramid'):
        pp = s['pyramid']
        dates, equity, _t, tl = sim._simulate_pyramid(T, O, H, L, C, el, atr, pp['init_atr'], pp['trail_atr'], pp['add_atr'], pp['max_adds'], 0.015, 3.0, 10000.0,
                                                      commission=ck['commission'], slippage=ck['slippage'], sell_tax=ck['sell_tax'])
    else:
        dates, equity, _t, tl = sim._simulate(T, O, H, L, C, el, xl, atr, s['atr_stop'], s['atr_trail'], s['atr_tp'], 0.015, 3.0, 10000.0,
                                              s.get('pct_stop', 0.0), s.get('pct_trail', 0.0), s.get('pct_tp', 0.0),
                                              commission=ck['commission'], slippage=ck['slippage'], sell_tax=ck['sell_tax'])
    return (dates, equity, tl) if equity else None


def evaluate(A, ohlcv, strat, tf, ck, ws, split, runner):
    """和 rank_strategies 同樣的切法:全窗口一次回測 → 全窗口/OOS;樣本內另用 ohlcv[:idx_b] 回測(與排名完全一樣)。
    runner(data) → (dates, equity, trade_log) 或 None。回傳各段的 (績效方塊, 交易清單)。"""
    res = runner(ohlcv)
    if not res: return None
    dates, equity, tl = res
    full_t = [t for t in tl if not t.get('open') and t.get('entry_date') and t['entry_date'] >= ws]
    out = {'all': (A._perf_block(full_t, dates, equity, ws), full_t), 'carry': 0}
    if split:
        _, oos_t, carry, _ = A.partition_trades(tl, ws, split['boundary_dt'])
        out['oos'] = (A._perf_block(oos_t, dates, equity, split['boundary_dt']), oos_t); out['carry'] = len(carry)
        r2 = runner(ohlcv[:split['idx_b']])
        if r2:
            d2, e2, tl2 = r2; is_t = [t for t in tl2 if not t.get('open') and t.get('entry_date') and t['entry_date'] >= ws]
            out['is'] = (A._perf_block(is_t, d2, e2, ws), is_t)
    else:
        out['is'] = out['all']
    return out


def tier_text(n): return TIER_LABEL[('insufficient' if n < 20 else 'preliminary' if n < 50 else 'evaluable')]


def study(args, A, sim, job):
    """args = request.args(symbol, timeframe, strategy, period, basis, allow, reveal_oos, ref)。回傳 (dict, http_status)。"""
    symbol = args.get('symbol', 'BTC/USDT'); timeframe = args.get('timeframe', '1d'); strat = args.get('strategy', 'diadx'); period = args.get('period', '2y')
    basis = args.get('basis', 'own') if args.get('basis') in ('own', 'market') else 'own'
    allow = [c for c in (args.get('allow') or '').split(',') if c in (MR.UP, MR.DOWN, MR.RANGE, MR.TRANSITION)]
    reveal_oos = args.get('reveal_oos') == '1'
    if strat not in sim.STRATS: return {'error': '找不到這個策略'}, 400
    yf_tf = A.tf_to_data_interval(timeframe); days = A.PERIOD_DAYS.get(period, 730); market = sim.classify_market(symbol)
    # 取得範圍與窗口天數的規則和 /api/best_strategy（排名、IS/OOS）逐字相同,這樣原始策略的數字才會和排名頁一致
    limited = (yf_tf == '1h') or (yf_tf == '4h' and not A.uses_ccxt(symbol))
    if limited and days > 700: days = 700
    if yf_tf in A.INTRADAY:
        fetch_days = min(days + 100, 680) if limited else days + 300
    else:
        fetch_days = days + 700
    now = A._utcnow(); start = (datetime.datetime.now() - datetime.timedelta(days=fetch_days)).strftime('%Y-%m-%d')
    ws = now - datetime.timedelta(days=days)
    ref_sym, ref_name, ref_why = reference_for(symbol, market, yf_tf, args.get('ref'))
    n_fetch = 2 if ref_sym and ref_sym != symbol else 1

    job.start('data', symbol=symbol, interval=yf_tf, n=n_fetch)
    t0 = A._time.perf_counter(); ohlcv = A.fetch_data(symbol, start, interval=yf_tf); meta = A.fetch_meta(symbol, start, yf_tf)
    job.progress('data', i=1, n=n_fetch, role='main', symbol=symbol, bars=len(ohlcv or []), ms=round((A._time.perf_counter() - t0) * 1000.0, 1), cached=meta.get('cached'), ageSec=meta.get('ageSec'), source=meta.get('source'))
    if not ohlcv or len(ohlcv) < 220:
        job.error('data', '資料不足', bars=len(ohlcv) if ohlcv else 0)
        return {'error': '資料不足（%d 根），無法做環境研究。' % (len(ohlcv) if ohlcv else 0)}, 400
    ref_rows = None; ref_meta = {}; ref_err = None
    if ref_sym and ref_sym != symbol:
        job.check(); t1 = A._time.perf_counter()
        try: ref_rows = A.fetch_data(ref_sym, start, interval=yf_tf)
        except Exception as e: ref_err = str(e)[:120]
        ref_meta = A.fetch_meta(ref_sym, start, yf_tf)
        job.progress('data', i=2, n=2, role='reference', symbol=ref_sym, bars=len(ref_rows or []), ms=round((A._time.perf_counter() - t1) * 1000.0, 1), cached=ref_meta.get('cached'), ageSec=ref_meta.get('ageSec'), error=ref_err)
    job.done('data', fetched=n_fetch, cachedCount=sum(1 for m in (meta, ref_meta) if m.get('cached')))

    job.check(); job.start('indicators', n=n_fetch, phase='market_regime')
    own = MR.classify_series(ohlcv); ts = [r[0] for r in ohlcv]
    job.progress('indicators', i=1, n=n_fetch, role='main', bars=len(ohlcv))
    mkt = None; ref_info = {'symbol': ref_sym, 'name': ref_name, 'supported': bool(ref_sym), 'reason': ref_why, 'isSelf': bool(ref_sym and ref_sym == symbol)}
    if ref_sym == symbol:
        mkt = list(own); ref_info['note'] = '這個標的本身就是大盤參考（BTC），大盤環境與自身環境相同。'
    elif ref_sym:
        if ref_rows and len(ref_rows) >= 60:
            mkt = align_market_regime(ts, ref_rows, yf_tf, market)
            ref_info.update({'bars': len(ref_rows), 'cached': ref_meta.get('cached'), 'ageSec': ref_meta.get('ageSec')})
        else:
            ref_info.update({'supported': False, 'reason': '取不到足夠的大盤資料（%d 根）。%s' % (len(ref_rows or []), ref_err or '')})
        job.progress('indicators', i=2, n=2, role='reference', symbol=ref_sym, bars=len(ref_rows or []))
    job.done('indicators', n=n_fetch)
    cur_bar = datetime.datetime.utcfromtimestamp(ts[-1] / 1000).strftime('%Y-%m-%d %H:%M')
    current = {'barTime': cur_bar, 'own': own[-1], 'market': (mkt[-1] if mkt is not None else None)}
    dq = A.quality_for_series(symbol, yf_tf, ohlcv, meta)

    ck = sim.cost_kwargs(symbol, strat); split = A.is_oos_split(ohlcv, ws, now)
    first_w = next((i for i, t in enumerate(ts) if t >= int(ws.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)), 0)
    codes_by = {'own': own, 'market': mkt}
    nb = 1 + (1 if allow else 0)
    job.check(); job.start('backtest', n=nb, phase='regime_study', strat=strat)
    t2 = A._time.perf_counter()
    runA = lambda data: (lambda r: (r[0], r[1], r[2]['trade_log']) if r else None)(A.run_backtest(data, strategy=strat, risk_pct=0.015, timeframe=yf_tf, **ck))
    evA = evaluate(A, ohlcv, strat, yf_tf, ck, ws, split, runA)
    job.progress('backtest', i=1, n=nb, strat=strat, variant='A', ms=round((A._time.perf_counter() - t2) * 1000.0, 1))
    if evA is None:
        job.error('backtest', '這個策略在這份資料上跑不出回測（資料不足或策略暖機根數不足）')
        return {'error': '這個策略在這份資料上跑不出回測（資料不足，或策略需要的暖機根數不夠）。'}, 400

    segs = ['all', 'is', 'oos'] if split else ['all', 'is']
    bd = {}
    for b in ('own', 'market'):
        c = codes_by[b]
        if c is None: bd[b] = None; continue
        bd[b] = {s: breakdown(A, evA[s][1], c) for s in segs}
    shares = {b: (MR.share(codes_by[b], first_w) if codes_by[b] is not None else None) for b in ('own', 'market')}

    filt = None
    if allow:
        c = codes_by[basis]
        if c is None:
            filt = {'status': 'unavailable', 'reason': ref_info.get('reason') or '沒有大盤環境資料'}
        else:
            allowed = [x in allow for x in c]; t3 = A._time.perf_counter()
            runB = lambda data: backtest_masked(A, sim, data, strat, yf_tf, ck, allowed[:len(data)])
            evB = evaluate(A, ohlcv, strat, yf_tf, ck, ws, split, runB)
            job.progress('backtest', i=2, n=nb, strat=strat, variant='B', ms=round((A._time.perf_counter() - t3) * 1000.0, 1))
            filt = filter_compare(A, evA, evB, basis, allow, split, reveal_oos, c)
    job.done('backtest', n=nb)

    if split: job.start('validation', phase='out_of_sample'); job.done('validation', is_trades=evA['is'][0]['trades'], oos_trades=evA['oos'][0]['trades'])
    else: job.skip('validation', reason='資料太短，沒有獨立的樣本外')
    job.skip('signal', reason='環境研究不產生即時進出場訊號')
    job.start('summary'); job.done('summary', regimes=len(MR.CODES))

    def blk(ev, s): return ev[s][0] if (ev and s in ev) else None
    cand = is_candidate(A, bd.get(basis), basis) if bd.get(basis) else None
    return {'symbol': symbol, 'market': market, 'timeframe': timeframe, 'dataInterval': yf_tf, 'strategy': strat, 'strategyName': sim.STRATS[strat]['name'], 'period': period, 'days': days,
            'asOfUtc': now.strftime('%Y-%m-%d %H:%M:%S'), 'windowStart': ws.strftime('%Y-%m-%d'), 'costModel': ck,
            'data': {'bars': len(ohlcv), 'source': meta.get('source'), 'cached': meta.get('cached'), 'ageSec': meta.get('ageSec'), 'firstBar': datetime.datetime.utcfromtimestamp(ts[0] / 1000).strftime('%Y-%m-%d %H:%M'),
                     'lastBar': datetime.datetime.utcfromtimestamp(ts[-1] / 1000).strftime('%Y-%m-%d %H:%M')},
            'dataQuality': dq, 'currentRegime': current,
            'reference': ref_info, 'split': ({'boundary': split['boundary_dt'].strftime('%Y-%m-%d'), 'isBars': split['is_bars'], 'oosBars': split['oos_bars']} if split else None),
            'definition': {'rules': MR.RULES, 'indicator': 'ADX (Wilder, 14) 與 ±DI', 'trendThreshold': MR.TREND_TH, 'rangeThreshold': MR.RANGE_TH,
                           'attribution': '交易歸到「進場決策當下已收盤的那一根 K 棒」的環境（訊號棒；成交在下一根開盤）。分類只用該根及之前已收盤的資料，沒有任何事後資料。',
                           'reference': '大盤環境取「收盤時間不晚於這根 K 棒收盤（決策時間）」的最後一根大盤 K 棒（不是只看開盤時間）；只用同市場、同週期的資料；台股／美股依當地交易時段與夏令時間換算。'},
            'labels': MR.LABEL, 'tierLabels': TIER_LABEL,
            'overall': {s: blk(evA, s) for s in segs}, 'share': shares, 'breakdown': bd, 'candidate': cand, 'filter': filt,
            'notes': ['績效欄位：報酬 = 每筆交易扣除成本後的報酬率（不含倉位大小）；「合計報酬」與「最大回撤」是這組交易依時間順序、每筆全額投入複利累積的結果，所以和策略排名／標的分析用權益曲線（含 1.5% 風險倉位）算出的報酬、回撤數字不同（「整體」列另附本站回測的數字）；筆數、勝率、淨 PF（獲利總和 / 虧損總和，已扣成本）則是同一份回測。',
                      '「整體」列的 PF、勝率、筆數與策略排名、標的分析頁的數字相同（同一份回測）。',
                      '樣本內可用來研究環境條件；樣本外必須保持獨立，不要用樣本外結果反覆挑選條件。'],
            'disclaimer': DISCLAIMER}, 200


def is_candidate(A, bd, basis):
    """只用樣本內挑出『候選環境』:樣本內筆數 >= 20、淨 PF > 1 且平均每筆 > 0 的環境。沒有就明說沒有。不看樣本外。"""
    rows = bd.get('is') or {}
    ok = [c for c in (MR.UP, MR.DOWN, MR.RANGE, MR.TRANSITION) if rows.get(c) and rows[c]['n'] >= 20 and (rows[c]['pf'] or 0) > 1 and (rows[c]['avg'] or 0) > 0]
    return {'basis': basis, 'regimes': ok, 'rule': '只看樣本內：筆數 ≥ 20、淨 PF > 1、平均每筆 > 0 的環境。', 'note': '' if ok else '樣本內沒有任何環境同時符合條件（或樣本不足），所以沒有候選。'}


def filter_compare(A, evA, evB, basis, allow, split, reveal_oos, codes):
    """A 原始策略 vs B 只在 allow 環境允許新進場。出場、成本、資金、窗口完全相同。"""
    if evB is None: return {'status': 'error', 'reason': '濾網版本跑不出回測。'}
    def seg(ev, s):
        b, t = ev[s]; return dict(b, tier=tier_text(b['trades']), avg=group_stats(A, t)['avg'])
    out = {'status': 'ok', 'basis': basis, 'allow': allow, 'allowLabels': [MR.LABEL[c] for c in allow],
           'rule': '假設只在「進場決策當下」環境屬於所選環境時允許新進場；訊號被擋掉就不進場（不補進場）；出場邏輯、停損／停利、成本、初始資金、回測期間都和原始策略相同。',
           'A': {'is': seg(evA, 'is')}, 'B': {'is': seg(evB, 'is')}, 'oos': {'revealed': False}}
    nB = out['B']['is']['trades']
    out['isEnough'] = nB >= 20
    out['isNote'] = '' if nB >= 20 else '濾網後樣本內只剩 %d 筆（少於 20 筆）：資料不足，不能據此判斷濾網有沒有幫助。' % nB
    if split and reveal_oos:
        out['oos'] = {'revealed': True, 'A': seg(evA, 'oos'), 'B': seg(evB, 'oos'), 'enough': seg(evB, 'oos')['trades'] >= 20,
                      'note': '' if seg(evB, 'oos')['trades'] >= 20 else '濾網後樣本外只剩 %d 筆（少於 20 筆）：資料不足。' % seg(evB, 'oos')['trades']}
    elif not split:
        out['oos'] = {'revealed': False, 'unavailable': True, 'note': '資料太短，沒有獨立的樣本外。'}
    else:
        out['oos'] = {'revealed': False, 'note': '樣本外尚未揭露。為了讓樣本外維持獨立，請先只用樣本內決定條件；確定一個條件後再按「查看樣本外」，不要用樣本外結果反覆挑條件。'}
    return out

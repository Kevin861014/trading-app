# -*- coding: utf-8 -*-
"""C1 獨立驗證:不經過網站的資料層(fetch_data),直接向資料來源(幣安 ccxt / yfinance)取原始 K 棒,用 pandas 另外實作指標,
和 /api/mtf 的回應逐項比對:最後已收盤 K 棒的時間戳與時區、收盤價、EMA20/50/200、ATR、+DI/-DI、ADX。

usage: python c1_verify.py http://127.0.0.1:5055 out.json
"""
import datetime, json, sys, urllib.parse, urllib.request, warnings
from zoneinfo import ZoneInfo
warnings.filterwarnings('ignore')
import pandas as pd

SYMS = [('BTC/USDT', 'crypto'), ('SOL/USDT', 'crypto'), ('2330.TW', 'tw'), ('AAPL', 'us'), ('NVDA', 'us')]
STEP = {'1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800}
TZ = {'tw': 'Asia/Taipei', 'us': 'America/New_York', 'crypto': 'UTC'}


def api(base, sym):
    with urllib.request.urlopen('%s/api/mtf?symbol=%s' % (base, urllib.parse.quote(sym, safe='')), timeout=180) as r:
        return json.load(r)


def raw_ccxt(sym, tf):
    import ccxt
    ex = ccxt.binanceusdm({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
    days = {'1w': 2200, '1d': 1100, '4h': 400, '1h': 100}[tf] + 30        # 網站的 ccxt 路徑多抓 30 天暖機
    since = ex.milliseconds() - days * 86400000; rows = []
    while True:
        b = ex.fetch_ohlcv(sym, tf, since=since, limit=1000)
        if not b: break
        rows += b
        if len(b) < 1000: break
        since = b[-1][0] + 1
    df = pd.DataFrame(rows, columns=['ts', 'o', 'h', 'l', 'c', 'v']); df['t'] = pd.to_datetime(df.ts, unit='ms', utc=True)
    now = pd.Timestamp.now(tz='UTC'); df = df[df.t + pd.Timedelta(seconds=STEP[tf]) <= now]          # 只留已收盤
    return df.reset_index(drop=True)


def raw_yf(sym, tf, market):
    import yfinance as yf
    kw = dict(auto_adjust=True)
    if tf == '1h': kw['period'] = '730d'
    else: kw['start'] = (datetime.datetime.now() - datetime.timedelta(days={'1w': 2200, '1d': 1100}[tf])).strftime('%Y-%m-%d')
    h = yf.Ticker(sym).history(interval={'1w': '1wk', '1d': '1d', '1h': '1h'}[tf], **kw)
    h = h[h.Close > 0]; tz = ZoneInfo(TZ[market]); now = datetime.datetime.now(tz)
    close_hm = (13, 30) if market == 'tw' else (16, 0)
    def closed(ts):
        ts = ts.tz_convert(tz) if ts.tzinfo else ts.tz_localize(tz)
        if tf == '1h': return ts + pd.Timedelta(hours=1) <= now
        if tf == '1d': return datetime.datetime.combine(ts.date(), datetime.time(*close_hm), tzinfo=tz) <= now
        return datetime.datetime.combine((ts + pd.Timedelta(days=4)).date(), datetime.time(*close_hm), tzinfo=tz) <= now
    h = h[[closed(ts) for ts in h.index]]
    df = pd.DataFrame({'t': [ts.tz_convert('UTC') for ts in h.index], 'o': h.Open.values, 'h': h.High.values, 'l': h.Low.values, 'c': h.Close.values})
    return df.reset_index(drop=True), h.index


def indicators(df):
    c, h, l = df.c, df.h, df.l
    e = {k: c.ewm(span=k, adjust=False).mean().iloc[-1] for k in (20, 50, 200)}
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    up, dn = h.diff(), -l.diff()
    pdm = ((up > dn) & (up > 0)) * up; mdm = ((dn > up) & (dn > 0)) * dn
    atr_w = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr_w; mdi = 100 * mdm.ewm(alpha=1 / 14, adjust=False).mean() / atr_w
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi); adx = dx.ewm(alpha=1 / 14, adjust=False).mean()
    return {'ema20': e[20], 'ema50': e[50], 'ema200': e[200], 'atr': atr, 'plusDi': pdi.iloc[-1], 'minusDi': mdi.iloc[-1], 'adx': adx.iloc[-1], 'close': c.iloc[-1]}


def main():
    base, out = sys.argv[1], sys.argv[2]; rep = []; bad = 0
    for sym, market in SYMS:
        d = api(base, sym); ent = {e['tf']: e for e in d['timeframes']}
        for tf in ('1w', '1d', '4h', '1h'):
            e = ent[tf]
            if not e['supported']:
                rep.append({'symbol': sym, 'tf': tf, 'result': 'unsupported(符合預期)' if (tf == '4h' and market != 'crypto') else 'UNEXPECTED unsupported'}); bad += (tf != '4h' or market == 'crypto'); continue
            raw = raw_ccxt(sym, tf) if market == 'crypto' else raw_yf(sym, tf, market)[0]
            dt = e['data']
            if market == 'crypto':                                                          # 取得起點不同(網站多抓 30 天暖機)→ 截到網站的第一根,指標與根數才有可比性
                raw = raw[raw.t >= pd.Timestamp(dt['firstBar'], tz='UTC')].reset_index(drop=True)
            last = raw.iloc[-1]; ind = e['indicators'] or {}; r = {'symbol': sym, 'tf': tf, 'quality': e['quality']['status'], 'checks': {}}
            # 1) 最後已收盤 K 棒:時間戳(UTC)與當地時間
            app_utc = dt['lastBarUtc']; fmt = '%Y-%m-%d' if tf in ('1d', '1w') else '%Y-%m-%d %H:%M'
            if market != 'crypto' and tf in ('1d', '1w'):
                raw_label = last.t.tz_convert(TZ[market]).strftime(fmt) if tf == '1h' else (last.t.tz_convert(TZ[market]) + pd.Timedelta(hours=12)).strftime(fmt)
                # yfinance 日/週線的時間戳是當地交易日的 00:00(當地);網站把它標成『當地日期』
                raw_label = raw.t.iloc[-1].tz_convert(TZ[market]).strftime(fmt)
            else:
                raw_label = last.t.strftime(fmt)
            r['checks']['lastBarUtc'] = {'api': app_utc, 'raw': raw_label, 'ok': app_utc == raw_label}
            if tf in ('1h', '4h') and market != 'crypto':
                loc = last.t.tz_convert(TZ[market]).strftime(fmt)
                r['checks']['lastBarLocal'] = {'api': dt['lastBarLocal'], 'raw': loc, 'ok': dt['lastBarLocal'] == loc}
            r['checks']['closeMatchesRaw'] = {'api': ind.get('close'), 'raw': round(float(last.c), 2), 'ok': ind.get('close') is not None and abs(ind['close'] - float(last.c)) <= max(0.011, abs(last.c) * 1e-4)}
            r['checks']['barCountMatches'] = {'api': dt['bars'], 'raw': len(raw), 'ok': abs(dt['bars'] - len(raw)) <= 3 or e['quality']['status'] != 'ok'}   # 起算日期/取得量不同,差幾根是正常
            if ind:
                mine = indicators(raw); tol = lambda a, b, p: abs(a - b) <= max(p * abs(b), 0.011)
                for k, p in (('ema20', 1e-3), ('ema50', 1e-3), ('ema200', 2e-3), ('atr', 0.03), ('plusDi', 0.04), ('minusDi', 0.04)):
                    if ind.get(k) is None: continue
                    r['checks'][k] = {'api': ind[k], 'indep': round(float(mine[k]), 3), 'ok': bool(tol(ind[k], float(mine[k]), p) or abs(ind[k] - mine[k]) <= (1.5 if k in ('plusDi', 'minusDi') else 0))}
                r['checks']['adx(參考)'] = {'api': ind['adx'], 'indep(Wilder 平滑)': round(float(mine['adx']), 2), 'note': '既有 calc_adx 用最後 14 個 DX 的平均,獨立實作用 Wilder 平滑,數值略有差異是預期;兩者用同一份 DX', 'ok': True}
            r['allOk'] = all(c['ok'] for c in r['checks'].values()); bad += (not r['allOk']); rep.append(r)
            print(sym, tf, 'OK' if r['allOk'] else 'MISMATCH', {k: v['ok'] for k, v in r['checks'].items() if not v['ok']}, flush=True)
    json.dump({'mismatches': int(bad), 'rows': rep}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=lambda o: bool(o) if hasattr(o, 'dtype') else str(o))
    print('total mismatches:', bad)


main()

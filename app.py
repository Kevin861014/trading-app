from flask import Flask, jsonify, request
from flask_cors import CORS
import sys, os, datetime, time, math, bisect, calendar
sys.path.insert(0, os.path.dirname(__file__))
from sim import run_backtest, STRATS, market_cost, cost_kwargs, classify_market
from sim import ema as calc_ema

EXTRA_STRAT_CODES = set()  # 擴充策略代碼（integration/ 研究產出，主要在幣安加密貨幣上驗證過）

def _register_extra_strats():
    """載入 integration/ 底下研究產出的擴充策略，合併進 STRATS。
    跟機器人 app.py 的 _register_extra_strats() 保持同一份清單，讓網頁的策略庫跟機器人同步。"""
    integ = os.path.join(os.path.dirname(__file__), "integration")
    if integ not in sys.path:
        sys.path.insert(0, integ)
    try:
        from extra_strats import EXTRA_STRATS as V1
        from extra_strats_v3 import EXTRA_STRATS_V3
        from extra_strats_v4 import EXTRA_STRATS_V4
        from extra_strats_v5 import EXTRA_STRATS_V5
        from extra_strats_v6 import EXTRA_STRATS_V6
        from extra_strats_v7 import EXTRA_STRATS_V7
        from extra_strats_v8 import EXTRA_STRATS_V8
        from extra_strats_v9 import EXTRA_STRATS_V9
        from extra_strats_loop import EXTRA_STRATS_LOOP
    except Exception as e:
        print(f'⚠️  擴充策略載入失敗（{e}），僅使用基礎策略庫')
        return
    def wrap(fn):
        def build(O, H, L, C, V, tf):
            out = fn(O, H, L, C, V, tf)
            if isinstance(out, tuple) and len(out) == 4:
                return out[0], out[1]
            return out
        return build
    for pool in (V1, EXTRA_STRATS_V3, EXTRA_STRATS_V4, EXTRA_STRATS_V5, EXTRA_STRATS_V6,
                 EXTRA_STRATS_V7, EXTRA_STRATS_V8, EXTRA_STRATS_V9, EXTRA_STRATS_LOOP):
        for code, meta in pool.items():
            if not meta.get("build") or code in STRATS:
                continue
            STRATS[code] = dict(
                name=meta.get("name", code),
                build=wrap(meta["build"]),
                atr_stop=0.0, atr_trail=0.0, atr_tp=0.0,
                pct_stop=0.025, pct_tp=0.075,
                min_bars=int(meta.get("min_bars") or 0),    # 策略自己宣告需要的暖機根數;資料不夠時 run_backtest 會回報不足
            )
            EXTRA_STRAT_CODES.add(code)
    print(f'✅ 擴充策略載入完成，新增 {len(EXTRA_STRAT_CODES)} 個策略（策略庫共 {len(STRATS)} 個）')

_register_extra_strats()

app = Flask(__name__)
CORS(app)

import os
IS_RENDER = os.environ.get('RENDER') == 'true'

# 啟動時測試 ccxt 連線一次，之後直接用結果
CCXT_AVAILABLE = False
if not IS_RENDER:
    try:
        import ccxt as _ccxt_test
        _ex = _ccxt_test.binanceusdm({'enableRateLimit': True,
                                       'options': {'defaultType': 'future'}})
        _ex.fetch_ohlcv('BTC/USDT', '1d', limit=1)
        CCXT_AVAILABLE = True
        print('✅ ccxt 幣安連線成功，加密貨幣使用真實 4H 資料')
    except Exception as _e:
        CCXT_AVAILABLE = False
        print(f'⚠️  ccxt 連線失敗（{_e}），使用 yfinance')

PERIOD_DAYS = {
    '7d': 7, '1mo': 30, '3mo': 90, '6mo': 180, '1y': 365, '2y': 730, '3y': 1095, '5y': 1825
}

STRAT_LIST = [
    # ── 核心順勢 ──
    {"v": "sixline",    "l": "⭐ 六條線 多頭排列（最推薦）"},
    {"v": "diadx",      "l": "⭐ DMI/ADX 方向動能（台股最強）"},
    {"v": "tsmom",      "l": "⭐ 時間序列動能（美股最強）"},
    {"v": "vbreakr",    "l": "⭐ 波動突破+趨勢過濾（美股強）"},
    {"v": "supertrend", "l": "Supertrend（黃金/PAXG 最佳）"},
    {"v": "keltner",    "l": "Keltner 通道突破"},
    {"v": "volbreak",   "l": "波動突破（貴金屬最強）"},
    {"v": "ttm",        "l": "TTM 擠壓突破（加密4H最強）"},
    {"v": "donchian",   "l": "Donchian 突破"},
    {"v": "smc",        "l": "SMC 結構突破+FVG"},
    {"v": "bbreak",     "l": "布林帶突破"},
    {"v": "lrs",        "l": "線性回歸斜率"},
    {"v": "ichimoku",   "l": "Ichimoku 雲突破"},
    {"v": "cci",        "l": "CCI 動能突破"},
    {"v": "vortex",     "l": "Vortex 渦流順勢"},
    {"v": "hma",        "l": "Hull MA 斜率翻轉"},
    {"v": "rsi50",      "l": "RSI-50 收復"},
    {"v": "ema_cross",  "l": "EMA 快慢線交叉"},
    {"v": "pullback",   "l": "順勢回檔買進（貴金屬佳）"},
    {"v": "pullbk",     "l": "順勢回檔買 2.0（美股佳）"},
    {"v": "rolltrend",  "l": "順勢滾倉加碼（美股日線）"},
    {"v": "trend",      "l": "順勢 EMA20/100（通用）"},
    {"v": "trend3",     "l": "三點一線趨勢線突破"},
    # ── 指標類 ──
    {"v": "macd",       "l": "MACD 趨勢"},
    {"v": "psar",       "l": "Parabolic SAR 順勢"},
    {"v": "kama",       "l": "KAMA 自適應均線（貴金屬佳）"},
    {"v": "heikin",     "l": "Heikin-Ashi 趨勢（貴金屬佳）"},
    # ── 量能類（需成交量，加密4H） ──
    {"v": "vwap",       "l": "VWAP 收復（加密4H量能）"},
    {"v": "obv",        "l": "OBV 量能趨勢（加密4H）"},
    {"v": "force",      "l": "Force Index 力度（加密4H）"},
    {"v": "cmf",        "l": "Chaikin 資金流（加密4H）"},
    # ── 型態類 ──
    {"v": "wbottom",    "l": "雙重/三重底反轉"},
    # ── 逆勢類 ──
    {"v": "crsi",       "l": "Connors RSI 逆勢（勝率67%）"},
    {"v": "rsi",        "l": "RSI 均值回歸（逆勢）"},
]

# ── 擴充策略（integration/ 研究產出，跟機器人同步）──
_listed = {s["v"] for s in STRAT_LIST}
STRAT_LIST += [{"v": code, "l": meta.get("name", code)}
               for code, meta in STRATS.items() if code not in _listed]

_cache = {}
_cache_time = {}
CACHE_TTL = 3600

def is_crypto_symbol(symbol):
    """判斷是不是加密貨幣代碼。只看代碼本身,跟 sim.classify_market 是同一套規則(成本與資料路由才不會各判各的)。
    以前用子字串比對(代碼裡含 BTC/ETH/SOL… 就算加密),像 GBTC、ETHE 這種美股會被誤判。"""
    return classify_market(symbol) == 'crypto'

def _utcnow():
    """交易紀錄與權益曲線的日期都是『UTC 的 naive datetime』,切窗口也要用 UTC,不能用本機時間(台灣差 8 小時)。"""
    return datetime.datetime.utcnow()

def _fmt_px(x):
    """價格顯示:>=1 取 2 位;小於 1(例如 1000PEPE、VET)取 6 位,避免被 round(,2) 變成 0。"""
    return round(x, 2) if x >= 1 else round(x, 6)

INTRADAY = ('1h', '4h')

def tf_to_data_interval(timeframe):
    """前端時框 → 實際資料時框。4H 就是 4H（以前被偷換成 1H，造成跟機器人用的 K 棒不一致）。"""
    return {'1d': '1d', '4h': '4h', '1h': '1h'}.get(timeframe, '1d')

def uses_ccxt(symbol):
    return bool(CCXT_AVAILABLE and is_crypto_symbol(symbol))

def resample_ohlcv(rows, bucket_ms):
    """把較細的 K 棒合成較粗的（以 UTC epoch 對齊，跟幣安 4H 的 0/4/8/12/16/20 點一致）。
    只收『填滿』的區間，最後一根未走完的不收。"""
    out = []; cur = None; n = 0; per = None
    if len(rows) >= 2:
        per = min(rows[i+1][0] - rows[i][0] for i in range(min(len(rows)-1, 50)) if rows[i+1][0] > rows[i][0])
    need = int(bucket_ms // per) if per else 0
    for r in rows:
        b = r[0] - (r[0] % bucket_ms)
        if cur is None or cur[0] != b:
            if cur is not None and n >= need: out.append(cur)
            cur = [b, r[1], r[2], r[3], r[4], (r[5] if len(r) > 5 else 0.0)]; n = 1
        else:
            cur[2] = max(cur[2], r[2]); cur[3] = min(cur[3], r[3]); cur[4] = r[4]
            cur[5] += (r[5] if len(r) > 5 else 0.0); n += 1
    if cur is not None and n >= need:
        out.append(cur)
    return out

def fetch_ccxt_ohlcv(symbol, interval, days):
    """用 ccxt 從幣安抓加密貨幣 K 棒（本機專用）"""
    try:
        import ccxt
        # 轉換代碼格式：BTC-USD → BTC/USDT，PAXG.TW → 不支援
        sym = symbol.upper()
        if '-USD' in sym:
            base = sym.replace('-USD','')
            ccxt_sym = f"{base}/USDT"
        elif '/USDT' in sym:
            ccxt_sym = sym
        else:
            # 嘗試直接用代碼加 /USDT
            ccxt_sym = f"{sym}/USDT"

        # 時框轉換
        tf_map = {'1d':'1d', '1h':'1h', '4h':'4h'}
        ccxt_tf = tf_map.get(interval, '1d')

        ex = ccxt.binanceusdm({'enableRateLimit': True,
                               'options': {'defaultType': 'future'}})
        since = ex.milliseconds() - days * 24 * 3600 * 1000
        all_ohlcv = []
        while True:
            batch = ex.fetch_ohlcv(ccxt_sym, ccxt_tf, since=since, limit=1000)
            if not batch: break
            all_ohlcv += batch
            if len(batch) < 1000: break
            since = batch[-1][0] + 1
        # 機器人只用『已收盤』的 K 棒；日內時框把還在走的最後一根拿掉，訊號才會跟機器人一致
        _ms = {'1h': 3600000, '4h': 14400000, '1d': 86400000}.get(ccxt_tf)
        if _ms and all_ohlcv and all_ohlcv[-1][0] + _ms > ex.milliseconds():
            all_ohlcv = all_ohlcv[:-1]
        # 格式：[ts, o, h, l, c, v]
        return [[r[0],r[1],r[2],r[3],r[4],r[5]] for r in all_ohlcv if r[4] > 0]
    except Exception as e:
        print(f"ccxt 失敗（{symbol}）: {e}，退回 yfinance")
        return None

def _is_forming(ts, symbol, interval, now=None):
    """yfinance 最後一根 K 棒是不是還沒收盤(盤中/當日)。沒收盤的 K 棒不能拿來算訊號,機器人也只用已收盤的。
    now 只給測試注入時間用;None 就用目前時間(取該 K 棒所在交易所的時區)。"""
    try:
        tz = ts.tzinfo
        if now is None:
            now = datetime.datetime.now(tz) if tz else datetime.datetime.now()
        if interval == '1h':
            return ts + datetime.timedelta(hours=1) > now
        if interval == '1d':
            if ts.date() != now.date():
                return False
            m = classify_market(symbol)
            if m == 'crypto':
                return True
            hh, mm = (13, 30) if m == 'tw' else (16, 0)     # 台股 13:30 收盤;美股/其他 16:00(當地時間)
            return (now.hour, now.minute) < (hh, mm)
    except Exception:
        pass
    return False

def fetch_data(symbol, start_date, interval='1d'):
    cache_key = f"{symbol}_{start_date}_{interval}"
    now = time.time()
    if cache_key in _cache and (now - _cache_time.get(cache_key, 0)) < CACHE_TTL:
        return _cache[cache_key]

    # 本機 + 加密貨幣 + ccxt 可用 → 用 ccxt（可抓真正 4H 和更長歷史）
    if CCXT_AVAILABLE and is_crypto_symbol(symbol) and interval in ('1h','4h','1d'):
        days = max(int((datetime.datetime.now() -
                        datetime.datetime.strptime(start_date, '%Y-%m-%d')).days) + 30, 100)
        # 4H 用真正的 4h 時框，不用 1H 替代
        ccxt_interval = interval
        result = fetch_ccxt_ohlcv(symbol, ccxt_interval, days)
        if result and len(result) > 100:
            _cache[cache_key] = result
            _cache_time[cache_key] = now
            return result

    # 沒有 ccxt（例如 Render）：yfinance 沒有 4H，改抓 1H 再合成真正的 4H
    if interval == '4h':
        base = fetch_data(symbol, start_date, '1h')
        out = resample_ohlcv(base, 4 * 3600 * 1000) if base else []
        if out:
            _cache[cache_key] = out
            _cache_time[cache_key] = now
        return out

    # 其他情況用 yfinance
    import yfinance as yf
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(2 * attempt)
            ticker = yf.Ticker(symbol)
            kw = dict(auto_adjust=True)
            if interval == '1h':
                kw['period'] = '730d'
            else:
                kw['start'] = start_date
            df = ticker.history(interval=interval, **kw)
            if df is not None and not df.empty:
                out = []; out_ts = []
                for ts, row in df.iterrows():
                    try:
                        o=float(row['Open']); h=float(row['High'])
                        l=float(row['Low']);  c=float(row['Close'])
                        v=float(row['Volume']) if 'Volume' in row else 0.0
                        if c > 0:
                            ms = int(ts.timestamp()*1000)
                            if interval == '1d':
                                # 日線時間戳統一成「交易所當地日期的 00:00 UTC」。不然台股(UTC+8)的 11/05 會被標成 11/04。
                                ms = int(datetime.datetime(ts.year, ts.month, ts.day, tzinfo=datetime.timezone.utc).timestamp()*1000)
                            out.append([ms, o, h, l, c, v]); out_ts.append(ts)
                    except Exception:
                        continue
                if out and interval in ('1d', '1h') and _is_forming(out_ts[-1], symbol, interval):
                    out.pop()          # 還沒收盤的最後一根不用
                if out:
                    _cache[cache_key] = out
                    _cache_time[cache_key] = now
                    return out
        except Exception as e:
            if attempt == 2: raise e
            time.sleep(2)
    return []

def calc_pf(trade_log):
    """從 trade_log 直接計算真實 PF（總獲利 / 總虧損），跟阿軒 sim.py 一致"""
    wins  = [t['ret'] for t in trade_log if t.get('ret') is not None and t['ret'] > 0]
    losses= [t['ret'] for t in trade_log if t.get('ret') is not None and t['ret'] < 0]
    if not losses:
        return round(sum(wins), 2) if wins else 0.0
    pf = sum(wins) / abs(sum(losses))
    return round(min(pf, 999), 2)

def compound_metrics(rets, years=None):
    """以「複利／權益曲線」計算總報酬、最大回撤、年化。
    rets 是每筆交易報酬（%）的 list，例如 +10% 傳 10。
    本金從 1.0 開始逐筆相乘（equity *= 1 + ret/100），代表「本金實際變多少」。
    回傳 (total%, mdd%, cagr%)。"""
    equity = 1.0; peak = 1.0; mdd = 0.0
    for r in rets:
        if r is None:
            continue
        equity *= (1 + r / 100.0)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
        if dd > mdd:
            mdd = dd
    total = round((equity - 1.0) * 100, 2)
    mdd = round(mdd, 2)
    if years and years > 0 and equity > 0:
        cagr = round((equity ** (1.0 / years) - 1) * 100, 2)
    else:
        cagr = total
    return total, mdd, cagr

def equity_window_metrics(dates, equity, cutoff_dt=None, years=None):
    """照搬機器人邏輯：從 run_backtest 的權益曲線取一段期間，算總報酬/回撤/年化。
    dates、equity 同長度（run_backtest 回傳，含 1.5% 風險部位 + 3倍槓桿 + 複利）。
    cutoff_dt：只取此日期之後的曲線；None 代表整段。
    總報酬是 seg[-1]/seg[0] 的比率，期間之前累積的本金會自動約掉，只算這段期間的漲跌。"""
    if not equity or not dates or len(equity) < 2:
        return 0.0, 0.0, 0.0
    if cutoff_dt is not None:
        idx = next((i for i, d in enumerate(dates) if d >= cutoff_dt), 0)
    else:
        idx = 0
    seg = equity[idx:]
    if len(seg) < 2 or seg[0] <= 0:
        return 0.0, 0.0, 0.0
    base = seg[0]
    peak = base; mdd = 0.0
    for v in seg:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0.0
        if dd > mdd:
            mdd = dd
    total = (seg[-1] / base - 1) * 100
    if years and years > 0:
        yrs = years
    else:
        yrs = max((dates[-1] - dates[idx]).days / 365.25, 1e-9)
    cagr = ((seg[-1] / base) ** (1.0 / yrs) - 1) * 100 if seg[-1] > 0 else 0.0
    return round(total, 2), round(mdd, 2), round(cagr, 2)

def calc_adx(ohlcv, period=14):
    """
    計算 ADX（趨勢強度）與方向。
    回傳 dict: {adx, plus_di, minus_di} 或 None（資料不足）。
    純 Python 實作，不依賴 numpy/pandas。ohlcv 格式 [ts,o,h,l,c,v]。
    """
    n = len(ohlcv)
    if n < period * 2 + 1:
        return None
    H = [r[2] for r in ohlcv]
    L = [r[3] for r in ohlcv]
    C = [r[4] for r in ohlcv]

    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, n):
        up_move   = H[i] - H[i-1]
        down_move = L[i-1] - L[i]
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        tr = max(H[i] - L[i], abs(H[i] - C[i-1]), abs(L[i] - C[i-1]))
        tr_list.append(tr)

    # Wilder 平滑
    def wilder(arr, p):
        if len(arr) < p:
            return []
        out = [sum(arr[:p])]
        for i in range(p, len(arr)):
            out.append(out[-1] - out[-1] / p + arr[i])
        return out

    atr = wilder(tr_list, period)
    pdm = wilder(plus_dm, period)
    mdm = wilder(minus_dm, period)
    if not atr or len(atr) < 1:
        return None

    dx_list = []
    for i in range(len(atr)):
        if atr[i] == 0:
            continue
        pdi = 100 * pdm[i] / atr[i]
        mdi = 100 * mdm[i] / atr[i]
        denom = pdi + mdi
        if denom == 0:
            dx_list.append(0.0)
        else:
            dx_list.append(100 * abs(pdi - mdi) / denom)

    if len(dx_list) < period:
        adx = sum(dx_list) / len(dx_list) if dx_list else 0.0
    else:
        adx = sum(dx_list[-period:]) / period

    last_pdi = 100 * pdm[-1] / atr[-1] if atr[-1] else 0.0
    last_mdi = 100 * mdm[-1] / atr[-1] if atr[-1] else 0.0
    return {'adx': round(adx, 1), 'plus_di': round(last_pdi, 1), 'minus_di': round(last_mdi, 1)}


def market_character(ohlcv, period=14):
    """
    判斷市場性格：結合 ADX（趨勢強度）與 +DI/-DI（方向）。
    回傳 {adx, label, dir, code}。
      code: 'up'(上升趨勢) / 'down'(下降趨勢) / 'range'(盤整) / 'na'(資料不足)
    """
    a = calc_adx(ohlcv, period)
    if a is None:
        return {'adx': None, 'label': '資料不足', 'dir': '', 'code': 'na'}
    adx = a['adx']
    up = a['plus_di'] >= a['minus_di']
    if adx >= 25:
        if up:
            return {'adx': adx, 'label': '上升趨勢', 'dir': 'up', 'code': 'up'}
        return {'adx': adx, 'label': '下降趨勢', 'dir': 'down', 'code': 'down'}
    elif adx < 20:
        return {'adx': adx, 'label': '盤整', 'dir': '', 'code': 'range'}
    else:
        # 20~25 過渡帶：方向不明
        return {'adx': adx, 'label': '趨勢轉換中', 'dir': 'up' if up else 'down', 'code': 'range'}


def calc_oos_pf(trade_log, split_date):
    """計算 OOS 段（split_date 之後）的 PF"""
    oos = [t for t in trade_log
           if t.get('exit_date') and
           t['exit_date'].strftime('%Y-%m-%d') >= split_date]
    return calc_pf(oos)


def get_real_trades(ohlcv, el_full, xl_full, strat_info=None):
    """圖上買賣標記與目前持倉狀態。
    以前這裡自己另寫一套進出場模擬(不支援 pct_trail/pct_tp/atr_tp、停損時序也跟回測不同),
    標記會跟回測績效對不起來。現在直接用 sim 同一個模擬器,標記 = 回測的實際進出場棒。"""
    import sim as _sim
    N = len(ohlcv)
    T=[r[0] for r in ohlcv]; O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
    L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
    A = _sim.atr(H, L, C, 14)
    s = strat_info or STRATS['trend']
    if s.get('pyramid'):
        pp = s['pyramid']
        _, _, _, tlog = _sim._simulate_pyramid(T,O,H,L,C, el_full, A, pp['init_atr'], pp['trail_atr'],
                                               pp['add_atr'], pp['max_adds'], 0.015, 3.0, 10000.0)
    else:
        _, _, _, tlog = _sim._simulate(T,O,H,L,C, el_full, xl_full, A, s.get('atr_stop',0), s.get('atr_trail',0),
                                       s.get('atr_tp',0), 0.015, 3.0, 10000.0,
                                       s.get('pct_stop',0.0), s.get('pct_trail',0.0), s.get('pct_tp',0.0))
    buy_idx = [None] * N
    sell_idx = [None] * N
    for t in tlog:
        if t.get('entry_i') is not None: buy_idx[t['entry_i']] = True
        if t.get('exit_i') is not None:  sell_idx[t['exit_i']] = True
    return buy_idx, sell_idx

_MARKET_TZ = {'crypto': ('UTC', 'UTC'), 'tw': ('Asia/Taipei', '台北時間 (UTC+8)'),
              'us': ('America/New_York', '美東時間'), 'commodity': ('America/New_York', '美東時間'),
              'metal_etf': ('America/New_York', '美東時間')}


def build_data_info(symbol, yf_tf, ohlcv):
    """最新資料時間與時區(只描述事實;完整的資料品質狀態機在後續階段)。最後一根一律是已收盤 K 棒(fetch 時已排除未收盤)。"""
    market = classify_market(symbol)
    tz, tz_label = _MARKET_TZ.get(market, ('UTC', 'UTC'))
    intraday = yf_tf in INTRADAY
    fmt = '%Y-%m-%d %H:%M' if intraday else '%Y-%m-%d'
    last_ts = ohlcv[-1][0] / 1000.0
    last_utc = datetime.datetime.utcfromtimestamp(last_ts)
    info = {'market': market, 'tz': tz, 'tzLabel': tz_label, 'interval': yf_tf, 'bars': len(ohlcv),
            'source': 'ccxt' if uses_ccxt(symbol) else 'yfinance',
            'firstBar': datetime.datetime.utcfromtimestamp(ohlcv[0][0] / 1000.0).strftime(fmt),
            'lastBarUtc': last_utc.strftime(fmt), 'lastBarClosed': True}
    if intraday:
        try:
            from zoneinfo import ZoneInfo
            info['lastBarLocal'] = datetime.datetime.fromtimestamp(last_ts, ZoneInfo(tz)).strftime(fmt)
        except Exception:
            info['lastBarLocal'] = None
    else:
        info['lastBarLocal'] = last_utc.strftime(fmt)      # 日線時間戳已統一成「交易所當地日期」
    return info


def build_validation(symbol, strategy, yf_tf, days, ohlcv, dates, equity, stats, now_dt):
    """這個『已選定策略』的樣本內 / 樣本外績效(跟排名用同一套切分與函式)。
    注意:若這個策略是看過排名或 OOS 結果後才選的,這段 OOS 就已經不是完全獨立的了。"""
    base = {'minOosTrades': OOS_MIN_TRADES, 'tierThresholds': {'preliminary': OOS_TIER_PRELIM, 'evaluable': OOS_TIER_EVAL}}
    window_start = now_dt - datetime.timedelta(days=days)
    split = is_oos_split(ohlcv, window_start, now_dt)
    if not split:
        return dict(base, available=False, reason='這個期間的資料不夠長,切不出樣本內/樣本外')
    ck = cost_kwargs(symbol, strategy)
    is_blk = None
    res_is = run_backtest(ohlcv[:split['idx_b']], strategy=strategy, risk_pct=0.015, timeframe=yf_tf, **ck)
    if res_is:
        d_is, e_is, st_is = res_is
        tl = [t for t in st_is.get('trade_log', []) if not t.get('open') and t.get('entry_date') and t['entry_date'] >= window_start]
        is_blk = _perf_block(tl, d_is, e_is, window_start)
    boundary = split['boundary_dt']
    _, oos_t, carry, _ = partition_trades(stats.get('trade_log', []), window_start, boundary)
    oos = _perf_block(oos_t, dates, equity, boundary)
    oos['carry'] = len(carry)
    oos['tier'] = oos_tier(oos['trades'])
    _insuff, legacy = oos_verdict(oos['trades'], oos['pf'])
    oos['legacyTechPass'] = legacy
    return dict(base, available=True, tier=oos['tier'], legacyTechPass=legacy, **{'is': is_blk}, oos=oos,
                split={'windowStart': window_start.strftime('%Y-%m-%d'), 'boundary': boundary.strftime('%Y-%m-%d'),
                       'end': split['end_dt'].strftime('%Y-%m-%d'), 'isBars': split['is_bars'], 'oosBars': split['oos_bars']})


def _downsample(seq, max_pts):
    n = len(seq)
    if n <= max_pts: return list(seq)
    step = (n - 1) / float(max_pts - 1)
    idx = sorted({int(round(i * step)) for i in range(max_pts)} | {n - 1})
    return [seq[i] for i in idx]


def build_backtest_viz(symbol, strategy, ohlcv, dates, equity, stats, cut_dt, yf_tf, n_trades, max_pts=300):
    """權益 / 回撤 / 買進持有 / 成本,全部來自同一次回測與同一份已收盤 K 棒(沒有另外編造)。
    權益與回撤以『顯示期間起點』為 0%,與卡片上的總報酬、最大回撤同口徑(同一個 equity_window_metrics 切法)。"""
    idx = next((i for i, d in enumerate(dates) if d >= cut_dt), 0)
    seg_d, seg_e = dates[idx:], equity[idx:]
    if len(seg_e) < 2 or seg_e[0] <= 0:
        return {'available': False, 'reason': '這個期間的權益曲線資料不足'}
    base = seg_e[0]
    ts = [_to_ms(d) // 1000 for d in seg_d]
    eq_pct = [(e / base - 1.0) * 100.0 for e in seg_e]
    peak = seg_e[0]; dd = []
    for e in seg_e:
        peak = max(peak, e); dd.append((e / peak - 1.0) * 100.0 if peak > 0 else 0.0)
    close_by_ms = {r[0]: r[4] for r in ohlcv}
    bh = []; c0 = close_by_ms.get(_to_ms(seg_d[0]))
    if c0:
        for d, t in zip(seg_d, ts):
            c = close_by_ms.get(_to_ms(d))
            bh.append([t, round((c / c0 - 1.0) * 100.0, 3)] if c else None)
    bh = [x for x in bh if x]
    bh_mdd = None
    if bh:
        pk = -1e18; bh_mdd = 0.0
        for _, v in bh:
            lvl = 100.0 + v; pk = max(pk, lvl); bh_mdd = max(bh_mdd, (pk - lvl) / pk * 100.0)
    ck = cost_kwargs(symbol, strategy)
    win_tr = [t for t in stats.get('trade_log', []) if not t.get('open') and t.get('entry_date') and t['entry_date'] >= cut_dt]
    paid = sum(t.get('cost', 0.0) for t in win_tr)
    rt = 2 * (ck['commission'] + ck['slippage']) + ck['sell_tax']
    mk = lambda xs, ys: [[t, round(v, 3)] for t, v in zip(xs, ys)]
    return {'available': True, 'tz': 'UTC',
            'period': {'start': seg_d[0].strftime('%Y-%m-%d'), 'end': seg_d[-1].strftime('%Y-%m-%d'), 'bars': len(seg_e), 'trades': n_trades},
            'equity': _downsample(mk(ts, eq_pct), max_pts), 'drawdown': _downsample(mk(ts, dd), max_pts), 'buyHold': _downsample(bh, max_pts),
            'summary': {'strategyTotal': round(eq_pct[-1], 2), 'strategyMaxDD': round(-min(dd), 2),
                        'buyHoldTotal': bh[-1][1] if bh else None, 'buyHoldMaxDD': round(bh_mdd, 2) if bh_mdd is not None else None},
            'cost': {'paidPctOfEquity': round(paid / base * 100.0, 2), 'tradesInWindow': len(win_tr), 'roundTripPct': round(rt * 100.0, 3),
                     'commission': ck['commission'], 'slippage': ck['slippage'], 'sellTax': ck['sell_tax'],
                     'note': '成本已計入上面的策略權益曲線(每筆交易:手續費+滑價,台股另加賣出證交稅);買進持有未計成本。'}}


@app.route('/api/strategies')
def get_strategies():
    return jsonify(STRAT_LIST)

@app.route('/api/analyze')
def analyze():
    symbol    = request.args.get('symbol', '2330.TW')
    strategy  = request.args.get('strategy', 'diadx')
    period    = request.args.get('period', '1y')
    timeframe = request.args.get('timeframe', '1d')

    # 4H 用真正的 4H K 棒（本機走 ccxt；沒有 ccxt 時由 1H 合成 4H），不再偷換成 1H
    yf_tf = tf_to_data_interval(timeframe)

    days = PERIOD_DAYS.get(period, 365)
    if yf_tf in INTRADAY:
        if yf_tf == '4h' and uses_ccxt(symbol):
            fetch_days = days + 300        # ccxt 真 4H：足夠暖機（約 1800 根）
        else:
            fetch_days = min(days + 100, 680)  # yfinance 1h（含由 1h 合成的 4h）上限約 730 天
    else:
        fetch_days = days + 700
    start_date = (datetime.datetime.now() - datetime.timedelta(days=fetch_days)).strftime('%Y-%m-%d')

    try:
        import sim as _sim
        _ck = cost_kwargs(symbol, strategy)    # 依代碼所屬市場計成本(加密/台股/美股...),所有 API 同一個入口

        ohlcv = fetch_data(symbol, start_date, interval=yf_tf)

        if not ohlcv or len(ohlcv) < 100:
            cnt = len(ohlcv) if ohlcv else 0
            return jsonify({'error': f'資料不足（取得 {cnt} 根）。台股如 2330.TW，美股如 AAPL，加密如 PAXG-USD'}), 400

        # 回測需要足夠暖機，不夠就提示
        if len(ohlcv) < 220:
            return jsonify({'error': f'資料不足以跑回測（{len(ohlcv)} 根），請選擇更長的時間範圍或改用日線'}), 400

        result = run_backtest(ohlcv, strategy=strategy, risk_pct=0.015, timeframe=yf_tf,
                              **_ck)
        if not result:
            return jsonify({'error': '回測失敗，請選擇更長的時間範圍'}), 400

        dates_dt, equity, stats = result

        O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
        L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
        V=[(r[5] if len(r)>5 else 0.0) for r in ohlcv]
        s = STRATS.get(strategy, STRATS['trend'])
        el_full, xl_full = s['build'](O, H, L, C, V, yf_tf)

        real_buy, real_sell = get_real_trades(ohlcv, el_full, xl_full, strat_info=s)

        # 顯示窗口以「時間」切（最近 days 天），不用根數推算——
        # 因為 4H/1H 都被轉成 1H 資料抓取，舊的 days×6 會把窗口算成只剩 ~1/4 時間，
        # 導致卡片與「最佳策略」涵蓋的期間不同、筆數/報酬對不上。
        _disp_cut_ms = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp() * 1000
        display_n = sum(1 for r in ohlcv if r[0] >= _disp_cut_ms)
        display_n = max(min(display_n, len(ohlcv)), 30)
        disp = ohlcv[-display_n:]
        offset = len(ohlcv) - display_n

        opens  = [r[1] for r in disp]
        highs  = [r[2] for r in disp]
        lows   = [r[3] for r in disp]
        prices = [r[4] for r in disp]
        dates  = [datetime.datetime.utcfromtimestamp(r[0]/1000).strftime('%Y-%m-%d %H:%M' if yf_tf in INTRADAY else '%Y-%m-%d') for r in disp]

        ema20 = calc_ema(prices, 20)
        ema50 = calc_ema(prices, 50)

        buy_points  = [prices[i] if real_buy[offset+i]  else None for i in range(len(prices))]
        sell_points = [prices[i] if real_sell[offset+i] else None for i in range(len(prices))]

        diff = []
        for i in range(len(prices)):
            if ema20[i] is not None and ema50[i] is not None and ema50[i] > 0:
                diff.append(round((ema20[i] - ema50[i]) / ema50[i] * 100, 3))
            else:
                diff.append(0)

        # 交易紀錄：直接用 run_backtest() 的 trade_log（next-bar open 進出場），
        # 與 best_strategy 使用同一個價格基礎，確保 PF/總報酬一致。
        _disp_cut_dt = _utcnow() - datetime.timedelta(days=days)
        if strategy == 'rolltrend':
            trades_list = [{'buyPrice': None, 'sellPrice': None, 'buyDate': None, 'sellDate': None,
                           'ret': None, 'note': '此策略使用加碼引擎，交易紀錄請參考回測數據'}]
            _all_disp = []
        else:
            _tlog_disp = [
                t for t in stats.get('trade_log', [])
                if not t.get('open') and t.get('exit_date') and t['exit_date'] >= _disp_cut_dt
            ]
            _all_disp = _tlog_disp
            fmt = '%Y-%m-%d %H:%M' if yf_tf in INTRADAY else '%Y-%m-%d'
            trades_list = [
                {
                    'buyPrice': _fmt_px(t['entry_px']) if t.get('entry_px') else None,
                    'sellPrice': _fmt_px(t['exit_px']) if t.get('exit_px') else None,
                    'buyDate': t['entry_date'].strftime(fmt) if t.get('entry_date') else None,
                    'sellDate': t['exit_date'].strftime(fmt) if t.get('exit_date') else None,
                    'ret': round(t['ret'], 2) if t.get('ret') is not None else None,
                }
                for t in _tlog_disp
            ]

        # ── 顯示期間的統計數字（與圖表三角形一致）──
        if strategy != 'rolltrend':
            _disp_wins = sum(1 for t in _all_disp if t.get('ret', 0) > 0)
            _disp_pf   = calc_pf([{'ret': t['ret']} for t in _all_disp])
            _disp_count = len(_all_disp)
            _disp_wr   = round(_disp_wins / len(_all_disp) * 100, 1) if _all_disp else 0
        else:
            _disp_pf   = calc_pf([t for t in stats.get('trade_log', []) if not t.get('open')])
            _disp_count = stats['trades']
            _disp_wr   = round(stats['win'], 1)

        trades_list = trades_list[-10:][::-1]  # 最新10筆，倒序顯示

        # ── 策略目前持倉狀態 ──
        current_pos = False
        last_buy_price = None
        last_buy_date = None
        last_buy_idx_display = None
        last_sell_date = None

        for i in range(len(prices)):
            if real_buy[offset+i]:
                current_pos = True
                last_buy_price = round(prices[i], 2)
                last_buy_date = dates[i]
                last_buy_idx_display = i
            elif real_sell[offset+i]:
                current_pos = False
                last_sell_date = dates[i]

        # 訊號有效期判斷
        signal_expired = False
        signal_days_ago = None
        if current_pos and last_buy_date:
            from datetime import datetime as dt2
            try:
                buy_dt = dt2.strptime(last_buy_date, '%Y-%m-%d')
                days_diff = (dt2.now() - buy_dt).days
                signal_days_ago = days_diff
                expire_days = 1 if yf_tf in INTRADAY else 3
                if days_diff > expire_days:
                    signal_expired = True
                if last_buy_price and prices[-1] > last_buy_price * 1.03:
                    signal_expired = True
            except:
                pass

        # 浮動損益
        float_pnl = None
        if current_pos and last_buy_price and prices:
            float_pnl = round((prices[-1] - last_buy_price) / last_buy_price * 100, 2)

        volumes = [round(r[5], 0) if r[5] > 0 else None for r in disp]

        # ── 顯示窗口的總報酬／回撤／年化 ──
        # 照搬機器人邏輯：直接用 run_backtest 的權益曲線（1.5%風險部位+3倍槓桿+複利），
        # 切到圖表顯示的期間（_disp_cut_dt 之後）。確定性、與圖表期間一致。
        _disp_total, _disp_mdd, _disp_cagr = equity_window_metrics(dates_dt, equity, _disp_cut_dt)

        try:
            _extras = {'dataInfo': build_data_info(symbol, yf_tf, ohlcv),
                       'validation': build_validation(symbol, strategy, yf_tf, days, ohlcv, dates_dt, equity, stats, _utcnow()),
                       'backtest': build_backtest_viz(symbol, strategy, ohlcv, dates_dt, equity, stats, _disp_cut_dt, yf_tf, _disp_count)}
        except Exception as _e:
            _extras = {'extrasError': str(_e)}
        return jsonify({
            **_extras,
            'dates': dates,
            'opens':  [round(p,2) for p in opens],
            'highs':  [round(p,2) for p in highs],
            'lows':   [round(p,2) for p in lows],
            'prices': [round(p,2) for p in prices],
            'ema20': [round(v,2) if v is not None else None for v in ema20],
            'ema50': [round(v,2) if v is not None else None for v in ema50],
            'buyPoints': buy_points,
            'sellPoints': sell_points,
            'diff': diff,
            'volumes': volumes,
            'posState': {
                'inPos': current_pos,
                'lastBuyPrice': last_buy_price,
                'lastBuyDate': last_buy_date,
                'lastSellDate': last_sell_date,
                'floatPnl': float_pnl,
                'signalExpired': signal_expired,
                'signalDaysAgo': signal_days_ago,
            },
            'metrics': {
                'totalReturn': _disp_total,
                'cagr': _disp_cagr,
                'pf': _disp_pf,
                'maxDD': _disp_mdd,
                'wr': _disp_wr,
                'tradeCount': _disp_count,
                'trades': trades_list,
            }
        })

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500

@app.route('/api/config')
def get_config():
    return jsonify({
        'isRender': IS_RENDER,
        'ccxtAvailable': CCXT_AVAILABLE,
        'dataSource': 'ccxt+yfinance' if CCXT_AVAILABLE else 'yfinance'
    })


@app.route('/api/market_character')
def api_market_character():
    """偵測標的當前市場性格（趨勢 / 盤整），給卡片顯示徽章用。"""
    symbol    = request.args.get('symbol', '2330.TW')
    timeframe = request.args.get('timeframe', '1d')
    yf_tf = tf_to_data_interval(timeframe)
    # 只需近期資料算 ADX，抓約 120 根足夠
    start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime('%Y-%m-%d')
    try:
        ohlcv = fetch_data(symbol, start_date, interval=yf_tf)
        if not ohlcv or len(ohlcv) < 30:
            return jsonify({'adx': None, 'label': '資料不足', 'dir': '', 'code': 'na'})
        return jsonify(market_character(ohlcv))
    except Exception as e:
        return jsonify({'adx': None, 'label': '偵測失敗', 'dir': '', 'code': 'na', 'error': str(e)})


# 策略分類：順勢 / 均值回歸 / 突破，給市場性格篩選用
STRAT_CATEGORY = {
    # 順勢（趨勢行情適用）
    'supertrend':'trend','donchian':'trend','ema_cross':'trend','sixline':'trend',
    'ichimoku':'trend','psar':'trend','kama':'trend','heikin':'trend','tsmom':'trend',
    'macd':'trend','lrs':'trend','vortex':'trend','diadx':'trend','hma':'trend',
    'keltner':'trend','rolltrend':'trend',
    # 均值回歸（盤整行情適用）
    'crsi':'range','cci':'range','rsi50':'range','rsi':'range','vwap':'range',
    'pullback':'range','pullbk':'range','obv':'range','cmf':'range','force':'range',
    # 突破（兩者皆可，偏趨勢啟動）
    'bbreak':'breakout','volbreak':'breakout','vbreakr':'breakout','ttm':'breakout',
    'smc':'breakout',
}
# 讓 /api/strategies 也帶上分類，前端才能比對「目前策略類型」跟「當下市場性格」合不合
for _s in STRAT_LIST:
    _s['cat'] = STRAT_CATEGORY.get(_s['v'], '')


# ── 樣本內(IS)/ 樣本外(OOS)驗證 ─────────────────────────────────────────
# 設計見 validation/stage2_oos/DESIGN.md。重點:
#   1. 只按時間順序切(前 70% = IS、後 30% = OOS),不隨機、不混合 K 棒。
#   2. 只用 IS 資料選策略並排名;IS 回測只拿『截斷到邊界之前』的資料跑,OOS 資料物理上進不了選擇流程。
#   3. 對入選者只做一次 OOS 驗證,結果只標註,不重排、不剔除、不調參。
#   4. 交易依『進場時間』歸屬;跨邊界的交易(IS 進場、OOS 出場)兩邊都不算。
#   5. OOS 筆數不足 → 標「證據不足」,不算通過。
OOS_FRACTION = 0.30
OOS_MIN_TRADES = 5
MIN_IS_WINDOW_BARS = 60     # IS 窗口(不含暖機)至少要有這麼多根,否則不切分
MIN_OOS_BARS = 20
SCALPERS = {'rsi2dip', 'ibsdip', 'zdip'}


def _to_ms(dt_):
    """naive UTC datetime → epoch ms"""
    return int(calendar.timegm(dt_.timetuple()) * 1000)


def strategy_pool(market, deep_intraday=False):
    """各市場適合跑的策略集合(跟原本 best_strategy / deep_analysis 內的集合相同,只是集中成一處)。"""
    tw_strats  = {'diadx','volbreak','sixline','pullback','supertrend','donchian',
                  'ema_cross','bbreak','lrs','ichimoku','cci','vortex','macd','kama','heikin','crsi','tsmom','rolltrend'}
    us_strats  = {'tsmom','vbreakr','bbreak','lrs','sixline','ema_cross','pullbk',
                  'rolltrend','crsi','macd','supertrend','ichimoku','cci','vortex','donchian'}
    crypto_strats = {'sixline','ttm','keltner','donchian','smc','hma','rsi50',
                     'vwap','obv','force','cmf','bbreak','lrs','cci','vortex','diadx'} | EXTRA_STRAT_CODES
    if deep_intraday:
        crypto_strats = crypto_strats | {'tsmom', 'ema_cross', 'supertrend'}
    metal_strats  = {'volbreak','supertrend','kama','heikin','ema_cross','pullback',
                     'macd','psar','rsi50','sixline','donchian'}
    if market == 'tw': return tw_strats
    if market == 'crypto': return crypto_strats
    if market in ('commodity', 'metal_etf'): return metal_strats
    return us_strats


def min_trades_for(market, deep=False):
    if deep:
        return 15 if market == 'crypto' else 8
    return 10 if market == 'crypto' else 5


def is_oos_split(ohlcv, window_start_dt, end_dt, oos_fraction=OOS_FRACTION):
    """時間順序切割。回傳切點資訊 dict;資料不夠切就回 None(呼叫端要明確回報,不能假裝有 OOS)。"""
    ts = [r[0] for r in ohlcv]
    boundary_dt = window_start_dt + (end_dt - window_start_dt) * (1.0 - oos_fraction)
    idx_b = bisect.bisect_left(ts, _to_ms(boundary_dt))
    w0 = _to_ms(window_start_dt)
    is_bars = sum(1 for t in ts[:idx_b] if t >= w0)
    oos_bars = len(ts) - idx_b
    if idx_b < 220 or is_bars < MIN_IS_WINDOW_BARS or oos_bars < MIN_OOS_BARS:
        return None
    return dict(boundary_dt=boundary_dt, idx_b=idx_b, window_start_dt=window_start_dt, end_dt=end_dt,
                is_bars=is_bars, oos_bars=oos_bars)


def partition_trades(trade_log, window_start_dt, boundary_dt):
    """依『進場時間』把交易分到 IS / OOS。回傳 (is_trades, oos_trades, carry_trades, open_trades)。
    - 進場早於窗口起點(暖機期)的不算任何一邊。
    - 進場在邊界前、出場在邊界後(跨邊界)→ carry,兩邊都不算(purge)。
    - 尚未平倉的不算(但會回傳,方便呼叫端說明)。"""
    is_t, oos_t, carry, opened = [], [], [], []
    for t in trade_log:
        ed = t.get('entry_date')
        if ed is None or ed < window_start_dt:
            continue
        if t.get('open'):
            opened.append(t); continue
        if ed < boundary_dt:
            (carry if t['exit_date'] >= boundary_dt else is_t).append(t)
        else:
            oos_t.append(t)
    return is_t, oos_t, carry, opened


# OOS 筆數的『展示分級』:只是讓人知道樣本量大概在哪個層級,不是統計顯著性判定,也不用於選策略。
OOS_TIER_PRELIM = 20     # < 20 筆:樣本不足
OOS_TIER_EVAL = 50       # 20~49 筆:初步觀察;>= 50 筆:可進一步評估(不代表已證明有效)


def oos_tier(n_trades):
    if n_trades < OOS_TIER_PRELIM: return 'insufficient'
    if n_trades < OOS_TIER_EVAL: return 'preliminary'
    return 'evaluable'


def oos_verdict(n_trades, pf):
    """回傳 (證據不足, 通過)。筆數不足就是『證據不足』,**不可能**算通過;夠了才看 PF 是否 > 1。"""
    insufficient = n_trades < OOS_MIN_TRADES
    return insufficient, (not insufficient) and pf > 1


def _trade_stats(trades):
    n = len(trades)
    wins = sum(1 for t in trades if (t.get('ret') or 0) > 0)
    return {'pf': calc_pf(trades), 'win': round(wins / n * 100, 1) if n else 0.0, 'trades': n}


def _perf_block(trades, dates, equity, cutoff_dt):
    total, mdd, cagr = equity_window_metrics(dates, equity, cutoff_dt)
    s = _trade_stats(trades)
    return {'pf': s['pf'], 'total': total, 'cagr': cagr, 'mdd': mdd, 'win': s['win'], 'trades': s['trades']}


def rank_strategies(ohlcv, symbol, yf_tf, allowed, min_trades, days, use_oos=True, top_n=8, now_dt=None):
    """跑 allowed 內所有策略,只用 IS 資料排名,回傳 (前 top_n 名, 切分資訊 或 None, 測試的策略數)。
    use_oos=False(快速模式)或資料不夠切 → 不切分,用全窗口排名,沒有 OOS。"""
    now_dt = now_dt or _utcnow()
    window_start_dt = now_dt - datetime.timedelta(days=days)
    split = is_oos_split(ohlcv, window_start_dt, now_dt) if use_oos else None
    rank_data = ohlcv[:split['idx_b']] if split else ohlcv          # 排名用的資料:OOS 資料在這裡就已經被截掉
    boundary_dt = split['boundary_dt'] if split else None

    pool = [k for k in STRATS if k not in SCALPERS and k in allowed]
    cands = []
    for strat_key in pool:
        try:
            ck = cost_kwargs(symbol, strat_key)
            res = run_backtest(rank_data, strategy=strat_key, risk_pct=0.015, timeframe=yf_tf, **ck)
            if not res:
                continue
            dates, equity, st = res
            tl = [t for t in st.get('trade_log', [])
                  if not t.get('open') and t.get('entry_date') and t['entry_date'] >= window_start_dt]
            blk = _perf_block(tl, dates, equity, window_start_dt)
            if not (blk['pf'] > 1 and blk['trades'] >= min_trades and blk['mdd'] < 50):
                continue
            ret_bonus = 1.5 if blk['total'] >= 20 else (1.2 if blk['total'] >= 10 else 1.0)
            score = round(blk['pf'] * math.log(max(blk['trades'], 2)) * ret_bonus / (1 + blk['mdd'] / 100), 2)
            cands.append({'strat': strat_key, 'name': STRATS[strat_key]['name'], 'cat': STRAT_CATEGORY.get(strat_key, ''),
                          'score': score, **blk, 'is': dict(blk)})
        except Exception:
            continue

    cands.sort(key=lambda x: x['score'], reverse=True)               # 排序只看 IS 分數
    top = cands[:top_n]

    for r in top:
        r.update({'oos': None, 'full': None, 'oosStatus': 'unavailable', 'oosPf': None, 'oosTotal': None,
                  'oosTrades': None, 'oosPass': None, 'oosInsufficient': None, 'oosIndependent': bool(split),
                  'minOosTrades': OOS_MIN_TRADES, 'oosTier': 'unavailable', 'legacyTechPass': None})
        if not split:
            r['full'] = dict(r['is'])
            continue
        try:                                                           # 只對入選者做一次 OOS,結果只標註
            ck = cost_kwargs(symbol, r['strat'])
            res = run_backtest(ohlcv, strategy=r['strat'], risk_pct=0.015, timeframe=yf_tf, **ck)
            if not res:
                continue
            dates, equity, st = res
            tlog = st.get('trade_log', [])
            _, oos_t, carry, _ = partition_trades(tlog, window_start_dt, boundary_dt)
            full_t = [t for t in tlog if not t.get('open') and t.get('entry_date') and t['entry_date'] >= window_start_dt]
            r['full'] = _perf_block(full_t, dates, equity, window_start_dt)
            o = _perf_block(oos_t, dates, equity, boundary_dt)
            o['carry'] = len(carry)
            o['insufficient'], o['pass'] = oos_verdict(o['trades'], o['pf'])
            o['tier'] = oos_tier(o['trades'])                 # 展示分級(樣本量),與 pass 無關
            o['legacyTechPass'] = o['pass']                   # 舊版技術門檻:>=5 筆且 PF>1(非研究可信度)
            r['oosTier'] = o['tier']; r['legacyTechPass'] = o['pass']
            r['oos'] = o
            r['oosStatus'] = 'insufficient' if o['insufficient'] else ('pass' if o['pass'] else 'fail')
            r['oosInsufficient'] = o['insufficient']
            r['oosTrades'] = o['trades']
            r['oosTotal'] = o['total']
            if not o['insufficient']:
                r['oosPf'] = o['pf']
                r['oosPass'] = o['pass']
        except Exception:
            continue

    info = None
    if split:
        info = {'mode': 'time', 'oosFraction': OOS_FRACTION, 'minOosTrades': OOS_MIN_TRADES,
                'windowStart': split['window_start_dt'].strftime('%Y-%m-%d'),
                'boundary': split['boundary_dt'].strftime('%Y-%m-%d'),
                'end': split['end_dt'].strftime('%Y-%m-%d'),
                'isBars': split['is_bars'], 'oosBars': split['oos_bars'],
                'tierThresholds': {'preliminary': OOS_TIER_PRELIM, 'evaluable': OOS_TIER_EVAL}}
    return top, info, len(pool)


@app.route('/api/best_strategy')
def best_strategy():
    """跑所有策略,只用『樣本內(IS)』資料排名取前 8 名,再對這 8 名做一次獨立的『樣本外(OOS)』驗證。
    回傳每名的 is / oos / full 三組績效(full = IS+OOS 全期間,僅供參考)。"""
    symbol    = request.args.get('symbol', '2330.TW')
    period    = request.args.get('period', '2y')
    timeframe = request.args.get('timeframe', '1d')
    use_oos   = request.args.get('use_oos', '1') == '1'
    yf_tf = tf_to_data_interval(timeframe)

    days = PERIOD_DAYS.get(period, 730)
    # yfinance 1H 資料上限約 730 天（沒有 ccxt 時 4H 也是由 1H 合成，同樣受限）；本機 ccxt 的真 4H 沒這個限制
    _limited = (yf_tf == '1h') or (yf_tf == '4h' and not uses_ccxt(symbol))
    if _limited and days > 700:
        days = 700
    # 跟一般查詢一樣用暖機資料，確保筆數一致
    if yf_tf in INTRADAY:
        fetch_days = min(days + 100, 680) if _limited else days + 300
    else:
        fetch_days = days + 700
    start_date = (datetime.datetime.now() - datetime.timedelta(days=fetch_days)).strftime('%Y-%m-%d')

    try:
        ohlcv = fetch_data(symbol, start_date, interval=yf_tf)
        if not ohlcv or len(ohlcv) < 220:
            return jsonify({'error': f'資料不足（{len(ohlcv) if ohlcv else 0} 根），4H 策略建議選 2 年以內'}), 400

        market = classify_market(symbol)
        top, split, tested = rank_strategies(ohlcv, symbol, yf_tf, strategy_pool(market),
                                             min_trades_for(market), days, use_oos=use_oos)
        mc = market_character(ohlcv) if ohlcv else {'code': 'na', 'label': '資料不足', 'adx': None}
        return jsonify({'results': top, 'total_tested': tested, 'character': mc,
                        'split': split, 'oosAvailable': bool(split), 'oosRequested': use_oos})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500


@app.route('/api/deep_analysis')
def deep_analysis():
    """深度分析:資料比較長(加密 2 年、台股/美股 5 年),門檻比較嚴。
    跟 best_strategy 用同一套 IS/OOS:只用 IS 選與排名,OOS 只標註(trust=2 代表 OOS 通過,但不影響排序)。
    以前的『3年+5年 / 6個月+2年 交叉驗證』是互相重疊的巢狀窗口,而且用 OOS 當篩選門檻,已移除。"""
    if IS_RENDER:
        return jsonify({'error': '深度分析僅支援本機執行，Render 免費版會超時'}), 403

    symbol    = request.args.get('symbol', '2330.TW')
    timeframe = request.args.get('timeframe', '1d')
    use_oos   = request.args.get('use_oos', '1') == '1'
    yf_tf = tf_to_data_interval(timeframe)

    try:
        market = classify_market(symbol)
        intraday = yf_tf in INTRADAY
        if intraday:
            days = 730
            start = (datetime.datetime.now() - datetime.timedelta(days=days + 400)).strftime('%Y-%m-%d')
            ohlcv = fetch_data(symbol, start, interval=yf_tf)
            if not ohlcv or len(ohlcv) < 220:
                return jsonify({'error': '資料不足，請確認幣種代碼是否正確'}), 400
            allowed = strategy_pool('crypto', deep_intraday=True)    # 1H/4H 深度分析一律用加密策略集(跟原本一樣)
            min_trades = min_trades_for('crypto', deep=True)
        else:
            days = 5 * 365
            start = (datetime.datetime.now() - datetime.timedelta(days=days + 700)).strftime('%Y-%m-%d')
            ohlcv = fetch_data(symbol, start, interval=yf_tf)
            if not ohlcv or len(ohlcv) < 220:
                return jsonify({'error': '5年資料不足'}), 400
            allowed = strategy_pool(market)
            min_trades = min_trades_for(market, deep=True)

        top, split, tested = rank_strategies(ohlcv, symbol, yf_tf, allowed, min_trades, days, use_oos=use_oos)
        for r in top:
            r['trust'] = 2 if r.get('oosStatus') == 'pass' else 1     # 只代表 OOS 是否通過,不影響排序
        return jsonify({'results': top, 'hasOos': use_oos, 'isDeep': True, 'isCrypto': intraday,
                        'total_tested': tested, 'split': split, 'oosAvailable': bool(split)})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500


@app.route('/api/validate')
def validate():
    """驗證股票代碼是否能抓到資料，並嘗試取得名稱"""
    symbol = request.args.get('symbol', '')
    if not symbol:
        return jsonify({'valid': False, 'error': '代碼不能為空'})

    def try_fetch(sym):
        """嘗試抓資料，回傳 (成功, 名稱)"""
        try:
            import yfinance as yf
            ticker = yf.Ticker(sym)
            # 先抓資料，不抓 info（info 很慢容易超時）
            df = ticker.history(period='5d')
            if df is not None and not df.empty:
                # 有資料才嘗試抓名稱
                try:
                    info = ticker.fast_info
                    name = getattr(info, 'long_name', None) or sym
                except:
                    name = sym
                name = str(name).replace(' Inc.','').replace(' Corp.','').replace(' Co.','').replace(',','').strip()
                return True, name
            return False, None
        except:
            return False, None

    # 先試原本代碼
    ok, name = try_fetch(symbol)
    if ok:
        return jsonify({'valid': True, 'symbol': symbol, 'name': name})

    # 4位數字自動補 .TW
    if symbol.isdigit() and len(symbol) == 4:
        symbol2 = symbol + '.TW'
        ok2, name2 = try_fetch(symbol2)
        if ok2:
            return jsonify({'valid': True, 'symbol': symbol2, 'name': name2 or symbol2, 'suggestion': symbol2})

    # 加密貨幣常見寫法（CHZ/USDT、CHZUSDT、純代碼 CHZ）→ 換成 yfinance 認得的 XXX-USD 再試一次。
    # 這裡不用 yfinance 查 CHZ/USDT 本身一定查不到（yfinance 沒有這種代碼格式），
    # 但其餘功能（fetch_data／is_crypto_symbol）本來就支援 /USDT，只有這支驗證漏掉，要跟資料抓取那邊統一。
    sym_upper = symbol.upper()
    base = None
    if '/USDT' in sym_upper:
        base = sym_upper.split('/USDT')[0]
    elif sym_upper.endswith('USDT') and len(sym_upper) > 4:
        base = sym_upper[:-4]
    elif '-USD' not in sym_upper and sym_upper.isalpha():
        base = sym_upper  # 純代碼（例如只打 CHZ）也順便試試看
    if base:
        symbol3 = f'{base}-USD'
        ok3, name3 = try_fetch(symbol3)
        if ok3:
            return jsonify({'valid': True, 'symbol': symbol3, 'name': name3 or symbol3, 'suggestion': symbol3})

    # 都找不到
    return jsonify({'valid': False, 'error': f'找不到 {symbol}，請確認代碼是否正確（台股格式：1101.TW，加密：BTC-USD 或 BTC/USDT）'})


@app.route('/api/signal')
def signal():
    """輕量版：只回傳訊號狀態，不回傳完整 K 線資料，用於導覽列快速載入"""
    symbol   = request.args.get('symbol', '2330.TW')
    strategy = request.args.get('strategy', 'diadx')
    timeframe = request.args.get('timeframe', '1d')
    yf_tf = tf_to_data_interval(timeframe)

    # 輕量版只需要最近 300 天
    start_date = (datetime.datetime.now() - datetime.timedelta(days=300)).strftime('%Y-%m-%d')

    try:
        import sim as _sim
        ohlcv = fetch_data(symbol, start_date, interval=yf_tf)
        if not ohlcv or len(ohlcv) < 50:
            return jsonify({'error': '資料不足', 'state': 'unknown'})

        # 補暖機資料不夠就拉長
        if len(ohlcv) < 220:
            start_date2 = (datetime.datetime.now() - datetime.timedelta(days=700)).strftime('%Y-%m-%d')
            ohlcv = fetch_data(symbol, start_date2, interval=yf_tf)

        if not ohlcv or len(ohlcv) < 100:
            return jsonify({'error': '資料不足', 'state': 'unknown'})

        O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
        L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
        V=[(r[5] if len(r)>5 else 0.0) for r in ohlcv]
        s = STRATS.get(strategy, STRATS['trend'])
        el_full, xl_full = s['build'](O, H, L, C, V, yf_tf)

        real_buy, real_sell = get_real_trades(ohlcv, el_full, xl_full, strat_info=s)

        # 只看最後狀態
        prices = [r[4] for r in ohlcv]
        dates = [datetime.datetime.utcfromtimestamp(r[0]/1000).strftime('%Y-%m-%d') for r in ohlcv]

        current_pos = False
        last_buy_price = None
        last_buy_date = None
        last_sell_date = None

        for i in range(len(prices)):
            if real_buy[i]:
                current_pos = True
                last_buy_price = round(prices[i], 2)
                last_buy_date = dates[i]
            elif real_sell[i]:
                current_pos = False
                last_sell_date = dates[i]

        # EMA 差距判斷趨勢
        from sim import ema as calc_ema_sig
        ema20 = calc_ema_sig(prices, 20)
        ema50 = calc_ema_sig(prices, 50)
        last_diff = 0
        if ema20[-1] and ema50[-1] and ema50[-1] > 0:
            last_diff = (ema20[-1] - ema50[-1]) / ema50[-1] * 100

        has_buy_now = real_buy[-1]
        has_sell_now = real_sell[-1]

        # 訊號有效期
        signal_expired = False
        float_pnl = None
        signal_days_ago = None
        if current_pos and last_buy_date:
            try:
                buy_dt = datetime.datetime.strptime(last_buy_date, '%Y-%m-%d')
                days_diff = (datetime.datetime.now() - buy_dt).days
                signal_days_ago = days_diff
                expire_days = 1 if yf_tf in INTRADAY else 3
                if days_diff > expire_days:
                    signal_expired = True
                if last_buy_price and prices[-1] > last_buy_price * 1.03:
                    signal_expired = True
                if last_buy_price:
                    float_pnl = round((prices[-1] - last_buy_price) / last_buy_price * 100, 2)
            except:
                pass

        # 判斷狀態
        if has_buy_now:
            state = 'buy'
            label = '▲ 買進訊號！'
            dot = 'buy'
        elif has_sell_now:
            state = 'sell'
            label = '▼ 賣出訊號！'
            dot = 'sell'
        elif current_pos:
            if signal_expired:
                state = 'expired'
                label = '⚠ 訊號已過期'
                dot = 'expired'
            else:
                days_str = f'第{signal_days_ago+1}天' if signal_days_ago is not None else ''
                state = 'holding'
                label = f'▲ 持有中 {days_str}'
                dot = 'buy'
        elif last_sell_date:
            state = 'exited'
            label = '▼ 已出場'
            dot = 'sell'
        elif last_diff > 0.1:
            state = 'wait'
            label = '▲ 多頭等待'
            dot = 'hold'
        elif last_diff < -0.1:
            state = 'bear'
            label = '▼ 空頭觀望'
            dot = 'sell'
        else:
            state = 'neutral'
            label = '— 中立'
            dot = 'hold'

        return jsonify({
            'state': state,
            'label': label,
            'dot': dot,
            'floatPnl': float_pnl,
            'lastBuyDate': last_buy_date,
            'lastSellDate': last_sell_date,
        })

    except Exception as e:
        return jsonify({'error': str(e), 'state': 'unknown', 'label': '— 載入失敗', 'dot': 'hold'})


@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)

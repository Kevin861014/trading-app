from flask import Flask, jsonify, request
from flask_cors import CORS
import sys, os, datetime, time
sys.path.insert(0, os.path.dirname(__file__))
from sim import run_backtest, STRATS, market_cost
from sim import ema as calc_ema

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

_cache = {}
_cache_time = {}
CACHE_TTL = 3600

def is_crypto_symbol(symbol):
    """判斷是不是加密貨幣代碼"""
    s = symbol.upper()
    return (s.endswith('-USD') or '/USDT' in s or
            any(c in s for c in ['BTC','ETH','BNB','SOL','XRP','DOGE','ADA',
                                  'LINK','LTC','TRX','PAXG','DOT','XLM']))

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
        # 格式：[ts, o, h, l, c, v]
        return [[r[0],r[1],r[2],r[3],r[4],r[5]] for r in all_ohlcv if r[4] > 0]
    except Exception as e:
        print(f"ccxt 失敗（{symbol}）: {e}，退回 yfinance")
        return None

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
                out = []
                for ts, row in df.iterrows():
                    try:
                        o=float(row['Open']); h=float(row['High'])
                        l=float(row['Low']);  c=float(row['Close'])
                        v=float(row['Volume']) if 'Volume' in row else 0.0
                        if c > 0:
                            out.append([int(ts.timestamp()*1000), o, h, l, c, v])
                    except Exception:
                        continue
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

def calc_oos_pf(trade_log, split_date):
    """計算 OOS 段（split_date 之後）的 PF"""
    oos = [t for t in trade_log
           if t.get('exit_date') and
           t['exit_date'].strftime('%Y-%m-%d') >= split_date]
    return calc_pf(oos)


def get_real_trades(ohlcv, el_full, xl_full, strat_info=None):
    """
    模擬 sim.py 的進出場邏輯，包含停損判斷，確保交易筆數與 run_backtest 一致。
    """
    from sim import atr as calc_atr
    N = len(ohlcv)
    O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
    L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
    A = calc_atr(H, L, C, 14)

    pos = False
    buy_idx = [None] * N
    sell_idx = [None] * N
    entry = 0.0
    stop = None

    # 取策略停損參數
    atr_stop = strat_info.get('atr_stop', 0) if strat_info else 0
    atr_trail = strat_info.get('atr_trail', 0) if strat_info else 0
    pct_stop = strat_info.get('pct_stop', 0) if strat_info else 0
    peak = None

    for i in range(N - 1):
        o2 = O[i+1]
        if pos:
            # 停損判斷
            if stop is not None and L[i] <= stop:
                pos = False
                sell_idx[i] = True
                stop = None; peak = None
                continue
            # 追蹤停損更新
            if atr_trail > 0 and A[i] is not None:
                peak = max(peak if peak else -1e18, H[i])
                new_stop = peak - atr_trail * A[i]
                stop = max(stop, new_stop) if stop else new_stop
            # 一般出場訊號
            if xl_full[i]:
                pos = False
                sell_idx[i+1] = True
                stop = None; peak = None
        if not pos and el_full[i]:
            pos = True
            entry = o2
            buy_idx[i+1] = True
            peak = H[i]
            if atr_stop > 0 and A[i] is not None:
                stop = C[i] - atr_stop * A[i]
            elif pct_stop > 0:
                stop = entry * (1 - pct_stop)
            else:
                stop = None

    return buy_idx, sell_idx

@app.route('/api/strategies')
def get_strategies():
    return jsonify(STRAT_LIST)

@app.route('/api/analyze')
def analyze():
    symbol    = request.args.get('symbol', '2330.TW')
    strategy  = request.args.get('strategy', 'diadx')
    period    = request.args.get('period', '1y')
    timeframe = request.args.get('timeframe', '1d')

    # yfinance 不支援 4h，用 1h 替代（sim.py 也這樣處理）
    yf_tf = {'1d':'1d', '4h':'1h', '1h':'1h'}.get(timeframe, '1d')

    days = PERIOD_DAYS.get(period, 365)
    if yf_tf == '1h':
        fetch_days = min(days + 100, 680)  # yfinance 1h 上限約 730 天
    else:
        fetch_days = days + 700
    start_date = (datetime.datetime.now() - datetime.timedelta(days=fetch_days)).strftime('%Y-%m-%d')

    try:
        import sim as _sim
        spec = ('yf', symbol)
        _sim.COMMISSION, _sim.SLIPPAGE = market_cost(spec, strategy)

        ohlcv = fetch_data(symbol, start_date, interval=yf_tf)

        if not ohlcv or len(ohlcv) < 100:
            cnt = len(ohlcv) if ohlcv else 0
            return jsonify({'error': f'資料不足（取得 {cnt} 根）。台股如 2330.TW，美股如 AAPL，加密如 PAXG-USD'}), 400

        # 回測需要足夠暖機，不夠就提示
        if len(ohlcv) < 220:
            return jsonify({'error': f'資料不足以跑回測（{len(ohlcv)} 根），請選擇更長的時間範圍或改用日線'}), 400

        result = run_backtest(ohlcv, strategy=strategy, risk_pct=0.015, timeframe=yf_tf)
        if not result:
            return jsonify({'error': '回測失敗，請選擇更長的時間範圍'}), 400

        dates_dt, equity, stats = result

        O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
        L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
        V=[(r[5] if len(r)>5 else 0.0) for r in ohlcv]
        s = STRATS.get(strategy, STRATS['trend'])
        el_full, xl_full = s['build'](O, H, L, C, V, yf_tf)

        real_buy, real_sell = get_real_trades(ohlcv, el_full, xl_full, strat_info=s)

        display_n = min(days * (6 if yf_tf=='1h' else 1) + 30, len(ohlcv))
        disp = ohlcv[-display_n:]
        offset = len(ohlcv) - display_n

        opens  = [r[1] for r in disp]
        highs  = [r[2] for r in disp]
        lows   = [r[3] for r in disp]
        prices = [r[4] for r in disp]
        dates  = [datetime.datetime.utcfromtimestamp(r[0]/1000).strftime('%Y-%m-%d %H:%M' if yf_tf=='1h' else '%Y-%m-%d') for r in disp]

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

        # 交易紀錄：賣出日期必須在顯示期間內，買進可以在之前
        # rolltrend 使用加碼引擎，訊號結構不同，略過交易紀錄
        if strategy == 'rolltrend':
            trades_list = [{'buyPrice': None, 'sellPrice': None, 'buyDate': None, 'sellDate': None,
                           'ret': None, 'note': '此策略使用加碼引擎，交易紀錄請參考回測數據'}]
        else:
            trades_list = []
        buy_px = None; buy_date = None
        full_prices = [r[4] for r in ohlcv]
        full_dates = [datetime.datetime.utcfromtimestamp(r[0]/1000).strftime(
            '%Y-%m-%d %H:%M' if yf_tf=='1h' else '%Y-%m-%d') for r in ohlcv]
        # 顯示期間的起始日期
        display_start = dates[0] if dates else ''
        for i in range(len(full_prices)):
            if real_buy[i]:
                buy_px = full_prices[i]; buy_date = full_dates[i]
            elif real_sell[i] and buy_px:
                sell_date = full_dates[i]
                # 只顯示賣出日期在顯示期間內的交易
                if sell_date >= display_start:
                    ret = round((full_prices[i] - buy_px) / buy_px * 100, 2)
                    trades_list.append({
                        'buyPrice': round(buy_px,2),
                        'sellPrice': round(full_prices[i],2),
                        'buyDate': buy_date,
                        'sellDate': sell_date,
                        'ret': ret
                    })
                buy_px = None
        # ── 顯示期間的統計數字（與圖表三角形一致）──
        if strategy != 'rolltrend':
            _all_disp = [t for t in trades_list if t.get('ret') is not None]
            _disp_wins = sum(1 for t in _all_disp if t['ret'] > 0)
            _disp_pf   = calc_pf([{'ret': t['ret']} for t in _all_disp])
            _disp_count = len(_all_disp)
            _disp_wr   = round(_disp_wins / len(_all_disp) * 100, 1) if _all_disp else 0
        else:
            _disp_pf   = calc_pf([t for t in stats.get('trade_log', []) if not t.get('open')])
            _disp_count = stats['trades']
            _disp_wr   = round(stats['win'], 1)

        trades_list = trades_list[-10:][::-1]

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
                expire_days = 1 if yf_tf == '1h' else 3
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

        return jsonify({
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
                'totalReturn': round(stats['total'],2),
                'cagr': round(stats['cagr'],2),
                'pf': _disp_pf,
                'maxDD': round(stats['mdd'],2),
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


@app.route('/api/best_strategy')
def best_strategy():
    """跑所有策略，回傳最佳前5名"""
    symbol    = request.args.get('symbol', '2330.TW')
    period    = request.args.get('period', '2y')
    timeframe = request.args.get('timeframe', '1d')
    use_oos   = request.args.get('use_oos', '1') == '1'
    yf_tf = {'1d':'1d', '4h':'1h', '1h':'1h'}.get(timeframe, '1d')

    days = PERIOD_DAYS.get(period, 730)
    # yfinance 1H 資料上限約 730 天，4H 策略用 1H 替代，超過會抓不到
    if yf_tf == '1h' and days > 700:
        days = 700
    # 跟一般查詢一樣用 +700 暖機資料，確保筆數一致
    if yf_tf == '1h':
        fetch_days = min(days + 100, 680)
    else:
        fetch_days = days + 700
    start_date = (datetime.datetime.now() - datetime.timedelta(days=fetch_days)).strftime('%Y-%m-%d')

    try:
        import sim as _sim

        # 只抓一次資料
        ohlcv = fetch_data(symbol, start_date, interval=yf_tf)
        if not ohlcv or len(ohlcv) < 220:
            return jsonify({'error': f'資料不足（{len(ohlcv) if ohlcv else 0} 根），4H 策略建議選 2 年以內'}), 400

        O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
        L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
        V=[(r[5] if len(r)>5 else 0.0) for r in ohlcv]

        results = []

        # ── OOS 驗證切割點（前70% IS 選策略，後30% OOS 驗證）──
        if use_oos:
            split_idx = int(len(ohlcv) * 0.7)
            ohlcv_is  = ohlcv[:split_idx]
            ohlcv_oos = ohlcv[split_idx:]
            do_oos = len(ohlcv_oos) >= 60 and len(ohlcv_is) >= 220
        else:
            # 快速模式：直接用全部資料
            ohlcv_is  = ohlcv
            ohlcv_oos = []
            do_oos = False

        # 根據市場選擇適合的策略，避免跑不適合的策略浪費時間
        tw_strats  = {'diadx','volbreak','sixline','pullback','supertrend','donchian',
                      'ema_cross','bbreak','lrs','ichimoku','cci','vortex','macd','kama','heikin','crsi','tsmom','rolltrend'}
        us_strats  = {'tsmom','vbreakr','bbreak','lrs','sixline','ema_cross','pullbk',
                      'rolltrend','crsi','macd','supertrend','ichimoku','cci','vortex','donchian'}
        crypto_strats = {'sixline','ttm','keltner','donchian','smc','hma','rsi50',
                         'vwap','obv','force','cmf','bbreak','lrs','cci','vortex','diadx'}
        metal_strats  = {'volbreak','supertrend','kama','heikin','ema_cross','pullback',
                         'macd','psar','rsi50','sixline','donchian'}

        # 判斷市場
        sym = symbol.upper()
        if sym.endswith('.TW'):
            allowed = tw_strats
        elif any(sym.endswith(x) for x in ['-USD','/USDT']) or any(c in sym for c in ['BTC','ETH','BNB','SOL','XRP','PAXG']):
            allowed = crypto_strats
        elif sym in {'GC=F','SI=F','PL=F','PA=F','GLD','SLV','PPLT','PALL'}:
            allowed = metal_strats
        else:
            allowed = us_strats

        # 永遠跳過剝頭皮類
        skip = {'rsi2dip','ibsdip','zdip'}

        for strat_key, strat_info in _sim.STRATS.items():
            if strat_key in skip or strat_key not in allowed:
                continue
            try:
                _sim.COMMISSION, _sim.SLIPPAGE = market_cost(('yf', symbol), strat_key)

                # 用 IS 資料選策略
                result_is = run_backtest(ohlcv_is, strategy=strat_key, risk_pct=0.015, timeframe=yf_tf)
                if not result_is:
                    continue
                _, _, stats_is = result_is

                # 用顯示期間的交易計算 PF / 筆數 / 勝率（與套用後圖表一致）
                import datetime as _dt
                _disp_start = datetime.datetime.now() - datetime.timedelta(days=days + 30)
                _disp_tlog = [
                    t for t in stats_is.get('trade_log', [])
                    if not t.get('open') and t.get('exit_date') and t['exit_date'] >= _disp_start
                ]
                pf_is = calc_pf(_disp_tlog)
                _disp_wins_is = sum(1 for t in _disp_tlog if t.get('ret', 0) > 0)
                _disp_wr_is = round(_disp_wins_is / len(_disp_tlog) * 100, 1) if _disp_tlog else 0

                # 用全量數據計算分數（統計樣本更多，排名更準）
                stats = stats_is
                pf = pf_is
                total = round(stats['total'], 2)
                trades = len(_disp_tlog)

                # 依市場設定最低筆數門檻
                sym_upper = symbol.upper()
                if sym_upper.endswith('.TW'):
                    min_trades = 5   # 台股日線
                elif any(sym_upper.endswith(x) for x in ['-USD','/USDT']) or any(c in sym_upper for c in ['BTC','ETH','BNB','SOL','XRP','PAXG']):
                    min_trades = 10  # 加密
                else:
                    min_trades = 5   # 美股日線

                # 篩選條件：PF > 1 且筆數達標 且 MDD < 50%
                mdd = round(stats['mdd'], 2)
                if pf > 1 and trades >= min_trades and mdd < 50:
                    import math
                    # 綜合分數 = PF × log(筆數) × 報酬加成 / (1 + MDD/100)
                    # PF 和筆數是主角，報酬是加分項，MDD 是懲罰項
                    if total >= 20:
                        ret_bonus = 1.5
                    elif total >= 10:
                        ret_bonus = 1.2
                    else:
                        ret_bonus = 1.0
                    mdd_penalty = 1 + mdd / 100  # MDD 越大，分數越低
                    score = round(pf * math.log(max(trades, 2)) * ret_bonus / mdd_penalty, 2)
                    results.append({
                        'strat': strat_key,
                        'name': strat_info['name'],
                        'pf': pf,
                        'total': total,
                        'cagr': round(stats['cagr'], 2),
                        'mdd': mdd,
                        'win': _disp_wr_is,
                        'trades': trades,
                        'score': score,
                        'oosPf': None,
                        'oosTotal': None,
                    })
            except Exception:
                continue

        # 按綜合分數排序（報酬 × PF × log(筆數)），取前 8 名
        results.sort(key=lambda x: x['score'], reverse=True)
        top = results[:8]

        tested_count = len([k for k in _sim.STRATS if k not in skip and k in allowed])
        return jsonify({'results': top, 'total_tested': tested_count})

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500


@app.route('/api/deep_analysis')
def deep_analysis():
    """深度分析：自動跑 3年+5年交叉驗證，找兩段都通過的策略"""
    if IS_RENDER:
        return jsonify({'error': '深度分析僅支援本機執行，Render 免費版會超時'}), 403

    symbol    = request.args.get('symbol', '2330.TW')
    timeframe = request.args.get('timeframe', '1d')
    use_oos   = request.args.get('use_oos', '1') == '1'
    yf_tf = {'1d':'1d', '4h':'1h', '1h':'1h'}.get(timeframe, '1d')

    try:
        import sim as _sim
        import math

        def run_for_period(period_key, ohlcv_data, symbol, yf_tf, do_oos_check=True):
            """跑指定資料的最佳策略，回傳通過的策略 dict"""
            sym_upper = symbol.upper()
            if sym_upper.endswith('.TW'):
                min_trades = 8
            elif any(sym_upper.endswith(x) for x in ['-USD','/USDT']) or any(c in sym_upper for c in ['BTC','ETH','BNB','SOL','XRP','PAXG']):
                min_trades = 15
            else:
                min_trades = 8

            tw_strats  = {'diadx','volbreak','sixline','pullback','supertrend','donchian',
                          'ema_cross','bbreak','lrs','ichimoku','cci','vortex','macd',
                          'kama','heikin','crsi','tsmom','rolltrend'}
            us_strats  = {'tsmom','vbreakr','bbreak','lrs','sixline','ema_cross','pullbk',
                          'rolltrend','crsi','macd','supertrend','ichimoku','cci','vortex','donchian'}
            crypto_strats = {'sixline','ttm','keltner','donchian','smc','hma','rsi50',
                             'vwap','obv','force','cmf','bbreak','lrs','cci','vortex','diadx'}
            metal_strats  = {'volbreak','supertrend','kama','heikin','ema_cross','pullback',
                             'macd','psar','rsi50','sixline','donchian'}

            if sym_upper.endswith('.TW'):
                allowed = tw_strats
            elif any(sym_upper.endswith(x) for x in ['-USD','/USDT']) or any(c in sym_upper for c in ['BTC','ETH','BNB','SOL','XRP','PAXG']):
                allowed = crypto_strats
            elif sym_upper in {'GC=F','SI=F','PL=F','PA=F','GLD','SLV'}:
                allowed = metal_strats
            else:
                allowed = us_strats

            skip = {'rsi2dip','ibsdip','zdip'}
            passed = {}

            split_idx = int(len(ohlcv_data) * 0.7)
            ohlcv_is  = ohlcv_data[:split_idx]
            ohlcv_oos = ohlcv_data[split_idx:]
            do_oos = len(ohlcv_oos) >= 60 and len(ohlcv_is) >= 220

            for strat_key, strat_info in _sim.STRATS.items():
                if strat_key in skip or strat_key not in allowed:
                    continue
                try:
                    _sim.COMMISSION, _sim.SLIPPAGE = market_cost(('yf', symbol), strat_key)
                    result_is = run_backtest(ohlcv_is, strategy=strat_key, risk_pct=0.015, timeframe=yf_tf)
                    if not result_is:
                        continue
                    _, _, stats_is = result_is
                    pf = calc_pf([t for t in stats_is.get('trade_log',[]) if not t.get('open')])
                    total = round(stats_is['total'], 2)
                    trades = stats_is.get('trades', 0)
                    mdd = round(stats_is['mdd'], 2)

                    if pf <= 1 or trades < min_trades or mdd >= 50:
                        continue

                    # OOS 驗證（可選）
                    oos_pf = None; oos_total = None
                    if do_oos and do_oos_check:
                        result_oos = run_backtest(ohlcv_oos, strategy=strat_key, risk_pct=0.015, timeframe=yf_tf)
                        if not result_oos:
                            continue
                        _, _, stats_oos = result_oos
                        oos_pf = calc_pf([t for t in stats_oos.get('trade_log',[]) if not t.get('open')])
                        if oos_pf <= 1:
                            continue
                        oos_total = round(stats_oos['total'], 2)

                    ret_bonus = 1.5 if total >= 20 else (1.2 if total >= 10 else 1.0)
                    mdd_penalty = 1 + mdd / 100
                    score = round(pf * math.log(max(trades, 2)) * ret_bonus / mdd_penalty, 2)

                    passed[strat_key] = {
                        'strat': strat_key,
                        'name': strat_info['name'],
                        'pf': pf, 'total': total,
                        'cagr': round(stats_is['cagr'], 2),
                        'mdd': mdd,
                        'win': round(stats_is['win'], 1),
                        'trades': trades,
                        'score': score,
                        'oosPf': oos_pf,
                        'oosTotal': oos_total,
                    }
                except Exception:
                    continue
            return passed

        # 抓 5 年資料（包含 3 年）
        start_5y = (datetime.datetime.now() - datetime.timedelta(days=5*365+700)).strftime('%Y-%m-%d')
        start_3y = (datetime.datetime.now() - datetime.timedelta(days=3*365+700)).strftime('%Y-%m-%d')

        _sim.COMMISSION, _sim.SLIPPAGE = market_cost(('yf', symbol), 'trend')

        if yf_tf == '1h':
            # ── 加密貨幣 4H/1H ──
            import math
            start_2y = (datetime.datetime.now() - datetime.timedelta(days=730+400)).strftime('%Y-%m-%d')
            ohlcv_2y = fetch_data(symbol, start_2y, interval=yf_tf)
            if not ohlcv_2y or len(ohlcv_2y) < 220:
                return jsonify({'error': '資料不足，請確認幣種代碼是否正確'}), 400

            sym_upper = symbol.upper()
            allowed = {'sixline','ttm','keltner','donchian','smc','hma','rsi50',
                       'vwap','obv','force','cmf','bbreak','lrs','cci','vortex','diadx',
                       'tsmom','ema_cross','supertrend'}
            skip = {'rsi2dip','ibsdip','zdip'}

            # 時間切割點
            cutoff_6mo = (datetime.datetime.now() - datetime.timedelta(days=180)).timestamp() * 1000
            cutoff_2y  = (datetime.datetime.now() - datetime.timedelta(days=730)).timestamp() * 1000

            def get_window_trades(trade_log, cutoff_ms):
                """取某個時間窗口內的交易"""
                return [t for t in trade_log
                        if not t.get('open') and t.get('exit_date') and
                        t['exit_date'].timestamp()*1000 >= cutoff_ms]

            def eval_window(trades):
                """評估一段時間內的交易績效"""
                if len(trades) < 10:
                    return None
                pf = calc_pf(trades)
                if pf <= 1:
                    return None
                total = round(sum(t['ret'] for t in trades if t.get('ret')), 2)
                wins = [t for t in trades if t.get('ret') and t['ret'] > 0]
                win_rate = round(len(wins)/len(trades)*100, 1)
                return {'pf': pf, 'total': total, 'win': win_rate, 'trades': len(trades)}

            crypto_results = []
            for strat_key, strat_info in _sim.STRATS.items():
                if strat_key in skip or strat_key not in allowed:
                    continue
                try:
                    result = run_backtest(ohlcv_2y, strategy=strat_key, risk_pct=0.015, timeframe=yf_tf)
                    if not result:
                        continue
                    _, _, stats = result
                    trade_log_all = stats.get('trade_log', [])
                    mdd = round(stats['mdd'], 2)
                    if mdd >= 50:
                        continue

                    # 評估兩個窗口
                    trades_6mo = get_window_trades(trade_log_all, cutoff_6mo)
                    trades_2y  = get_window_trades(trade_log_all, cutoff_2y)

                    r6mo = eval_window(trades_6mo)
                    r2y  = eval_window(trades_2y)

                    if not r6mo and not r2y:
                        continue

                    # 可信度
                    if r6mo and r2y:
                        trust = 2  # ⭐⭐ 兩段都通過
                        base = r6mo  # 顯示6個月的數字
                    elif r6mo:
                        trust = 1  # ⭐ 只有近期
                        base = r6mo
                    else:
                        trust = 1  # ⭐ 只有長期
                        base = r2y

                    ret_bonus = 1.5 if base['total'] >= 20 else (1.2 if base['total'] >= 10 else 1.0)
                    score = round(base['pf'] * math.log(max(base['trades'], 2)) * ret_bonus / (1 + mdd/100), 2)

                    crypto_results.append({
                        'strat': strat_key, 'name': strat_info['name'],
                        'pf': base['pf'], 'total': base['total'],
                        'cagr': round(stats['cagr'],2),
                        'mdd': mdd, 'win': base['win'],
                        'trades': base['trades'], 'score': score,
                        'oosPf': r2y['pf'] if r2y else None,
                        'oosTotal': r2y['total'] if r2y else None,
                        'trust': trust,
                        'in3y': bool(r6mo),   # 近6個月
                        'in5y': bool(r2y),    # 近2年
                    })
                except Exception:
                    continue

            if not use_oos:
                # 快速模式：只按報酬排序，不看可信度
                crypto_results.sort(key=lambda x: x['total'], reverse=True)
            else:
                crypto_results.sort(key=lambda x: (x['trust'], x['total']), reverse=True)
            return jsonify({'results': crypto_results[:8], 'hasOos': use_oos,
                           'isDeep': True, 'isCrypto': True})

        else:
            # ── 台股/美股日線 ──
            ohlcv_5y = fetch_data(symbol, start_5y, interval=yf_tf)
            if not ohlcv_5y or len(ohlcv_5y) < 220:
                return jsonify({'error': '5年資料不足'}), 400

            if not use_oos:
                # 快速模式：直接用全部 5 年資料，不切 IS/OOS，按報酬排序
                passed_3y = run_for_period('full', ohlcv_5y, symbol, yf_tf, do_oos_check=False)
                passed_5y = passed_3y  # 同一份資料，合併結果
            else:
                cutoff_3y = (datetime.datetime.now() - datetime.timedelta(days=3*365)).timestamp() * 1000
                ohlcv_3y = [r for r in ohlcv_5y if r[0] >= cutoff_3y]
                if len(ohlcv_3y) < 220:
                    return jsonify({'error': '3年資料不足'}), 400

                passed_3y = run_for_period('3y', ohlcv_3y, symbol, yf_tf, do_oos_check=True)
                passed_5y = run_for_period('5y', ohlcv_5y, symbol, yf_tf, do_oos_check=True)

        # 合併結果，標記可信度
        all_strats = set(passed_3y.keys()) | set(passed_5y.keys())
        results = []
        for strat_key in all_strats:
            in_3y = strat_key in passed_3y
            in_5y = strat_key in passed_5y

            if not use_oos:
                # 快速模式：直接用結果，不標記可信度
                base = passed_3y.get(strat_key) or passed_5y.get(strat_key)
                results.append({**base, 'trust': 1, 'in3y': True, 'in5y': True})
            else:
                if in_3y and in_5y:
                    trust = 2
                    base = passed_5y[strat_key]
                elif in_5y:
                    trust = 1
                    base = passed_5y[strat_key]
                else:
                    trust = 1
                    base = passed_3y[strat_key]
                results.append({**base, 'trust': trust, 'in3y': in_3y, 'in5y': in_5y})

        if not use_oos:
            # 快速模式按報酬排序
            results.sort(key=lambda x: x['total'], reverse=True)
        else:
            results.sort(key=lambda x: (x['trust'], x['score']), reverse=True)
        top = results[:8]

        return jsonify({'results': top, 'hasOos': use_oos, 'isDeep': True})

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

    # 都找不到
    return jsonify({'valid': False, 'error': f'找不到 {symbol}，請確認代碼是否正確（台股格式：1101.TW，加密：BTC-USD）'})


@app.route('/api/signal')
def signal():
    """輕量版：只回傳訊號狀態，不回傳完整 K 線資料，用於導覽列快速載入"""
    symbol   = request.args.get('symbol', '2330.TW')
    strategy = request.args.get('strategy', 'diadx')
    timeframe = request.args.get('timeframe', '1d')
    yf_tf = {'1d':'1d', '4h':'1h', '1h':'1h'}.get(timeframe, '1d')

    # 輕量版只需要最近 300 天
    start_date = (datetime.datetime.now() - datetime.timedelta(days=300)).strftime('%Y-%m-%d')

    try:
        import sim as _sim
        spec = ('yf', symbol)
        _sim.COMMISSION, _sim.SLIPPAGE = market_cost(spec, strategy)

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
                expire_days = 1 if yf_tf == '1h' else 3
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

from flask import Flask, jsonify, request
from flask_cors import CORS
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sim import run_backtest, fetch_yf, STRATS, COMMISSION, SLIPPAGE, market_cost
import datetime

app = Flask(__name__)
CORS(app)

PERIOD_DAYS = {
    '7d': 7, '1mo': 30, '1y': 365, '2y': 730, '3y': 1095, '5y': 1825
}

STRAT_LIST = [
    {"v": "sixline",    "l": "六條線 多頭排列（最推薦）"},
    {"v": "diadx",      "l": "DMI/ADX 方向動能（台股最強）"},
    {"v": "supertrend", "l": "Supertrend（黃金/PAXG 最佳）"},
    {"v": "keltner",    "l": "Keltner 通道突破"},
    {"v": "volbreak",   "l": "波動突破（貴金屬最強）"},
    {"v": "ttm",        "l": "TTM 擠壓突破（加密4H最強）"},
    {"v": "donchian",   "l": "Donchian 突破"},
    {"v": "ema_cross",  "l": "EMA 快慢線交叉"},
    {"v": "hma",        "l": "Hull MA 斜率翻轉"},
    {"v": "rsi50",      "l": "RSI-50 收復"},
    {"v": "tsmom",      "l": "時間序列動能（美股最強）"},
    {"v": "ichimoku",   "l": "Ichimoku 雲突破"},
    {"v": "cci",        "l": "CCI 動能突破"},
    {"v": "vortex",     "l": "Vortex 渦流順勢"},
    {"v": "bbreak",     "l": "布林帶突破"},
    {"v": "lrs",        "l": "線性回歸斜率"},
    {"v": "macd",       "l": "MACD 趨勢"},
    {"v": "crsi",       "l": "Connors RSI 逆勢（勝率67%）"},
    {"v": "rsi",        "l": "RSI 均值回歸（逆勢）"},
    {"v": "trend",      "l": "順勢 EMA20/100（通用）"},
]

@app.route('/api/strategies')
def get_strategies():
    return jsonify(STRAT_LIST)

@app.route('/api/analyze')
def analyze():
    symbol  = request.args.get('symbol', '2330.TW')
    strategy= request.args.get('strategy', 'diadx')
    period  = request.args.get('period', '1y')

    days = PERIOD_DAYS.get(period, 365)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days+400)).strftime('%Y-%m-%d')

    try:
        # 設定正確費率
        spec = ('yf', symbol)
        import sim as _sim
        _sim.COMMISSION, _sim.SLIPPAGE = market_cost(spec, strategy)

        ohlcv = fetch_yf(symbol, start=start_date, interval='1d')
        if not ohlcv or len(ohlcv) < 50:
            return jsonify({'error': '資料不足，請確認股票代碼'}), 400

        # 只取需要的天數
        target = days + 30
        if len(ohlcv) > target:
            ohlcv = ohlcv[-target:]

        result = run_backtest(ohlcv, strategy=strategy, risk_pct=0.015, timeframe='1d')
        if not result:
            return jsonify({'error': '回測資料不足（至少需要 220 根 K 棒）'}), 400

        dates_dt, equity, stats = result

        # 準備 K 線資料
        prices  = [r[4] for r in ohlcv]
        dates   = [datetime.datetime.utcfromtimestamp(r[0]/1000).strftime('%Y-%m-%d') for r in ohlcv]

        # 計算 EMA20/50 用於顯示
        from sim import ema as calc_ema
        ema20 = calc_ema(prices, 20)
        ema50 = calc_ema(prices, 50)

        # 重新跑訊號取得進出場點
        O=[r[1] for r in ohlcv]; H=[r[2] for r in ohlcv]
        L=[r[3] for r in ohlcv]; C=[r[4] for r in ohlcv]
        V=[(r[5] if len(r)>5 else 0.0) for r in ohlcv]
        s = STRATS.get(strategy, STRATS['trend'])
        el, xl = s['build'](O, H, L, C, V, '1d')

        buy_points  = [prices[i] if el[i] else None for i in range(len(prices))]
        sell_points = [prices[i] if xl[i] else None for i in range(len(prices))]

        # EMA 差距
        diff = []
        for i in range(len(prices)):
            if ema20[i] is not None and ema50[i] is not None and ema50[i] > 0:
                diff.append(round((ema20[i] - ema50[i]) / ema50[i] * 100, 3))
            else:
                diff.append(0)

        # 最近交易紀錄
        from sim import atr as calc_atr
        A = calc_atr(H, L, C, 14)
        trades_list = []
        buy_px = None
        for i in range(len(prices)):
            if el[i]: buy_px = prices[i]
            elif xl[i] and buy_px:
                ret = round((prices[i] - buy_px) / buy_px * 100, 2)
                trades_list.append({'buyPrice': round(buy_px,2), 'sellPrice': round(prices[i],2), 'ret': ret})
                buy_px = None
        trades_list = trades_list[-10:][::-1]

        return jsonify({
            'dates':      dates,
            'prices':     [round(p, 2) for p in prices],
            'ema20':      [round(v, 2) if v is not None else None for v in ema20],
            'ema50':      [round(v, 2) if v is not None else None for v in ema50],
            'buyPoints':  buy_points,
            'sellPoints': sell_points,
            'diff':       diff,
            'metrics': {
                'totalReturn': round(stats['total'], 2),
                'cagr':        round(stats['cagr'], 2),
                'pf':          round(stats.get('payoff', 0) * (stats['win']/100) / max((1 - stats['win']/100), 0.001), 2),
                'maxDD':       round(stats['mdd'], 2),
                'wr':          round(stats['win'], 1),
                'tradeCount':  stats['trades'],
                'trades':      trades_list,
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)

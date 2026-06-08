from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

def get_period_dates(period):
    end = datetime.now()
    periods = {
        '7d': timedelta(days=7),
        '1mo': timedelta(days=30),
        '1y': timedelta(days=365),
        '2y': timedelta(days=730),
        '3y': timedelta(days=1095),
        '5y': timedelta(days=1825),
    }
    start = end - periods.get(period, timedelta(days=365))
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')

def calc_ema(prices, period):
    k = 2 / (period + 1)
    ema = [prices[0]]
    for p in prices[1:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema

def calc_atr(highs, lows, closes, period=14):
    tr = [abs(highs[i] - lows[i]) for i in range(len(highs))]
    atr = [None] * period
    atr.append(sum(tr[:period]) / period)
    for i in range(period + 1, len(tr)):
        atr.append((atr[-1] * (period - 1) + tr[i]) / period)
    return atr

def run_strategy(prices, strategy, cost=0.0045):
    n = len(prices)
    signals = []

    if strategy == 'ema':
        fast = calc_ema(prices, 20)
        slow = calc_ema(prices, 50)
        in_pos = False
        for i in range(1, n):
            if not in_pos and fast[i] > slow[i] and fast[i-1] <= slow[i-1]:
                signals.append({'i': i, 'type': 'buy', 'price': prices[i]})
                in_pos = True
            elif in_pos and fast[i] < slow[i] and fast[i-1] >= slow[i-1]:
                signals.append({'i': i, 'type': 'sell', 'price': prices[i]})
                in_pos = False

    elif strategy == 'dmi':
        fast = calc_ema(prices, 20)
        slow = calc_ema(prices, 100)
        in_pos = False
        for i in range(15, n):
            up = prices[i] - prices[i-1]
            down = prices[i-1] - prices[i]
            plus_di = (up if up > down and up > 0 else 0)
            minus_di = (down if down > up and down > 0 else 0)
            if not in_pos and plus_di > 0 and fast[i] > slow[i]:
                signals.append({'i': i, 'type': 'buy', 'price': prices[i]})
                in_pos = True
            elif in_pos and minus_di > plus_di and fast[i] < slow[i]:
                signals.append({'i': i, 'type': 'sell', 'price': prices[i]})
                in_pos = False

    elif strategy == 'vol':
        slow = calc_ema(prices, 100)
        in_pos = False
        for i in range(15, n):
            atr_val = abs(prices[i] - prices[i-1]) * 1.5
            vol_break = prices[i] > prices[i-1] + atr_val
            if not in_pos and vol_break and prices[i] > slow[i]:
                signals.append({'i': i, 'type': 'buy', 'price': prices[i]})
                in_pos = True
            elif in_pos and prices[i] < slow[i]:
                signals.append({'i': i, 'type': 'sell', 'price': prices[i]})
                in_pos = False

    elif strategy == 'sixline':
        emas = [calc_ema(prices, p) for p in [10, 20, 30, 60, 120, 200]]
        in_pos = False
        for i in range(200, n):
            all_up = all(emas[j][i] > emas[j+1][i] for j in range(5))
            if not in_pos and all_up:
                signals.append({'i': i, 'type': 'buy', 'price': prices[i]})
                in_pos = True
            elif in_pos and prices[i] < emas[2][i]:
                signals.append({'i': i, 'type': 'sell', 'price': prices[i]})
                in_pos = False

    return signals

def calc_metrics(prices, signals, cost=0.0045):
    trades = []
    wins = 0
    total_win = 0
    total_loss = 0
    equity = 10000
    max_eq = 10000
    max_dd = 0
    last_buy = None

    for s in signals:
        if s['type'] == 'buy':
            last_buy = s
        elif s['type'] == 'sell' and last_buy:
            ret = (s['price'] - last_buy['price']) / last_buy['price'] - cost
            equity *= (1 + ret)
            if equity > max_eq:
                max_eq = equity
            dd = (max_eq - equity) / max_eq
            if dd > max_dd:
                max_dd = dd
            if ret > 0:
                wins += 1
                total_win += ret
            else:
                total_loss += abs(ret)
            trades.append({
                'buyPrice': round(last_buy['price'], 2),
                'sellPrice': round(s['price'], 2),
                'ret': round(ret * 100, 2),
                'buyIdx': last_buy['i'],
                'sellIdx': s['i']
            })
            last_buy = None

    total_return = (equity - 10000) / 10000
    pf = total_win / total_loss if total_loss > 0 else (999 if total_win > 0 else 0)
    wr = wins / len(trades) if trades else 0
    years = len(prices) / 252
    cagr = (equity / 10000) ** (1 / years) - 1 if years > 0 else 0

    return {
        'totalReturn': round(total_return * 100, 2),
        'pf': round(pf, 2),
        'maxDD': round(max_dd * 100, 2),
        'wr': round(wr * 100, 2),
        'tradeCount': len(trades),
        'cagr': round(cagr * 100, 2),
        'trades': trades[-10:][::-1]
    }

@app.route('/api/analyze')
def analyze():
    symbol = request.args.get('symbol', '2330.TW')
    strategy = request.args.get('strategy', 'dmi')
    period = request.args.get('period', '1y')

    try:
        start, end = get_period_dates(period)
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end)

        if df.empty:
            return jsonify({'error': '無法取得資料，請確認股票代碼'}), 400

        df = df.dropna()
        prices = df['Close'].tolist()
        dates = [d.strftime('%Y-%m-%d') for d in df.index]

        signals = run_strategy(prices, strategy)
        metrics = calc_metrics(prices, signals)

        ema20 = calc_ema(prices, 20)
        ema50 = calc_ema(prices, 50)

        buy_points = [None] * len(prices)
        sell_points = [None] * len(prices)
        for s in signals:
            if s['i'] < len(prices):
                if s['type'] == 'buy':
                    buy_points[s['i']] = prices[s['i']]
                else:
                    sell_points[s['i']] = prices[s['i']]

        diff = [round((ema20[i] - ema50[i]) / ema50[i] * 100, 3) for i in range(len(prices))]

        return jsonify({
            'dates': dates,
            'prices': [round(p, 2) for p in prices],
            'ema20': [round(e, 2) for e in ema20],
            'ema50': [round(e, 2) for e in ema50],
            'buyPoints': buy_points,
            'sellPoints': sell_points,
            'diff': diff,
            'metrics': metrics
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)

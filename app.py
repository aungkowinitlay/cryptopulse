from flask import Flask, render_template, jsonify, request
import requests
import pandas as pd
from datetime import datetime, timedelta
import websocket
import json
import threading
import ta

app = Flask(__name__)

# Global variables
symbols = []
data_cache = []
alerts = {}
watchlist = []

# Fetch top 50 USDT pairs from Binance
def fetch_symbols():
    global symbols
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url).json()
    symbols = [s['symbol'] for s in response['symbols'] if s['symbol'].endswith('USDT')][:50]

# Fetch historical data for charting
def fetch_historical_data(symbol, interval='3h', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url).json()
    df = pd.DataFrame(response, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'trades',
        'taker_buy_base', 'taker_buy_quote', 'ignored'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)

    # Calculate indicators
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['sma20'] = ta.trend.SMAIndicator(df['close'], window=20).sma_indicator()
    df['sma50'] = ta.trend.SMAIndicator(df['close'], window=50).sma_indicator()
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()

    return df

# Update data cache with real-time prices
def update_data():
    global data_cache
    url = "https://api.binance.com/api/v3/ticker/24hr"
    while True:
        try:
            response = requests.get(url).json()
            data = []
            for item in response:
                if item['symbol'] in symbols:
                    price = float(item['lastPrice'])
                    price_change = float(item['priceChangePercent'])
                    volume = float(item['quoteVolume'])
                    historical_data = fetch_historical_data(item['symbol'])
                    latest = historical_data.iloc[-1]
                    rsi = latest['rsi']
                    sma20 = latest['sma20']
                    sma50 = latest['sma50']
                    macd = latest['macd']
                    macd_signal = latest['macd_signal']

                    status = 'Neutral'
                    if rsi > 70:
                        status = 'Overbought'
                    elif rsi < 30:
                        status = 'Oversold'

                    trend = 'Bullish' if sma20 > sma50 else 'Bearish'
                    macd_signal_type = 'Buy' if macd > macd_signal else 'Sell'

                    alert = None
                    if item['symbol'] in alerts:
                        high_price, low_price = alerts[item['symbol']]
                        if price > high_price:
                            alert = f"Price reached ${high_price}!"
                        elif price < low_price:
                            alert = f"Price dropped to ${low_price}!"

                    data.append({
                        'symbol': item['symbol'],
                        'price': price,
                        'price_change': price_change,
                        'volume_usdt': volume,
                        'rsi': rsi,
                        'status': status,
                        'sma20': sma20,
                        'sma50': sma50,
                        'trend': trend,
                        'macd': macd,
                        'macd_signal': macd_signal,
                        'macd_signal_type': macd_signal_type,
                        'chart_data': historical_data.tail(20).to_dict('records'),
                        'alert': alert
                    })
            data_cache = sorted(data, key=lambda x: x['price_change'], reverse=True)
        except Exception as e:
            print(f"Error updating data: {e}")
        threading.Event().wait(5)

# WebSocket callbacks
def on_message(ws, message):
    global data_cache
    data = json.loads(message)
    symbol = data['s']
    if symbol in symbols:
        price = float(data['p'])
        for item in data_cache:
            if item['symbol'] == symbol:
                item['price'] = price
                if symbol in alerts:
                    high_price, low_price = alerts[symbol]
                    if price > high_price:
                        item['alert'] = f"Price reached ${high_price}!"
                    elif price < low_price:
                        item['alert'] = f"Price dropped to ${low_price}!"
                break

def on_error(ws, error):
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def on_open(ws):
    print("WebSocket opened")
    for symbol in symbols:
        ws.send(json.dumps({
            "method": "SUBSCRIBE",
            "params": [f"{symbol.lower()}@ticker"],
            "id": 1
        }))

def start_websocket():
    ws_url = "wss://stream.binance.com:9443/ws"
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    ws.run_forever()

# Flask routes
@app.route('/')
def index():
    global data_cache
    top_gainers = sorted(data_cache, key=lambda x: x['price_change'], reverse=True)[:10]
    top_losers = sorted(data_cache, key=lambda x: x['price_change'])[:10]
    return jsonify({
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "all_data": data_cache
    })

@app.route('/alert', methods=['POST'])
def set_alert():
    symbol = request.json.get('symbol')
    high = float(request.json.get('high'))
    low = float(request.json.get('low'))
    alerts[symbol] = (high, low)
    return jsonify({"message": f"Alert set for {symbol} between {low} - {high}"}), 200

@app.route('/watchlist', methods=['POST'])
def update_watchlist():
    global watchlist
    watchlist = request.json.get('symbols', [])
    return jsonify({"watchlist": watchlist})

# Startup logic
if __name__ == '__main__':
    fetch_symbols()
    threading.Thread(target=update_data, daemon=True).start()
    threading.Thread(target=start_websocket, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)

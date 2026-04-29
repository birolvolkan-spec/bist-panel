from flask import Flask, render_template_string
import threading
import time
import yfinance as yf
import ta
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)

# =========================
# BIST SYMBOLS (fallback included)
# =========================
def get_bist_symbols():
    try:
        url = "https://tr.wikipedia.org/wiki/Borsa_%C4%B0stanbul"
        tables = pd.read_html(url)

        symbols = []

        for t in tables:
            for col in t.columns:
                for v in t[col].values:
                    if isinstance(v, str) and v.isalpha() and len(v) <= 6:
                        symbols.append(v + ".IS")

        symbols = list(set(symbols))

        if len(symbols) < 50:
            raise Exception("fallback")

        return symbols

    except:
        return [
            "AEFES.IS","AGHOL.IS","AKBNK.IS","AKSA.IS","ALARK.IS","ARCLK.IS",
            "ASELS.IS","ASTOR.IS","BIMAS.IS","DOHOL.IS","EKGYO.IS","EREGL.IS",
            "FROTO.IS","GARAN.IS","GWIND.IS","HEKTS.IS","ISCTR.IS","KCHOL.IS",
            "KONTR.IS","KOZAL.IS","KRDMD.IS","ODAS.IS","PETKM.IS","PGSUS.IS",
            "SAHOL.IS","SASA.IS","SISE.IS","TCELL.IS","THYAO.IS","TOASO.IS",
            "TSKB.IS","TUPRS.IS","ULKER.IS","VAKBN.IS","YKBNK.IS"
        ]

signals = []

# =========================
# ANALYSIS ENGINE (1-8 SCORE GUARANTEED)
# =========================
def analyze(symbol):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", progress=False)

        if df is None or len(df) < 30:
            return {"symbol": symbol, "score": 1, "price": 0}

        df = df.dropna()

        df["vol_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
        df["vol_ratio"] = df["vol_ratio"].fillna(1)

        df["max10"] = df["Close"].rolling(10).max()
        df["breakout"] = df["Close"] / df["max10"]

        df["body"] = abs(df["Close"] - df["Open"])
        df["range"] = df["High"] - df["Low"]
        df["upper"] = df["High"] - df[["Close","Open"]].max(axis=1)

        df["bull"] = (
            (df["Close"] > df["Open"]) &
            (df["body"] > df["range"] * 0.5) &
            (df["upper"] < df["body"] * 0.5)
        )

        df["rsi"] = ta.momentum.RSIIndicator(df["Close"]).rsi()

        last = df.iloc[-1]

        score = 0

        # volume
        if last["vol_ratio"] > 1.3:
            score += 3
        elif last["vol_ratio"] > 1.1:
            score += 2
        else:
            score += 1

        # breakout
        if last["breakout"] > 0.95:
            score += 3
        elif last["breakout"] > 0.92:
            score += 2
        else:
            score += 1

        # candle
        if last["bull"]:
            score += 2

        # RSI
        if pd.notna(last["rsi"]) and 40 < last["rsi"] < 70:
            score += 1

        # 🔥 GARANTİ ALT SINIR
        if score < 1:
            score = 1

        if score > 8:
            score = 8

        return {
            "symbol": symbol,
            "score": round(score, 1),
            "price": round(float(last["Close"]), 2) if not pd.isna(last["Close"]) else 0
        }

    except Exception as e:
        print("ERROR:", symbol, e)
        return {
            "symbol": symbol,
            "score": 1,
            "price": 0
        }


# =========================
# FULL SCAN LOOP
# =========================
def update_loop():
    global signals

    while True:
        temp = []

        symbols = get_bist_symbols()

        def worker(s):
            return analyze(s)

        with ThreadPoolExecutor(max_workers=10) as ex:
            results = ex.map(worker, symbols)

        for r in results:
            temp.append(r)   # 🔥 artık HERKES giriyor

        signals = sorted(temp, key=lambda x: x["score"], reverse=True)

        time.sleep(300)

threading.Thread(target=update_loop, daemon=True).start()

# =========================
# UI
# =========================
HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">

<style>
body { background:#0f0f0f; color:white; font-family:Arial; margin:0; }
header { text-align:center; padding:15px; background:#1a1a1a; }
.card { background:#1c1c1c; margin:10px; padding:15px; border-radius:12px; }

.high { color:#00ff88; }
.mid { color:#ffaa00; }
.low { color:#ff5555; }
</style>
</head>

<body>

<header>📊 FULL BIST SCANNER (1–8 SCORE)</header>

{% for s in signals %}
<div class="card">

<b>{{s.symbol}}</b><br>
Price: {{s.price}}<br>

{% if s.score >= 7 %}
<span class="high">Score: {{s.score}} 🔥</span>
{% elif s.score >= 5 %}
<span class="mid">Score: {{s.score}} ⚠️</span>
{% else %}
<span class="low">Score: {{s.score}}</span>
{% endif %}

</div>
{% endfor %}

</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML, signals=signals)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
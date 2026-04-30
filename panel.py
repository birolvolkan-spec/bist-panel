from flask import Flask, render_template_string
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)

def get_symbols():
    return [
        "THYAO.IS","GARAN.IS","ASELS.IS","KCHOL.IS","SISE.IS",
        "BIMAS.IS","AKBNK.IS","EREGL.IS","TUPRS.IS","SAHOL.IS",
        "YKBNK.IS","PETKM.IS","PGSUS.IS","TCELL.IS","ULKER.IS"
    ]

def analyze(symbol):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", progress=False)

        if df is None or len(df) < 20:
            return None

        df = df.dropna()
        last = df.iloc[-1]

        score = 1  # GARANTİ

        # mum
        last3 = df.tail(3)
        candles = ["🟢" if r["Close"] > r["Open"] else "🔴" for _, r in last3.iterrows()]
        pattern = "".join(candles)

        if candles.count("🟢") >= 2:
            score += 1

        # hacim
        vol_ma = df["Volume"].rolling(20).mean().iloc[-1]
        if vol_ma and last["Volume"] / vol_ma > 1.2:
            score += 1

        # fiyat
        price = last["Close"]
        if pd.isna(price):
            price = 0

        return {
            "symbol": symbol,
            "score": score,
            "price": round(float(price),2),
            "pattern": pattern
        }

    except:
        return None


@app.route("/")
def home():
    temp = []
    symbols = get_symbols()

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = ex.map(analyze, symbols)

    for r in results:
        if r:
            temp.append(r)

    temp = sorted(temp, key=lambda x: x["score"], reverse=True)

    HTML = """
    <html>
    <body style="background:#111;color:white;font-family:Arial">
    <h2>BIST LIVE SCAN</h2>

    {% for s in signals %}
        <div style="margin:10px;padding:10px;background:#1c1c1c">
        <b>{{s.symbol}}</b><br>
        Price: {{s.price}}<br>
        Score: {{s.score}}<br>
        Pattern: {{s.pattern}}<br>
        </div>
    {% endfor %}

    </body>
    </html>
    """

    return render_template_string(HTML, signals=temp)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
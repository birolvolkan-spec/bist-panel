from flask import Flask, render_template_string
import threading, time, os
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
signals = []

# =========================
# FULL BIST
# =========================
def get_symbols():
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
            "THYAO.IS","GARAN.IS","ASELS.IS","KCHOL.IS","SISE.IS",
            "BIMAS.IS","AKBNK.IS","EREGL.IS","TUPRS.IS","SAHOL.IS",
            "YKBNK.IS","PETKM.IS","PGSUS.IS","TCELL.IS","ULKER.IS"
        ]

# =========================
# ASO (PINE -> PYTHON)
# =========================
def calculate_aso(df, length=10):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    open_ = df["Open"]

    intrarange = high - low
    grouplow = low.rolling(length).min()
    grouphigh = high.rolling(length).max()
    groupopen = open_.shift(length-1)
    grouprange = grouphigh - grouplow

    K1 = intrarange.replace(0,1)
    K2 = grouprange.replace(0,1)

    intrabarbulls = (((close-low)+(high-open_))/2)*100 / K1
    groupbulls = (((close-grouplow)+(grouphigh-groupopen))/2)*100 / K2

    intrabarbears = (((high-close)+(open_-low))/2)*100 / K1
    groupbears = (((grouphigh-close)+(groupopen-grouplow))/2)*100 / K2

    bulls = (intrabarbulls + groupbulls)/2
    bears = (intrabarbears + groupbears)/2

    return bulls.rolling(length).mean(), bears.rolling(length).mean()

# =========================
# ANALYZE
# =========================
def analyze(symbol):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", progress=False)

        if df is None or len(df) < 20:
            return None

        bulls, bears = calculate_aso(df)

        last = df.iloc[-1]

        score = 0
        details = []

        # ASO
        if bulls.iloc[-1] > bears.iloc[-1]:
            score += 2
            details.append("Trend UP")

        # Son 3 mum
        last3 = df.tail(3)
        candles = ["🟢" if r["Close"] > r["Open"] else "🔴" for i,r in last3.iterrows()]
        pattern = "".join(candles)

        if candles.count("🟢") >= 2:
            score += 1
            details.append("Bull candles")

        # Hacim (skor için)
        vol_ma = df["Volume"].rolling(20).mean().iloc[-1]
        if vol_ma and last["Volume"] / vol_ma > 1.2:
            score += 1
            details.append("Volume up")

        # =========================
        # RVOL (INFO ONLY)
        # =========================
        if vol_ma and vol_ma != 0:
            rvol = last["Volume"] / vol_ma
        else:
            rvol = 0

        # Aksiyon
        if score >= 3:
            action = "🔥 AL"
        elif score == 2:
            action = "⚠️ İZLE"
        else:
            action = "❌ PAS"

        price = last["Close"]
        if pd.isna(price):
            price = 0

        return {
            "symbol": symbol,
            "score": score,
            "price": round(float(price),2),
            "pattern": pattern,
            "action": action,
            "rvol": round(float(rvol),2),
            "details": details
        }

    except:
        return None

# =========================
# LOOP
# =========================
def update():
    global signals
    while True:
        temp = []
        symbols = get_symbols()

        with ThreadPoolExecutor(max_workers=10) as ex:
            results = ex.map(analyze, symbols)

        for r in results:
            if r:
                temp.append(r)

        signals = sorted(temp, key=lambda x: x["score"], reverse=True)
        time.sleep(600)  # 10 dk

threading.Thread(target=update, daemon=True).start()

# =========================
# UI
# =========================
HTML = """
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{background:#111;color:white;font-family:Arial}
.card{background:#1c1c1c;margin:10px;padding:15px;border-radius:10px}
</style>
</head>
<body>

<h2>📊 FULL BIST SCANNER (OPTIMIZED)</h2>

{% for s in signals %}
<div class="card">
<b>{{s.symbol}}</b> - {{s.action}}<br>
Price: {{s.price}}<br>
RVOL: {{s.rvol}}<br>
Score: {{s.score}} / 4<br>
Pattern: {{s.pattern}}<br>

{% for d in s.details %}
- {{d}}<br>
{% endfor %}

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
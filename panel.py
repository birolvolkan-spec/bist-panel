from flask import Flask, render_template_string
import requests
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)

# 🔑 Senin API anahtarın
API_KEY = "d7pq42pr01qosaaphklgd7pq42pr01qosaaphkm0"

symbols = [
    "THYAO.IS","GARAN.IS","ASELS.IS","KCHOL.IS","SISE.IS",
    "BIMAS.IS","AKBNK.IS","EREGL.IS","TUPRS.IS","SAHOL.IS"
]

def get_data(symbol):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={API_KEY}"
        r = requests.get(url, timeout=5).json()

        price = r.get("c", 0)
        prev = r.get("pc", 0)

        if price == 0:
            return None

        return price, prev
    except:
        return None

def analyze(symbol):
    data = get_data(symbol)
    if not data:
        return None

    price, prev = data

    score = 1
    details = []

    if price > prev:
        score += 1
        details.append("Up day")

    pattern = "🟢" if price > prev else "🔴"
    rvol = 1.0  # free planda yok, placeholder

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "score": score,
        "pattern": pattern,
        "rvol": rvol,
        "details": details
    }

@app.route("/")
def home():
    temp = []

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = ex.map(analyze, symbols)

    for r in results:
        if r:
            temp.append(r)

    if len(temp) == 0:
        temp = [{
            "symbol": "DATA_YOK",
            "price": 0,
            "score": 1,
            "pattern": "❌",
            "rvol": 0,
            "details": ["API veri dönmedi"]
        }]

    HTML = """
    <html>
    <body style="background:#111;color:white;font-family:Arial">
    <h2>BIST LIVE (FINNHUB)</h2>

    {% for s in signals %}
        <div style="margin:10px;padding:10px;background:#1c1c1c">
        <b>{{s.symbol}}</b><br>
        Price: {{s.price}}<br>
        Score: {{s.score}}<br>
        Pattern: {{s.pattern}}<br>
        RVOL: {{s.rvol}}<br>
        {% for d in s.details %}
        - {{d}}<br>
        {% endfor %}
        </div>
    {% endfor %}

    </body>
    </html>
    """

    return render_template_string(HTML, signals=temp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
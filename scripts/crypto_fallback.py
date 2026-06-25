import json
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "daily_report.json"

YF_MAP = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "BNBUSDT": "BNB-USD",
    "XRPUSDT": "XRP-USD",
    "ADAUSDT": "ADA-USD",
    "DOGEUSDT": "DOGE-USD",
    "AVAXUSDT": "AVAX-USD",
    "LINKUSDT": "LINK-USD",
    "DOTUSDT": "DOT-USD",
    "LTCUSDT": "LTC-USD",
    "ARBUSDT": "ARB-USD",
    "OPUSDT": "OP-USD",
    "NEARUSDT": "NEAR-USD",
    "APTUSDT": "APT-USD",
}


def safe_float(x, ndigits=4):
    try:
        if x is None:
            return None
        return round(float(x), ndigits)
    except Exception:
        return None


def fetch_yf(symbol):
    yf_symbol = YF_MAP.get(symbol)
    if not yf_symbol:
        return None
    try:
        df = yf.Ticker(yf_symbol).history(period="60d", interval="1d", auto_adjust=False)
        if df.empty:
            return None
        rows = []
        for idx, row in df.tail(30).iterrows():
            close = safe_float(row.get("Close"))
            if close is None:
                continue
            label = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
            rows.append({
                "date": label,
                "close": close,
                "volume": safe_float(row.get("Volume")),
            })
        if len(rows) < 3:
            return None
        return rows
    except Exception:
        return None


def volume_status(hist):
    vols = [x.get("volume") for x in hist if x.get("volume") is not None]
    if len(vols) < 6:
        return "Veri sınırlı"
    avg = sum(vols[-6:-1]) / 5
    if vols[-1] > avg * 1.15:
        return "Artıyor"
    if vols[-1] < avg * 0.85:
        return "Zayıf"
    return "Normal"


def trend_status(closes, change):
    recent = closes[-20:] if len(closes) >= 20 else closes
    ma5 = sum(closes[-5:]) / min(5, len(closes))
    ma20 = sum(recent) / len(recent)
    ch = change or 0
    if ma5 > ma20 and ch > 0:
        return "Güçleniyor"
    if ma5 < ma20 and ch < 0:
        return "Zayıflıyor"
    return "Kararsız"


def fill_asset(asset):
    symbol = asset.get("symbol")
    if asset.get("last_price") is not None and asset.get("history"):
        return asset

    hist = fetch_yf(symbol)
    if not hist:
        asset["fallback_source"] = "Yahoo Finance fallback başarısız"
        return asset

    closes = [x["close"] for x in hist]
    last = closes[-1]
    prev = closes[-2]
    change = ((last - prev) / prev * 100) if prev else None
    recent = closes[-20:] if len(closes) >= 20 else closes
    trend = trend_status(closes, change)
    vol = volume_status(hist)

    asset["last_price"] = safe_float(last)
    asset["change_pct"] = safe_float(change)
    asset["support"] = safe_float(min(recent))
    asset["resistance"] = safe_float(max(recent))
    asset["volume_status"] = vol
    asset["trend"] = trend
    asset["history"] = hist
    asset["fallback_source"] = "Yahoo Finance spot fallback"
    asset["comment"] = f"{asset.get('name')} Binance Futures verisi alınamadığı için spot fiyat/hacim yedeğiyle izlendi. Futures delta/OI gelirse ayrıca skorlanır."
    asset["compare"] = f"Yedek kaynağa göre 24 saatlik değişim {change:+.2f}%."

    metrics = asset.get("futures_metrics") or {}
    metrics.setdefault("data_ready", False)
    metrics.setdefault("source", "Binance Futures unavailable, Yahoo spot fallback used for price/volume")
    asset["futures_metrics"] = metrics
    return asset


def main():
    report = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    crypto = report.get("crypto", [])
    report["crypto"] = [fill_asset(asset) for asset in crypto]
    layer = report.setdefault("data_layer", {})
    layer["crypto_fallback"] = "Yahoo Finance spot fallback fills price/volume when Binance Futures is unavailable from GitHub Actions"
    DATA_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Crypto fallback applied")


if __name__ == "__main__":
    main()

import json
import math
from datetime import datetime
from pathlib import Path

import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "chart_series.json"
DAYS = 90

BINANCE_BASES = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com",
]

HEADERS = {"User-Agent": "Mozilla/5.0 VolkanDailyRadar/1.0", "Accept": "application/json"}


def safe_float(x):
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def normalize(points):
    base = None
    for p in points:
        v = safe_float(p.get("value"))
        if v not in (None, 0):
            base = v
            break
    out = []
    for p in points:
        v = safe_float(p.get("value"))
        n = (v / base * 100) if base and v is not None else None
        if v is not None:
            out.append({"date": p["date"], "value": round(v, 6), "normalized": round(n, 4) if n is not None else None})
    return out


def request_json(url, params=None, timeout=20):
    try:
        r = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
        if r.status_code >= 400:
            return None
        return r.json()
    except Exception:
        return None


def yfinance_close_series(symbol, label, unit=""):
    try:
        df = yf.Ticker(symbol).history(period=f"{DAYS}d", interval="1d", auto_adjust=False)
        rows = []
        for idx, row in df.iterrows():
            close = safe_float(row.get("Close"))
            if close is None:
                continue
            d = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
            rows.append({"date": d, "value": close})
        return {"id": label, "points": normalize(rows)}
    except Exception:
        return {"id": label, "points": []}


def binance_futures_close(symbol):
    for base in BINANCE_BASES:
        data = request_json(f"{base}/fapi/v1/klines", {"symbol": symbol, "interval": "1d", "limit": DAYS})
        if isinstance(data, list) and data:
            rows = []
            for r in data:
                try:
                    d = datetime.utcfromtimestamp(int(r[0]) / 1000).strftime("%Y-%m-%d")
                    close = safe_float(r[4])
                    if close is not None:
                        rows.append({"date": d, "value": close})
                except Exception:
                    pass
            if rows:
                return rows
    return []


def coin_market_caps(coin_id):
    data = request_json(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart", {"vs_currency": "usd", "days": DAYS, "interval": "daily"})
    rows = []
    if not isinstance(data, dict):
        return rows
    for ts, value in data.get("market_caps", []):
        d = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        v = safe_float(value)
        if v is not None:
            rows.append({"date": d, "value": v})
    return rows


def global_market_cap():
    # CoinGecko supports this endpoint on many accounts. If unavailable, return empty and chart will still work for available series.
    data = request_json("https://api.coingecko.com/api/v3/global/market_cap_chart", {"vs_currency": "usd", "days": DAYS})
    if not isinstance(data, dict):
        return []
    raw = data.get("market_cap_chart") or data.get("market_caps") or data.get("market_cap") or []
    if isinstance(raw, dict):
        raw = raw.get("market_cap") or raw.get("market_caps") or []
    rows = []
    for item in raw:
        try:
            ts, value = item[0], item[1]
            d = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            v = safe_float(value)
            if v is not None:
                rows.append({"date": d, "value": v})
        except Exception:
            pass
    return rows


def as_map(rows):
    return {x["date"]: safe_float(x.get("value")) for x in rows if safe_float(x.get("value")) is not None}


def combine_market_series():
    total = global_market_cap()
    btc_mc = coin_market_caps("bitcoin")
    eth_mc = coin_market_caps("ethereum")
    usdt_mc = coin_market_caps("tether")
    total_m = as_map(total)
    btc_m = as_map(btc_mc)
    eth_m = as_map(eth_mc)
    usdt_m = as_map(usdt_mc)
    dates = sorted(set(total_m) & set(btc_m))

    total_rows = []
    total2_rows = []
    total3_rows = []
    btc_dom_rows = []
    usdt_dom_rows = []

    for d in dates:
        t = total_m.get(d)
        b = btc_m.get(d)
        e = eth_m.get(d)
        u = usdt_m.get(d)
        if t:
            total_rows.append({"date": d, "value": t})
            if b is not None:
                total2_rows.append({"date": d, "value": max(t - b, 0)})
                btc_dom_rows.append({"date": d, "value": b / t * 100})
            if b is not None and e is not None:
                total3_rows.append({"date": d, "value": max(t - b - e, 0)})
            if u is not None:
                usdt_dom_rows.append({"date": d, "value": u / t * 100})

    return {
        "TOTAL": total_rows,
        "TOTAL2": total2_rows,
        "TOTAL3": total3_rows,
        "BTC.D": btc_dom_rows,
        "DOMINANCE": usdt_dom_rows,
    }


def make_series(series_id, label, unit, rows, source):
    return {
        "id": series_id,
        "label": label,
        "unit": unit,
        "source": source,
        "points": normalize(rows),
    }


def main():
    market = combine_market_series()
    btc_f = binance_futures_close("BTCUSDT")
    eth_f = binance_futures_close("ETHUSDT")
    if not btc_f:
        btc_f = yfinance_close_series("BTC-USD", "BTCUSDT.P")["points"]
        btc_f = [{"date": x["date"], "value": x["value"]} for x in btc_f]
    if not eth_f:
        eth_f = yfinance_close_series("ETH-USD", "ETHUSDT.P")["points"]
        eth_f = [{"date": x["date"], "value": x["value"]} for x in eth_f]

    dxy_raw = yfinance_close_series("DX-Y.NYB", "DXY")
    dxy_rows = [{"date": x["date"], "value": x["value"]} for x in dxy_raw.get("points", [])]

    payload = {
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "mode": "normalized_first_value_100",
        "note": "All plotted values use normalized index = 100 at first available value so mixed units can share one chart.",
        "series": [
            make_series("DOMINANCE", "Dominance / USDT.D", "%", market.get("DOMINANCE", []), "CoinGecko derived from USDT market cap / global market cap"),
            make_series("DXY", "DXY", "index", dxy_rows, "Yahoo Finance DX-Y.NYB"),
            make_series("TOTAL", "TOTAL", "USD", market.get("TOTAL", []), "CoinGecko global market cap"),
            make_series("TOTAL2", "TOTAL2", "USD", market.get("TOTAL2", []), "CoinGecko derived total minus BTC market cap"),
            make_series("TOTAL3", "TOTAL3", "USD", market.get("TOTAL3", []), "CoinGecko derived total minus BTC and ETH market cap"),
            make_series("BTC.D", "BTC Dominance", "%", market.get("BTC.D", []), "CoinGecko derived BTC market cap / global market cap"),
            make_series("BTCUSDT.P", "BTCUSDT.P", "USD", btc_f, "Binance USD-M Futures daily close; fallback Yahoo BTC-USD"),
            make_series("ETHUSDT.P", "ETHUSDT.P", "USD", eth_f, "Binance USD-M Futures daily close; fallback Yahoo ETH-USD"),
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Chart series written: {OUT}")


if __name__ == "__main__":
    main()

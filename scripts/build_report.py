import json
import math
from datetime import datetime
from pathlib import Path

import pytz
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "daily_report.json"
IST = pytz.timezone("Europe/Istanbul")
BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_DATA = "https://fapi.binance.com/futures/data"

CRYPTO_ASSETS = [
    ("Bitcoin", "BTCUSDT", " $"),
    ("Ethereum", "ETHUSDT", " $"),
    ("Solana", "SOLUSDT", " $"),
    ("BNB", "BNBUSDT", " $"),
    ("XRP", "XRPUSDT", " $"),
    ("Cardano", "ADAUSDT", " $"),
    ("Dogecoin", "DOGEUSDT", " $"),
    ("Avalanche", "AVAXUSDT", " $"),
    ("Chainlink", "LINKUSDT", " $"),
    ("Polkadot", "DOTUSDT", " $"),
    ("Litecoin", "LTCUSDT", " $"),
    ("Arbitrum", "ARBUSDT", " $"),
    ("Optimism", "OPUSDT", " $"),
    ("NEAR", "NEARUSDT", " $"),
    ("Aptos", "APTUSDT", " $"),
]

COMMODITIES = [
    ("Altın", "GC=F", " $"),
    ("Brent Petrol", "BZ=F", " $"),
]

BIST = [
    ("SASA", "SASA.IS", " ₺"),
    ("ZOREN", "ZOREN.IS", " ₺"),
    ("HEKTAŞ", "HEKTS.IS", " ₺"),
]

MACRO_YF = [
    ("DXY", "DX-Y.NYB", ""),
    ("BIST 100", "XU100.IS", ""),
]


def safe_float(value, ndigits=4):
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, ndigits)
    except Exception:
        return None


def get_json(url, params=None, timeout=20):
    try:
        response = requests.get(url, params=params or {}, timeout=timeout)
        if response.status_code >= 400:
            return None
        return response.json()
    except Exception:
        return None


def previous_report():
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else {}
    except Exception:
        return {}


def yfinance_history(symbol, days="60d"):
    try:
        df = yf.Ticker(symbol).history(period=days, interval="1d", auto_adjust=False)
        if df.empty:
            return []
        rows = []
        for idx, row in df.tail(30).iterrows():
            label = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
            close = safe_float(row.get("Close"))
            if close is not None:
                rows.append({"date": label, "close": close, "volume": safe_float(row.get("Volume"))})
        return rows
    except Exception:
        return []


def binance_klines(symbol, interval="1d", limit=30):
    raw = get_json(f"{BINANCE_FAPI}/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(raw, list):
        return []
    rows = []
    for row in raw:
        try:
            ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=IST)
            volume = safe_float(row[5])
            taker_buy = safe_float(row[9])
            taker_sell = safe_float((volume or 0) - (taker_buy or 0)) if volume is not None and taker_buy is not None else None
            delta = safe_float((taker_buy or 0) - (taker_sell or 0)) if taker_buy is not None and taker_sell is not None else None
            delta_ratio = safe_float((delta / volume) * 100, 4) if volume and delta is not None else None
            rows.append({
                "date": ts.strftime("%Y-%m-%d"),
                "open": safe_float(row[1]),
                "high": safe_float(row[2]),
                "low": safe_float(row[3]),
                "close": safe_float(row[4]),
                "volume": volume,
                "quote_volume": safe_float(row[7]),
                "trade_count": int(row[8]) if row[8] is not None else None,
                "taker_buy_volume": taker_buy,
                "taker_sell_volume": taker_sell,
                "candle_delta": delta,
                "delta_ratio_pct": delta_ratio,
            })
        except Exception:
            continue
    return [x for x in rows if x.get("close") is not None]


def binance_ticker(symbol):
    return get_json(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr", {"symbol": symbol}) or {}


def binance_premium(symbol):
    return get_json(f"{BINANCE_FAPI}/fapi/v1/premiumIndex", {"symbol": symbol}) or {}


def binance_open_interest(symbol):
    current = get_json(f"{BINANCE_FAPI}/fapi/v1/openInterest", {"symbol": symbol}) or {}
    hist = get_json(f"{BINANCE_DATA}/openInterestHist", {"symbol": symbol, "period": "15m", "limit": 8})
    oi = safe_float(current.get("openInterest"))
    oi_change = None
    if isinstance(hist, list) and len(hist) >= 2:
        first = safe_float(hist[0].get("sumOpenInterest"))
        last = safe_float(hist[-1].get("sumOpenInterest"))
        if first and last is not None:
            oi_change = safe_float(((last - first) / first) * 100)
    return {"open_interest": oi, "open_interest_change_pct": oi_change}


def binance_taker_ratio(symbol):
    data = get_json(f"{BINANCE_DATA}/takerlongshortRatio", {"symbol": symbol, "period": "15m", "limit": 1})
    if isinstance(data, list) and data:
        row = data[-1]
        return {
            "taker_buy_sell_ratio": safe_float(row.get("buySellRatio")),
            "taker_buy_volume_15m": safe_float(row.get("buyVol")),
            "taker_sell_volume_15m": safe_float(row.get("sellVol")),
        }
    return {"taker_buy_sell_ratio": None, "taker_buy_volume_15m": None, "taker_sell_volume_15m": None}


def futures_metrics(symbol, hist):
    latest = hist[-1] if hist else {}
    premium = binance_premium(symbol)
    oi = binance_open_interest(symbol)
    taker = binance_taker_ratio(symbol)
    funding = safe_float(premium.get("lastFundingRate"))
    mark_price = safe_float(premium.get("markPrice"))
    return {
        "source": "Binance USD-M Futures public endpoints",
        "mark_price": mark_price,
        "funding_rate": funding,
        "funding_rate_pct": safe_float(funding * 100, 6) if funding is not None else None,
        "open_interest": oi.get("open_interest"),
        "open_interest_change_pct": oi.get("open_interest_change_pct"),
        "taker_buy_sell_ratio": taker.get("taker_buy_sell_ratio"),
        "taker_buy_volume_15m": taker.get("taker_buy_volume_15m"),
        "taker_sell_volume_15m": taker.get("taker_sell_volume_15m"),
        "last_candle_delta": latest.get("candle_delta"),
        "last_delta_ratio_pct": latest.get("delta_ratio_pct"),
        "last_taker_buy_volume": latest.get("taker_buy_volume"),
        "last_taker_sell_volume": latest.get("taker_sell_volume"),
        "data_ready": any([
            oi.get("open_interest") is not None,
            oi.get("open_interest_change_pct") is not None,
            taker.get("taker_buy_sell_ratio") is not None,
            latest.get("delta_ratio_pct") is not None,
            funding is not None,
        ]),
    }


def volume_status_from_hist(hist):
    volumes = [x.get("volume") for x in hist if x.get("volume") is not None]
    if len(volumes) < 6:
        return "Veri sınırlı"
    avg_vol = sum(volumes[-6:-1]) / 5
    if volumes[-1] > avg_vol * 1.15:
        return "Artıyor"
    if volumes[-1] < avg_vol * 0.85:
        return "Zayıf"
    return "Normal"


def trend_from_closes(closes, change_pct):
    recent = closes[-20:] if len(closes) >= 20 else closes
    ma5 = sum(closes[-5:]) / min(5, len(closes))
    ma20 = sum(recent) / len(recent)
    ch = change_pct or 0
    if ma5 > ma20 and ch > 0:
        return "Güçleniyor"
    if ma5 < ma20 and ch < 0:
        return "Zayıflıyor"
    return "Kararsız"


def limited_asset(name, symbol, currency, category, hist=None):
    item = {
        "name": name,
        "symbol": symbol,
        "currency": currency,
        "last_price": None,
        "change_pct": None,
        "support": None,
        "resistance": None,
        "volume_status": "Veri sınırlı",
        "trend": "Veri sınırlı",
        "comment": "Ücretsiz kaynaktan yeterli veri alınamadı. Veri yoksa yorum uydurulmaz.",
        "compare": "Dün-bugün karşılaştırması için veri sınırlı.",
        "history": hist or [],
    }
    if category == "bist":
        item["bist_extra"] = "BIST verisi gecikmeli olabilir. Yabancı para akışı, kademe, kurum dağılımı ve takas detayı için ayrıca veri kaynağı gerekir."
    return item


def find_old(previous, symbol):
    for group in ("crypto", "commodities", "bist"):
        for item in previous.get(group, []):
            if item.get("symbol") == symbol:
                return item
    return None


def crypto_asset_report(name, symbol, currency, previous):
    hist = binance_klines(symbol, "1d", 30)
    if len(hist) < 3:
        return limited_asset(name, symbol, currency, "crypto", hist)

    ticker = binance_ticker(symbol)
    closes = [x["close"] for x in hist if x.get("close") is not None]
    last = safe_float(ticker.get("lastPrice")) or hist[-1]["close"]
    change = safe_float(ticker.get("priceChangePercent"))
    if change is None and len(closes) >= 2 and closes[-2]:
        change = safe_float(((last - closes[-2]) / closes[-2]) * 100)
    recent = closes[-20:] if len(closes) >= 20 else closes
    support = min(recent)
    resistance = max(recent)
    trend = trend_from_closes(closes, change)
    vol_status = volume_status_from_hist(hist)
    metrics = futures_metrics(symbol, hist)

    ch = change or 0
    if ch > 1 and trend == "Güçleniyor":
        comment = f"{name} tarafında alıcılar güçleniyor. Direnç üstü kalıcılık gelirse hareket daha sağlıklı olur."
    elif ch < -1 and trend == "Zayıflıyor":
        comment = f"{name} tarafında satış baskısı var. Destek kaybı olursa risk artar; tepki için hacim teyidi gerekir."
    else:
        comment = f"{name} net yön üretmiyor. Destek ve direnç arası takip edilmeli; acele işlem yerine teyit beklemek daha doğru."

    old = find_old(previous, symbol)
    if old and old.get("last_price"):
        old_price = old["last_price"]
        diff = ((last - old_price) / old_price) * 100 if old_price else ch
        compare = f"Önceki rapora göre fiyat değişimi {diff:+.2f}%."
    else:
        compare = f"24 saatlik değişim {ch:+.2f}%."

    return {
        "name": name,
        "symbol": symbol,
        "currency": currency,
        "last_price": safe_float(last),
        "change_pct": change,
        "support": safe_float(support),
        "resistance": safe_float(resistance),
        "volume_status": vol_status,
        "trend": trend,
        "comment": comment,
        "compare": compare,
        "history": hist,
        "futures_metrics": metrics,
        "delta_note": "Mum içi taker buy/sell verisinden delta proxy hesaplandı. Gerçek footprint değildir; karar filtresidir.",
    }


def yfinance_asset_report(name, symbol, currency, category, previous):
    hist = yfinance_history(symbol)
    if len(hist) < 3:
        return limited_asset(name, symbol, currency, category, hist)
    closes = [x["close"] for x in hist if x.get("close") is not None]
    last = closes[-1]
    prev = closes[-2]
    change = safe_float(((last - prev) / prev) * 100) if prev else None
    recent = closes[-20:] if len(closes) >= 20 else closes
    support = min(recent)
    resistance = max(recent)
    trend = trend_from_closes(closes, change)
    vol_status = volume_status_from_hist(hist)
    ch = change or 0
    if ch > 1 and trend == "Güçleniyor":
        comment = f"{name} tarafında alıcılar güçleniyor. Direnç üstü kalıcılık izlenmeli."
    elif ch < -1 and trend == "Zayıflıyor":
        comment = f"{name} tarafında satış baskısı var. Destek kaybı risk artırır."
    else:
        comment = f"{name} net yön üretmiyor. Destek ve direnç arası takip edilmeli."
    item = {
        "name": name,
        "symbol": symbol,
        "currency": currency,
        "last_price": safe_float(last),
        "change_pct": change,
        "support": safe_float(support),
        "resistance": safe_float(resistance),
        "volume_status": vol_status,
        "trend": trend,
        "comment": comment,
        "compare": f"Düne göre değişim {ch:+.2f}%.",
        "history": hist,
    }
    if category == "bist":
        item["bist_extra"] = "Fiyat ve hacim gecikmeli günlük veriyle izleniyor. Yabancı para akışı, kurum dağılımı, kademe ve takas detayı veri kaynağına bağlıdır; veri yoksa uydurulmaz."
    return item


def coingecko_macro():
    data = get_json("https://api.coingecko.com/api/v3/global")
    if not data:
        return [{"name": "Kripto makro", "change_pct": None, "note": "CoinGecko verisi alınamadı.", "data_ready": False}]
    g = data.get("data", {})
    total = safe_float(g.get("total_market_cap", {}).get("usd"), 2)
    change = safe_float(g.get("market_cap_change_percentage_24h_usd"))
    pct = g.get("market_cap_percentage", {}) or {}
    btc_pct = safe_float(pct.get("btc"))
    eth_pct = safe_float(pct.get("eth"))
    usdt_pct = safe_float(pct.get("usdt"))
    total2 = safe_float(total * (1 - (btc_pct or 0) / 100), 2) if total and btc_pct is not None else None
    total3 = safe_float(total * (1 - ((btc_pct or 0) + (eth_pct or 0)) / 100), 2) if total and btc_pct is not None and eth_pct is not None else None
    return [
        {"name": "TOTAL", "change_pct": change, "note": f"Toplam kripto piyasa değeri yaklaşık {total:,} USD.", "value": total, "data_ready": total is not None},
        {"name": "TOTAL2", "change_pct": change, "note": f"BTC hariç piyasa değeri yaklaşık {total2:,} USD. Altcoin geniş piyasa gücü için izlenir.", "value": total2, "data_ready": total2 is not None},
        {"name": "TOTAL3", "change_pct": change, "note": f"BTC ve ETH hariç piyasa değeri yaklaşık {total3:,} USD. Altcoin risk iştahı için ana filtredir.", "value": total3, "data_ready": total3 is not None},
        {"name": "BTC Dominance", "change_pct": None, "note": f"BTC piyasa payı yaklaşık %{btc_pct}. BTC ağırlığı artarsa altcoinlerde seçici olmak gerekir.", "value": btc_pct, "data_ready": btc_pct is not None},
        {"name": "ETH Dominance", "change_pct": None, "note": f"ETH piyasa payı yaklaşık %{eth_pct}. Altcoin iştahı için izlenir.", "value": eth_pct, "data_ready": eth_pct is not None},
        {"name": "USDT.D", "change_pct": None, "note": f"USDT piyasa payı yaklaşık %{usdt_pct}. Yükseliş riskten kaçışı, düşüş risk iştahını gösterebilir.", "value": usdt_pct, "data_ready": usdt_pct is not None},
    ]


def macro_report():
    rows = []
    for name, symbol, currency in MACRO_YF:
        item = yfinance_asset_report(name, symbol, currency, "macro", {})
        rows.append({"name": name, "change_pct": item.get("change_pct"), "note": item.get("comment", ""), "value": item.get("last_price"), "data_ready": item.get("last_price") is not None})
    rows.extend(coingecko_macro())
    return rows


def avg_change(items):
    values = [x.get("change_pct") for x in items if x.get("change_pct") is not None]
    return sum(values) / len(values) if values else 0


def opportunity_list(items):
    ranked = sorted(items, key=lambda x: x.get("change_pct") if x.get("change_pct") is not None else -999, reverse=True)
    out = []
    for item in ranked[:7]:
        metrics = item.get("futures_metrics", {})
        metric_note = ""
        if metrics:
            metric_note = f" Delta: {metrics.get('last_delta_ratio_pct')}%, OI değişim: {metrics.get('open_interest_change_pct')}%, funding: {metrics.get('funding_rate_pct')}%."
        out.append({"name": item["name"], "change_pct": item.get("change_pct"), "note": f"Trend: {item.get('trend')}. Hacim: {item.get('volume_status')}.{metric_note}"})
    return out


def main():
    now = datetime.now(IST)
    previous = previous_report()
    crypto = [crypto_asset_report(*asset, previous=previous) for asset in CRYPTO_ASSETS]
    commodities = [yfinance_asset_report(*asset, category="commodities", previous=previous) for asset in COMMODITIES]
    bist = [yfinance_asset_report(*asset, category="bist", previous=previous) for asset in BIST]
    macro = macro_report()

    crypto_avg = avg_change(crypto)
    bist_avg = avg_change(bist)

    if crypto_avg > 1 and bist_avg > 0:
        title, risk, summary = "🟢 Risk alınabilir ama seçici", "ORTA-DÜŞÜK", "Kripto ve BIST tarafında toparlanma işaretleri var. Yine de direnç kırılımı ve hacim teyidi beklenmeli."
    elif crypto_avg < -1 or bist_avg < -1:
        title, risk, summary = "🔴 Korunmacı kal", "YÜKSEK", "Piyasada satış baskısı öne çıkıyor. Destekler korunmadan agresif işlem almak riskli."
    else:
        title, risk, summary = "🟡 Seçici olun", "ORTA", "Piyasa net yön üretmiyor. Destek-direnç arası hareketlerde acele etmek yerine teyit beklemek daha sağlıklı."

    report = {
        "report_date": now.strftime("%Y-%m-%d"),
        "updated_at": now.strftime("%H:%M Türkiye saati"),
        "data_layer": {
            "crypto_source": "Binance USD-M Futures public data",
            "macro_source": "Yahoo Finance + CoinGecko global",
            "included_crypto_symbols": [x[1] for x in CRYPTO_ASSETS],
            "included_macro": ["DXY", "TOTAL", "TOTAL2", "TOTAL3", "BTC Dominance", "ETH Dominance", "USDT.D"],
            "included_futures_metrics": ["funding", "open_interest", "open_interest_change", "taker_buy_sell_ratio", "candle_delta", "delta_ratio"],
        },
        "daily_decision": {"title": title, "risk": risk, "summary": summary},
        "weekly_report": {
            "title": "Pazartesi haftalık radar" if now.weekday() == 0 else "Haftalık izleme özeti",
            "summary": "Pazartesi günleri haftalık yön, güçlenenler ve zayıflayanlar özetlenir. Diğer günlerde haftanın mevcut izleme durumu gösterilir.",
            "items": [f"Kripto ortalama: {crypto_avg:.2f}%", f"BIST öncelik ortalama: {bist_avg:.2f}%", "Delta/OI/Funding verisi coin öneri motoruna aktarılır"],
        },
        "macro": macro,
        "comparison": [
            {"name": "Kripto ortalama", "change_pct": safe_float(crypto_avg), "note": "15 Binance Futures coin ortalama değişimi."},
            {"name": "BIST öncelikli ortalama", "change_pct": safe_float(bist_avg), "note": "SASA, ZOREN ve HEKTAŞ takip listesinin ortalama değişimi."},
        ],
        "crypto": crypto,
        "commodities": commodities,
        "bist": bist,
        "opportunities": opportunity_list(crypto + bist),
        "funds": [{"name": "Fon radarı", "change_pct": None, "note": "Fon verisi için TEFAS/KAP kaynakları sonraki aşamada eklenecek. Şimdilik otomatik veri sınırlı."}],
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rapor yazıldı: {DATA_PATH}")


if __name__ == "__main__":
    main()

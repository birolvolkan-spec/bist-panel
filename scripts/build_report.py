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

ASSETS = {
    "crypto": [
        ("Bitcoin", "BTC-USD", " $"),
        ("Ethereum", "ETH-USD", " $"),
        ("Solana", "SOL-USD", " $"),
        ("BNB", "BNB-USD", " $"),
        ("Optimism", "OP-USD", " $"),
    ],
    "commodities": [
        ("Altın", "GC=F", " $"),
        ("Brent Petrol", "BZ=F", " $"),
    ],
    "bist": [
        ("SASA", "SASA.IS", " ₺"),
        ("ZOREN", "ZOREN.IS", " ₺"),
        ("HEKTAŞ", "HEKTS.IS", " ₺"),
    ],
    "macro_yf": [
        ("DXY", "DX-Y.NYB", ""),
        ("BIST 100", "XU100.IS", ""),
    ],
}


def safe_float(value):
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 4)
    except Exception:
        return None


def previous_report():
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else {}
    except Exception:
        return {}


def history(symbol, days="60d"):
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


def latest_price(symbol, fallback):
    try:
        fast = yf.Ticker(symbol).fast_info
        for key in ("last_price", "lastPrice", "regular_market_price"):
            try:
                price = safe_float(fast[key])
            except Exception:
                price = None
            if price is not None and price > 0:
                return price
    except Exception:
        pass
    return fallback


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


def asset_report(name, symbol, currency, category, previous):
    hist = history(symbol)
    if len(hist) < 3:
        return limited_asset(name, symbol, currency, category, hist)

    closes = [x["close"] for x in hist if x.get("close") is not None]
    volumes = [x.get("volume") for x in hist if x.get("volume") is not None]
    if len(closes) < 3:
        return limited_asset(name, symbol, currency, category, hist)

    last_close = closes[-1]
    last = latest_price(symbol, last_close)
    prev = closes[-2]
    change = safe_float(((last - prev) / prev) * 100) if prev else None

    recent = closes[-20:] if len(closes) >= 20 else closes
    support = min(recent)
    resistance = max(recent)
    ma5 = sum(closes[-5:]) / min(5, len(closes))
    ma20 = sum(recent) / len(recent)
    ch = change or 0

    if ma5 > ma20 and ch > 0:
        trend = "Güçleniyor"
    elif ma5 < ma20 and ch < 0:
        trend = "Zayıflıyor"
    else:
        trend = "Kararsız"

    volume_status = "Veri sınırlı"
    if len(volumes) >= 6:
        avg_vol = sum(volumes[-6:-1]) / 5
        volume_status = "Artıyor" if volumes[-1] > avg_vol * 1.15 else "Zayıf" if volumes[-1] < avg_vol * 0.85 else "Normal"

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
        compare = f"Düne göre değişim {ch:+.2f}%."

    item = {
        "name": name,
        "symbol": symbol,
        "currency": currency,
        "last_price": safe_float(last),
        "change_pct": change,
        "support": safe_float(support),
        "resistance": safe_float(resistance),
        "volume_status": volume_status,
        "trend": trend,
        "comment": comment,
        "compare": compare,
        "history": hist,
    }
    if category == "bist":
        item["bist_extra"] = "Fiyat ve hacim gecikmeli günlük veriyle izleniyor. Yabancı para akışı, kurum dağılımı, kademe ve takas detayı veri kaynağına bağlıdır; veri yoksa uydurulmaz."
    return item


def coingecko_macro():
    try:
        response = requests.get("https://api.coingecko.com/api/v3/global", timeout=20)
        data = response.json().get("data", {})
        btc_dom = safe_float(data.get("market_cap_percentage", {}).get("btc"))
        eth_dom = safe_float(data.get("market_cap_percentage", {}).get("eth"))
        total_change = safe_float(data.get("market_cap_change_percentage_24h_usd"))
        return [
            {"name": "BTC Dominance", "change_pct": None, "note": f"BTC piyasa payı yaklaşık %{btc_dom}. BTC ağırlığı artarsa altcoinlerde seçici olmak gerekir."},
            {"name": "ETH Dominance", "change_pct": None, "note": f"ETH piyasa payı yaklaşık %{eth_dom}. Altcoin iştahı için izlenir."},
            {"name": "Kripto toplam piyasa", "change_pct": total_change, "note": "Toplam piyasa değeri 24 saatlik değişime göre yorumlanır."},
        ]
    except Exception:
        return [{"name": "Kripto makro", "change_pct": None, "note": "CoinGecko verisi alınamadı."}]


def macro_report():
    rows = []
    for name, symbol, _ in ASSETS["macro_yf"]:
        item = asset_report(name, symbol, "", "macro", {})
        rows.append({"name": name, "change_pct": item.get("change_pct"), "note": item.get("comment", "")})
    rows.extend(coingecko_macro())
    return rows


def avg_change(items):
    values = [x.get("change_pct") for x in items if x.get("change_pct") is not None]
    return sum(values) / len(values) if values else 0


def opportunity_list(items):
    ranked = sorted(items, key=lambda x: x.get("change_pct") if x.get("change_pct") is not None else -999, reverse=True)
    out = []
    for item in ranked[:5]:
        out.append({"name": item["name"], "change_pct": item.get("change_pct"), "note": f"Trend: {item.get('trend')}. Hacim: {item.get('volume_status')}."})
    return out


def main():
    now = datetime.now(IST)
    previous = previous_report()

    crypto = [asset_report(*asset, category="crypto", previous=previous) for asset in ASSETS["crypto"]]
    commodities = [asset_report(*asset, category="commodities", previous=previous) for asset in ASSETS["commodities"]]
    bist = [asset_report(*asset, category="bist", previous=previous) for asset in ASSETS["bist"]]
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
        "daily_decision": {"title": title, "risk": risk, "summary": summary},
        "weekly_report": {
            "title": "Pazartesi haftalık radar" if now.weekday() == 0 else "Haftalık izleme özeti",
            "summary": "Pazartesi günleri haftalık yön, güçlenenler ve zayıflayanlar özetlenir. Diğer günlerde haftanın mevcut izleme durumu gösterilir.",
            "items": [f"Kripto ortalama: {crypto_avg:.2f}%", f"BIST öncelik ortalama: {bist_avg:.2f}%", "BIST detay verisi yoksa açıkça sınırlı veri yazılır"],
        },
        "macro": macro,
        "comparison": [
            {"name": "Kripto ortalama", "change_pct": safe_float(crypto_avg), "note": "BTC, ETH, SOL, BNB ve OP ortalama değişimi."},
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

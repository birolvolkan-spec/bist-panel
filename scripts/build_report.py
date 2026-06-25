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
        ("BJKAS / BEKTAŞ", "BJKAS.IS", " ₺"),
    ],
    "macro_yf": [
        ("DXY", "DX-Y.NYB", ""),
        ("BIST 100", "XU100.IS", ""),
    ],
}


def safe_float(x):
    try:
        if x is None or math.isnan(float(x)):
            return None
        return round(float(x), 4)
    except Exception:
        return None


def load_previous():
    if not DATA_PATH.exists():
        return {}
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fetch_history(symbol):
    try:
        df = yf.Ticker(symbol).history(period="45d", interval="1d", auto_adjust=False)
        if df.empty:
            return []
        df = df.tail(30).reset_index()
        rows = []
        for _, r in df.iterrows():
            date_value = r.get("Date")
            label = str(date_value.date()) if hasattr(date_value, "date") else str(date_value)[:10]
            rows.append({
                "date": label,
                "close": safe_float(r.get("Close")),
                "volume": safe_float(r.get("Volume")),
            })
        return [x for x in rows if x["close"] is not None]
    except Exception:
        return []


def asset_report(name, symbol, currency, category, previous):
    hist = fetch_history(symbol)
    if len(hist) < 3:
        return {
            "name": name,
            "symbol": symbol,
            "currency": currency,
            "last_price": None,
            "change_pct": 0,
            "support": None,
            "resistance": None,
            "volume_status": "Veri sınırlı",
            "trend": "Veri sınırlı",
            "comment": "Bu varlık için ücretsiz kaynaktan yeterli veri alınamadı. Veri yoksa yorum uydurulmaz.",
            "compare": "Dün-bugün karşılaştırması için veri sınırlı.",
            "history": hist,
            "bist_extra": "Yabancı para akışı, kademeli emir ve takas detayı ücretsiz kaynaklarda sınırlı olabilir. Veri sağlanırsa ayrıca gösterilecek." if category == "bist" else None,
        }

    closes = [x["close"] for x in hist if x["close"] is not None]
    vols = [x.get("volume") for x in hist if x.get("volume") is not None]
    last = closes[-1]
    prev = closes[-2]
    change = ((last - prev) / prev * 100) if prev else 0
    recent = closes[-20:] if len(closes) >= 20 else closes
    support = min(recent)
    resistance = max(recent)
    ma5 = sum(closes[-5:]) / min(5, len(closes))
    ma20 = sum(recent) / len(recent)
    trend = "Güçleniyor" if ma5 > ma20 and change > 0 else "Zayıflıyor" if ma5 < ma20 and change < 0 else "Kararsız"

    volume_status = "Veri sınırlı"
    if len(vols) >= 6:
        avg_vol = sum(vols[-6:-1]) / 5
        volume_status = "Artıyor" if vols[-1] > avg_vol * 1.15 else "Zayıf" if vols[-1] < avg_vol * 0.85 else "Normal"

    if change > 1 and trend == "Güçleniyor":
        comment = f"{name} bugün alıcı tarafı toparlıyor. Direnç bölgesi kırılırsa hareket güçlenebilir; acele işlem yerine kapanış teyidi izlenmeli."
    elif change < -1 and trend == "Zayıflıyor":
        comment = f"{name} tarafında satış baskısı öne çıkıyor. Destek kaybedilirse risk artar; tepki alımı için hacim teyidi gerekir."
    else:
        comment = f"{name} şu an net yön üretmiyor. Destek ve direnç arası hareket izlenmeli; seçici olmak daha sağlıklı."

    old = None
    for group in ["crypto", "commodities", "bist"]:
        for item in previous.get(group, []):
            if item.get("symbol") == symbol:
                old = item
                break
    if old and old.get("last_price"):
        old_price = old.get("last_price")
        diff = ((last - old_price) / old_price * 100) if old_price else change
        compare = f"Önceki rapora göre fiyat değişimi {diff:+.2f}%. Yorum güncel veriye göre revize edildi."
    else:
        compare = f"Düne göre değişim {change:+.2f}%."

    out = {
        "name": name,
        "symbol": symbol,
        "currency": currency,
        "last_price": safe_float(last),
        "change_pct": safe_float(change),
        "support": safe_float(support),
        "resistance": safe_float(resistance),
        "volume_status": volume_status,
        "trend": trend,
        "comment": comment,
        "compare": compare,
        "history": hist,
    }
    if category == "bist":
        out["bist_extra"] = "Fiyat ve hacim otomatik izleniyor. Yabancı para akışı, kurum dağılımı, kademe ve takas detayı veri kaynağına bağlıdır; veri yoksa uydurulmaz."
    return out


def coingecko_macro():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=20)
        data = r.json().get("data", {})
        btc_dom = data.get("market_cap_percentage", {}).get("btc")
        eth_dom = data.get("market_cap_percentage", {}).get("eth")
        change = data.get("market_cap_change_percentage_24h_usd")
        return [
            {"name": "BTC Dominance", "change_pct": safe_float(0), "note": f"BTC piyasa payı yaklaşık %{safe_float(btc_dom)}. BTC ağırlığı artarsa altcoinlerde seçici olmak gerekir."},
            {"name": "ETH Dominance", "change_pct": safe_float(0), "note": f"ETH piyasa payı yaklaşık %{safe_float(eth_dom)}. Altcoin iştahı için izlenir."},
            {"name": "Kripto toplam piyasa", "change_pct": safe_float(change), "note": "Toplam piyasa değeri 24 saatlik değişime göre yorumlanır."},
        ]
    except Exception:
        return [
            {"name": "BTC Dominance", "change_pct": 0, "note": "CoinGecko verisi alınamadı."},
            {"name": "TOTAL / TOTAL2 / TOTAL3", "change_pct": 0, "note": "Ücretsiz kaynak sınırlı; sonraki sürümde TradingView alternatifi değerlendirilecek."},
        ]


def macro_report():
    rows = []
    for name, symbol, _ in ASSETS["macro_yf"]:
        a = asset_report(name, symbol, "", "macro", {})
        rows.append({"name": name, "change_pct": a.get("change_pct") or 0, "note": a.get("comment", "")})
    rows.extend(coingecko_macro())
    return rows


def simple_list_from_assets(assets):
    ranked = sorted(assets, key=lambda x: x.get("change_pct") or 0, reverse=True)
    out = []
    for a in ranked[:5]:
        out.append({"name": a["name"], "change_pct": a.get("change_pct") or 0, "note": f"Trend: {a.get('trend')}. Hacim: {a.get('volume_status')}."})
    return out


def main():
    now = datetime.now(IST)
    previous = load_previous()

    crypto = [asset_report(*x, category="crypto", previous=previous) for x in ASSETS["crypto"]]
    commodities = [asset_report(*x, category="commodities", previous=previous) for x in ASSETS["commodities"]]
    bist = [asset_report(*x, category="bist", previous=previous) for x in ASSETS["bist"]]
    macro = macro_report()

    crypto_avg = sum([(x.get("change_pct") or 0) for x in crypto]) / max(1, len(crypto))
    bist_avg = sum([(x.get("change_pct") or 0) for x in bist]) / max(1, len(bist))
    if crypto_avg > 1 and bist_avg > 0:
        decision = ("🟢 Risk alınabilir ama seçici", "ORTA-DÜŞÜK", "Kripto ve BIST tarafında toparlanma işaretleri var. Yine de direnç kırılımı ve hacim teyidi beklenmeli.")
    elif crypto_avg < -1 or bist_avg < -1:
        decision = ("🔴 Korunmacı kal", "YÜKSEK", "Piyasada satış baskısı öne çıkıyor. Destekler korunmadan agresif işlem almak riskli.")
    else:
        decision = ("🟡 Seçici olun", "ORTA", "Piyasa net yön üretmiyor. Destek-direnç arası hareketlerde acele etmek yerine teyit beklemek daha sağlıklı.")

    weekly_items = ["Kripto ortalama: %.2f%%" % crypto_avg, "BIST öncelik ortalama: %.2f%%" % bist_avg, "BIST detay verisi sınırlıysa uyarı gösterilir"]
    weekly_title = "Pazartesi haftalık radar" if now.weekday() == 0 else "Haftalık izleme özeti"
    weekly_summary = "Bu bölüm her pazartesi haftalık yön, güçlenenler ve zayıflayanları özetler. Diğer günlerde haftanın mevcut izleme durumunu gösterir."

    report = {
        "report_date": now.strftime("%Y-%m-%d"),
        "updated_at": now.strftime("%H:%M Türkiye saati"),
        "daily_decision": {"title": decision[0], "risk": decision[1], "summary": decision[2]},
        "weekly_report": {"title": weekly_title, "summary": weekly_summary, "items": weekly_items},
        "macro": macro,
        "comparison": [
            {"name": "Kripto ortalama", "change_pct": safe_float(crypto_avg), "note": "BTC, ETH, SOL, BNB ve OP ortalama günlük değişimi."},
            {"name": "BIST öncelikli ortalama", "change_pct": safe_float(bist_avg), "note": "SASA, ZOREN ve BJKAS takip listesinin ortalama günlük değişimi."},
        ],
        "crypto": crypto,
        "commodities": commodities,
        "bist": bist,
        "opportunities": simple_list_from_assets(crypto + bist),
        "funds": [
            {"name": "Fon radarı", "change_pct": 0, "note": "Fon verisi için TEFAS/KAP kaynakları sonraki aşamada eklenecek. Şimdilik otomatik veri sınırlı."}
        ],
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rapor yazıldı: {DATA_PATH}")


if __name__ == "__main__":
    main()

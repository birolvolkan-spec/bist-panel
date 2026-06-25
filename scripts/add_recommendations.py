import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "daily_report.json"


def val(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def classify_macro(report):
    macro = {m.get("name", ""): m for m in report.get("macro", [])}
    dxy = val(macro.get("DXY", {}).get("change_pct"))
    total_crypto = val(macro.get("Kripto toplam piyasa", {}).get("change_pct"))
    btc_dom_note = macro.get("BTC Dominance", {}).get("note", "")

    # USDT.D ve TOTAL2/TOTAL3 doğrudan yoksa karar motoru bunları eksik veri olarak kabul eder.
    missing = ["USDT.D", "TOTAL2", "TOTAL3", "OI", "Gerçek delta"]

    risk_off_score = 0
    risk_on_score = 0

    if dxy > 0.15:
        risk_off_score += 20
    elif dxy < -0.15:
        risk_on_score += 20

    if total_crypto < -0.75:
        risk_off_score += 25
    elif total_crypto > 0.75:
        risk_on_score += 25

    if "BTC piyasa payı" in btc_dom_note:
        risk_off_score += 5
        risk_on_score += 5

    if risk_off_score > risk_on_score + 10:
        regime = "SHORT ağırlıklı / risk-off"
        direction_bias = "SHORT"
        summary = "Makro tablo temkinli. DXY ve toplam piyasa zayıflığı short adaylarını öne çıkarabilir."
    elif risk_on_score > risk_off_score + 10:
        regime = "LONG ağırlıklı / risk-on"
        direction_bias = "LONG"
        summary = "Makro tablo toparlanma eğiliminde. Güçlü coinlerde long adayları öne çıkarılabilir."
    else:
        regime = "Kararsız / seçici"
        direction_bias = "MIXED"
        summary = "Makro tablo net yön üretmiyor. Coin bazlı güç-zayıflık ve destek/direnç teyidi daha önemli."

    return {
        "regime": regime,
        "direction_bias": direction_bias,
        "risk_on_score": round(risk_on_score, 2),
        "risk_off_score": round(risk_off_score, 2),
        "summary": summary,
        "missing_data": missing,
    }


def volume_score(asset, direction):
    status = asset.get("volume_status")
    if status == "Artıyor":
        return 12
    if status == "Normal":
        return 5
    if status == "Zayıf":
        return -6
    return 0


def trend_score(asset, direction):
    trend = asset.get("trend")
    ch = val(asset.get("change_pct"))
    if direction == "LONG":
        score = 0
        if trend == "Güçleniyor":
            score += 22
        if ch > 0:
            score += min(18, ch * 4)
        if ch < -1:
            score -= 15
        return score
    score = 0
    if trend == "Zayıflıyor":
        score += 22
    if ch < 0:
        score += min(18, abs(ch) * 4)
    if ch > 1:
        score -= 15
    return score


def relative_score(asset, benchmark_change, direction):
    ch = val(asset.get("change_pct"))
    rel = ch - benchmark_change
    if direction == "LONG":
        return max(-20, min(25, rel * 5))
    return max(-20, min(25, -rel * 5))


def location_penalty(asset, direction):
    price = val(asset.get("last_price"), None)
    support = val(asset.get("support"), None)
    resistance = val(asset.get("resistance"), None)
    if not price or not support or not resistance or resistance <= support:
        return 0, "Destek/direnç verisi sınırlı."
    pos = (price - support) / (resistance - support)
    if direction == "LONG":
        if pos > 0.88:
            return -15, "Fiyat dirence çok yakın; long için geç kalma riski var."
        if pos < 0.25:
            return 8, "Fiyat destek bölgesine yakın; dönüş teyidi aranabilir."
        return 0, "Fiyat destek/direnç arasında."
    if pos < 0.12:
        return -15, "Fiyat desteğe çok yakın; short için geç kalma riski var."
    if pos > 0.75:
        return 8, "Fiyat direnç bölgesine yakın; red teyidi aranabilir."
    return 0, "Fiyat destek/direnç arasında."


def timeframe_for(asset, direction, score):
    ch = abs(val(asset.get("change_pct")))
    trend = asset.get("trend")
    vol = asset.get("volume_status")

    if score >= 75 and vol == "Artıyor" and ch >= 2:
        return {
            "higher_tf": "1h",
            "setup_tf": "15m",
            "entry_tf": "5m",
            "style": "Gün içi momentum",
            "note": "Hareket güçlü; 15m yapı ve 5m tetik beklenmeli."
        }
    if trend in ("Güçleniyor", "Zayıflıyor"):
        return {
            "higher_tf": "4h / 1h",
            "setup_tf": "30m / 15m",
            "entry_tf": "5m",
            "style": "Trend devamı",
            "note": "Üst zaman dilimi yönü bozmadan 15m-30m setup aranmalı."
        }
    return {
        "higher_tf": "1h",
        "setup_tf": "15m",
        "entry_tf": "5m / 3m",
        "style": "Seçici kısa vade",
        "note": "Piyasa kararsız; destek/direnç teyidi olmadan işlem aranmaz."
    }


def build_candidate(asset, direction, macro, btc_change):
    base = 35
    if macro["direction_bias"] == direction:
        base += 16
    elif macro["direction_bias"] == "MIXED":
        base += 4
    else:
        base -= 15

    score = base
    score += trend_score(asset, direction)
    score += volume_score(asset, direction)
    score += relative_score(asset, btc_change, direction)
    loc_penalty, loc_note = location_penalty(asset, direction)
    score += loc_penalty
    score = max(0, min(100, round(score, 1)))

    tf = timeframe_for(asset, direction, score)
    reasons = []
    reasons.append(f"Makro rejim: {macro['regime']}.")
    reasons.append(f"Trend: {asset.get('trend')}, hacim: {asset.get('volume_status')}.")
    reasons.append(f"BTC'ye göre göreceli fark: {val(asset.get('change_pct')) - btc_change:+.2f} puan.")
    reasons.append(loc_note)
    reasons.append("Delta/OI gerçek verisi henüz bağlı değil; şimdilik hacim ve fiyat davranışı proxy olarak kullanıldı.")

    if score >= 70:
        action = f"{direction} adayı"
    elif score >= 55:
        action = f"İzleme / {direction} eğilimi"
    else:
        action = "Pas / net sinyal yok"

    return {
        "symbol": asset.get("symbol"),
        "name": asset.get("name"),
        "direction": direction,
        "score": score,
        "action": action,
        "higher_tf": tf["higher_tf"],
        "setup_tf": tf["setup_tf"],
        "entry_tf": tf["entry_tf"],
        "style": tf["style"],
        "timeframe_note": tf["note"],
        "reasons": reasons,
        "entry_plan": entry_plan(asset, direction, tf),
        "invalid_if": invalidation(asset, direction),
    }


def entry_plan(asset, direction, tf):
    support = asset.get("support")
    resistance = asset.get("resistance")
    if direction == "LONG":
        return f"{tf['setup_tf']} destekten dönüş veya direnç üstü kapanış beklenir. {tf['entry_tf']} pozitif hacim/delta teyidi aranır."
    return f"{tf['setup_tf']} direnç retesti veya destek kırılımı beklenir. {tf['entry_tf']} negatif hacim/delta teyidi aranır."


def invalidation(asset, direction):
    support = asset.get("support")
    resistance = asset.get("resistance")
    cur = asset.get("currency", "")
    if direction == "LONG":
        return f"Destek altı kapanış veya hacimsiz kırılım. Takip destek: {support}{cur}."
    return f"Direnç üstü kapanış veya satış hacminin kaybolması. Takip direnç: {resistance}{cur}."


def build_recommendations(report):
    macro = classify_macro(report)
    crypto = report.get("crypto", [])
    btc = next((x for x in crypto if x.get("symbol") == "BTC-USD"), None)
    btc_change = val(btc.get("change_pct") if btc else 0)

    candidates = []
    for asset in crypto:
        if asset.get("symbol") == "BTC-USD":
            continue
        candidates.append(build_candidate(asset, "LONG", macro, btc_change))
        candidates.append(build_candidate(asset, "SHORT", macro, btc_change))

    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
    top = [c for c in candidates if c["score"] >= 55][:5]

    if not top:
        summary = "Temiz işlem adayı çıkmadı. Sistem NO TRADE modunda kalmayı önerir."
    else:
        first = top[0]
        summary = f"En güçlü aday: {first['name']} {first['direction']} ({first['score']}/100)."

    return {
        "engine_version": "v1.0",
        "market_regime": macro,
        "summary": summary,
        "top_candidates": top,
        "rules": [
            "Skor 70 üzeri: işlem adayı",
            "Skor 55-69: izleme adayı",
            "Skor 55 altı: pas",
            "Delta/OI bağlanana kadar bu motor hacim ve fiyat davranışını proxy olarak kullanır",
            "Veri yoksa sistem uydurma sinyal üretmez",
        ],
    }


def main():
    report = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    report["trade_recommendations"] = build_recommendations(report)
    DATA_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Trade recommendations added")


if __name__ == "__main__":
    main()

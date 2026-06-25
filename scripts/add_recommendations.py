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


def get_macro(report, name):
    for item in report.get("macro", []):
        if item.get("name") == name:
            return item
    return {}


def is_ready(item):
    return bool(item.get("data_ready")) or item.get("value") is not None or item.get("change_pct") is not None


def classify_macro(report):
    dxy = get_macro(report, "DXY")
    total = get_macro(report, "TOTAL")
    total2 = get_macro(report, "TOTAL2")
    total3 = get_macro(report, "TOTAL3")
    usdt_d = get_macro(report, "USDT.D")
    btc_d = get_macro(report, "BTC Dominance")

    missing = []
    for name, item in [("DXY", dxy), ("TOTAL", total), ("TOTAL2", total2), ("TOTAL3", total3), ("USDT.D", usdt_d), ("BTC.D", btc_d)]:
        if not is_ready(item):
            missing.append(name)

    dxy_ch = val(dxy.get("change_pct"))
    total_ch = val(total.get("change_pct"))
    total3_ch = val(total3.get("change_pct"), total_ch)
    usdt_value = val(usdt_d.get("value"), None)

    risk_off_score = 0
    risk_on_score = 0

    if dxy_ch > 0.15:
        risk_off_score += 20
    elif dxy_ch < -0.15:
        risk_on_score += 20

    if total_ch < -0.75:
        risk_off_score += 25
    elif total_ch > 0.75:
        risk_on_score += 25

    if total3_ch < -0.75:
        risk_off_score += 20
    elif total3_ch > 0.75:
        risk_on_score += 20

    if usdt_value is not None:
        if usdt_value >= 6:
            risk_off_score += 8
        elif usdt_value <= 4:
            risk_on_score += 8

    if risk_off_score > risk_on_score + 10:
        regime = "SHORT ağırlıklı / risk-off"
        direction_bias = "SHORT"
        summary = "Makro tablo temkinli. TOTAL/TOTAL3 zayıflığı ve DXY etkisi short adaylarını öne çıkarabilir."
    elif risk_on_score > risk_off_score + 10:
        regime = "LONG ağırlıklı / risk-on"
        direction_bias = "LONG"
        summary = "Makro tablo toparlanma eğiliminde. TOTAL/TOTAL3 güçlenirse güçlü coinlerde long adayları öne çıkar."
    else:
        regime = "Kararsız / seçici"
        direction_bias = "MIXED"
        summary = "Makro tablo net yön üretmiyor. Coin bazlı güç-zayıflık, delta, OI ve destek/direnç teyidi daha önemli."

    return {
        "regime": regime,
        "direction_bias": direction_bias,
        "risk_on_score": round(risk_on_score, 2),
        "risk_off_score": round(risk_off_score, 2),
        "summary": summary,
        "missing_data": missing,
    }


def metrics(asset):
    return asset.get("futures_metrics") or {}


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


def futures_score(asset, direction):
    m = metrics(asset)
    score = 0
    delta_ratio = val(m.get("last_delta_ratio_pct"), None)
    taker_ratio = val(m.get("taker_buy_sell_ratio"), None)
    oi_change = val(m.get("open_interest_change_pct"), None)
    funding_pct = val(m.get("funding_rate_pct"), None)
    price_ch = val(asset.get("change_pct"))

    if delta_ratio is not None:
        if direction == "LONG":
            score += max(-16, min(18, delta_ratio * 1.2))
        else:
            score += max(-16, min(18, -delta_ratio * 1.2))

    if taker_ratio is not None:
        if direction == "LONG":
            if taker_ratio > 1.08:
                score += 12
            elif taker_ratio < 0.92:
                score -= 10
        else:
            if taker_ratio < 0.92:
                score += 12
            elif taker_ratio > 1.08:
                score -= 10

    if oi_change is not None:
        if direction == "LONG" and price_ch > 0 and oi_change > 0:
            score += 12
        elif direction == "SHORT" and price_ch < 0 and oi_change > 0:
            score += 12
        elif oi_change < -1:
            score -= 5

    if funding_pct is not None:
        if direction == "SHORT" and funding_pct > 0.02:
            score += 6
        elif direction == "LONG" and funding_pct < -0.02:
            score += 6
        elif direction == "LONG" and funding_pct > 0.06:
            score -= 8
        elif direction == "SHORT" and funding_pct < -0.06:
            score -= 8

    return score


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
    m = metrics(asset)
    oi_change = val(m.get("open_interest_change_pct"), 0)
    delta_ratio = abs(val(m.get("last_delta_ratio_pct"), 0))

    if score >= 75 and vol == "Artıyor" and (ch >= 2 or delta_ratio >= 10 or oi_change >= 1):
        return {"higher_tf": "1h", "setup_tf": "15m", "entry_tf": "5m", "style": "Gün içi momentum", "note": "Hareket güçlü; 15m yapı ve 5m tetik beklenmeli."}
    if trend in ("Güçleniyor", "Zayıflıyor"):
        return {"higher_tf": "4h / 1h", "setup_tf": "30m / 15m", "entry_tf": "5m", "style": "Trend devamı", "note": "Üst zaman dilimi yönü bozmadan 15m-30m setup aranmalı."}
    return {"higher_tf": "1h", "setup_tf": "15m", "entry_tf": "5m / 3m", "style": "Seçici kısa vade", "note": "Piyasa kararsız; destek/direnç teyidi olmadan işlem aranmaz."}


def fmt_metric(x, suffix=""):
    if x is None:
        return "-"
    try:
        return f"{float(x):.4f}{suffix}"
    except Exception:
        return "-"


def build_candidate(asset, direction, macro, btc_change):
    base = 35
    if macro["direction_bias"] == direction:
        base += 16
    elif macro["direction_bias"] == "MIXED":
        base += 4
    else:
        base -= 15

    score = base
    trend_part = trend_score(asset, direction)
    volume_part = volume_score(asset, direction)
    relative_part = relative_score(asset, btc_change, direction)
    futures_part = futures_score(asset, direction)
    loc_penalty, loc_note = location_penalty(asset, direction)
    score += trend_part + volume_part + relative_part + futures_part + loc_penalty
    score = max(0, min(100, round(score, 1)))

    price_change = val(asset.get("change_pct"), None)
    relative_to_btc = price_change - btc_change if price_change is not None else None

    tf = timeframe_for(asset, direction, score)
    m = metrics(asset)
    reasons = [
        f"Makro rejim: {macro['regime']}.",
        f"Trend: {asset.get('trend')}, hacim: {asset.get('volume_status')}.",
        f"Fiyat değişim: {fmt_metric(price_change, '%')}, BTC'ye göre fark: {fmt_metric(relative_to_btc, ' puan')}.",
        f"Delta oranı: {fmt_metric(m.get('last_delta_ratio_pct'), '%')}, taker al/sat: {fmt_metric(m.get('taker_buy_sell_ratio'))}.",
        f"OI değişim: {fmt_metric(m.get('open_interest_change_pct'), '%')}, funding: {fmt_metric(m.get('funding_rate_pct'), '%')}.",
        loc_note,
    ]

    missing_metrics = []
    if m.get("last_delta_ratio_pct") is None:
        missing_metrics.append("delta")
    if m.get("open_interest_change_pct") is None:
        missing_metrics.append("OI değişim")
    if m.get("taker_buy_sell_ratio") is None:
        missing_metrics.append("taker al/sat")
    if m.get("funding_rate_pct") is None:
        missing_metrics.append("funding")
    if missing_metrics:
        reasons.append("Eksik coin verisi: " + ", ".join(missing_metrics) + ".")

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
        "price_change_pct": price_change,
        "relative_to_btc_pct": relative_to_btc,
        "score_breakdown": {
            "base_macro": base,
            "trend": round(trend_part, 2),
            "volume": round(volume_part, 2),
            "relative_strength": round(relative_part, 2),
            "futures": round(futures_part, 2),
            "location": round(loc_penalty, 2),
        },
        "higher_tf": tf["higher_tf"],
        "setup_tf": tf["setup_tf"],
        "entry_tf": tf["entry_tf"],
        "style": tf["style"],
        "timeframe_note": tf["note"],
        "reasons": reasons,
        "entry_plan": entry_plan(asset, direction, tf),
        "invalid_if": invalidation(asset, direction),
        "futures_metrics": m,
    }


def entry_plan(asset, direction, tf):
    if direction == "LONG":
        return f"{tf['setup_tf']} destekten dönüş veya direnç üstü kapanış beklenir. {tf['entry_tf']} pozitif delta/taker teyidi aranır."
    return f"{tf['setup_tf']} direnç retesti veya destek kırılımı beklenir. {tf['entry_tf']} negatif delta/taker teyidi aranır."


def invalidation(asset, direction):
    support = asset.get("support")
    resistance = asset.get("resistance")
    cur = asset.get("currency", "")
    if direction == "LONG":
        return f"Destek altı kapanış veya pozitif deltanın kaybolması. Takip destek: {support}{cur}."
    return f"Direnç üstü kapanış veya negatif deltanın kaybolması. Takip direnç: {resistance}{cur}."


def build_recommendations(report):
    macro = classify_macro(report)
    crypto = report.get("crypto", [])
    btc = next((x for x in crypto if x.get("symbol") == "BTCUSDT"), None)
    btc_change = val(btc.get("change_pct") if btc else 0)

    candidates = []
    for asset in crypto:
        if asset.get("symbol") == "BTCUSDT":
            continue
        candidates.append(build_candidate(asset, "LONG", macro, btc_change))
        candidates.append(build_candidate(asset, "SHORT", macro, btc_change))

    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
    top = [c for c in candidates if c["score"] >= 55][:7]

    if not top:
        summary = "Temiz işlem adayı çıkmadı. Sistem NO TRADE modunda kalmayı önerir."
    else:
        first = top[0]
        summary = f"En güçlü aday: {first['name']} {first['direction']} ({first['score']}/100)."

    return {
        "engine_version": "v2.1",
        "market_regime": macro,
        "summary": summary,
        "top_candidates": top,
        "rules": [
            "Skor 70 üzeri: işlem adayı",
            "Skor 55-69: izleme adayı",
            "Skor 55 altı: pas",
            "Delta, OI, taker al/sat ve funding skorlamaya dahil edilir",
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

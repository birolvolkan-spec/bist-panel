import json
import math
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "daily_report.json"

FAPI_BASES = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 VolkanDailyRadar/1.0",
    "Accept": "application/json,text/plain,*/*",
}


def safe_float(value, ndigits=6):
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, ndigits)
    except Exception:
        return None


def request_json(url, params=None, timeout=12):
    try:
        r = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
        if r.status_code >= 400:
            return None, f"HTTP {r.status_code}: {r.text[:120]}"
        return r.json(), None
    except Exception as exc:
        return None, str(exc)[:160]


def get_from_bases(path, params=None):
    errors = []
    for base in FAPI_BASES:
        url = base + path
        data, err = request_json(url, params=params)
        if data is not None:
            return data, base, None
        errors.append(f"{base} -> {err}")
    return None, None, " | ".join(errors[-2:])


def get_data_endpoint(path, params=None):
    errors = []
    for base in FAPI_BASES:
        url = base + "/futures/data" + path
        data, err = request_json(url, params=params)
        if data is not None:
            return data, base, None
        errors.append(f"{base}/futures/data -> {err}")
    return None, None, " | ".join(errors[-2:])


def latest_15m_delta(symbol):
    rows, base, err = get_from_bases("/fapi/v1/klines", {"symbol": symbol, "interval": "15m", "limit": 1})
    if not isinstance(rows, list) or not rows:
        return {"last_candle_delta": None, "last_delta_ratio_pct": None, "delta_error": err}
    row = rows[-1]
    try:
        volume = safe_float(row[5])
        taker_buy = safe_float(row[9])
        if volume is None or taker_buy is None or volume == 0:
            return {"last_candle_delta": None, "last_delta_ratio_pct": None, "delta_error": "volume/taker empty"}
        taker_sell = volume - taker_buy
        delta = taker_buy - taker_sell
        return {
            "last_candle_delta": safe_float(delta),
            "last_delta_ratio_pct": safe_float((delta / volume) * 100, 4),
            "last_taker_buy_volume": safe_float(taker_buy),
            "last_taker_sell_volume": safe_float(taker_sell),
            "delta_source_base": base,
        }
    except Exception as exc:
        return {"last_candle_delta": None, "last_delta_ratio_pct": None, "delta_error": str(exc)[:120]}


def open_interest(symbol):
    current, base_current, err_current = get_from_bases("/fapi/v1/openInterest", {"symbol": symbol})
    hist, base_hist, err_hist = get_data_endpoint("/openInterestHist", {"symbol": symbol, "period": "15m", "limit": 8})

    oi = safe_float(current.get("openInterest")) if isinstance(current, dict) else None
    oi_change = None
    if isinstance(hist, list) and len(hist) >= 2:
        first = safe_float(hist[0].get("sumOpenInterest"))
        last = safe_float(hist[-1].get("sumOpenInterest"))
        if first and last is not None:
            oi_change = safe_float(((last - first) / first) * 100, 4)
    return {
        "open_interest": oi,
        "open_interest_change_pct": oi_change,
        "oi_source_base": base_current or base_hist,
        "oi_error": None if oi is not None or oi_change is not None else (err_current or err_hist),
    }


def premium(symbol):
    data, base, err = get_from_bases("/fapi/v1/premiumIndex", {"symbol": symbol})
    if not isinstance(data, dict):
        return {"mark_price": None, "funding_rate": None, "funding_rate_pct": None, "premium_error": err}
    funding = safe_float(data.get("lastFundingRate"), 8)
    return {
        "mark_price": safe_float(data.get("markPrice"), 6),
        "funding_rate": funding,
        "funding_rate_pct": safe_float(funding * 100, 6) if funding is not None else None,
        "premium_source_base": base,
    }


def taker_ratio(symbol):
    rows, base, err = get_data_endpoint("/takerlongshortRatio", {"symbol": symbol, "period": "15m", "limit": 1})
    if not isinstance(rows, list) or not rows:
        return {
            "taker_buy_sell_ratio": None,
            "taker_buy_volume_15m": None,
            "taker_sell_volume_15m": None,
            "taker_error": err,
        }
    row = rows[-1]
    return {
        "taker_buy_sell_ratio": safe_float(row.get("buySellRatio"), 6),
        "taker_buy_volume_15m": safe_float(row.get("buyVol"), 4),
        "taker_sell_volume_15m": safe_float(row.get("sellVol"), 4),
        "taker_source_base": base,
    }


def build_metrics(symbol):
    p = premium(symbol)
    oi = open_interest(symbol)
    tk = taker_ratio(symbol)
    d = latest_15m_delta(symbol)
    metrics = {
        "source": "Binance USD-M Futures multi-endpoint patch",
        **p,
        **oi,
        **tk,
        **d,
    }
    metrics["data_ready"] = any(metrics.get(k) is not None for k in [
        "mark_price",
        "funding_rate_pct",
        "open_interest",
        "open_interest_change_pct",
        "taker_buy_sell_ratio",
        "last_delta_ratio_pct",
    ])
    metrics["status_note"] = "OK" if metrics["data_ready"] else "Binance Futures public endpoints returned no usable futures metrics"
    return metrics


def main():
    report = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    crypto = report.get("crypto", [])
    patched = 0
    for asset in crypto:
        symbol = asset.get("symbol")
        if not symbol:
            continue
        metrics = build_metrics(symbol)
        old = asset.get("futures_metrics") or {}
        # Yeni patch veri bulduysa eski boş/fallback verinin üstüne yaz.
        # Veri bulamadıysa eski dolu veri varsa koru, ama hata notunu ekle.
        if metrics.get("data_ready"):
            asset["futures_metrics"] = metrics
            asset["delta_note"] = "15m kline taker buy/sell verisinden delta proxy hesaplandı. Gerçek footprint değildir; karar filtresidir."
            patched += 1
        else:
            old.setdefault("data_ready", False)
            old.setdefault("source", "Binance Futures multi-endpoint patch failed")
            old["status_note"] = metrics.get("status_note")
            old["patch_error_sample"] = metrics.get("oi_error") or metrics.get("taker_error") or metrics.get("premium_error") or metrics.get("delta_error")
            asset["futures_metrics"] = old
    layer = report.setdefault("data_layer", {})
    layer["futures_patch_updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    layer["futures_patch_ready_count"] = patched
    layer["futures_patch_symbols"] = len(crypto)
    layer["futures_patch_note"] = "Tries fapi, fapi1, fapi2, fapi3, fapi4 for premium/OI/taker/delta."
    DATA_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Futures patch complete: {patched}/{len(crypto)} symbols ready")


if __name__ == "__main__":
    main()

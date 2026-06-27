import argparse
import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "ARBUSDT", "OPUSDT", "NEARUSDT", "APTUSDT",
]

BASES = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 VolkanBacktestPoolMonthly/1.0",
    "Accept": "application/json,text/plain,*/*",
}

CSV_HEADER = [
    "timestamp", "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_volume", "trade_count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def utc_ms(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def ms_to_utc(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def month_start(dt):
    return datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)


def add_month(dt):
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=timezone.utc)


def iter_month_ranges(start_dt, end_dt):
    cur = month_start(start_dt)
    while cur < end_dt:
        nxt = add_month(cur)
        yield max(cur, start_dt), min(nxt, end_dt)
        cur = nxt


def get_klines(symbol, interval, start_ms, end_ms, limit=1500):
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": limit,
    }
    last_error = None
    for base in BASES:
        try:
            r = requests.get(f"{base}/fapi/v1/klines", params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return data, base, None
                last_error = f"bad-json {base}: {str(data)[:120]}"
            else:
                last_error = f"{base} HTTP {r.status_code}: {r.text[:160]}"
        except Exception as exc:
            last_error = f"{base} {type(exc).__name__}: {str(exc)[:160]}"
        time.sleep(0.2)
    return [], None, last_error


def fetch_csv(symbol, interval, start_dt, end_dt, csv_path, sleep_s):
    start_ms = utc_ms(start_dt)
    end_ms = utc_ms(end_dt)
    cursor = start_ms
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    rows_written = 0
    batches = 0
    first_ts = None
    last_ts = None
    errors = []
    bases_used = set()

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)

        while cursor < end_ms:
            rows, base, err = get_klines(symbol, interval, cursor, end_ms)
            batches += 1
            if base:
                bases_used.add(base)
            if err:
                errors.append(err)

            if not rows:
                cursor += 60 * 60 * 1000
                if len(errors) > 80:
                    break
                continue

            for r in rows:
                open_time = int(r[0])
                if open_time < start_ms or open_time >= end_ms:
                    continue
                writer.writerow([
                    ms_to_utc(open_time), open_time, r[1], r[2], r[3], r[4], r[5],
                    r[6], r[7], r[8], r[9], r[10], r[11],
                ])
                rows_written += 1
                if first_ts is None:
                    first_ts = open_time
                last_ts = open_time

            next_cursor = int(rows[-1][0]) + 60_000
            if next_cursor <= cursor:
                next_cursor = cursor + 60_000
            cursor = next_cursor
            if sleep_s:
                time.sleep(sleep_s)

    expected = int((end_ms - start_ms) / 60_000) if interval == "1m" else None
    return {
        "file": str(csv_path),
        "rows": rows_written,
        "expected_rows_1m": expected,
        "coverage_pct": round((rows_written / expected) * 100, 4) if expected else None,
        "first_timestamp": ms_to_utc(first_ts) if first_ts else None,
        "last_timestamp": ms_to_utc(last_ts) if last_ts else None,
        "batches": batches,
        "bases_used": sorted(bases_used),
        "errors_sample": errors[-5:],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backtest_data")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--sleep", type=float, default=0.05)
    args = ap.parse_args()

    out = Path(args.out).resolve()
    if args.end:
        end_dt = parse_date(args.end)
    else:
        now = datetime.now(timezone.utc)
        end_dt = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    if args.start:
        start_dt = parse_date(args.start)
    else:
        start_dt = end_dt - timedelta(days=args.days)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    data_root = out / "futures" / args.interval
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Binance USD-M Futures public klines",
        "interval": args.interval,
        "start_utc": start_dt.isoformat(),
        "end_utc_exclusive": end_dt.isoformat(),
        "days": (end_dt - start_dt).days,
        "symbols": symbols,
        "storage": "monthly_csv_chunks_committed_to_backtest_data_branch",
        "notes": [
            "CSV timestamps are UTC.",
            "Files are split monthly to avoid GitHub single-file size limits.",
            "Each CSV contains OHLCV plus quote volume, trade count and taker buy fields from Binance Futures klines.",
            "This data pool is for backtests; fee/slippage/spread/execution must be modeled by the backtest engine.",
        ],
        "files": [],
    }

    out.mkdir(parents=True, exist_ok=True)
    print(f"Building monthly data pool to {out}")
    print(f"Symbols={len(symbols)} interval={args.interval} range={start_dt.date()}->{end_dt.date()} exclusive")

    for s_idx, symbol in enumerate(symbols, start=1):
        for m_start, m_end in iter_month_ranges(start_dt, end_dt):
            ym = m_start.strftime("%Y-%m")
            csv_path = data_root / symbol / f"{symbol}-{args.interval}-{ym}.csv"
            print(f"[{s_idx}/{len(symbols)}] {symbol} {ym}")
            info = fetch_csv(symbol, args.interval, m_start, m_end, csv_path, args.sleep)
            rel = csv_path.relative_to(out).as_posix()
            info.update({
                "symbol": symbol,
                "interval": args.interval,
                "month": ym,
                "start_utc": m_start.isoformat(),
                "end_utc_exclusive": m_end.isoformat(),
                "file": rel,
            })
            manifest["files"].append(info)
            print(f"  rows={info['rows']} coverage={info['coverage_pct']}% file={rel}")

    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "README.md").write_text(
        "# Volkan Futures Backtest Data Pool\n\n"
        "Bu branch sadece backtest verisi içindir; panel dosyalarıyla karıştırılmamalıdır.\n\n"
        f"Aralık UTC: {start_dt.date()} -> {end_dt.date()} exclusive\n\n"
        f"Interval: `{args.interval}`\n\n"
        f"Coinler: {', '.join(symbols)}\n\n"
        "Dosyalar aylık CSV parçalarıdır: `futures/1m/SYMBOL/SYMBOL-1m-YYYY-MM.csv`.\n\n"
        "Kontrol için `manifest.json` içindeki satır ve coverage değerlerine bak.\n",
        encoding="utf-8",
    )
    print("Done")


if __name__ == "__main__":
    main()

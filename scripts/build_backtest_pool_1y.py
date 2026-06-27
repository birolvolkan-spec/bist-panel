import argparse
import csv
import json
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "backtest_pool_output"

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
    "User-Agent": "Mozilla/5.0 VolkanBacktestPool/1.0",
    "Accept": "application/json,text/plain,*/*",
}

CSV_HEADER = [
    "timestamp", "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_volume", "trade_count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore"
]


def utc_ms(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def ms_to_utc(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


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
        time.sleep(0.25)
    return [], None, last_error


def fetch_symbol(symbol, interval, start_dt, end_dt, out_dir, sleep_s):
    start_ms = utc_ms(start_dt)
    end_ms = utc_ms(end_dt)
    cursor = start_ms
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{symbol}-{interval}-{start_dt.date()}_{end_dt.date()}.csv"

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
                if len(errors) > 50:
                    break
                continue

            for r in rows:
                open_time = int(r[0])
                if open_time < start_ms or open_time >= end_ms:
                    continue
                writer.writerow([
                    ms_to_utc(open_time), open_time, r[1], r[2], r[3], r[4], r[5],
                    r[6], r[7], r[8], r[9], r[10], r[11]
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
        "symbol": symbol,
        "interval": interval,
        "file": str(csv_path.relative_to(OUT_ROOT)),
        "rows": rows_written,
        "expected_rows_1m": expected,
        "coverage_pct": round((rows_written / expected) * 100, 4) if expected else None,
        "first_timestamp": ms_to_utc(first_ts) if first_ts else None,
        "last_timestamp": ms_to_utc(last_ts) if last_ts else None,
        "batches": batches,
        "bases_used": sorted(bases_used),
        "errors_sample": errors[-5:],
    }


def zip_output(folder, zip_path):
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p != zip_path:
                z.write(p, p.relative_to(folder))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--sleep", type=float, default=0.05)
    args = ap.parse_args()

    if args.end:
        end_dt = parse_date(args.end)
    else:
        # Use today's UTC midnight so the final day is complete.
        now = datetime.now(timezone.utc)
        end_dt = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    if args.start:
        start_dt = parse_date(args.start)
    else:
        start_dt = end_dt - timedelta(days=args.days)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    tag = f"{args.interval}_{start_dt.date()}_{end_dt.date()}_{len(symbols)}symbols"
    run_dir = OUT_ROOT / tag
    data_dir = run_dir / "csv"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building pool: {len(symbols)} symbols, {args.interval}, {start_dt.date()} -> {end_dt.date()}")
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Binance USD-M Futures public klines",
        "interval": args.interval,
        "start_utc": start_dt.isoformat(),
        "end_utc_exclusive": end_dt.isoformat(),
        "days": (end_dt - start_dt).days,
        "symbols": symbols,
        "notes": [
            "CSV timestamps are UTC.",
            "end_utc_exclusive means the final timestamp is before end date 00:00 UTC.",
            "For 1m data, expected_rows_1m = days * 1440.",
            "This artifact is for realistic backtest data loading; execution assumptions must still be handled by the backtest engine."
        ],
        "files": [],
    }

    for i, symbol in enumerate(symbols, start=1):
        print(f"[{i}/{len(symbols)}] Fetching {symbol}...")
        info = fetch_symbol(symbol, args.interval, start_dt, end_dt, data_dir, args.sleep)
        print(f"  rows={info['rows']} coverage={info['coverage_pct']}%")
        manifest["files"].append(info)

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = run_dir / "README.md"
    readme.write_text(
        "# Volkan 1Y Futures Backtest Data Pool\n\n"
        f"Symbols: {', '.join(symbols)}\n\n"
        f"Interval: {args.interval}\n\n"
        f"Range UTC: {start_dt.date()} -> {end_dt.date()} exclusive\n\n"
        "Files are in `csv/`. Use `manifest.json` to check row counts and coverage.\n",
        encoding="utf-8",
    )

    zip_path = OUT_ROOT / f"volkan_futures_backtest_pool_{tag}.zip"
    zip_output(run_dir, zip_path)
    print(f"ZIP created: {zip_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()

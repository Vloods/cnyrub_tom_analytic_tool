from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .analysis import summarize_orderbook, summarize_trades
from .clusterdelta import build_cluster_delta_rows, render_cluster_delta_chart
from .dataset import build_feature_rows, build_label_rows
from .models import Trade
from .orderflow import AccumulationZone, LiquidityEvent, detect_accumulation_zones, detect_liquidity_events
from .providers import DEFAULT_SECID, FileOrderBookProvider, HttpJsonOrderBookProvider, MoexIssProvider, ProviderCapabilityError
from .storage import SnapshotStore


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _quote(args: argparse.Namespace) -> int:
    quote = MoexIssProvider().get_quote(args.secid)
    _print_json({
        "secid": quote.secid,
        "ts": quote.ts.isoformat(),
        "last": quote.last,
        "bid": quote.bid,
        "ask": quote.ask,
        "high": quote.high,
        "low": quote.low,
        "open": quote.open,
        "volume": quote.volume,
        "value": quote.value,
        "seqnum": quote.seqnum,
        "source": quote.source,
    })
    return 0


def _candles(args: argparse.Namespace) -> int:
    candles = MoexIssProvider().get_candles(args.secid, from_=args.from_date, till=args.till, interval=args.interval)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["begin", "open", "high", "low", "close", "volume", "value"])
            writer.writeheader()
            for candle in candles:
                writer.writerow({
                    "begin": candle.begin.isoformat(),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "value": candle.value,
                })
        print(f"saved {len(candles)} candles to {path}")
    else:
        _print_json([candle.__dict__ for candle in candles])
    return 0


def _trade_fieldnames() -> list[str]:
    return ["tradeno", "secid", "ts", "price", "quantity", "value", "buysell", "boardid", "source"]


def _trade_rows(trades: list[Any]) -> list[dict[str, Any]]:
    return [{
        "tradeno": trade.tradeno,
        "secid": trade.secid,
        "ts": trade.ts.isoformat(),
        "price": trade.price,
        "quantity": trade.quantity,
        "value": trade.value,
        "buysell": trade.buysell,
        "boardid": trade.boardid,
        "source": trade.source,
    } for trade in trades]


def _trades(args: argparse.Namespace) -> int:
    trades = MoexIssProvider().get_trades(args.secid, from_=args.from_date, till=args.till, limit=args.limit)
    rows = _trade_rows(trades)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=_trade_fieldnames())
            writer.writeheader()
            writer.writerows(rows)
        print(f"saved {len(rows)} anonymous trades to {path}")
    else:
        _print_json(rows)
    return 0


def _ensure_trade_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_trade_fieldnames())
        writer.writeheader()


def _existing_trade_numbers(path: Path) -> set[int]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {int(float(row["tradeno"])) for row in csv.DictReader(handle) if row.get("tradeno")}


def _append_new_trade_rows(path: Path, trades: list[Trade], seen: set[int]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_trades = [trade for trade in sorted(trades, key=lambda item: (item.ts, item.tradeno)) if trade.tradeno not in seen]
    if not new_trades:
        return 0
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_trade_fieldnames())
        if write_header:
            writer.writeheader()
        rows = _trade_rows(new_trades)
        writer.writerows(rows)
    seen.update(trade.tradeno for trade in new_trades)
    return len(new_trades)


def _record_trades(args: argparse.Namespace) -> int:
    provider = MoexIssProvider()
    path = Path(args.output)
    _ensure_trade_csv(path)
    seen = _existing_trade_numbers(path)
    deadline = None if args.seconds is None else time.monotonic() + args.seconds
    polls = 0
    while True:
        trades = provider.get_trades(args.secid, from_=args.from_date, till=args.till, limit=args.limit)
        saved = _append_new_trade_rows(path, trades, seen)
        polls += 1
        print(f"saved {saved} new anonymous trades to {path} (seen={len(seen)})")
        if args.count is not None and polls >= args.count:
            break
        if deadline is not None and time.monotonic() >= deadline:
            break
        time.sleep(args.interval)
    return 0


def _analyze_trades(args: argparse.Namespace) -> int:
    trades = MoexIssProvider().get_trades(args.secid, from_=args.from_date, till=args.till, limit=args.limit)
    summary = summarize_trades(trades)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary.keys()))
            writer.writeheader()
            writer.writerow(summary)
        print(f"saved trades analysis to {path}")
    else:
        _print_json(summary)
    return 0


def _cluster_delta(args: argparse.Namespace) -> int:
    trades = _load_trades_csv(args.trades_csv, secid=args.secid) if args.trades_csv else MoexIssProvider().get_trades(
        args.secid,
        from_=args.from_date,
        till=args.till,
        limit=args.limit,
    )
    rows = build_cluster_delta_rows(trades, bucket_minutes=args.bucket_minutes, price_step=args.price_step)
    if args.output:
        _write_csv(args.output, rows, fallback_fieldnames=[
            "bucket_start", "bucket_end", "secid", "price", "buy_qty", "sell_qty", "delta", "volume", "trade_count",
        ])
        print(f"saved {len(rows)} cluster delta rows to {args.output}")
    print(render_cluster_delta_chart(rows, bucket_minutes=args.bucket_minutes))
    return 0


def _provider_from_args(args: argparse.Namespace) -> HttpJsonOrderBookProvider | FileOrderBookProvider:
    path = getattr(args, "orderbook_path", None) or os.environ.get("CNYRUB_ORDERBOOK_PATH")
    if path:
        return FileOrderBookProvider(path)
    url = args.orderbook_url or os.environ.get("CNYRUB_ORDERBOOK_URL")
    if not url:
        raise ProviderCapabilityError(
            "Для полного стакана нужен локальный JSON файл QUIK (--orderbook-path/CNYRUB_ORDERBOOK_PATH) "
            "или JSON endpoint брокера/фида (--orderbook-url/CNYRUB_ORDERBOOK_URL). "
            "Публичный MOEX ISS дает котировки/свечи, но не полный стакан."
        )
    return HttpJsonOrderBookProvider(url)


def _orderbook_once(args: argparse.Namespace) -> int:
    book = _provider_from_args(args).get_orderbook(args.secid)
    _print_json({
        "summary": summarize_orderbook(book, levels=args.levels),
        "bids": [[level.price, level.quantity] for level in book.bids[:args.depth]],
        "asks": [[level.price, level.quantity] for level in book.asks[:args.depth]],
    })
    return 0


def _record_orderbook(args: argparse.Namespace) -> int:
    provider = _provider_from_args(args)
    store = SnapshotStore(args.db)
    deadline = None if args.seconds is None else time.monotonic() + args.seconds
    saved = 0
    while True:
        book = provider.get_orderbook(args.secid)
        snapshot_id = store.save_orderbook(book)
        saved += 1
        print(f"saved snapshot id={snapshot_id} ts={book.ts.isoformat()} bids={len(book.bids)} asks={len(book.asks)}")
        if args.count is not None and saved >= args.count:
            break
        if deadline is not None and time.monotonic() >= deadline:
            break
        time.sleep(args.interval)
    return 0


def _export_orderbook(args: argparse.Namespace) -> int:
    count = SnapshotStore(args.db).export_jsonl(args.output, secid=args.secid)
    print(f"exported {count} snapshots to {args.output}")
    return 0


def _analyze_orderbook(args: argparse.Namespace) -> int:
    store = SnapshotStore(args.db)
    rows = [summarize_orderbook(book, levels=args.levels) for book in store.iter_orderbooks(secid=args.secid)]
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["secid"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"saved {len(rows)} analysis rows to {path}")
    else:
        _print_json(rows)
    return 0


def _accumulation_fieldnames() -> list[str]:
    return [
        "kind",
        "start_ts",
        "end_ts",
        "secid",
        "snapshots",
        "mid_low",
        "mid_high",
        "mid_range",
        "avg_mid",
        "avg_spread",
        "avg_bid_qty",
        "avg_ask_qty",
        "avg_total_depth",
        "avg_imbalance",
        "confidence",
        "reason",
    ]


def _accumulation_rows(zones: list[AccumulationZone]) -> list[dict[str, Any]]:
    return [{field: zone.to_row()[field] for field in _accumulation_fieldnames()} for zone in zones]


def _detect_accumulation(args: argparse.Namespace) -> int:
    books = list(SnapshotStore(args.db).iter_orderbooks(secid=args.secid))
    zones = detect_accumulation_zones(
        books,
        levels=args.levels,
        window=args.window,
        min_snapshots=args.min_snapshots,
        max_mid_range=args.max_mid_range,
        min_total_depth=args.min_total_depth,
        imbalance_threshold=args.imbalance_threshold,
    )
    rows = _accumulation_rows(zones)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=_accumulation_fieldnames())
            writer.writeheader()
            writer.writerows(rows)
        print(f"saved {len(rows)} accumulation zones to {path}")
    else:
        _print_json(rows)
    return 0


def _liquidity_fieldnames() -> list[str]:
    return [
        "kind",
        "start_ts",
        "end_ts",
        "secid",
        "side",
        "price",
        "trade_qty",
        "trades",
        "visible_qty_before",
        "visible_qty_after",
        "recovery_ratio",
        "trade_to_visible_ratio",
        "confidence",
        "reason",
    ]


def _liquidity_rows(events: list[LiquidityEvent]) -> list[dict[str, Any]]:
    return [{field: event.to_row()[field] for field in _liquidity_fieldnames()} for event in events]


def _load_trades_csv(path: str | Path, secid: str | None = None) -> list[Trade]:
    trades: list[Trade] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            trade_secid = row.get("secid") or row.get("SECID") or secid or DEFAULT_SECID
            if secid and trade_secid != secid:
                continue
            trades.append(Trade(
                tradeno=int(float(row.get("tradeno") or row.get("TRADENO") or len(trades) + 1)),
                secid=trade_secid,
                ts=datetime.fromisoformat(row.get("ts") or row.get("TRADETIME") or row.get("tradetime") or ""),
                price=float(row.get("price") or row.get("PRICE") or 0),
                quantity=float(row.get("quantity") or row.get("QUANTITY") or 0),
                value=float(row.get("value") or row.get("VALUE") or 0),
                buysell=row.get("buysell") or row.get("BUYSELL"),
                boardid=row.get("boardid") or row.get("BOARDID"),
                source=row.get("source") or "csv-trades",
            ))
    return trades


def _detect_liquidity_events(args: argparse.Namespace) -> int:
    books = list(SnapshotStore(args.db).iter_orderbooks(secid=args.secid))
    trades = _load_trades_csv(args.trades_csv, secid=args.secid)
    events = detect_liquidity_events(
        books,
        trades,
        window_seconds=args.window_seconds,
        min_trade_qty=args.min_trade_qty,
        min_recovery_ratio=args.min_recovery_ratio,
        iceberg_trade_to_visible_ratio=args.iceberg_trade_to_visible_ratio,
        price_tolerance=args.price_tolerance,
    )
    rows = _liquidity_rows(events)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=_liquidity_fieldnames())
            writer.writeheader()
            writer.writerows(rows)
        print(f"saved {len(rows)} liquidity events to {path}")
    else:
        _print_json(rows)
    return 0


def _write_csv(path_value: str | Path, rows: list[dict[str, Any]], *, fallback_fieldnames: list[str]) -> None:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else fallback_fieldnames
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _parse_levels(value: str) -> tuple[int, ...]:
    levels = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not levels:
        raise argparse.ArgumentTypeError("levels must contain at least one integer")
    return levels


def _export_features(args: argparse.Namespace) -> int:
    books = list(SnapshotStore(args.db).iter_orderbooks(secid=args.secid))
    rows = build_feature_rows(books, levels=args.levels)
    _write_csv(args.output, rows, fallback_fieldnames=["secid", "ts"])
    print(f"saved {len(rows)} feature rows to {args.output}")
    return 0


def _export_labels(args: argparse.Namespace) -> int:
    books = list(SnapshotStore(args.db).iter_orderbooks(secid=args.secid))
    rows = build_label_rows(books, horizon_seconds=args.horizon_seconds, flat_threshold=args.flat_threshold)
    _write_csv(args.output, rows, fallback_fieldnames=["secid", "ts", "horizon_sec", "label"])
    print(f"saved {len(rows)} label rows to {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cnyrub", description="CNYRUB_TOM quotes, candles, full orderbook snapshots and analysis")
    parser.add_argument("--secid", default=DEFAULT_SECID)
    sub = parser.add_subparsers(dest="command", required=True)

    quote = sub.add_parser("quote", help="Get current MOEX ISS quote/top-of-book fields")
    quote.set_defaults(func=_quote)

    candles = sub.add_parser("candles", help="Download MOEX historical candles")
    candles.add_argument("--from", dest="from_date", help="YYYY-MM-DD")
    candles.add_argument("--till", help="YYYY-MM-DD")
    candles.add_argument("--interval", type=int, default=1, help="MOEX interval: 1=minute, 10=10m, 60=hour, 24=day")
    candles.add_argument("--output", help="CSV output path")
    candles.set_defaults(func=_candles)

    trades = sub.add_parser("trades", help="Download MOEX anonymous trades")
    trades.add_argument("--from", dest="from_date", help="YYYY-MM-DD")
    trades.add_argument("--till", help="YYYY-MM-DD")
    trades.add_argument("--limit", type=int, default=100)
    trades.add_argument("--output", help="CSV output path")
    trades.set_defaults(func=_trades)

    record_trades = sub.add_parser("record-trades", help="Poll MOEX anonymous trades and append only new trades to CSV")
    record_trades.add_argument("--from", dest="from_date", help="YYYY-MM-DD")
    record_trades.add_argument("--till", help="YYYY-MM-DD")
    record_trades.add_argument("--limit", type=int, default=1000, help="Trades requested on each poll")
    record_trades.add_argument("--output", required=True, help="Append-only CSV output path")
    record_trades.add_argument("--interval", type=float, default=0.001, help="Polling interval in seconds")
    record_trades.add_argument("--count", type=int, help="Number of polling iterations")
    record_trades.add_argument("--seconds", type=float, help="Stop after this many seconds")
    record_trades.set_defaults(func=_record_trades)

    trades_ana = sub.add_parser("analyze-trades", help="Compute VWAP/volume/side imbalance from MOEX anonymous trades")
    trades_ana.add_argument("--from", dest="from_date", help="YYYY-MM-DD")
    trades_ana.add_argument("--till", help="YYYY-MM-DD")
    trades_ana.add_argument("--limit", type=int, default=100)
    trades_ana.add_argument("--output", help="CSV output path")
    trades_ana.set_defaults(func=_analyze_trades)

    cluster = sub.add_parser("cluster-delta", help="Build 3-minute cluster delta/footprint rows from trades")
    cluster.add_argument("--trades-csv", help="CSV with trades; if omitted, downloads MOEX anonymous trades")
    cluster.add_argument("--from", dest="from_date", help="YYYY-MM-DD when downloading MOEX trades")
    cluster.add_argument("--till", help="YYYY-MM-DD when downloading MOEX trades")
    cluster.add_argument("--limit", type=int, default=1000, help="MOEX trade limit when --trades-csv is omitted")
    cluster.add_argument("--bucket-minutes", type=int, default=3, help="Cluster time bucket in minutes")
    cluster.add_argument("--price-step", type=float, help="Optional price grouping step, e.g. 0.001 or 0.01")
    cluster.add_argument("--output", help="CSV output path")
    cluster.set_defaults(func=_cluster_delta)

    ob = sub.add_parser("orderbook", help="Fetch one full-orderbook snapshot from QUIK JSON file or broker/feed JSON endpoint")
    ob.add_argument("--orderbook-url")
    ob.add_argument("--orderbook-path", help="Path to JSON file exported by local QUIK/QLua")
    ob.add_argument("--levels", type=int, default=10)
    ob.add_argument("--depth", type=int, default=20)
    ob.set_defaults(func=_orderbook_once)

    rec = sub.add_parser("record-orderbook", help="Poll full orderbook and store snapshots into SQLite")
    rec.add_argument("--orderbook-url")
    rec.add_argument("--orderbook-path", help="Path to JSON file exported by local QUIK/QLua")
    rec.add_argument("--db", default="data/orderbook_snapshots.sqlite")
    rec.add_argument("--interval", type=float, default=1.0)
    rec.add_argument("--count", type=int)
    rec.add_argument("--seconds", type=float)
    rec.set_defaults(func=_record_orderbook)

    exp = sub.add_parser("export-orderbook", help="Export recorded SQLite snapshots to JSONL")
    exp.add_argument("--db", default="data/orderbook_snapshots.sqlite")
    exp.add_argument("--output", required=True)
    exp.set_defaults(func=_export_orderbook)

    ana = sub.add_parser("analyze-orderbook", help="Compute spread/mid/imbalance series from recorded snapshots")
    ana.add_argument("--db", default="data/orderbook_snapshots.sqlite")
    ana.add_argument("--levels", type=int, default=10)
    ana.add_argument("--output", help="CSV output path")
    ana.set_defaults(func=_analyze_orderbook)

    accum = sub.add_parser("detect-accumulation", help="Detect narrow-range high-depth accumulation zones from recorded orderbook snapshots")
    accum.add_argument("--db", default="data/orderbook_snapshots.sqlite")
    accum.add_argument("--levels", type=int, default=10, help="Orderbook depth levels used for depth/imbalance metrics")
    accum.add_argument("--window", type=int, default=20, help="Maximum snapshots per detection window")
    accum.add_argument("--min-snapshots", type=int, default=5, help="Minimum snapshots required for a zone")
    accum.add_argument("--max-mid-range", type=float, default=0.002, help="Maximum mid-price range inside a zone")
    accum.add_argument("--min-total-depth", type=float, default=1000, help="Minimum average bid+ask depth over selected levels")
    accum.add_argument("--imbalance-threshold", type=float, default=0.25, help="Side imbalance threshold for buy/sell accumulation labels")
    accum.add_argument("--output", help="CSV output path")
    accum.set_defaults(func=_detect_accumulation)

    liq = sub.add_parser("detect-liquidity-events", help="Detect bid/ask absorption and iceberg candidates from trades plus orderbook recovery")
    liq.add_argument("--db", default="data/orderbook_snapshots.sqlite")
    liq.add_argument("--trades-csv", required=True, help="CSV with anonymous trades: tradeno,secid,ts,price,quantity,value,buysell")
    liq.add_argument("--window-seconds", type=float, default=20, help="Orderbook/trade matching window in seconds")
    liq.add_argument("--min-trade-qty", type=float, default=100, help="Minimum aggressive trade quantity at one best-price level")
    liq.add_argument("--min-recovery-ratio", type=float, default=0.8, help="Minimum visible size after/before ratio for replenishment")
    liq.add_argument("--iceberg-trade-to-visible-ratio", type=float, default=1.5, help="Trade/visible-size ratio required for iceberg candidates")
    liq.add_argument("--price-tolerance", type=float, default=1e-9, help="Float tolerance for matching trade price to best bid/ask")
    liq.add_argument("--output", help="CSV output path")
    liq.set_defaults(func=_detect_liquidity_events)

    features = sub.add_parser("export-features", help="Export ML-ready orderbook feature rows from recorded snapshots")
    features.add_argument("--db", default="data/orderbook_snapshots.sqlite")
    features.add_argument("--levels", type=_parse_levels, default=(1, 5, 10), help="Comma-separated depth levels, e.g. 1,5,10")
    features.add_argument("--output", required=True, help="CSV output path")
    features.set_defaults(func=_export_features)

    labels = sub.add_parser("export-labels", help="Export future mid-price direction labels for ML training")
    labels.add_argument("--db", default="data/orderbook_snapshots.sqlite")
    labels.add_argument("--horizon-seconds", type=int, default=5)
    labels.add_argument("--flat-threshold", type=float, default=0.0)
    labels.add_argument("--output", required=True, help="CSV output path")
    labels.set_defaults(func=_export_labels)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ProviderCapabilityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

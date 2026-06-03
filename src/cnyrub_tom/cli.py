from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .analysis import summarize_orderbook, summarize_trades
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
            fieldnames = ["tradeno", "secid", "ts", "price", "quantity", "value", "buysell", "boardid", "source"]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"saved {len(rows)} anonymous trades to {path}")
    else:
        _print_json(rows)
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

    trades_ana = sub.add_parser("analyze-trades", help="Compute VWAP/volume/side imbalance from MOEX anonymous trades")
    trades_ana.add_argument("--from", dest="from_date", help="YYYY-MM-DD")
    trades_ana.add_argument("--till", help="YYYY-MM-DD")
    trades_ana.add_argument("--limit", type=int, default=100)
    trades_ana.add_argument("--output", help="CSV output path")
    trades_ana.set_defaults(func=_analyze_trades)

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

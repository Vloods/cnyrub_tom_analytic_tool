from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .models import OrderBook, OrderLevel


class SnapshotStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("pragma foreign_keys = on")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists orderbook_snapshots (
                    id integer primary key autoincrement,
                    secid text not null,
                    ts text not null,
                    source text not null
                );
                create table if not exists orderbook_levels (
                    snapshot_id integer not null references orderbook_snapshots(id) on delete cascade,
                    side text not null check (side in ('bid', 'ask')),
                    position integer not null,
                    price real not null,
                    quantity real not null,
                    primary key (snapshot_id, side, position)
                );
                create index if not exists idx_orderbook_snapshots_secid_ts
                    on orderbook_snapshots(secid, ts);
                """
            )

    def save_orderbook(self, book: OrderBook) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "insert into orderbook_snapshots(secid, ts, source) values (?, ?, ?)",
                (book.secid, book.ts.isoformat(), book.source),
            )
            snapshot_id = int(cursor.lastrowid)
            rows = []
            for side, levels in (("bid", book.bids), ("ask", book.asks)):
                for position, level in enumerate(levels, start=1):
                    rows.append((snapshot_id, side, position, level.price, level.quantity))
            conn.executemany(
                "insert into orderbook_levels(snapshot_id, side, position, price, quantity) values (?, ?, ?, ?, ?)",
                rows,
            )
            return snapshot_id

    def iter_orderbooks(self, secid: str | None = None) -> Iterator[OrderBook]:
        query = "select id, secid, ts, source from orderbook_snapshots"
        params: tuple[str, ...] = ()
        if secid:
            query += " where secid = ?"
            params = (secid,)
        query += " order by ts, id"
        with self._connect() as conn:
            for snapshot_id, item_secid, ts, source in conn.execute(query, params):
                levels = conn.execute(
                    "select side, price, quantity from orderbook_levels where snapshot_id = ? order by side, position",
                    (snapshot_id,),
                ).fetchall()
                bids = [OrderLevel(price=price, quantity=quantity) for side, price, quantity in levels if side == "bid"]
                asks = [OrderLevel(price=price, quantity=quantity) for side, price, quantity in levels if side == "ask"]
                yield OrderBook(secid=item_secid, ts=datetime.fromisoformat(ts), bids=bids, asks=asks, source=source)

    def export_jsonl(self, output: str | Path, secid: str | None = None) -> int:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with output.open("w", encoding="utf-8") as handle:
            for book in self.iter_orderbooks(secid=secid):
                handle.write(json.dumps({
                    "secid": book.secid,
                    "ts": book.ts.isoformat(),
                    "source": book.source,
                    "bids": [[level.price, level.quantity] for level in book.bids],
                    "asks": [[level.price, level.quantity] for level in book.asks],
                }, ensure_ascii=False) + "\n")
                count += 1
        return count

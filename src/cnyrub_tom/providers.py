from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .models import Candle, OrderBook, OrderLevel, Quote, Trade, now_utc

DEFAULT_SECID = "CNYRUB_TOM"
MOEX_BASE = "https://iss.moex.com/iss"


class ProviderCapabilityError(RuntimeError):
    pass


class HttpClient(Protocol):
    def get_json(self, url: str) -> dict[str, Any]: ...


class UrllibHttpClient:
    def get_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "cnyrub-tom-analytic-tool/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read().decode(charset)
        return json.loads(payload)


def _row_dict(block: dict[str, Any], row_index: int = 0) -> dict[str, Any]:
    rows = block.get("data") or []
    if not rows:
        return {}
    return dict(zip(block.get("columns") or [], rows[row_index], strict=False))


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _parse_ts(value: Any | None = None) -> datetime:
    if not value:
        return now_utc()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        # MOEX marketdata often exposes only TIME/UPDATETIME. Attach today's UTC date.
        parsed_time = datetime.strptime(text, "%H:%M:%S").time()
        parsed = datetime.combine(date.today(), parsed_time, tzinfo=timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_moex_marketdata(payload: dict[str, Any], secid: str = DEFAULT_SECID) -> Quote:
    row = _row_dict(payload.get("marketdata", {}))
    if not row:
        raise ValueError("MOEX response does not contain marketdata rows")
    ts = _parse_ts(row.get("UPDATETIME") or row.get("TIME"))
    return Quote(
        secid=str(row.get("SECID") or secid),
        ts=ts,
        last=_as_float(row.get("LAST")),
        bid=_as_float(row.get("BID") or row.get("HIGHBID")),
        ask=_as_float(row.get("OFFER") or row.get("LOWOFFER")),
        high=_as_float(row.get("HIGH")),
        low=_as_float(row.get("LOW")),
        open=_as_float(row.get("OPEN")),
        volume=_as_float(row.get("VOLTODAY")),
        value=_as_float(row.get("VALTODAY") or row.get("VALUE")),
        seqnum=_as_int(row.get("SEQNUM")),
        raw=row,
    )


def parse_moex_trades(payload: dict[str, Any], secid: str = DEFAULT_SECID) -> list[Trade]:
    block = payload.get("trades", {})
    columns = block.get("columns") or []
    trades: list[Trade] = []
    for row in block.get("data") or []:
        item = dict(zip(columns, row, strict=False))
        trades.append(Trade(
            tradeno=int(item["TRADENO"]),
            secid=str(item.get("SECID") or secid),
            ts=_parse_ts(item.get("SYSTIME") or item.get("TRADETIME")),
            price=float(item["PRICE"]),
            quantity=float(item.get("QUANTITY") or 0),
            value=float(item.get("VALUE") or 0),
            buysell=str(item["BUYSELL"]) if item.get("BUYSELL") not in (None, "") else None,
            boardid=str(item["BOARDID"]) if item.get("BOARDID") not in (None, "") else None,
        ))
    return trades


class MoexIssProvider:
    """Public MOEX ISS provider for quotes and candle/trade history.

    Public ISS exposes marketdata, candles, and trades. Full level-2/level-3 historical
    order books are not exposed by the free ISS endpoint; use HttpJsonOrderBookProvider
    with a broker/feed URL to record full realtime snapshots locally.
    """

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or UrllibHttpClient()

    def get_quote(self, secid: str = DEFAULT_SECID) -> Quote:
        path = f"{MOEX_BASE}/engines/currency/markets/selt/securities/{urllib.parse.quote(secid)}.json"
        query = urllib.parse.urlencode({"iss.meta": "off", "iss.only": "marketdata,securities"})
        return parse_moex_marketdata(self.http.get_json(f"{path}?{query}"), secid=secid)

    def get_candles(self, secid: str = DEFAULT_SECID, from_: str | None = None, till: str | None = None, interval: int = 1) -> list[Candle]:
        path = f"{MOEX_BASE}/engines/currency/markets/selt/securities/{urllib.parse.quote(secid)}/candles.json"
        params: dict[str, str | int] = {"iss.meta": "off", "interval": interval}
        if from_:
            params["from"] = from_
        if till:
            params["till"] = till
        payload = self.http.get_json(f"{path}?{urllib.parse.urlencode(params)}")
        block = payload.get("candles", {})
        columns = block.get("columns") or []
        candles: list[Candle] = []
        for row in block.get("data") or []:
            item = dict(zip(columns, row, strict=False))
            candles.append(Candle(
                begin=_parse_ts(item.get("begin")),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item.get("volume") or 0),
                value=_as_float(item.get("value")),
            ))
        return candles

    def get_trades(self, secid: str = DEFAULT_SECID, from_: str | None = None, till: str | None = None, limit: int = 100) -> list[Trade]:
        path = f"{MOEX_BASE}/engines/currency/markets/selt/securities/{urllib.parse.quote(secid)}/trades.json"
        params: dict[str, str | int] = {"iss.meta": "off", "limit": limit}
        if from_:
            params["from"] = from_
        if till:
            params["till"] = till
        payload = self.http.get_json(f"{path}?{urllib.parse.urlencode(params)}")
        return parse_moex_trades(payload, secid=secid)

    def get_orderbook(self, secid: str = DEFAULT_SECID) -> OrderBook:
        raise ProviderCapabilityError(
            "MOEX ISS public API does not provide full CNYRUB_TOM order book snapshots. "
            "Use --orderbook-url with a broker/feed JSON endpoint and record snapshots locally."
        )


def _parse_level(raw: Any) -> OrderLevel:
    if isinstance(raw, dict):
        price = raw.get("price") or raw.get("p")
        quantity = raw.get("quantity") or raw.get("qty") or raw.get("volume") or raw.get("q")
    else:
        price, quantity = raw[0], raw[1]
    return OrderLevel(price=float(price), quantity=float(quantity))


class HttpJsonOrderBookProvider:
    """Generic full-orderbook adapter for broker/feed HTTP JSON endpoints.

    Accepted payload shape:
        {"ts": "2026-01-02T10:30:00+00:00", "bids": [[price, qty], ...], "asks": [{"price": ..., "quantity": ...}, ...]}
    """

    def __init__(self, url: str, http: HttpClient | None = None) -> None:
        self.url = url
        self.http = http or UrllibHttpClient()

    def get_orderbook(self, secid: str = DEFAULT_SECID) -> OrderBook:
        payload = self.http.get_json(self.url)
        return orderbook_from_json_payload(payload, secid=secid, source="http-json")


def orderbook_from_json_payload(payload: dict[str, Any], secid: str = DEFAULT_SECID, source: str = "json") -> OrderBook:
    bids_raw = payload.get("bids") if "bids" in payload else payload.get("bid", [])
    asks_raw = payload.get("asks") if "asks" in payload else (payload.get("ask") if "ask" in payload else payload.get("offer", []))
    return OrderBook(
        secid=str(payload.get("secid") or payload.get("sec_code") or secid),
        ts=_parse_ts(payload.get("ts") or payload.get("timestamp") or payload.get("time")),
        bids=[_parse_level(level) for level in bids_raw or []],
        asks=[_parse_level(level) for level in asks_raw or []],
        source=source,
    )


class FileOrderBookProvider:
    """Read latest full-orderbook snapshot from a local JSON file.

    This is the recommended bridge for local Windows QUIK: QLua writes the current
    getQuoteLevel2() result to JSON on every interval, while this provider polls
    the file and stores snapshots into SQLite.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get_orderbook(self, secid: str = DEFAULT_SECID) -> OrderBook:
        with self.path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        return orderbook_from_json_payload(payload, secid=secid, source="file-json")

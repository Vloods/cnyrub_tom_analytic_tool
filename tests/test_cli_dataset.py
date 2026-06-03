from datetime import datetime, timedelta, timezone

from cnyrub_tom import cli
from cnyrub_tom.models import OrderBook, OrderLevel
from cnyrub_tom.storage import SnapshotStore


def _book(ts: datetime, bid: float, ask: float) -> OrderBook:
    return OrderBook(
        secid="CNYRUB_TOM",
        ts=ts,
        bids=[OrderLevel(bid, 1000)],
        asks=[OrderLevel(ask, 800)],
        source="test",
    )


def test_export_features_command_writes_ml_feature_csv(tmp_path, capsys):
    db_path = tmp_path / "snapshots.sqlite"
    output = tmp_path / "features.csv"
    store = SnapshotStore(db_path)
    base = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
    store.save_orderbook(_book(base, 12.34, 12.35))
    store.save_orderbook(_book(base + timedelta(seconds=1), 12.341, 12.351))

    result = cli.main(["export-features", "--db", str(db_path), "--output", str(output), "--levels", "1,2"])

    assert result == 0
    assert "saved 2 feature rows" in capsys.readouterr().out
    text = output.read_text(encoding="utf-8")
    assert "bid_depth_1" in text
    assert "imbalance_2" in text


def test_export_labels_command_writes_future_direction_csv(tmp_path, capsys):
    db_path = tmp_path / "snapshots.sqlite"
    output = tmp_path / "labels.csv"
    store = SnapshotStore(db_path)
    base = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
    store.save_orderbook(_book(base, 12.34, 12.35))
    store.save_orderbook(_book(base + timedelta(seconds=5), 12.345, 12.355))

    result = cli.main(["export-labels", "--db", str(db_path), "--output", str(output), "--horizon-seconds", "5"])

    assert result == 0
    assert "saved 1 label rows" in capsys.readouterr().out
    text = output.read_text(encoding="utf-8")
    assert "future_return" in text
    assert "up" in text

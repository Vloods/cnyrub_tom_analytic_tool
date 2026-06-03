from cnyrub_tom.gui import build_cli_command, command_to_text, default_paths


def test_default_paths_are_windows_friendly():
    paths = default_paths()

    assert paths.orderbook_path.endswith("cnyrub_tom_orderbook.json")
    assert paths.db_path.endswith("cnyrub_tom_orderbook.sqlite")
    assert paths.analysis_csv.endswith("cnyrub_tom_analysis.csv")


def test_build_cli_command_for_orderbook_includes_quik_file_levels_and_depth():
    command = build_cli_command(
        "orderbook",
        secid="CNYRUB_TOM",
        orderbook_path="C:\\quik_export\\cnyrub_tom_orderbook.json",
        levels=10,
        depth=20,
    )

    assert command == [
        "cnyrub",
        "--secid",
        "CNYRUB_TOM",
        "orderbook",
        "--orderbook-path",
        "C:\\quik_export\\cnyrub_tom_orderbook.json",
        "--levels",
        "10",
        "--depth",
        "20",
    ]


def test_build_cli_command_for_record_orderbook_omits_empty_limits():
    command = build_cli_command(
        "record-orderbook",
        orderbook_path="C:\\quik_export\\cnyrub_tom_orderbook.json",
        db_path="C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        interval=0.25,
        count=None,
        seconds=None,
    )

    assert "--count" not in command
    assert "--seconds" not in command
    assert command_to_text(command) == 'cnyrub record-orderbook --orderbook-path C:\\quik_export\\cnyrub_tom_orderbook.json --db C:\\quik_export\\cnyrub_tom_orderbook.sqlite --interval 0.25'


def test_build_cli_command_for_analyze_trades_supports_csv_output():
    command = build_cli_command(
        "analyze-trades",
        from_date="2026-06-03",
        till="2026-06-03",
        limit=1000,
        output="data/trades_analysis.csv",
    )

    assert command == [
        "cnyrub",
        "analyze-trades",
        "--from",
        "2026-06-03",
        "--till",
        "2026-06-03",
        "--limit",
        "1000",
        "--output",
        "data/trades_analysis.csv",
    ]


def test_build_cli_command_for_detect_accumulation():
    command = build_cli_command(
        "detect-accumulation",
        db_path="C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        output="C:\\quik_export\\accumulation_zones.csv",
        levels=10,
        window=20,
        max_mid_range=0.002,
        min_total_depth=1000,
    )

    assert command == [
        "cnyrub",
        "detect-accumulation",
        "--db",
        "C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        "--levels",
        "10",
        "--window",
        "20",
        "--max-mid-range",
        "0.002",
        "--min-total-depth",
        "1000",
        "--output",
        "C:\\quik_export\\accumulation_zones.csv",
    ]


def test_build_cli_command_for_detect_liquidity_events():
    command = build_cli_command(
        "detect-liquidity-events",
        db_path="C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        trades_csv="C:\\quik_export\\cnyrub_tom_trades.csv",
        output="C:\\quik_export\\liquidity_events.csv",
        window_seconds=20,
        min_trade_qty=150,
        min_recovery_ratio=0.8,
        iceberg_trade_to_visible_ratio=1.5,
    )

    assert command == [
        "cnyrub",
        "detect-liquidity-events",
        "--db",
        "C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        "--trades-csv",
        "C:\\quik_export\\cnyrub_tom_trades.csv",
        "--window-seconds",
        "20",
        "--min-trade-qty",
        "150",
        "--min-recovery-ratio",
        "0.8",
        "--iceberg-trade-to-visible-ratio",
        "1.5",
        "--output",
        "C:\\quik_export\\liquidity_events.csv",
    ]

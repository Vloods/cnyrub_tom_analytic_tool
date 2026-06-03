# cnyrub_tom_analytic_tool

Инструмент для CNYRUB_TOM:

- текущая котировка/top-of-book из публичного MOEX ISS;
- исторические свечи MOEX ISS в CSV;
- запись полного стакана в SQLite из локального QUIK/QLua JSON-файла или внешнего JSON endpoint брокера/фида;
- экспорт записанных стаканов в JSONL;
- анализ записанного стакана: best bid/ask, spread, mid, bid/ask depth, imbalance.

Важное ограничение: публичный MOEX ISS не отдает полный level-2/level-3 стакан и исторический полный стакан. Поэтому модуль истории полного стакана построен как локальная запись realtime snapshots из брокерского/рыночного фида. Для локального QUIK на Windows используйте `--orderbook-path` и QLua-скрипт из `scripts/quik_cnyrub_tom_orderbook_export.lua`. Для HTTP-фида используйте `--orderbook-url` или переменную `CNYRUB_ORDERBOOK_URL`.

## Установка

```bash
python -m pip install -e .
```

## Котировка CNYRUB_TOM

```bash
cnyrub quote
```

## Исторические свечи

```bash
cnyrub candles --from 2026-06-03 --till 2026-06-03 --interval 60 --output data/candles_2026-06-03.csv
```

Интервалы MOEX: `1` — минута, `10` — 10 минут, `60` — час, `24` — день.

## Полный стакан: ожидаемый формат JSON endpoint

```json
{
  "ts": "2026-06-03T19:30:00+00:00",
  "bids": [[10.85, 1000000], [10.84, 500000]],
  "asks": [[10.86, 750000], [10.87, 300000]]
}
```

Также поддерживаются уровни вида `{"price": 10.86, "quantity": 750000}`.

## QUIK на Windows: получение полного стакана

Для локального QUIK самый простой и надежный мост без сокетов: QLua-скрипт в QUIK каждые 250 мс пишет текущий стакан `getQuoteLevel2("CETS", "CNYRUB_TOM")` в JSON-файл, а `cnyrub` на этом же Windows-компьютере читает файл и сохраняет snapshots в SQLite.

Файл QLua-скрипта:

```text
scripts/quik_cnyrub_tom_orderbook_export.lua
```

По умолчанию он пишет сюда:

```text
C:\quik_export\cnyrub_tom_orderbook.json
```

В QUIK:

1. Откройте `Сервисы -> Lua скрипты`.
2. Нажмите `Добавить`.
3. Выберите `scripts\quik_cnyrub_tom_orderbook_export.lua`.
4. Запустите скрипт.
5. Проверьте, что появился файл `C:\quik_export\cnyrub_tom_orderbook.json`.

На Windows в папке проекта установите CLI:

```powershell
py -m pip install -e .
```

Разово посмотреть стакан из QUIK-файла:

```powershell
cnyrub orderbook --orderbook-path C:\quik_export\cnyrub_tom_orderbook.json --levels 10 --depth 20
```

Писать историю стакана в SQLite:

```powershell
cnyrub record-orderbook `
  --orderbook-path C:\quik_export\cnyrub_tom_orderbook.json `
  --db C:\quik_export\cnyrub_tom_orderbook.sqlite `
  --interval 0.25
```

Анализ истории:

```powershell
cnyrub analyze-orderbook `
  --db C:\quik_export\cnyrub_tom_orderbook.sqlite `
  --levels 10 `
  --output C:\quik_export\cnyrub_tom_analysis.csv
```

Экспорт полной истории стакана:

```powershell
cnyrub export-orderbook `
  --db C:\quik_export\cnyrub_tom_orderbook.sqlite `
  --output C:\quik_export\cnyrub_tom_orderbook.jsonl
```

Важно: `quantity` из QUIK — в лотах. Для CNYRUB_TOM MOEX показывает LOTSIZE 1000 CNY, поэтому при необходимости объем в CNY = `quantity * 1000`.

## Разовый снимок стакана

```bash
cnyrub orderbook --orderbook-url "https://broker.example/api/cnyrub_tom/book" --levels 10 --depth 20
```

## Запись realtime стакана в SQLite

```bash
cnyrub record-orderbook \
  --orderbook-url "https://broker.example/api/cnyrub_tom/book" \
  --db data/orderbook_snapshots.sqlite \
  --interval 1 \
  --seconds 3600
```

Или ограничить числом снимков:

```bash
cnyrub record-orderbook --orderbook-url "$CNYRUB_ORDERBOOK_URL" --count 100
```

## Анализ записанной истории стакана

```bash
cnyrub analyze-orderbook --db data/orderbook_snapshots.sqlite --levels 10 --output data/orderbook_analysis.csv
```

## Экспорт полной истории стакана

```bash
cnyrub export-orderbook --db data/orderbook_snapshots.sqlite --output data/orderbook.jsonl
```

## Локальная проверка без брокера

```bash
URL="file://$PWD/examples/orderbook_sample.json"
cnyrub orderbook --orderbook-url "$URL"
cnyrub record-orderbook --orderbook-url "$URL" --db data/test_orderbook.sqlite --count 2
cnyrub analyze-orderbook --db data/test_orderbook.sqlite --output data/test_orderbook_analysis.csv
```

## Тесты

```bash
python -m pytest -q
```

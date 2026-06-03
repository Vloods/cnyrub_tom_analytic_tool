# CNYRUB_TOM Analytics Tool

CLI-инструмент для котировок, свечей, записи полного стакана и анализа истории по инструменту `CNYRUB_TOM`.

Основной практический сценарий: QUIK на Windows получает стакан от брокера, QLua-скрипт выгружает его в JSON-файл, а `cnyrub` читает этот файл, сохраняет realtime snapshots в SQLite и строит аналитику по истории.

---

## Что умеет

- Получать текущую котировку и top-of-book поля из публичного MOEX ISS.
- Скачивать исторические свечи MOEX ISS в CSV.
- Получать обезличенные сделки MOEX ISS и считать по ним VWAP/объем/агрессорный imbalance.
- Запускать удобный desktop GUI без внешних зависимостей через `cnyrub-gui`.
- Читать полный стакан из:
  - локального JSON-файла, который пишет QUIK/QLua;
  - внешнего HTTP/JSON endpoint брокера или рыночного фида.
- Записывать realtime snapshots полного стакана в SQLite.
- Анализировать записанную историю стакана:
  - best bid;
  - best ask;
  - spread;
  - mid price;
  - bid/ask depth;
  - imbalance.
- Экспортировать полную историю стакана в JSONL.

---

## Важное ограничение по MOEX ISS

Публичный MOEX ISS подходит для котировок и свечей, но не отдает полный исторический level-2/level-3 стакан.

Поэтому история полного стакана в этом проекте строится так:

1. Берем realtime стакан из брокерского источника, например QUIK.
2. Регулярно сохраняем snapshots в локальную SQLite-базу.
3. Потом анализируем уже накопленную историю.

Для `CNYRUB_TOM` в QUIK используется:

```text
CLASS_CODE = CETS
SEC_CODE   = CNYRUB_TOM
```

---

## Быстрый старт

### 1. Установить проект

Linux/macOS:

```bash
python -m pip install -e .
```

Windows PowerShell:

```powershell
py -m pip install -e .
```

### 2. Проверить текущую котировку

```bash
cnyrub quote
```

### 3. Запустить desktop-интерфейс

После установки доступна GUI-оболочка:

```bash
cnyrub-gui
```

На Windows PowerShell:

```powershell
cnyrub-gui
```

В интерфейсе есть вкладки:

- `Стакан / QUIK` — посмотреть текущий стакан из `C:\quik_export\cnyrub_tom_orderbook.json`, запустить/остановить запись в SQLite, сделать CSV-анализ и JSONL-экспорт;
- `Сделки MOEX` — показать обезличенные сделки, сохранить их в CSV, посчитать VWAP/объем/side imbalance;
- `Свечи` — скачать свечи MOEX ISS в CSV.

GUI показывает точную CLI-команду, которую запускает, и позволяет скопировать её для ручного запуска.

### 4. Скачать свечи

```bash
cnyrub candles --from 2026-06-03 --till 2026-06-03 --interval 60 --output data/candles_2026-06-03.csv
```

Интервалы MOEX:

| Значение | Интервал |
|---:|---|
| `1` | 1 минута |
| `10` | 10 минут |
| `60` | 1 час |
| `24` | 1 день |

### 5. Скачать и проанализировать обезличенные сделки

Сырые обезличенные сделки MOEX ISS:

```bash
cnyrub trades --from 2026-06-03 --till 2026-06-03 --limit 1000 --output data/trades_2026-06-03.csv
```

Агрегированный анализ сделок:

```bash
cnyrub analyze-trades --from 2026-06-03 --till 2026-06-03 --limit 1000 --output data/trades_analysis_2026-06-03.csv
```

Метрики анализа сделок:

| Поле | Что означает |
|---|---|
| `trade_count` | количество обезличенных сделок в ответе MOEX |
| `quantity` | суммарный объем в лотах |
| `value` | суммарный оборот |
| `vwap` | средневзвешенная цена: `sum(price * quantity) / sum(quantity)` |
| `min_price` / `max_price` | минимум/максимум цены сделки |
| `last_price` | цена последней сделки в выборке |
| `buy_quantity` / `sell_quantity` | объем сделок с флагом `BUYSELL = B/S` |
| `side_imbalance` | `(buy_quantity - sell_quantity) / (buy_quantity + sell_quantity)` |

Примечание: это именно обезличенная лента сделок MOEX ISS — без контрагентов и клиентских данных.

---

## Основной сценарий: QUIK на Windows

### Как работает связка

```text
QUIK -> QLua getQuoteLevel2("CETS", "CNYRUB_TOM") -> JSON-файл -> cnyrub -> SQLite -> CSV/JSONL анализ
```

QLua-скрипт каждые 250 мс пишет текущий стакан в JSON-файл. Python CLI читает этот файл и сохраняет snapshots.

### 1. Подготовить папку для экспорта

На Windows создайте папку:

```text
C:\quik_export
```

По умолчанию QLua-скрипт пишет сюда:

```text
C:\quik_export\cnyrub_tom_orderbook.json
```

### 2. Подключить QLua-скрипт в QUIK

Файл скрипта в проекте:

```text
scripts/quik_cnyrub_tom_orderbook_export.lua
```

В QUIK:

1. Откройте `Сервисы -> Lua скрипты`.
2. Нажмите `Добавить`.
3. Выберите файл `scripts\quik_cnyrub_tom_orderbook_export.lua`.
4. Запустите скрипт.
5. Проверьте, что появился файл:

```text
C:\quik_export\cnyrub_tom_orderbook.json
```

Если нужно изменить путь или частоту записи, отредактируйте в Lua-файле:

```lua
EXPORT_PATH = "C:\\quik_export\\cnyrub_tom_orderbook.json"
INTERVAL_MS = 250
```

### 3. Разово посмотреть стакан из QUIK-файла

```powershell
cnyrub orderbook --orderbook-path C:\quik_export\cnyrub_tom_orderbook.json --levels 10 --depth 20
```

Параметры:

- `--levels 10` — сколько уровней использовать для расчета depth/imbalance.
- `--depth 20` — сколько уровней стакана вывести на экран.

### 4. Записать историю стакана в SQLite

Писать до ручной остановки `Ctrl+C`:

```powershell
cnyrub record-orderbook `
  --orderbook-path C:\quik_export\cnyrub_tom_orderbook.json `
  --db C:\quik_export\cnyrub_tom_orderbook.sqlite `
  --interval 0.25
```

Писать ограниченное время, например 1 час:

```powershell
cnyrub record-orderbook `
  --orderbook-path C:\quik_export\cnyrub_tom_orderbook.json `
  --db C:\quik_export\cnyrub_tom_orderbook.sqlite `
  --interval 0.25 `
  --seconds 3600
```

Писать ограниченное число snapshots:

```powershell
cnyrub record-orderbook `
  --orderbook-path C:\quik_export\cnyrub_tom_orderbook.json `
  --db C:\quik_export\cnyrub_tom_orderbook.sqlite `
  --interval 0.25 `
  --count 1000
```

### 5. Проанализировать историю

```powershell
cnyrub analyze-orderbook `
  --db C:\quik_export\cnyrub_tom_orderbook.sqlite `
  --levels 10 `
  --output C:\quik_export\cnyrub_tom_analysis.csv
```

На выходе CSV с метриками по каждому snapshot:

| Поле | Что означает |
|---|---|
| `best_bid` | лучшая цена покупки |
| `best_ask` | лучшая цена продажи |
| `spread` | `best_ask - best_bid` |
| `mid` | середина между best bid и best ask |
| `bid_qty` | суммарный bid-объем на выбранных уровнях |
| `ask_qty` | суммарный ask-объем на выбранных уровнях |
| `imbalance` | дисбаланс: `(bid_qty - ask_qty) / (bid_qty + ask_qty)` |

### 6. Экспортировать полную историю стакана

```powershell
cnyrub export-orderbook `
  --db C:\quik_export\cnyrub_tom_orderbook.sqlite `
  --output C:\quik_export\cnyrub_tom_orderbook.jsonl
```

JSONL удобен для последующей обработки в Python, pandas, ClickHouse или других системах.

### Примечание по объемам QUIK

`quantity` из QUIK — это количество в лотах.

Для `CNYRUB_TOM` MOEX показывает `LOTSIZE = 1000 CNY`, поэтому при необходимости:

```text
объем в CNY = quantity * 1000
```

---

## Альтернативный сценарий: HTTP/JSON endpoint

Если полный стакан приходит не из QUIK, а из брокерского API или другого фида, можно передать URL:

```bash
cnyrub orderbook --orderbook-url "https://broker.example/api/cnyrub_tom/book" --levels 10 --depth 20
```

Запись истории:

```bash
cnyrub record-orderbook \
  --orderbook-url "https://broker.example/api/cnyrub_tom/book" \
  --db data/orderbook_snapshots.sqlite \
  --interval 1 \
  --seconds 3600
```

Можно также задать URL через переменную окружения:

```bash
export CNYRUB_ORDERBOOK_URL="https://broker.example/api/cnyrub_tom/book"
cnyrub record-orderbook --db data/orderbook_snapshots.sqlite --interval 1
```

---

## Формат JSON для полного стакана

Поддерживается простой формат:

```json
{
  "ts": "2026-06-03T19:30:00+00:00",
  "bids": [[10.85, 1000000], [10.84, 500000]],
  "asks": [[10.86, 750000], [10.87, 300000]]
}
```

Также поддерживаются уровни-объекты:

```json
{
  "ts": "2026-06-03T19:30:00+00:00",
  "bids": [
    {"price": 10.85, "quantity": 1000000},
    {"price": 10.84, "quantity": 500000}
  ],
  "asks": [
    {"price": 10.86, "quantity": 750000},
    {"price": 10.87, "quantity": 300000}
  ]
}
```

QUIK-style формат из QLua-скрипта тоже поддерживается:

```json
{
  "ts": "2026-06-03T19:30:00+00:00",
  "class_code": "CETS",
  "secid": "CNYRUB_TOM",
  "bid": [{"price": "10.85", "quantity": "1500"}],
  "offer": [{"price": "10.86", "quantity": "1050"}]
}
```

---

## Локальная проверка без QUIK и брокера

В проекте есть тестовые JSON-файлы:

```text
examples/orderbook_sample.json
examples/quik_orderbook_sample.json
```

Проверка обычного формата:

```bash
URL="file://$PWD/examples/orderbook_sample.json"
cnyrub orderbook --orderbook-url "$URL" --levels 2 --depth 2
cnyrub record-orderbook --orderbook-url "$URL" --db data/test_orderbook.sqlite --count 2 --interval 0.1
cnyrub analyze-orderbook --db data/test_orderbook.sqlite --output data/test_orderbook_analysis.csv
```

Проверка QUIK-style формата:

```bash
cnyrub orderbook --orderbook-path examples/quik_orderbook_sample.json --levels 2 --depth 2
cnyrub record-orderbook --orderbook-path examples/quik_orderbook_sample.json --db data/quik_shape_test.sqlite --count 2 --interval 0.1
cnyrub analyze-orderbook --db data/quik_shape_test.sqlite --output data/quik_shape_test_analysis.csv
```

---

## Команды CLI

```text
cnyrub quote
cnyrub candles
cnyrub orderbook
cnyrub record-orderbook
cnyrub analyze-orderbook
cnyrub export-orderbook
```

Справка по любой команде:

```bash
cnyrub --help
cnyrub orderbook --help
cnyrub record-orderbook --help
```

---

## Структура проекта

```text
src/cnyrub_tom/
  cli.py        # команды CLI
  providers.py  # MOEX ISS, HTTP JSON, QUIK/file providers
  storage.py    # SQLite storage и JSONL export
  analysis.py   # расчет spread/mid/depth/imbalance
  models.py     # dataclass-модели

scripts/
  quik_cnyrub_tom_orderbook_export.lua

examples/
  orderbook_sample.json
  quik_orderbook_sample.json

tests/
  test_analysis.py
  test_providers.py
  test_quik_file_provider.py
  test_storage.py
```

---

## Тесты

```bash
python -m pytest -q
```

Ожидаемый результат:

```text
6 passed
```

---

## Что можно добавить дальше

- GitHub Actions CI для автоматического запуска тестов.
- Windows `.ps1` quickstart script.
- Дедупликацию snapshots, если QUIK-файл не менялся.
- Пересчет объемов из лотов в CNY с учетом `LOTSIZE = 1000`.
- Адаптеры для Alor, T-Invest, Finam или другого брокерского API.

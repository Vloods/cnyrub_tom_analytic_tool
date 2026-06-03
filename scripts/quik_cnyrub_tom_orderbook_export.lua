-- Export CNYRUB_TOM full order book from local QUIK to JSON.
--
-- How to use in QUIK on Windows:
--   1. Edit EXPORT_PATH if needed.
--   2. QUIK: Services -> Lua scripts -> Add -> select this file -> Run.
--   3. In Python recorder on the same Windows machine:
--        cnyrub record-orderbook --orderbook-path C:\\quik_export\\cnyrub_tom_orderbook.json --db C:\\quik_export\\cnyrub_tom.sqlite --interval 0.25
--
-- Notes:
--   class_code CETS is the primary MOEX board for CNYRUB_TOM.
--   getQuoteLevel2 returns quantity in lots. For CNYRUB_TOM LOTSIZE is 1000 CNY.

local CLASS_CODE = "CETS"
local SEC_CODE = "CNYRUB_TOM"
local EXPORT_PATH = "C:\\quik_export\\cnyrub_tom_orderbook.json"
local EXPORT_TMP_PATH = EXPORT_PATH .. ".tmp"
local INTERVAL_MS = 250
local is_run = true

local function ensure_export_dir()
    -- io.open cannot create directories. os.execute is available in standard Lua/QLua.
    os.execute('if not exist "C:\\quik_export" mkdir "C:\\quik_export"')
end

local function json_escape(value)
    value = tostring(value or "")
    value = string.gsub(value, "\\", "\\\\")
    value = string.gsub(value, '"', '\\"')
    value = string.gsub(value, "\r", "\\r")
    value = string.gsub(value, "\n", "\\n")
    return value
end

local function write_levels(parts, name, levels, count)
    table.insert(parts, '"' .. name .. '":[')
    local n = tonumber(count) or 0
    for i = 1, n do
        local level = levels[i]
        if level ~= nil then
            if i > 1 then table.insert(parts, ',') end
            table.insert(parts, '{"price":"')
            table.insert(parts, json_escape(level.price))
            table.insert(parts, '","quantity":"')
            table.insert(parts, json_escape(level.quantity))
            table.insert(parts, '"}')
        end
    end
    table.insert(parts, ']')
end

local function now_iso8601_utc()
    -- QUIK os.date supports UTC via ! on standard Lua builds.
    return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

local function export_orderbook()
    local q = getQuoteLevel2(CLASS_CODE, SEC_CODE)
    if q == nil then
        message("getQuoteLevel2 returned nil for " .. CLASS_CODE .. ":" .. SEC_CODE, 2)
        return
    end

    local parts = {}
    table.insert(parts, '{')
    table.insert(parts, '"secid":"' .. SEC_CODE .. '",')
    table.insert(parts, '"class_code":"' .. CLASS_CODE .. '",')
    table.insert(parts, '"ts":"' .. now_iso8601_utc() .. '",')
    table.insert(parts, '"bid_count":' .. tostring(tonumber(q.bid_count) or 0) .. ',')
    table.insert(parts, '"offer_count":' .. tostring(tonumber(q.offer_count) or 0) .. ',')
    write_levels(parts, "bid", q.bid or {}, q.bid_count)
    table.insert(parts, ',')
    write_levels(parts, "offer", q.offer or {}, q.offer_count)
    table.insert(parts, '}')

    local f = io.open(EXPORT_TMP_PATH, "w")
    if f == nil then
        message("Cannot open export tmp file: " .. EXPORT_TMP_PATH, 3)
        return
    end
    f:write(table.concat(parts))
    f:close()
    os.remove(EXPORT_PATH)
    os.rename(EXPORT_TMP_PATH, EXPORT_PATH)
end

function OnInit(script_path)
    ensure_export_dir()
    message("CNYRUB_TOM orderbook exporter started: " .. EXPORT_PATH, 1)
end

function OnStop(signal)
    is_run = false
    return 1000
end

function main()
    while is_run do
        export_orderbook()
        sleep(INTERVAL_MS)
    end
end

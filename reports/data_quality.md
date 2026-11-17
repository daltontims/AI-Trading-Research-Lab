# Data Quality Report

*Generated 2026-11-08 08:17 UTC by `lab quality`.*

PASS = no issues · WARN = usable with known caveats · FAIL = must not be used until fixed.

| Dataset | Status | Rows | Start | End | Fingerprint |
|---|---|---:|---|---|---|
| `crypto/binance/BTCUSDT/bars_1m` | **WARN** | 4,115,751 | 2019-01-01 00:00 | 2026-10-31 23:59 | `e756223d13efa0f8` |
| `crypto/binance/BTCUSDT/funding` | **PASS** | 7,488 | 2020-01-01 00:00 | 2026-10-31 16:00 | `5938ee368551e769` |
| `crypto/binance/ETHUSDT/bars_1m` | **WARN** | 4,115,750 | 2019-01-01 00:00 | 2026-10-31 23:59 | `e24d9dbe5f936ead` |
| `crypto/binance/ETHUSDT/funding` | **PASS** | 7,488 | 2020-01-01 00:00 | 2026-10-31 16:00 | `c5e62bdd244c08a1` |
| `crypto/binance/SOLUSDT/bars_1m` | **WARN** | 3,271,335 | 2020-08-11 06:00 | 2026-10-31 23:59 | `5e8ae8ebf4a45182` |
| `crypto/binance/SOLUSDT/funding` | **WARN** | 6,793 | 2020-09-13 16:00 | 2026-10-31 16:00 | `85bbb86e9f56af30` |
| `equity/yahoo/DIA/bars_1d` | **WARN** | 7,246 | 1998-01-20 00:00 | 2026-11-06 00:00 | `614e605e6d3c9455` |
| `equity/yahoo/GLD/bars_1d` | **PASS** | 5,527 | 2004-11-18 00:00 | 2026-11-06 00:00 | `1cdb5820bd891508` |
| `equity/yahoo/IWM/bars_1d` | **PASS** | 6,652 | 2000-05-26 00:00 | 2026-11-06 00:00 | `1dbd7c2632ef8124` |
| `equity/yahoo/QQQ/bars_1d` | **PASS** | 6,960 | 1999-03-10 00:00 | 2026-11-06 00:00 | `4ac6e8d6c00c1ff4` |
| `equity/yahoo/SPY/bars_1d` | **WARN** | 8,502 | 1993-01-29 00:00 | 2026-11-06 00:00 | `075e1490909c8846` |
| `equity/yahoo/TLT/bars_1d` | **PASS** | 6,109 | 2002-07-30 00:00 | 2026-11-06 00:00 | `6f90e793868c0439` |
| `equity/yahoo/XLE/bars_1d` | **WARN** | 7,012 | 1998-12-22 00:00 | 2026-11-06 00:00 | `dbd11acec37936ac` |
| `equity/yahoo/XLF/bars_1d` | **WARN** | 7,012 | 1998-12-22 00:00 | 2026-11-06 00:00 | `228284a9e92cbd1c` |
| `equity/yahoo/XLI/bars_1d` | **PASS** | 7,012 | 1998-12-22 00:00 | 2026-11-06 00:00 | `3dd6f60ad1f0cf30` |
| `equity/yahoo/XLK/bars_1d` | **PASS** | 7,012 | 1998-12-22 00:00 | 2026-11-06 00:00 | `519e38d1854a76c4` |
| `equity/yahoo/XLP/bars_1d` | **PASS** | 7,012 | 1998-12-22 00:00 | 2026-11-06 00:00 | `fdce0249372cce48` |
| `equity/yahoo/XLU/bars_1d` | **PASS** | 7,012 | 1998-12-22 00:00 | 2026-11-06 00:00 | `a25b233de1b49113` |
| `equity/yahoo/XLV/bars_1d` | **PASS** | 7,012 | 1998-12-22 00:00 | 2026-11-06 00:00 | `8eab45766cbadff9` |
| `equity/yahoo/XLY/bars_1d` | **PASS** | 7,012 | 1998-12-22 00:00 | 2026-11-06 00:00 | `fd857d892d1cacae` |
| `macro/yahoo/DXY/bars_1d` | **WARN** | 14,181 | 1971-01-04 00:00 | 2026-11-06 00:00 | `23231e87fa87cfa5` |
| `macro/yahoo/IDX_IRX/bars_1d` | **WARN** | 14,233 | 1970-01-02 00:00 | 2026-11-06 00:00 | `60bf9a8e352021ad` |
| `macro/yahoo/IDX_TNX/bars_1d` | **WARN** | 14,233 | 1970-01-02 00:00 | 2026-11-06 00:00 | `a9bc78273295a222` |
| `macro/yahoo/IDX_VIX/bars_1d` | **WARN** | 9,283 | 1990-01-02 00:00 | 2026-11-06 00:00 | `a67c94aec0a204b0` |
| `macro/yahoo/IDX_VIX3M/bars_1d` | **PASS** | 5,111 | 2006-07-17 00:00 | 2026-11-06 00:00 | `2a91d9843cc6a15a` |

## `crypto/binance/BTCUSDT/bars_1m` — WARN

- **WARN** · outliers: 154 moves beyond 50 robust σ — verify they are real events (largest at: 2020-03-12T10:47, 2020-03-13T02:31, 2020-03-13T02:40, 2020-03-12T10:48, 2020-03-12T23:29)
- **WARN** · gaps: 21 gaps ≥ 5 min, 4,086 minutes total; longest: 2019-05-15 03:00 (600m), 2019-08-15 02:00 (480m), 2019-03-12 02:00 (360m), 2020-02-19 11:36 (354m), 2021-04-25 04:01 (284m)
- **INFO** · coverage: 99.90% of expected minutes present

## `crypto/binance/BTCUSDT/funding` — PASS

- **INFO** · funding: mean 1.06 bps/interval, min -30.0, max 30.0

## `crypto/binance/ETHUSDT/bars_1m` — WARN

- **WARN** · outliers: 128 moves beyond 50 robust σ — verify they are real events (largest at: 2025-02-03T02:07, 2021-05-19T13:21, 2020-08-02T04:41, 2024-08-05T01:10, 2021-05-19T13:11)
- **WARN** · gaps: 21 gaps ≥ 5 min, 4,087 minutes total; longest: 2019-05-15 03:00 (600m), 2019-08-15 02:00 (480m), 2019-03-12 02:00 (360m), 2020-02-19 11:36 (354m), 2021-04-25 04:01 (284m)
- **INFO** · coverage: 99.90% of expected minutes present

## `crypto/binance/ETHUSDT/funding` — PASS

- **INFO** · funding: mean 1.25 bps/interval, min -35.6, max 37.5

## `crypto/binance/SOLUSDT/bars_1m` — WARN

- **WARN** · outliers: 72 moves beyond 50 robust σ — verify they are real events (largest at: 2023-01-02T07:14, 2020-09-05T11:23, 2021-05-20T17:01, 2022-11-08T19:34, 2022-12-29T22:38)
- **WARN** · gaps: 10 gaps ≥ 5 min, 1,424 minutes total; longest: 2021-04-25 04:01 (284m), 2021-08-13 02:00 (270m), 2020-12-21 14:09 (231m), 2021-04-20 02:00 (150m), 2021-09-29 07:00 (120m)
- **INFO** · coverage: 99.96% of expected minutes present

## `crypto/binance/SOLUSDT/funding` — WARN

- **WARN** · funding: 15 intervals with |funding| > 75 bps
- **INFO** · funding: mean 0.02 bps/interval, min -200.0, max 33.2

## `equity/yahoo/DIA/bars_1d` — WARN

- **WARN** · outliers: 3 moves beyond 15 robust σ — verify they are real events (largest at: 2020-03-16T00:00, 2008-10-28T00:00, 2008-10-13T00:00)
- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/GLD/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/IWM/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/QQQ/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/SPY/bars_1d` — WARN

- **WARN** · outliers: 1 moves beyond 15 robust σ — verify they are real events (largest at: 2008-10-13T00:00)
- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/TLT/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/XLE/bars_1d` — WARN

- **WARN** · outliers: 1 moves beyond 15 robust σ — verify they are real events (largest at: 2020-03-09T00:00)
- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/XLF/bars_1d` — WARN

- **WARN** · outliers: 2 moves beyond 15 robust σ — verify they are real events (largest at: 2008-12-01T00:00, 2009-01-20T00:00)
- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/XLI/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/XLK/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/XLP/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/XLU/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/XLV/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `equity/yahoo/XLY/bars_1d` — PASS

- **INFO** · survivorship: free daily data omits delisted symbols; do not use for stock-selection studies

## `macro/yahoo/DXY/bars_1d` — WARN

- **WARN** · stale: longest run of unchanged close: 12 bars

## `macro/yahoo/IDX_IRX/bars_1d` — WARN

- **WARN** · outliers: 114 moves beyond 15 robust σ — verify they are real events (largest at: 1981-05-04T00:00, 1980-12-19T00:00, 1982-02-01T00:00, 1981-01-05T00:00, 1979-10-09T00:00)
- **WARN** · stale: longest run of unchanged close: 19 bars
- **INFO** · prices: 9 bars with zero/negative yields (valid for interest rates)
- **INFO** · sessions: 2 NYSE sessions missing (first: 2010-10-11, 2016-11-11)

## `macro/yahoo/IDX_TNX/bars_1d` — WARN

- **WARN** · outliers: 1 moves beyond 15 robust σ — verify they are real events (largest at: 1987-10-20T00:00)
- **WARN** · stale: longest run of unchanged close: 8 bars
- **INFO** · sessions: 2 NYSE sessions missing (first: 2010-10-11, 2016-11-11)

## `macro/yahoo/IDX_VIX/bars_1d` — WARN

- **WARN** · sessions: 2 bars on non-trading days (first: 2026-05-25, 2026-09-07)

## `macro/yahoo/IDX_VIX3M/bars_1d` — PASS

No findings.

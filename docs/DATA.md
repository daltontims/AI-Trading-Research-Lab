# Data Guide

How market data gets into the lab, where it lives, and what its weaknesses are.

## Quick start

```bash
uv sync --extra dev          # install
uv run lab ingest all        # download the standard universe (resumable; re-run to continue)
uv run lab datasets          # list what is in the lake
uv run lab quality           # check every dataset -> reports/data_quality.md
uv run pytest                # offline tests
```

Market data is **not** stored in git. Everything can be re-downloaded with the
commands above (data is free and needs no accounts). Downloads skip months already
present, so interrupted runs resume where they stopped.

## Sources

| Asset class | Source | Dataset(s) | History | Notes |
|---|---|---|---|---|
| Crypto | Binance public archive | `bars_1m` (spot), `funding` (USD-M perps) | 2019+ (SOL 2020-08+) | Checksums verified. Trade-price bars, no bid/ask. |
| Forex | Dukascopy | `quote_bars_1m` (bid/ask), optional `quote_ticks` | 2018+ | Strict rate limits: downloads are throttled to 1 request/s. |
| US ETFs | Yahoo Finance | `bars_1d` | 1993+ (varies) | Survivorship-biased; unofficial API. |
| Macro | Yahoo Finance | `bars_1d` for ^VIX, ^VIX3M, ^TNX, ^IRX, DXY | 1990+ | Used as regime inputs, not traded. |

Unavailable in this environment: **FRED** (the server refuses this cloud provider's
network) and **Stooq** (needs a browser check). Yahoo covers VIX and rates instead.
Paid sources (futures, options, survivorship-free stocks) are not used; see ARCHITECTURE.md.

## Lake layout

```
data/<asset_class>/<source>/<symbol>/<dataset>/<chunk>.parquet
e.g. data/crypto/binance/BTCUSDT/bars_1m/2024-03.parquet
     data/equity/yahoo/SPY/bars_1d/all.parquet
```

Schemas are defined in `src/lab/data/schemas.py`. Rules:

- Timestamps are **UTC** and mark the **start** of a bar. A 1-minute bar stamped
  10:00 is only known at 10:01. Daily equity bars are stamped 00:00 UTC of the
  trading date; their close is only known after the US close that day.
- Equity `open/high/low/close` are split-adjusted, not dividend-adjusted; `adj_close`
  is fully adjusted (use it for return calculations).
- Forex quote bars keep bid and ask separately so costs come from real spreads.
  Minutes with no quote activity are dropped (no fake prices during closed markets).
- Each dataset has a **fingerprint** (content hash) recorded with every experiment.

## Research partitions

Defined in `configs/splits.yaml`, enforced by `lab.data.splits`:

| Market | Development | Validation | Vault (locked) |
|---|---|---|---|
| Crypto | start – 2023-12 | 2024-01 – 2025-06 | 2025-07 → |
| Forex | start – 2023-06 | 2023-07 – 2024-12 | 2025-01 → |
| Equity / macro | start – 2017-12 | 2018-01 – 2022-06 | 2022-07 → |

`splits.load(key, "vault")` raises an error unless `allow_vault=True` is passed.

## Known data caveats

- **Binance is one venue.** Prices differ slightly across exchanges; volume is venue-specific.
  Spot fees (10 bps/side assumed) dominate short-horizon crypto strategies.
- **Dukascopy is one liquidity provider.** Retail broker spreads are usually wider;
  cost models add a markup. Candle mode approximates spreads from minute open/close
  quotes; tick mode (exact) is used for scalping research.
- **Yahoo daily data** omits delisted symbols, so it is only used for ETFs and indices.
- See `reports/data_quality.md` for the latest automated checks (gaps, outages,
  outliers, stale prices, spread statistics).

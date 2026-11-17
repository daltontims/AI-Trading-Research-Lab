# Paper Trading

The lab trades **validated** strategies automatically in an Alpaca **paper** (simulated money)
account. There is no live-trading code: the broker client refuses any endpoint other than
`https://paper-api.alpaca.markets`, and adding live trading requires the owner's explicit permission.

## Setup (one time, done by the owner)

1. Create a free account at alpaca.markets, switch to **Paper Trading**, open **API Keys**, click
   **Generate**. Optionally reset the paper balance to $5,000 (orders are sized off at most $5,000
   anyway — `capital` in `configs/deployment.yaml`).
2. **Secret Key** → saved through the secure credential form in a Claude session (stored as a network
   secret on the `ai-trading-research-lab` environment; the proxy adds it to requests to Alpaca's paper
   API as the `APCA-API-SECRET-KEY` header). It never appears in code, files or chat.
3. **API Key ID** → environment settings: session title bar → environment **ai-trading-research-lab** →
   **Edit** → Environment variables → `ALPACA_KEY_ID=PK…`. Applies to sessions started afterwards.

On a personal computer instead: set `ALPACA_KEY_ID` and `ALPACA_SECRET_KEY` environment variables.

## Daily operation

```bash
uv run lab paper status            # account, positions, clock, recent orders
uv run lab paper run               # plan only: what would be ordered for the next open
uv run lab paper run --submit      # reconcile fills, submit market-on-open orders, snapshot
uv run lab paper run --sim         # practice run against an in-memory broker (not journalled)
```

Each trading day before the US open (≈08:40 New York time; Alpaca accepts opening-auction orders until
09:28), `lab paper run --submit`:

1. Records fills of earlier orders and their price versus the prior close (real slippage tracking).
2. Downloads fresh daily bars and replays each deployed strategy exactly as the backtest engine does
   (verified position-for-position in `tests/test_paper_runner.py`).
3. Compares the wanted position after the next open with the account's position.
4. Submits **market-on-open** (`opg`) orders — the same fill assumption as the backtest — with
   deterministic client order ids, so re-running the same day cannot duplicate orders.
5. Appends everything to `research/paper/journal.jsonl` (committed to git).

## Schedule

A weekday scheduled task (Claude app → scheduled tasks, "Paper trading daily run") starts a fresh cloud
session at **08:40 New York time** in the `ai-trading-research-lab` environment. It checks out the
paper-trading branch, runs `uv run lab paper run --submit`, commits `research/paper/journal.jsonl` and
`research/registry/` back to that branch, and reports fills, orders and the account. Market holidays
are harmless: the order is keyed to the last completed session, so it is queued for the next open and
the next day's run finds it already submitted.

The first submitted order also moves the hypothesis from VALIDATED to PAPER in the registry.

To stop trading: set `kill_switch: true` in `configs/deployment.yaml` and commit it (the next run
cancels open orders and places none), or disable the scheduled task.

## Safety rules

| Rule | Where |
|---|---|
| Paper endpoint only; live URLs refused | `lab/paper/broker.py` |
| Only `VALIDATED` hypotheses may be deployed | `runner.plan_orders` |
| Kill switch: `kill_switch: true` cancels open orders, places none | `configs/deployment.yaml` |
| Orders sized off at most `capital` ($5,000) and capped at 1.05 × allocation | `runner.plan_orders` |
| Whole shares; positions are held, not resized, while the strategy stays in | `runner.plan_orders` |
| Strategies with intrabar stops/targets are refused (not supported yet) | `runner.replay_target` |

## Deployed strategies

| Hypothesis | Strategy | Market | Allocation | Paper since |
|---|---|---|---|---|
| H4-17 | 2-day RSI pullback (entry RSI < 10 above 200-day average, exit RSI > 70) | SPY | 100% of $5,000 | 2026-11-17 |

## Evaluating paper results (protocol stage PAPER → PAPER_PASSED)

After at least 3 months, paper results are compared with what the backtest expects for the same period
(same signals, same days). Passing requires results within the backtest's expected range and real
fill prices consistent with the cost model. Until then the strategy's status is PAPER.

## Standing session

Daily runs happen in the standing cloud session 'Paper trading daily runs', woken by the scheduled task at 08:40 New York time.

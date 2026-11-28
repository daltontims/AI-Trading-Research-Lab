# Discovery Engine (Phase 5)

Tests hundreds of trading ideas at once, automatically, without fooling us. Code: `src/lab/discovery/`.
Run: `uv run python scripts/discovery.py <BATCH> --register` (commit), then `uv run python scripts/discovery.py <BATCH>`.

## In plain words

Instead of hand-writing a few ideas, the engine builds them from parts:

| Part | Choices |
|---|---|
| **Entry** (when to buy) | 2-day RSI oversold · lowest close in x days · x down days in a row · a drop larger than x standard deviations · close near the day's low · highest close in x days (breakout) · close crosses above its x-day average |
| **Trend filter** | none · only above the 200-day average · only below it |
| **Exit** (when to sell) | after y days · close back above its y-day average (pullback entries) · close below its y-day average · lowest close in y days (breakout entries) |
| **Market** | 14 ETFs (SPY, QQQ, IWM, DIA, TLT, GLD, 8 sector funds) and 3 coins (BTC, ETH, SOL), daily bars |

7 entries × 3 filters × 2 exits × 17 markets = **714 ideas per batch**, each with at most two tuned numbers (x, y).

## Why testing more ideas does not mean more fake winners

Try enough ideas and some look great by luck. The engine is built so that luck is filtered out:

1. **Pre-registration.** Every idea, with its exact rules and parameter choices, is written to the registry and
   committed *before* any test runs.
2. **Event study first (cheap).** For each entry condition: after it fires, are the next days' returns better than
   ordinary days on the same market? Measured exactly as we would trade it (buy at the next open). Overlapping
   signals are thinned so each event counts once. A **false-discovery control (Benjamini–Hochberg, 5%)** is applied
   across *every* test in the batch. Ideas without a real-looking effect are rejected and logged.
3. **Full test** (the same pipeline as before, `lab.validation.evaluate`) only for ideas with an effect: every
   parameter combination is a logged trial; must stay profitable at 2× costs; Deflated Sharpe uses the **whole
   rule family's planned trial count** (the same rule on all 17 markets counts together, so trying a rule on many
   markets makes the bar higher, not lower); PBO, SPA, walk-forward, parameter plateau, year consistency; then the
   validation data is looked at **once**.
4. **Cross-market check.** The report shows on how many markets each rule family works. One market only is a warning.
5. The **vault** (most recent data) is never used here. A candidate becomes VALIDATED only through the separate,
   once-only vault test, and only VALIDATED strategies can be paper traded.

Calibration (`tests/test_discovery.py`): on 30 random-walk markets × all 63 entry tests, the false-discovery control
lets through ≤ 1% (in practice none); a planted mean-reversion effect is found in 5 of 5 trials.

## Plans (which markets each batch covers)

| Plan | Markets | Entries | Batches |
|---|---|---|---|
| `core_daily` | 14 ETFs + 3 coins, daily bars | the 7 core entries | D5-01, D5-02 |
| `crypto_intraday_vix` | BTC, ETH, SOL on 1-hour and 4-hour bars; 14 ETFs daily | core entries on crypto; on ETFs two **fear-index** entries: the VIX jumps x times above its 10-day average, or the VIX is above x times the 3-month VIX (VIX3M) | D5-03 |

The fear-index entries read the VIX close of the same day (known before the next open, where orders fill). On
hourly bars, "x bars" means x hours, and the 200-bar trend filter is about 8 days. Crypto pays US retail costs
(about 0.4% per trade), which is hard to beat on short holding periods.

## Screen modes

- `per_instrument` (batch D5-01): each entry condition is tested on each market alone. Honest but low-powered:
  1,071 separate tests, so only a very strong single-market effect survives the false-discovery control.
- `pooled` (batch D5-02 onward): each entry condition is tested on a whole market group at once (14 US ETFs, or
  3 coins). Each market's events are measured against its own normal returns, then averaged **per date**, so ten
  ETFs reacting to the same sell-off count as one observation, not ten. 126 tests per batch instead of 1,071. If a
  group shows an effect, every market in that group goes to the full test for that rule, where each must pass alone.

Changing the screen after seeing results is a new batch: D5-02 repeats D5-01's 714 ideas with the pooled screen,
and every D5-02 idea is linked to its D5-01 parent (`parent_id`), so the earlier tests stay on record.

## Speed

The event studies take seconds. Full tests run in parallel on every CPU core (`--workers`), each writing to the
shared registry. Batches are resumable: re-running continues where it stopped.

## Outputs

- `research/discovery/<BATCH>/manifest.json` — the pre-registered batch definition
- `research/discovery/<BATCH>/event_studies.json` — every event-study test with p and q values
- `research/discovery/<BATCH>/evaluations.jsonl` — every full test result
- `reports/discovery/<BATCH>.md` — funnel, candidates, screened ideas, rule families, failure reasons
- `reports/strategies/<ID>.md` — strategy card per fully tested idea

## Limitations

- Long-only daily rules; intraday crypto and FX are not in batch 1.
- The event-study horizon is fixed per style (5 days for pullbacks, 20 for breakouts); an exit that holds much
  longer than that is screened on a shorter question than it trades.
- Ideas are correlated (similar rules on related markets), so the false-discovery control is conservative.
- The validation split for SPY was already used by earlier SPY hypotheses (one look each, as allowed);
  very SPY-RSI-like ideas should be read with that in mind.

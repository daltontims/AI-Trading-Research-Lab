# Technical Architecture Proposal

*Status: proposed (Phase 0). Last updated 2026-11-08.*

This document answers the "first assignment": what we build, with which tools,
what it costs, and what can go wrong. It is written for a reader with limited
programming and trading experience; technical terms are explained when first used.

---

## A. Recommended technical architecture

### The core idea in one paragraph

Most trading ideas that look profitable in a backtest are flukes. With enough
attempts, randomness alone produces impressive-looking results. So the lab is
designed less like a "strategy generator" and more like a **funnel with
increasingly strict filters**. Thousands of cheap ideas go in the top; almost
all are rejected; the few that survive every stage are treated as *candidates*,
and only paper trading on data the system has never seen can turn a candidate
into something worth trusting. Every attempt — including every failure — is
recorded, because the number of attempts is itself needed to judge whether a
success is real.

### The research funnel

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 1. HYPOTHESIS     "After a 3σ down-move in the first 15 min, does    │
 │    GENERATION      price drift back up over the next hour?"          │
 │                    (templates × feature library, curated ideas,      │
 │                     optional LLM proposals) → pre-registered in DB   │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 2. EVENT STUDY     Is there any measurable effect at all, before     │
 │    (cheap, no      we design a strategy? Compare forward returns     │
 │     parameters)    after the event vs. normal. Most ideas die here.  │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 3. VECTORIZED      Turn surviving effect into simple fixed rules.    │
 │    SCREEN          Fast backtest WITH realistic costs on the         │
 │                    training period only. Small parameter budget.     │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 4. VALIDATION      Walk-forward analysis, out-of-sample period,      │
 │                    deflated Sharpe ratio, probability of backtest    │
 │                    overfitting, cost stress tests, parameter         │
 │                    stability, regime breakdown, other markets.       │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 5. EVENT-DRIVEN    Re-test with a realistic order-by-order simulator │
 │    SIMULATION      (spreads, queue/fill logic, latency). Essential   │
 │                    for scalping and intraday strategies.             │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 6. HOLDOUT VAULT   One single test on the most recent data, which    │
 │                    no part of the system has ever looked at.         │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 7. PAPER TRADING   Simulated live trading for ≥ 3 months (requires   │
 │                    your permission to create a paper account).       │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 8. LIVE            Out of scope. Only ever with explicit permission. │
 └──────────────────────────────────────────────────────────────────────┘
```

Stages 2–3 are cheap and run thousands of times. Stages 4–6 are expensive and
reserved for survivors. This ordering keeps compute costs near zero and — more
importantly — limits how many times we "peek" at the precious validation data.

### System components

```
                ┌──────────────────────┐
  Free/paid ──► │  Data ingestion      │  downloaders per source, quality checks
  data sources  └─────────┬────────────┘
                          ▼
                ┌──────────────────────┐
                │  Data lake (Parquet) │  bars, ticks, quotes; one schema for all
                │  + DuckDB queries    │  asset classes; re-downloadable
                └─────────┬────────────┘
                          ▼
   ┌───────────────┐  ┌──────────────────────┐  ┌───────────────────────┐
   │ Instrument    │─►│ Feature library      │◄─│ Cost models           │
   │ registry      │  │ (returns, vol, gaps, │  │ (commission, spread,  │
   │ (tick size,   │  │  time-of-day, cross- │  │  slippage, funding,   │
   │  multiplier,  │  │  asset, regimes ...) │  │  latency per market)  │
   │  sessions)    │  └─────────┬────────────┘  └───────────┬───────────┘
   └───────────────┘            ▼                           │
                ┌──────────────────────────┐                │
                │ Discovery engine         │                │
                │ generate → event study → │◄───────────────┘
                │ screen → validate        │
                └─────────┬────────────────┘
                          ▼
                ┌──────────────────────────┐      ┌─────────────────────┐
                │ Research registry (SQL)  │─────►│ Dashboard +         │
                │ hypotheses, experiments, │      │ auto-generated      │
                │ every trial, results,    │      │ Markdown reports    │
                │ promotion status         │      └─────────────────────┘
                └─────────┬────────────────┘
                          ▼
                ┌──────────────────────────┐
                │ Event-driven simulator & │  NautilusTrader: same strategy code
                │ paper trading adapter    │  for realistic backtest and paper
                └──────────────────────────┘
```

### Key design principles

1. **Reproducibility.** Every experiment stores the code version (git commit),
   the data snapshot fingerprint, the exact configuration and the random seed.
   Any result can be regenerated.
2. **Pre-registration.** A hypothesis and its rules are written to the registry
   *before* it is tested. Rules cannot be quietly changed after seeing results;
   a change creates a new, linked hypothesis and counts as another attempt.
3. **Count every trial.** Statistical corrections need the true number of
   attempts. The registry records them automatically; nothing is "off the books".
4. **Costs are not optional.** No backtest runs without a cost model. A
   zero-cost run is only allowed as a diagnostic and is labelled as such.
5. **Time is sacred.** All features must only use information available at the
   moment of decision. This is enforced in code (point-in-time joins, signals
   applied on the *next* bar) and checked by automated tests.
6. **Simple first.** Fewer parameters, fewer rules. Complexity has to earn its
   place with out-of-sample evidence.
7. **The repo is the memory.** Docs, decision log, hypothesis registry exports
   and reports live in git so research can resume from any machine.

---

## B. Proposed software and data sources

### Programming language: Python

Python is the standard language of quantitative research: the best libraries,
the most documentation, and it is readable for a non-programmer. Speed-critical
parts use libraries written in faster languages underneath (Polars, NumPy,
Numba, DuckDB, NautilusTrader's Rust core), so we get both convenience and
performance. No second language is needed.

### Core libraries (all free and open source)

| Purpose | Library | Why |
|---|---|---|
| Environment & packages | **uv** | Fast, reliable, reproducible installs with a lock file |
| Data frames | **Polars** (primary), pandas (compatibility) | Polars is much faster and more memory-efficient on large tick/minute datasets |
| Numerics | NumPy, **Numba** | Numba compiles custom loops (e.g. trade simulation) to machine-code speed |
| Storage format | **Apache Parquet** via PyArrow | Compressed columnar files; the industry standard for research data lakes |
| Analytical queries | **DuckDB** | SQL directly over Parquet files; no database server to run or pay for |
| Research registry | **SQLite** | Zero-administration, single file, safe concurrent writes, built into Python |
| Statistics | SciPy, statsmodels, scikit-learn | Significance tests, regressions, bootstrap, clustering, ML baselines |
| Fast screening backtests | **Own vectorized engine** (Polars + Numba) | Small, fully understood, tested; no black-box assumptions about fills or costs |
| Realistic simulation & paper trading | **NautilusTrader** | Event-driven, multi-asset (stocks, futures, FX, crypto, options), tick/order-book aware, and the same strategy code runs in paper trading via broker adapters |
| Trading calendars | exchange_calendars | Correct market hours, holidays, early closes |
| Parameter search (bounded) | Optuna | Efficient search *with a hard trial budget* that the registry counts |
| Configuration | pydantic + YAML | Validated, human-readable experiment configs |
| Command line | Typer | `lab ingest ...`, `lab discover ...`, `lab report ...` |
| Dashboard | **Streamlit** + Plotly | Interactive web dashboard in pure Python, runs locally for free |
| Testing | pytest, hypothesis | Known-answer tests for engine and metrics; look-ahead bias tests |
| Crypto exchange APIs | CCXT | One interface to 100+ exchanges for data and (later) paper trading |

**Statistical validation methods we will implement ourselves** (they are short,
well-documented formulas, and writing them ourselves avoids paid libraries and
lets us test them): Deflated Sharpe Ratio, Probability of Backtest Overfitting
(CSCV), purged & embargoed cross-validation, White's Reality Check / Hansen's SPA
test, Benjamini–Hochberg false-discovery control, block bootstrap and Monte Carlo
trade resampling.

### Backtesting engines considered

| Engine | Verdict |
|---|---|
| **Own vectorized engine** | **Use** for stages 2–4. Thousands of tests per minute; we control every assumption. |
| **NautilusTrader** | **Use** for stage 5 and paper trading. Actively maintained, high-fidelity, multi-asset, open source. Steeper learning curve, so only survivors are ported to it. |
| vectorbt (open-source edition) | Optional helper. Fast, but the free edition gets fewer updates; we don't want to depend on it. |
| QuantConnect LEAN | Excellent but C#-centred and pushes toward their paid cloud; heavier than needed. |
| Backtrader / Zipline | Not recommended: Backtrader is effectively unmaintained; Zipline-reloaded is equity-focused. |

### Historical data sources

Free sources first. Paid sources are listed with the reason they might become
worth it; **none will be purchased without your explicit approval.**

| Market | Source | Cost | Use | Caveats |
|---|---|---|---|---|
| **Crypto** | Binance public data archive (data.binance.vision); Bybit/OKX archives | Free | Trades, 1-minute bars, futures funding rates, back to ~2017–2019 | Best free laboratory for **scalping** research (true trade-level data). Exchange-specific; US residents cannot *trade* on Binance.com, but research data is public. |
| **Forex** | Dukascopy historical ticks | Free | Tick data **with bid and ask** for major pairs, 2003+ | Second-best free scalping lab. One broker's feed; FX has no central exchange. |
| **US stocks/ETFs (daily)** | Yahoo Finance (yfinance), Tiingo free tier, Stooq | Free | Daily bars, prototyping | **Survivorship bias** (delisted companies missing), occasional bad prints. Fine for ETFs and index research; not for stock-picking studies. |
| **US stocks/ETFs (minute)** | Alpaca market data (free tier) | Free (needs a free account — will ask first) | Minute bars ~2016+ | Free tier is IEX feed (a few % of volume); adequate for liquid ETFs, not for precise scalping. |
| **Macro / regimes** | FRED (St. Louis Fed), CBOE VIX history | Free | Rates, VIX, yield curves for regime features | — |
| **Futures** | Databento | Pay-per-use; new accounts get free credit (≈$125 historically) | CME futures (ES, NQ, CL, GC, micros) ticks and top-of-book | The only realistic way to research futures scalping. Free credit may cover initial studies. **Will ask before creating an account.** |
| **Survivorship-free stocks** | Norgate Data or Sharadar (Nasdaq Data Link) | ~$25–55/month | Delisted stocks, point-in-time index membership | Needed only if we research individual-stock strategies. |
| **US stocks intraday (full market)** | Polygon.io (now Massive) | ~$29+/month | Full-volume minute/tick data | Only if equity intraday research becomes a focus. |
| **Options** | ThetaData, ORATS, CBOE DataShop | ~$30–200+/month | Historical option chains, quotes, IV | Options data is the most expensive. **Options research is deferred to a later phase** and needs a budget decision. |

Prices are approximate and change often; they will be re-verified before any
recommendation to buy.

---

## C. Project folder structure

```
AI-Trading-Research-Lab/
├── README.md                 Project overview and current status
├── CLAUDE.md                 Handoff notes so any session can resume work
├── pyproject.toml            Python dependencies (managed by uv)
├── docs/
│   ├── ARCHITECTURE.md       This document
│   ├── RESEARCH_PROTOCOL.md  The statistical rules every strategy must pass
│   ├── ROADMAP.md            Development phases and progress checklist
│   └── DECISIONS.md          Log of important decisions and why
├── configs/                  YAML: instruments, cost models, data splits, experiments
├── src/lab/
│   ├── data/                 Data lake access, schemas, quality checks
│   │   └── ingest/           One downloader per data source
│   ├── instruments/          Instrument definitions (tick size, multiplier, hours)
│   ├── features/             Feature library (all point-in-time safe)
│   ├── costs/                Commission, spread, slippage, funding, latency models
│   ├── engine/               Vectorized backtester and portfolio accounting
│   ├── validation/           Walk-forward, DSR, PBO, SPA, bootstrap, robustness
│   ├── discovery/            Hypothesis generator, event studies, pipeline runner
│   ├── registry/             SQLite research database + schema + export
│   ├── reporting/            Tearsheets, leaderboard, Markdown report generation
│   ├── dashboard/            Streamlit app
│   └── paper/                NautilusTrader strategies & paper-trading adapters (later)
├── research/
│   ├── hypotheses/           Exported hypothesis cards (one file each, in git)
│   ├── experiments/          Exported experiment summaries (in git)
│   └── graveyard/            Rejected ideas and why (in git — failures are data)
├── reports/                  Auto-generated leaderboard and strategy reports
├── notebooks/                Exploratory analysis (never the source of truth)
├── scripts/                  One-off utilities
├── tests/                    Automated tests (engine, metrics, bias checks)
└── data/                     Market data lake — NOT in git, re-downloadable
```

---

## D. Development phases

See [ROADMAP.md](ROADMAP.md) for the detailed checklist. Summary:

| Phase | Goal | Outcome |
|---|---|---|
| **0. Foundation** | Architecture, protocol, repo skeleton | *This deliverable* |
| **1. Data layer** | Free ingestors (Binance, Dukascopy, Yahoo/Tiingo, FRED), unified schema, data-quality checks | Clean, re-downloadable multi-asset data lake |
| **2. Engine & costs** | Vectorized backtester, per-market cost models, full metrics suite, known-answer tests | Trustworthy backtest numbers |
| **3. Validation toolkit** | Data splits + holdout vault, walk-forward, DSR, PBO, SPA, bootstrap, robustness tests. **Calibration:** prove the pipeline rejects random strategies | We know the filters work |
| **4. Registry & first research** | Registry DB, ~20 hand-designed hypotheses across markets run end-to-end | First real findings (mostly rejections, expected) |
| **5. Discovery engine** | Automated hypothesis generation, event studies, scheduled research runs, global multiple-testing control | Lab runs on its own |
| **6. Dashboard & reports** | Streamlit dashboard, leaderboard (candidates vs. validated), auto reports in git | Understandable progress at a glance |
| **7. High-fidelity simulation** | Port survivors to NautilusTrader; tick-level scalping tests with latency | Realistic execution estimates |
| **8. Paper trading** | *With your permission:* free paper accounts (Alpaca / OANDA practice / exchange testnet) | Forward performance on truly unseen data |
| **9. Expansion** | Options, paid data where justified, portfolio of uncorrelated strategies, account-size studies | Broader search |

---

## E. Installation requirements

**For you, right now: nothing.** The lab runs inside this cloud environment, and
everything needed is free and installable automatically.

What the project requires technically:

- Python 3.12+ and **uv** (package manager) — installed automatically.
- Git — already present.
- Disk: ~5–20 GB for the initial free datasets (1-minute crypto, FX ticks for a
  few pairs, daily equities). Tick data for many symbols can grow to 100+ GB.
- RAM: 8 GB minimum, 16 GB comfortable.
- Optional later: Docker (for running the dashboard/paper trader 24/7).

**An important practical point:** this cloud container is temporary. Code,
documents and the research registry are saved to GitHub, so nothing important
is lost. Market data is *not* stored in git (too large), so every dataset is
fetched by a script and can be re-downloaded deterministically. For long
unattended research runs and paper trading we will eventually want an
always-on machine — see decision #1 in section H.

---

## F. Estimated ongoing costs

| Item | Phase 0–6 | Later (optional, needs approval) |
|---|---|---|
| Software & libraries | $0 | $0 |
| Data (crypto, FX, daily equities, macro) | $0 | $0 |
| Futures data (Databento) | $0 (signup credit may cover first studies) | ~$10–50/month usage, only if futures look promising |
| Equity data (survivorship-free or full intraday) | $0 | ~$25–55/month, only if stock research becomes a focus |
| Options data | $0 (deferred) | ~$30–200/month |
| Compute | $0 (this environment or your computer) | ~$5–25/month for a small always-on cloud server, *or* $0 on a home computer |
| LLM-assisted hypothesis generation (Claude API) | $0 (not required — rule-based generator first) | ~$5–30/month if enabled, with a hard spending cap |
| Paper trading accounts | $0 | $0 (Alpaca paper, OANDA practice, exchange testnets are free) |

**Realistic total: $0/month for the first several phases; ~$10–60/month once
the lab is mature, and only for components that have proven they are worth it.**

---

## G. Biggest technical and financial risks

### Technical risks

1. **False discoveries (the #1 risk).** Testing many ideas guarantees some look
   great by luck. *Mitigation:* the research protocol — pre-registration, trial
   counting, deflated Sharpe, PBO, holdout vault, paper trading.
2. **Look-ahead bias and data leakage.** One subtle bug (e.g. using today's
   close to decide today's trade) creates fantasy profits. *Mitigation:*
   point-in-time feature design, next-bar execution enforced by the engine,
   automated "shuffle the future" tests, and suspicion of any result that looks
   too good.
3. **Unrealistic execution, especially for scalping.** Small-profit strategies
   are destroyed by spreads, fees, partial fills and latency. *Mitigation:*
   conservative cost models, 2× cost stress tests, tick-level simulation with
   latency before any scalping strategy is called a candidate.
4. **Bad or biased data.** Free data has gaps, errors and survivorship bias.
   *Mitigation:* automated quality checks, cross-checking sources, avoiding
   individual-stock studies on survivorship-biased data.
5. **Ephemeral compute.** This container is temporary. *Mitigation:* everything
   important is committed to git; data is re-downloadable.
6. **Complexity creep.** Building too much infrastructure before learning
   anything. *Mitigation:* phased plan; real research begins in Phase 4.
7. **Data access changes.** Free sources can change terms, rate-limit, or block
   regions. *Mitigation:* multiple sources per market; cached raw downloads.

### Financial risks

1. **No robust edge may be found.** This is the most likely outcome for most
   ideas, and possibly overall. Markets are competitive; professional firms
   with far more resources target the same inefficiencies, especially in
   scalping. The lab's value is that it tells us the truth cheaply, before any
   money is at risk.
2. **Edges decay.** Strategies that worked historically often stop working.
   Paper trading and ongoing monitoring are required.
3. **Small-account economics.** With $5,000, fixed costs and minimum position
   sizes matter. US stock day trading in margin accounts has historically
   required $25,000 under the Pattern Day Trader rule (FINRA has been revising
   this rule — current status will be verified before any paper/live phase).
   Micro futures, FX and crypto allow small sizes but involve leverage.
4. **Leverage and tail risk.** Strategies with high win rates often hide rare,
   very large losses. *Mitigation:* drawdown, tail and stress metrics are
   mandatory; win rate alone is never a promotion criterion.
5. **Over-confidence.** A beautiful equity curve is persuasive. The dashboard
   deliberately separates "promising" from "validated" and shows confidence
   levels and weaknesses for every strategy.

---

## H. First actions recommended

**I will do next (no approval needed — routine research engineering):**

1. Set up the Python environment and core package skeleton (done in this commit:
   folder structure, docs, research protocol, registry schema).
2. Build free data ingestors: BTC/ETH (Binance 1-minute bars and trades),
   EUR/USD & USD/JPY (Dukascopy ticks), SPY/QQQ/IWM + sector ETFs (daily),
   VIX and rates (FRED). Add data-quality reports.
3. Build the vectorized engine, cost models and metrics, with known-answer tests.
4. Build the validation toolkit and run the **calibration test**: feed the
   pipeline thousands of random strategies and confirm it rejects them at the
   expected rate. If it promotes random strategies, the filters are broken.
5. Then begin real research with a first batch of hand-designed hypotheses
   (opening-range behaviour, volatility-expansion continuation, short-term
   overreaction reversal, crypto funding-rate effects, cross-asset lead/lag).

**Decisions I will need from you later (not now):**

1. **Where to run long-term** (Phase 5+): your own computer vs. a ~$5–25/month
   cloud server. Either works.
2. **Free account creation** (Phase 1–2): permission to use free data accounts
   that require sign-up (Alpaca, Tiingo, FRED API key, Databento free credit).
   No payment details needed for most.
3. **Optional Claude API budget** for LLM-assisted hypothesis generation, with a
   monthly cap.
4. **Paper trading accounts** (Phase 8).

No live trading, brokerage connection or purchase will happen without your
explicit permission.

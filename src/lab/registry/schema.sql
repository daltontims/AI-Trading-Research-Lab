-- Research registry schema (SQLite).
-- Every hypothesis, experiment and trial is recorded, including failures.
-- Trial counts feed the multiple-testing corrections (Deflated Sharpe, BH-FDR).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS hypotheses (
    id              TEXT PRIMARY KEY,          -- e.g. H-000123
    parent_id       TEXT REFERENCES hypotheses(id),  -- set when rules were revised
    family          TEXT NOT NULL,             -- groups related variants for trial counting
    title           TEXT NOT NULL,
    question        TEXT NOT NULL,             -- plain-language research question
    rationale       TEXT,                      -- why this might work (economic story)
    source          TEXT NOT NULL,             -- 'manual' | 'generator' | 'llm' | 'literature'
    asset_classes   TEXT NOT NULL,             -- JSON list
    instruments     TEXT NOT NULL,             -- JSON list
    timeframe       TEXT NOT NULL,             -- 'tick' | '1m' | '5m' | '1h' | '1d' ...
    style           TEXT,                      -- scalping | intraday | swing | mean_reversion ...
    spec            TEXT NOT NULL,             -- JSON: event/condition, entry, exit, stop, sizing
    param_space     TEXT,                      -- JSON: allowed parameter ranges
    trial_budget    INTEGER NOT NULL DEFAULT 50,
    status          TEXT NOT NULL DEFAULT 'IDEA',
        -- IDEA | EFFECT | SCREENED | CANDIDATE | VALIDATED | PAPER | PAPER_PASSED | REJECTED
    rejection_reason TEXT,
    confidence      TEXT,                      -- very_low | low | moderate | high
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS experiments (
    id              TEXT PRIMARY KEY,          -- e.g. E-000456
    hypothesis_id   TEXT NOT NULL REFERENCES hypotheses(id),
    stage           TEXT NOT NULL,             -- event_study | screen | walk_forward | validation | robustness | vault | event_driven | paper
    data_split      TEXT NOT NULL,             -- development | validation | vault | live_paper
    git_commit      TEXT NOT NULL,
    data_fingerprint TEXT NOT NULL,            -- hash of the data snapshot used
    config          TEXT NOT NULL,             -- JSON: full experiment config incl. cost model
    seed            INTEGER,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    outcome         TEXT,                      -- pass | fail | error | diagnostic
    notes           TEXT
);

-- One row per backtest run / parameter set. Never deleted.
CREATE TABLE IF NOT EXISTS trials (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id   TEXT NOT NULL REFERENCES experiments(id),
    params          TEXT NOT NULL,             -- JSON
    n_trades        INTEGER,
    win_rate        REAL,
    profit_factor   REAL,
    expectancy      REAL,                      -- per trade, account currency, after costs
    net_return      REAL,
    max_drawdown    REAL,
    sharpe          REAL,
    sortino         REAL,
    cost_share      REAL,                      -- costs / gross profit
    metrics         TEXT,                      -- JSON: full metric set
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Statistical test results attached to an experiment.
CREATE TABLE IF NOT EXISTS stat_tests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id   TEXT NOT NULL REFERENCES experiments(id),
    test            TEXT NOT NULL,             -- deflated_sharpe | pbo | spa | bh_fdr | bootstrap ...
    statistic       REAL,
    p_value         REAL,
    passed          INTEGER,                   -- 0/1
    details         TEXT                       -- JSON
);

-- Audit trail of promotions/rejections.
CREATE TABLE IF NOT EXISTS status_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_id   TEXT NOT NULL REFERENCES hypotheses(id),
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    reason          TEXT NOT NULL,
    experiment_id   TEXT REFERENCES experiments(id),
    changed_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Vault access is logged separately: each strategy may open the vault once.
CREATE TABLE IF NOT EXISTS vault_access (
    hypothesis_id   TEXT PRIMARY KEY REFERENCES hypotheses(id),
    experiment_id   TEXT NOT NULL REFERENCES experiments(id),
    opened_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_hyp_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_hyp_family ON hypotheses(family);
CREATE INDEX IF NOT EXISTS idx_exp_hyp ON experiments(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_trial_exp ON trials(experiment_id);

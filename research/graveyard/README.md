# Graveyard

Rejected hypotheses and why. Failures are data: they stop us re-testing dead ideas and they count towards multiple-testing corrections.

| ID | Hypothesis | Failed gates |
|---|---|---|
| H4-01 | BTC hourly time-series momentum | net_profit_after_costs: -0.958; profit_factor: 0.835; profitable_at_2x_costs: -0.999; deflated_sharpe: 0.000; spa: 1.000; walk_forward_oos_sharpe: -0.750; walk_forward_positive_windows: 0.286; parameter_plateau: n/a; years_positive: 0.200; profitable_without_best_year: -0.959 |
| H4-03 | ETH daily trend filter (long/flat) | deflated_sharpe: 0.750; pbo: 0.794 |
| H4-04 | BTC+ETH 4-hour channel breakout (long/short) | net_profit_after_costs: -0.014; profit_factor: 0.993; profitable_at_2x_costs: -0.531; deflated_sharpe: 0.176; spa: 0.610; walk_forward_oos_sharpe: -0.475; walk_forward_positive_windows: 0.286; parameter_plateau: -6.286; years_positive: 0.400; profitable_without_best_year: -0.177 |
| H4-05 | BTC hourly overreaction reversal | net_profit_after_costs: -0.812; profit_factor: 0.508; profitable_at_2x_costs: -0.961; deflated_sharpe: 0.000; spa: 1.000; walk_forward_oos_sharpe: -1.056; walk_forward_positive_windows: 0.286; parameter_plateau: n/a; years_positive: 0.000; profitable_without_best_year: -0.787 |
| H4-06 | BTC funding-rate contrarian carry | min_trades: 6; deflated_sharpe: 0.520; spa: 0.296; walk_forward_positive_windows: 0.286; parameter_plateau: -0.398 |
| H4-07 | BTC time-of-day session effect | net_profit_after_costs: -0.991; profit_factor: 0.760; profitable_at_2x_costs: -0.999; deflated_sharpe: 0.000; spa: 1.000; walk_forward_oos_sharpe: -2.415; walk_forward_positive_windows: 0.143; parameter_plateau: n/a; years_positive: 0.000; profitable_without_best_year: -0.989 |
| H4-08 | BTC weekend drift (long) | net_profit_after_costs: -0.417; profit_factor: 0.844; profitable_at_2x_costs: -0.749; deflated_sharpe: 0.124; spa: 1.000; years_positive: 0.400; profitable_without_best_year: -0.487 |
| H4-09 | BTC daily volatility breakout (intraday) | net_profit_after_costs: -0.497; profit_factor: 0.918; profitable_at_2x_costs: -0.947; deflated_sharpe: 0.077; spa: 1.000; walk_forward_oos_sharpe: -0.664; walk_forward_positive_windows: 0.000; parameter_plateau: n/a; years_positive: 0.200; profitable_without_best_year: -0.693 |
| H4-10 | BTC 15-minute volume-shock continuation | net_profit_after_costs: -0.574; profit_factor: 0.626; profitable_at_2x_costs: -0.884; deflated_sharpe: 0.000; spa: 1.000; walk_forward_oos_sharpe: -1.566; walk_forward_positive_windows: 0.000; parameter_plateau: n/a; years_positive: 0.000; profitable_without_best_year: -0.544 |
| H4-11 | ETH follows BTC (lead-lag) | net_profit_after_costs: -0.973; profit_factor: 0.394; profitable_at_2x_costs: -0.999; deflated_sharpe: 0.000; spa: 1.000; walk_forward_oos_sharpe: -3.717; walk_forward_positive_windows: 0.000; parameter_plateau: n/a; years_positive: 0.000; profitable_without_best_year: -0.953 |
| H4-12 | ETH/BTC ratio mean reversion (pairs) | net_profit_after_costs: -0.458; profit_factor: 0.827; profitable_at_2x_costs: -0.575; deflated_sharpe: 0.054; spa: 1.000; walk_forward_oos_sharpe: -0.103; walk_forward_positive_windows: 0.429; parameter_plateau: n/a; years_positive: 0.200; profitable_without_best_year: -0.469 |
| H4-13 | BTC daily time-series momentum (long/short) | deflated_sharpe: 0.890; pbo: 0.405 |
| H4-14 | SPY trend filter (long/flat) | pbo: 0.236 |
| H4-15 | Sector ETF momentum rotation | deflated_sharpe: 0.764 |
| H4-16 | Dual momentum SPY/TLT/GLD | deflated_sharpe: 0.926; walk_forward_positive_windows: 0.383; years_positive: 0.360 |
| H4-18 | SPY turn-of-the-month | profitable_at_2x_costs: -0.095; deflated_sharpe: 0.191; spa: 0.544; walk_forward_oos_sharpe: -0.011; walk_forward_positive_windows: 0.234; parameter_plateau: -0.942; years_positive: 0.320; profitable_without_best_year: -0.098 |
| H4-19 | SPY with VIX term-structure filter | deflated_sharpe: 0.908; walk_forward_positive_windows: 0.255; years_positive: 0.320 |
| H4-20 | Buy SPY after VIX spikes | deflated_sharpe: 0.782; spa: 0.056 |
| H4-21 | SPY low-volatility regime | deflated_sharpe: 0.756; parameter_plateau: 0.463 |
| H4-02 | BTC daily trend filter (long/flat) | passed development + validation; **failed the final vault test** (−1.0%, PF 0.97, PSR 0.54) |

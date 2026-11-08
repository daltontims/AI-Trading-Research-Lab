"""Compiled bar-by-bar portfolio simulator (Numba).

This is the single source of truth for fills and accounting. Higher-level code
(`lab.engine.backtest`) prepares arrays and interprets the results.

Timeline inside each bar t, for every instrument with a bar at t:

  OPEN    1. dividends credited/debited (ex-date bars)
          2. pending EXIT orders fill at the open (signals from an earlier bar)
          3. pending ENTRY orders fill at the open, highest priority first,
             subject to buying power, position and exposure limits
  INTRABAR 4. stop / trailing stop / profit target checked against high & low
             - gap through the stop at the open  -> filled at the open (worse)
             - stop and target both inside the bar -> STOP assumed first (pessimistic)
             - target needs price to trade through it by the half-spread; filled
               at the target, never better (no favourable gap fills)
  CLOSE   5. funding (perpetuals), borrow (shorts), financing charged
          6. trailing extremes updated with this bar's high/low (used from the NEXT bar)
          7. equity marked to market at the close
          8. portfolio risk limits checked -> flatten orders for the next bar
          9. signals computed from bars <= t become orders for bar t+delay

Signals at bar t can therefore never fill at bar t's prices: the earliest fill is
the open of the next bar on which the instrument actually trades (gaps/missing bars
are skipped, never interpolated).

Prices: executed = reference × (1 ± (half_spread + slippage)); slippage uses the
signal bar's range (known at decision time), never the fill bar's.
"""

from __future__ import annotations

import numpy as np
from numba import njit

# Exit reason codes
EXIT_SIGNAL, EXIT_STOP, EXIT_TARGET, EXIT_TRAIL, EXIT_TIME, EXIT_DAILY, EXIT_MAXDD, EXIT_END = range(8)
EXIT_REASONS = ["signal", "stop", "target", "trailing_stop", "time", "daily_loss_limit",
                "max_drawdown_limit", "end_of_data"]

# Skipped-entry reason codes
SKIP_NO_STOP, SKIP_SIZE, SKIP_LIQUIDITY, SKIP_RISK_BLOCK, SKIP_MAX_POS, SKIP_NO_SHORT, SKIP_CONFLICT = range(7)
SKIP_REASONS = ["no_stop_for_risk_sizing", "below_min_size_or_buying_power", "no_liquidity",
                "risk_limit_block", "max_open_positions", "short_not_allowed", "conflicting_signals"]

SIZING_RISK, SIZING_PCT_EQUITY, SIZING_FIXED_NOTIONAL = 0, 1, 2

# Trade record columns
(T_INST, T_SIDE, T_ENTRY_IDX, T_EXIT_IDX, T_QTY, T_ENTRY_REF, T_ENTRY_PX, T_EXIT_REF, T_EXIT_PX,
 T_FEES, T_CARRY, T_PNL_GROSS, T_PNL_NET, T_INIT_RISK, T_REASON, T_BARS, T_NOTIONAL) = range(17)
N_TRADE_COLS = 17


@njit(cache=True)
def _round_lot(q, lot):
    if lot > 0.0:
        return np.floor(q / lot + 1e-9) * lot
    return q


@njit(cache=True)
def _fee(notional, qty, is_sell, fee_frac, sell_fee_frac, fee_unit, min_fee):
    f = notional * fee_frac + abs(qty) * fee_unit
    if is_sell:
        f += notional * sell_fee_frac
    if f < min_fee:
        f = min_fee
    return f


@njit(cache=True)
def simulate(
    day_id, dt_years,
    open_, high, low, close, volume, valid, half_spread, funding, dividend,
    entry_long, entry_short, exit_long, exit_short, stop_dist, target_dist, trail_dist, priority,
    mult, lot, min_notional, fee_frac, maker_fee_frac, sell_fee_frac, fee_unit, min_fee,
    slip_frac, slip_range, allow_short, borrow_rate, financing_rate, max_part,
    initial_cash, sizing_mode, risk_per_trade, position_pct, fixed_notional,
    max_position_pct, max_gross_exposure, max_open_positions, max_daily_loss, max_drawdown,
    max_bars_held, delay, max_trades,
):
    T, N = close.shape

    equity = np.empty(T)
    cash_hist = np.empty(T)
    gross_exp = np.empty(T)
    net_exp = np.empty(T)
    n_pos_hist = np.zeros(T, dtype=np.int64)
    trades = np.full((max_trades, N_TRADE_COLS), np.nan)
    skipped = np.zeros(7, dtype=np.int64)
    n_trades = 0
    traded_notional = 0.0
    total_fees = 0.0
    total_carry = 0.0
    total_spread_slip = 0.0

    cash = initial_cash
    pos = np.zeros(N)
    entry_px = np.zeros(N)
    entry_ref = np.zeros(N)
    entry_idx = np.zeros(N, dtype=np.int64)
    entry_fee = np.zeros(N)
    carry = np.zeros(N)
    stop_lvl = np.full(N, np.nan)
    target_lvl = np.full(N, np.nan)
    trail_d = np.full(N, np.nan)
    extreme = np.zeros(N)
    bars_held = np.zeros(N, dtype=np.int64)
    init_risk = np.zeros(N)
    last_px = np.full(N, np.nan)
    last_range = np.zeros(N)

    pend_side = np.zeros(N, dtype=np.int64)
    pend_wait = np.zeros(N, dtype=np.int64)
    pend_qty = np.zeros(N)
    pend_stop = np.full(N, np.nan)
    pend_target = np.full(N, np.nan)
    pend_trail = np.full(N, np.nan)
    pend_prio = np.zeros(N)
    pend_exit = np.zeros(N, dtype=np.bool_)
    pend_exit_wait = np.zeros(N, dtype=np.int64)
    pend_exit_reason = np.zeros(N, dtype=np.int64)

    peak = initial_cash
    eq_prev = initial_cash
    day_start_eq = initial_cash
    cur_day = day_id[0]
    halted = False
    day_block = False

    for t in range(T):
        if day_id[t] != cur_day:
            cur_day = day_id[t]
            day_start_eq = eq_prev
            day_block = False

        # ---------------- OPEN: dividends and exits ----------------
        for i in range(N):
            if not valid[t, i]:
                continue
            if pos[i] != 0.0 and dividend[t, i] != 0.0:
                d = pos[i] * dividend[t, i] * mult[i]
                cash += d
                carry[i] += d
            if pend_exit[i]:
                pend_exit_wait[i] -= 1
                if pend_exit_wait[i] <= 0:
                    pend_exit[i] = False
                    if pos[i] != 0.0:
                        ref = open_[t, i]
                        side = 1.0 if pos[i] > 0 else -1.0
                        px = ref * (1.0 - side * (half_spread[t, i] + slip_frac[i] + slip_range[i] * last_range[i]))
                        q = abs(pos[i])
                        n_trades, xfee = _close(t, i, px, ref, pend_exit_reason[i], False, pos, entry_px,
                                                entry_ref, entry_idx, entry_fee, carry, init_risk, bars_held,
                                                mult, fee_frac, maker_fee_frac, sell_fee_frac, fee_unit, min_fee,
                                                trades, n_trades, max_trades)
                        cash += side * q * px * mult[i] - xfee
                        traded_notional += q * px * mult[i]
                        total_spread_slip += q * abs(ref - px) * mult[i]

        # ---------------- OPEN: entries (priority order) ----------------
        n_cand = 0
        cand = np.empty(N, dtype=np.int64)
        for i in range(N):
            if valid[t, i] and pend_side[i] != 0:
                pend_wait[i] -= 1
                if pend_wait[i] <= 0:
                    cand[n_cand] = i
                    n_cand += 1
        if n_cand > 0:
            prio = np.empty(n_cand)
            for k in range(n_cand):
                prio[k] = -pend_prio[cand[k]]
            order = np.argsort(prio, kind="mergesort")
            for k in range(n_cand):
                i = cand[order[k]]
                side_i = pend_side[i]
                pend_side[i] = 0
                if halted or day_block:
                    skipped[SKIP_RISK_BLOCK] += 1
                    continue
                if pos[i] != 0.0:
                    continue  # still in a position (exit did not happen); ignore entry
                n_open = 0
                for j in range(N):
                    if pos[j] != 0.0:
                        n_open += 1
                if n_open >= max_open_positions:
                    skipped[SKIP_MAX_POS] += 1
                    continue
                ref = open_[t, i]
                side = float(side_i)
                px = ref * (1.0 + side * (half_spread[t, i] + slip_frac[i] + slip_range[i] * last_range[i]))
                # Mark-to-market at current opens where available.
                eq_now = cash
                gross_now = 0.0
                for j in range(N):
                    if pos[j] != 0.0:
                        pj = open_[t, j] if valid[t, j] else last_px[j]
                        eq_now += pos[j] * pj * mult[j]
                        gross_now += abs(pos[j]) * pj * mult[j]
                q = pend_qty[i]
                cap_pos = max_position_pct * eq_now / (px * mult[i])
                cap_gross = (max_gross_exposure * eq_now - gross_now) / (px * mult[i])
                if q > cap_pos:
                    q = cap_pos
                if q > cap_gross:
                    q = cap_gross
                if side > 0 and max_gross_exposure <= 1.0:
                    # No leverage: a long must be paid for with cash (incl. the fee).
                    cash_cap = cash / (px * mult[i] * (1.0 + fee_frac[i]) + fee_unit[i])
                    if q > cash_cap:
                        q = cash_cap
                q = _round_lot(q, lot[i])
                notional = q * px * mult[i]
                if q <= 0.0 or notional < min_notional[i] or notional <= 0.0:
                    skipped[SKIP_SIZE] += 1
                    continue
                fee = _fee(notional, q, side < 0, fee_frac[i], sell_fee_frac[i], fee_unit[i], min_fee[i])
                if side > 0 and max_gross_exposure <= 1.0 and notional + fee > cash + 1e-9:
                    skipped[SKIP_SIZE] += 1
                    continue
                cash -= side * notional + fee
                pos[i] = side * q
                entry_px[i] = px
                entry_ref[i] = ref
                entry_idx[i] = t
                entry_fee[i] = fee
                carry[i] = 0.0
                bars_held[i] = 0
                extreme[i] = ref
                sd = pend_stop[i]
                stop_lvl[i] = px - side * sd if sd == sd and sd > 0 else np.nan
                td = pend_target[i]
                target_lvl[i] = px + side * td if td == td and td > 0 else np.nan
                trail_d[i] = pend_trail[i] if pend_trail[i] == pend_trail[i] and pend_trail[i] > 0 else np.nan
                init_risk[i] = q * sd * mult[i] if sd == sd and sd > 0 else np.nan
                traded_notional += notional
                total_spread_slip += q * abs(px - ref) * mult[i]

        # ---------------- INTRABAR: stops, trailing stops, targets ----------------
        for i in range(N):
            if not valid[t, i] or pos[i] == 0.0:
                continue
            side = 1.0 if pos[i] > 0 else -1.0
            hs = half_spread[t, i]
            o = open_[t, i]
            h = high[t, i]
            lo = low[t, i]
            # Effective protective stop: the tighter of fixed stop and trailing stop.
            s = stop_lvl[i]
            reason = EXIT_STOP
            if trail_d[i] == trail_d[i]:
                tl = extreme[i] - side * trail_d[i]
                if s != s or (side > 0 and tl > s) or (side < 0 and tl < s):
                    s = tl
                    reason = EXIT_TRAIL
            tg = target_lvl[i]
            exit_ref = np.nan
            exit_reason = -1
            is_limit = False
            if s == s:
                if (side > 0 and o <= s) or (side < 0 and o >= s):
                    exit_ref = o  # gapped through the stop: filled at the (worse) open
                    exit_reason = reason
                elif (side > 0 and lo <= s) or (side < 0 and h >= s):
                    exit_ref = s  # stop wins even if the target was also touched
                    exit_reason = reason
            if exit_reason < 0 and tg == tg:
                if (side > 0 and h >= tg * (1.0 + hs)) or (side < 0 and lo <= tg * (1.0 - hs)):
                    exit_ref = tg
                    exit_reason = EXIT_TARGET
                    is_limit = True
            if exit_reason >= 0:
                if is_limit:
                    px = exit_ref
                else:
                    px = exit_ref * (1.0 - side * (hs + slip_frac[i] + slip_range[i] * last_range[i]))
                q = abs(pos[i])
                n_trades, xfee = _close(t, i, px, exit_ref, exit_reason, is_limit, pos, entry_px, entry_ref,
                                        entry_idx, entry_fee, carry, init_risk, bars_held, mult, fee_frac,
                                        maker_fee_frac, sell_fee_frac, fee_unit, min_fee, trades, n_trades,
                                        max_trades)
                cash += side * q * px * mult[i] - xfee
                traded_notional += q * px * mult[i]
                total_spread_slip += q * abs(exit_ref - px) * mult[i]
                pend_exit[i] = False

        # ---------------- CLOSE: carry, extremes, time exits ----------------
        for i in range(N):
            if not valid[t, i]:
                continue
            c = close[t, i]
            last_px[i] = c
            last_range[i] = (high[t, i] - low[t, i]) / c if c > 0 else 0.0
            if pos[i] == 0.0:
                continue
            notional = abs(pos[i]) * c * mult[i]
            ch = 0.0
            if funding[t, i] != 0.0:
                ch -= pos[i] * open_[t, i] * mult[i] * funding[t, i]  # longs pay positive funding
            if pos[i] < 0:
                ch -= notional * borrow_rate[i] * dt_years[t]
            ch -= notional * financing_rate[i] * dt_years[t]
            cash += ch
            carry[i] += ch
            if pos[i] > 0:
                if high[t, i] > extreme[i]:
                    extreme[i] = high[t, i]
            else:
                if low[t, i] < extreme[i]:
                    extreme[i] = low[t, i]
            bars_held[i] += 1
            if max_bars_held > 0 and bars_held[i] >= max_bars_held and not pend_exit[i]:
                pend_exit[i] = True
                pend_exit_wait[i] = delay
                pend_exit_reason[i] = EXIT_TIME

        # ---------------- mark to market ----------------
        eq = cash
        g = 0.0
        ne = 0.0
        npos = 0
        for i in range(N):
            if pos[i] != 0.0:
                v = pos[i] * last_px[i] * mult[i]
                eq += v
                g += abs(v)
                ne += v
                npos += 1
        equity[t] = eq
        cash_hist[t] = cash
        gross_exp[t] = g / eq if eq > 0 else 0.0
        net_exp[t] = ne / eq if eq > 0 else 0.0
        n_pos_hist[t] = npos
        eq_prev = eq

        # ---------------- portfolio risk limits ----------------
        if eq > peak:
            peak = eq
        flatten_reason = -1
        if max_drawdown > 0.0 and not halted and eq <= peak * (1.0 - max_drawdown):
            halted = True
            flatten_reason = EXIT_MAXDD
        elif max_daily_loss > 0.0 and not day_block and eq <= day_start_eq * (1.0 - max_daily_loss):
            day_block = True
            flatten_reason = EXIT_DAILY
        if flatten_reason >= 0:
            for i in range(N):
                pend_side[i] = 0
                if pos[i] != 0.0:
                    pend_exit[i] = True
                    pend_exit_wait[i] = delay
                    pend_exit_reason[i] = flatten_reason

        # ---------------- signals -> orders for a later bar ----------------
        for i in range(N):
            if not valid[t, i]:
                continue
            if pos[i] > 0 and exit_long[t, i] and not pend_exit[i]:
                pend_exit[i] = True
                pend_exit_wait[i] = delay
                pend_exit_reason[i] = EXIT_SIGNAL
            elif pos[i] < 0 and exit_short[t, i] and not pend_exit[i]:
                pend_exit[i] = True
                pend_exit_wait[i] = delay
                pend_exit_reason[i] = EXIT_SIGNAL
            el = entry_long[t, i]
            es = entry_short[t, i]
            if not (el or es):
                continue
            if el and es:
                skipped[SKIP_CONFLICT] += 1
                continue
            if es and not allow_short[i]:
                skipped[SKIP_NO_SHORT] += 1
                continue
            if halted or day_block:
                skipped[SKIP_RISK_BLOCK] += 1
                continue
            side_i = 1 if el else -1
            if pend_side[i] != 0:
                continue  # an entry is already waiting
            if (pos[i] > 0 and side_i > 0) or (pos[i] < 0 and side_i < 0):
                continue  # already positioned this way
            if pos[i] != 0.0 and not pend_exit[i]:
                # Reversal: close the current position first, at the same time.
                pend_exit[i] = True
                pend_exit_wait[i] = delay
                pend_exit_reason[i] = EXIT_SIGNAL
            c = close[t, i]
            sd = stop_dist[t, i]
            if sizing_mode == SIZING_RISK:
                if not (sd == sd and sd > 0):
                    skipped[SKIP_NO_STOP] += 1
                    continue
                q = eq * risk_per_trade / (sd * mult[i])
            elif sizing_mode == SIZING_PCT_EQUITY:
                q = eq * position_pct / (c * mult[i])
            else:
                q = fixed_notional / (c * mult[i])
            if max_part[i] < 1.0:
                vcap = max_part[i] * volume[t, i]
                if vcap <= 0.0:
                    skipped[SKIP_LIQUIDITY] += 1
                    continue
                if q > vcap:
                    q = vcap
            pend_side[i] = side_i
            pend_wait[i] = delay
            pend_qty[i] = q
            pend_stop[i] = sd
            pend_target[i] = target_dist[t, i]
            pend_trail[i] = trail_dist[t, i]
            pend_prio[i] = priority[t, i]

    # ---------------- end of data: liquidate at last close, with costs ----------------
    for i in range(N):
        if pos[i] != 0.0:
            side = 1.0 if pos[i] > 0 else -1.0
            ref = last_px[i]
            px = ref * (1.0 - side * (half_spread[T - 1, i] + slip_frac[i] + slip_range[i] * last_range[i]))
            q = abs(pos[i])
            n_trades, xfee = _close(T - 1, i, px, ref, EXIT_END, False, pos, entry_px, entry_ref, entry_idx,
                                    entry_fee, carry, init_risk, bars_held, mult, fee_frac, maker_fee_frac,
                                    sell_fee_frac, fee_unit, min_fee, trades, n_trades, max_trades)
            cash += side * q * px * mult[i] - xfee
            traded_notional += q * px * mult[i]
            total_spread_slip += q * abs(ref - px) * mult[i]
    if T > 0:
        equity[T - 1] = cash
        cash_hist[T - 1] = cash
        gross_exp[T - 1] = 0.0
        net_exp[T - 1] = 0.0
        n_pos_hist[T - 1] = 0

    n_rec = min(n_trades, max_trades)
    for k in range(n_rec):
        total_fees += trades[k, T_FEES]
        total_carry += trades[k, T_CARRY]

    stats = np.array([traded_notional, total_fees, total_carry, total_spread_slip, float(n_trades)])
    return equity, cash_hist, gross_exp, net_exp, n_pos_hist, trades[:n_rec], skipped, stats


@njit(cache=True)
def _close(t, i, px, ref, reason, is_limit, pos, entry_px, entry_ref, entry_idx, entry_fee, carry, init_risk,
           bars_held, mult, fee_frac, maker_fee_frac, sell_fee_frac, fee_unit, min_fee, trades, n_trades,
           max_trades):
    """Close position i at executed price px. Writes a trade record.

    Returns (new trade count, exit fee). The caller books the cash flow.
    """
    q = pos[i]
    side = 1.0 if q > 0 else -1.0
    aq = abs(q)
    notional = aq * px * mult[i]
    ff = maker_fee_frac[i] if is_limit else fee_frac[i]
    exit_fee = _fee(notional, aq, side > 0, ff, sell_fee_frac[i], fee_unit[i], min_fee[i])
    if n_trades < max_trades:
        r = trades[n_trades]
        r[T_INST] = i
        r[T_SIDE] = side
        r[T_ENTRY_IDX] = entry_idx[i]
        r[T_EXIT_IDX] = t
        r[T_QTY] = aq
        r[T_ENTRY_REF] = entry_ref[i]
        r[T_ENTRY_PX] = entry_px[i]
        r[T_EXIT_REF] = ref
        r[T_EXIT_PX] = px
        r[T_FEES] = entry_fee[i] + exit_fee
        r[T_CARRY] = carry[i]
        r[T_PNL_GROSS] = side * aq * (ref - entry_ref[i]) * mult[i]
        r[T_PNL_NET] = side * aq * (px - entry_px[i]) * mult[i] - entry_fee[i] - exit_fee + carry[i]
        r[T_INIT_RISK] = init_risk[i]
        r[T_REASON] = reason
        r[T_BARS] = bars_held[i]
        r[T_NOTIONAL] = aq * entry_px[i] * mult[i]
    pos[i] = 0.0
    carry[i] = 0.0
    return n_trades + 1, exit_fee

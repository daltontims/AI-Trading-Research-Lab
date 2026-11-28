"""Plain-language report for a discovery batch: reports/discovery/<batch>.md."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

from lab.validation import stats

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports" / "discovery"


def _p(v, pct=True, d=1):
    if v is None or (isinstance(v, float) and v != v):
        return "–"
    return f"{v:.{d}%}" if pct else f"{v:.{d}f}"


def write_report(batch: str, hs: list[dict], tests: list[dict], results: list[dict], reg) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    n_eff = len(results)
    verdicts = Counter(r["verdict"] for r in results)
    cands = sorted([r for r in results if r["verdict"] == "CANDIDATE"], key=lambda r: -(r["dev"]["sharpe"] or 0))
    screened = sorted([r for r in results if r["verdict"] == "SCREENED"], key=lambda r: -(r["dev"]["sharpe"] or 0))
    ok = [r for r in results if r.get("spa_p") is not None]
    q = dict(zip([r["id"] for r in ok], stats.bh_adjusted([r["spa_p"] for r in ok]))) if ok else {}
    lines = [
        f"# Discovery batch {batch}", "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by the discovery engine "
        "(`src/lab/discovery/`, docs/DISCOVERY.md). Development data only for the search; the validation "
        "split was opened once, only for ideas passing every development gate. The vault was not touched.*", "",
        "## Funnel", "",
        "| Stage | Count | What it means |", "|---|---|---|",
        f"| Ideas generated and pre-registered | {len(hs)} | every rule x instrument combination |",
        f"| Event-study tests | {len(tests)} | each entry condition x parameter x filter x instrument |",
        f"| Ideas with a real-looking effect (EFFECT) | {n_eff} | false-discovery rate held at 5% across all tests |",
        f"| Rejected in the full test | {verdicts.get('REJECTED', 0)} | failed at least one gate |",
        f"| Screened (passed development, failed validation or not opened) | {verdicts.get('SCREENED', 0)} | not an edge |",
        f"| **Candidates** (passed development and the one validation look) | **{len(cands)}** | promising, *not* validated |",
        f"| Errors | {verdicts.get('ERROR', 0)} | logged in research/discovery/{batch}/evaluations.jsonl |",
        "",
        "A *candidate* is still not a proven edge: it needs the one-time vault test before it can be paper traded.",
        "", "## Candidates", ""]
    if cands:
        lines += ["| ID | Idea | Params | Dev return | Dev Sharpe | Max DD | Trades | Buy & hold | Deflated Sharpe | "
                  "Batch FDR q | Validation return | Val Sharpe | Confidence |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in cands:
            d, v = r["dev"], r["val"] or {}
            lines.append(f"| [{r['id']}](../strategies/{r['id']}.md) | {r['title']} | `{r['best_params']}` | "
                         f"{_p(d['total_return'])} | {_p(d['sharpe'], False, 2)} | {_p(d['max_drawdown'])} | "
                         f"{d['trades']} | {_p(d['benchmark_total_return'])} | {_p(r['dsr'], False, 2)} | "
                         f"{_p(q.get(r['id']), False, 2)} | {_p(v.get('total_return'))} | "
                         f"{_p(v.get('sharpe'), False, 2)} | {r['confidence']} |")
    else:
        lines.append("None this batch.")
    lines += ["", "## Screened (passed development gates only)", ""]
    if screened:
        lines += ["| ID | Idea | Dev return | Dev Sharpe | Validation return | Why not a candidate |", "|---|---|---|---|---|---|"]
        for r in screened[:30]:
            lines.append(f"| [{r['id']}](../strategies/{r['id']}.md) | {r['title']} | {_p(r['dev']['total_return'])} | "
                         f"{_p(r['dev']['sharpe'], False, 2)} | {_p((r['val'] or {}).get('total_return'))} | "
                         f"{'; '.join(x.split(' (')[0] for x in r['reasons'][:2]) or '–'} |")
    else:
        lines.append("None.")
    # Cross-market replication: how many instruments show the same effect / pass the screen.
    fam = {}
    for r in results:
        f = fam.setdefault(r["family"], {"effect": 0, "screened": 0, "candidate": 0})
        f["effect"] += 1
        f["screened"] += r["verdict"] in ("SCREENED", "CANDIDATE")
        f["candidate"] += r["verdict"] == "CANDIDATE"
    lines += ["", "## Rule families (cross-market replication)", "",
              "An effect that shows up on many instruments is more believable than one that appears on a single one.",
              "", "| Family (entry : filter : exit) | Instruments with effect | Passed development | Candidates |",
              "|---|---|---|---|"]
    for k, f in sorted(fam.items(), key=lambda kv: (-kv[1]["candidate"], -kv[1]["screened"], -kv[1]["effect"])):
        lines.append(f"| `{k.removeprefix('disc:')}` | {f['effect']} | {f['screened']} | {f['candidate']} |")
    cnt = Counter(x.split(":")[0].split(" (")[0] for r in results if r["verdict"] == "REJECTED" for x in r["reasons"])
    lines += ["", "## Why ideas failed the full test", ""] + [f"- `{k}`: {v}" for k, v in cnt.most_common()]
    lines += ["", f"Registry trials so far: {reg.trial_count()}."]
    out = REPORTS / f"{batch}.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")
    return out

"""POST-HOC sensitivity analysis. Written AFTER the frozen results were observed; it does NOT alter
results.json and its numbers must never replace the frozen ones. Purpose: show how much the headline
depends on known scorer limitations found while auditing raw outputs.
"""
import json, re, statistics
from pathlib import Path
import scoring as S
H = Path(__file__).parent
res = json.loads((H / "results.json").read_text(encoding="utf-8"))
gt = json.loads((H / "ground_truth.json").read_text(encoding="utf-8"))
LABEL = re.compile(r"^[a-z]+(_[a-z0-9]+)+$")

def prose_only(resp):
    """Treat an action that is just a snake_case fix label (e.g. 'increase_postgres_pool_size') as not actionable prose."""
    r = dict(resp); r["first_actions"] = [a for a in resp["first_actions"] if not LABEL.match(a.strip())]; return r

out = {"note": "post-hoc, not frozen; see report.md 'Audit findings'", "actionability_prose_only": {}, "subsets": {}, "manual_adjudications": []}
act = {"A": [], "B": []}; label_only = {"A": 0, "B": 0}; comp = {"A": {}, "B": {}}
for e in res["per_case"]:
    raw = json.loads((H / "raw" / f"{e['case_id']}.json").read_text(encoding="utf-8"))
    for c in "AB":
        resp = raw[c]["response"]
        label_only[c] += sum(1 for a in resp["first_actions"] if LABEL.match(a.strip()))
        pa = S.score_actionability(prose_only(resp))["score"]; act[c].append(pa)
        s = e[c]["scores"]
        parts = [float(s["root_cause"]["specific"]), float(s["worked_fix"]["any_of_actions"]), float(s["unsupported_claims"]["clean"]), pa / 3.0]
        if s["failed_fix_avoidance"] is not None: parts.append(float(s["failed_fix_avoidance"]["avoided"]))
        comp[c][e["case_id"]] = sum(parts) / len(parts)
out["actionability_prose_only"] = {"A_mean": round(statistics.mean(act["A"]), 3), "B_mean": round(statistics.mean(act["B"]), 3),
    "label_only_actions_A": label_only["A"], "label_only_actions_B": label_only["B"], "frozen_A_mean": round(14/15, 3), "frozen_B_mean": round(32/15, 3)}
v = {cid: S.verdict(comp["A"][cid], comp["B"][cid]) for cid in comp["A"]}
out["composite_prose_only_actionability"] = {"A_mean": round(statistics.mean(comp["A"].values()), 4), "B_mean": round(statistics.mean(comp["B"].values()), 4),
    "wins": {k: list(v.values()).count(k) for k in ("recallops", "tie", "stateless")}}
for name, ids in {"demo_tuned_C01-C05": [f"C0{i}" for i in range(1, 6)], "authored_C06-C15": [f"C{i:02d}" for i in range(6, 16)]}.items():
    rows = [e for e in res["per_case"] if e["case_id"] in ids]
    m = lambda c, f: round(statistics.mean(f(e[c]["scores"]) for e in rows), 3)
    out["subsets"][name] = {"n": len(rows),
        "composite_A": round(statistics.mean(e["A"]["composite"] for e in rows), 3), "composite_B": round(statistics.mean(e["B"]["composite"] for e in rows), 3),
        "root_cause_specific_A": m("A", lambda s: s["root_cause"]["specific"]), "root_cause_specific_B": m("B", lambda s: s["root_cause"]["specific"]),
        "worked_fix_A": m("A", lambda s: s["worked_fix"]["any_of_actions"]), "worked_fix_B": m("B", lambda s: s["worked_fix"]["any_of_actions"]),
        "wins": {k: sum(1 for e in rows if e["verdict"] == k) for k in ("recallops", "tie", "stateless")}}
out["manual_adjudications"] = [
    {"case": "C01", "cond": "B", "metric": "root_cause_specific", "frozen": 0, "human": 1,
     "why": "Says the retry path 'never releases it on timeout' (leak + order-confirmation retry); frozen regex expects past-tense 'never released'."},
    {"case": "C09", "cond": "A", "metric": "failed_fix_avoidance", "frozen": 0, "human": 1,
     "why": "'Renew or replace the expired TLS certificate' then 'Restart auth-service' -- restart after renewal is not the failed bare pod restart (INC-012)."},
    {"case": "C03", "cond": "B", "metric": "root_cause_specific", "frozen": 0, "human": 0,
     "why": "Confirmed miss: RecallOps cited INC-003's older cause (no eviction policy) and its top hits were INC-003/008/016, not INC-015's TTL key-prefix cause."},
    {"case": "C14", "cond": "A", "metric": "root_cause_specific", "frozen": 1, "human": 0,
     "why": "Stateless said 'regression in the ranking algorithm' -- loose match on 'flag'+'timeout'; a strict reader might not credit the known mechanism."},
]
out["adjudicated_headline"] = {"root_cause_specific_B": "14/15 (frozen 13/15)", "root_cause_specific_A": "0/15 (frozen 1/15)", "failed_fix_avoided_A": "2/7 (frozen 1/7)", "failed_fix_avoided_B": "7/7"}
(H / "posthoc_audit.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))

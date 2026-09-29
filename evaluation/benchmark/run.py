"""Memory-vs-stateless benchmark runner.

  python run.py collect   # call both conditions per case, store raw outputs under raw/  (no scoring)
  python run.py score     # score raw/ with the FROZEN scoring.py -> results.json (+ report.md via report.py)

Condition A (Stateless): one llm.complete() call (same wrapper, same primary model, same JSON
  schema as the production briefing) with ONLY the current alert. No Hindsight, no ledger.
Condition B (RecallOps): the production with_memory path of POST /compare, replicated call-for-call
  in-process: analysis.analyze_alert() (Hindsight recall + ledger scoring + warnings/team/recurrence)
  then routes.briefing.generate_sections() (guarded LLM briefing) / template_sections() if no evidence.
  It has NO side effects (no retain, no incident record). The FastAPI lifespan (auto-seed) is never started.

Read-only against production Hindsight; never seeds/resets/retains.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

FROZEN_FILES = ["scoring.py", "cases.json", "ground_truth.json", "build_data.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen() -> dict:
    frozen = json.loads((HERE / "frozen.json").read_text(encoding="utf-8"))
    for name in FROZEN_FILES:
        if sha(HERE / name) != frozen["sha256"][name]:
            sys.exit(f"REFUSING: {name} changed after freeze (scoring/cases/ground truth must not be edited after seeing outputs)")
    return frozen


A_SYSTEM = (
    "You are an incident response assistant writing a short triage briefing for a new alert. "
    "You only have the alert below.\n"
    'Respond with strict JSON only: {"root_cause": string, "blast_radius": string, '
    '"first_actions": [string, string, string], "last_fixed_by": string or null}'
)


def a_messages(alert: dict) -> list[dict]:
    user = (
        f"New alert: {alert['title']}. Service: {alert['service']}, severity: {alert['severity']}.\n"
        f"Symptoms: {alert['symptoms']}\nError: {alert['error_message']}"
    )
    return [{"role": "system", "content": A_SYSTEM}, {"role": "user", "content": user}]


def _norm_sections(raw: dict) -> dict:
    fa = raw.get("first_actions") or []
    if isinstance(fa, str):
        fa = [fa]
    return {
        "root_cause": str(raw.get("root_cause") or ""),
        "blast_radius": str(raw.get("blast_radius") or ""),
        "first_actions": [str(x) for x in fa],
        "last_fixed_by": raw.get("last_fixed_by"),
    }


async def collect() -> None:
    frozen = verify_frozen()
    from app import analysis, llm, memory
    from app.config import get_settings
    from app.routes.briefing import generate_sections, template_sections

    settings = get_settings()
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))

    # --- recorder around the ONE llm wrapper (no source modified; runtime wrap only) ---------
    calls: list[dict] = []
    real_complete = llm.complete

    async def recording_complete(messages, **kw):
        t0 = time.perf_counter()
        res = await real_complete(messages, **kw)
        calls.append({
            "messages": messages, "kwargs": {k: v for k, v in kw.items() if k != "client"},
            "text": res.text, "degraded": res.degraded, "model_used": res.model_used,
            "parsed": res.parsed, "seconds": round(time.perf_counter() - t0, 3),
        })
        return res

    llm.complete = recording_complete

    meta = {
        "head_sha": (HERE / "head_sha.txt").read_text().strip(),
        "head_sha_at_collect": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "model_primary": settings.llm_model_primary, "model_fallback": settings.llm_model_fallback,
        "frozen_at": frozen["frozen_at"], "collect_started": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(cases), "temperature": 0.2,
    }
    (HERE / "raw").mkdir(exist_ok=True)

    ping_status, ping_s = await memory.ping()
    meta["hindsight_ping"] = {"status": ping_status, "seconds": round(ping_s, 3)}
    print("hindsight ping:", ping_status, round(ping_s, 2), "s", flush=True)

    for case in cases:
        cid, alert = case["case_id"], dict(case["alert"])
        alert["log_snippet"] = memory.mask_secrets(alert["log_snippet"])
        rec: dict = {"case_id": cid, "alert": alert}

        # ---------------- A: stateless ----------------
        calls.clear()
        t0 = time.perf_counter()
        try:
            res = await llm.complete(a_messages(alert), json_mode=True)
            elapsed = time.perf_counter() - t0
            ok = (not res.degraded) and isinstance(res.parsed, dict)
            rec["A"] = {
                "ok": ok, "degraded": res.degraded, "model_used": res.model_used, "latency_s": round(elapsed, 3),
                "response": _norm_sections(res.parsed) if ok else None, "raw_text": res.text, "llm_calls": list(calls),
            }
        except Exception as exc:  # never expected; recorded as failure
            rec["A"] = {"ok": False, "degraded": True, "error": type(exc).__name__, "latency_s": round(time.perf_counter() - t0, 3), "response": None}

        # ---------------- B: RecallOps (production with_memory path) ----------------
        calls.clear()
        t0 = time.perf_counter()
        try:
            result = await analysis.analyze_alert(dict(alert))
            t_analysis = time.perf_counter() - t0
            incident_like = {
                "title": alert["title"], "service": alert["service"], "severity": alert["severity"],
                "symptoms": alert["symptoms"], "error_message": alert["error_message"],
                "memory_state": result.memory_state,
                "evidence_incident_ids": [e["incident_id"] for e in result.evidence],
                "ranked_fixes": [r.to_dict() for r in result.ranked_fixes],
                "warnings": result.warnings, "team_hint": result.team_hint, "recurrence": result.recurrence,
            }
            if result.evidence:
                sections, cited = await generate_sections(incident_like)
                path = "generate_sections"
            else:
                sections, cited = template_sections(incident_like), []
                path = "template_no_evidence"
            elapsed = time.perf_counter() - t0
            llm_ok_calls = [c for c in calls if not c["degraded"]]
            template_fallback = path == "generate_sections" and (
                not llm_ok_calls or sections.get("first_actions", [""])[0].startswith("Apply the top-ranked fix:")
            )
            rec["B"] = {
                "ok": True, "degraded": bool(result.degraded), "degraded_reason": result.degraded_reason,
                "path": path, "template_fallback": template_fallback,
                "latency_s": round(elapsed, 3), "analysis_latency_s": round(t_analysis, 3),
                "models_used": sorted({c["model_used"] for c in llm_ok_calls if c["model_used"]}),
                "response": _norm_sections(sections), "cited_incident_ids": cited,
                "structured": {
                    "memory_state": result.memory_state, "evidence": result.evidence,
                    "ranked_fixes": [r.to_dict() for r in result.ranked_fixes], "warnings": result.warnings,
                    "team_hint": result.team_hint, "recurrence": result.recurrence,
                },
                "llm_calls": list(calls),
            }
        except Exception as exc:
            rec["B"] = {"ok": False, "degraded": True, "error": type(exc).__name__, "latency_s": round(time.perf_counter() - t0, 3), "response": None}

        (HERE / "raw" / f"{cid}.json").write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
        print(cid, "A ok" if rec["A"]["ok"] else "A FAIL", f'{rec["A"]["latency_s"]}s |',
              "B ok" if rec["B"]["ok"] else "B FAIL", f'{rec["B"]["latency_s"]}s',
              "state=" + str((rec["B"].get("structured") or {}).get("memory_state")),
              "degraded" if rec["B"].get("degraded") else "", flush=True)
        await asyncio.sleep(1.5)

    meta["collect_finished"] = datetime.now(timezone.utc).isoformat()
    (HERE / "raw" / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    await memory.get_client().aclose()


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)


def score() -> None:
    frozen = verify_frozen()
    import scoring

    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    gt = json.loads((HERE / "ground_truth.json").read_text(encoding="utf-8"))
    meta = json.loads((HERE / "raw" / "_meta.json").read_text(encoding="utf-8"))
    seed = json.loads((ROOT / "backend" / "data" / "seed_incidents.json").read_text(encoding="utf-8"))
    team = json.loads((ROOT / "backend" / "data" / "seed_team.json").read_text(encoding="utf-8"))
    seed_ids = {i["incident_id"] for i in seed}
    team_names = {m["name"] for m in (team if isinstance(team, list) else team.get("members", team.get("team", [])))}

    per_case = []
    for case in cases:
        cid = case["case_id"]
        raw = json.loads((HERE / "raw" / f"{cid}.json").read_text(encoding="utf-8"))
        g = gt[cid]
        entry = {"case_id": cid, "pattern": g["pattern_signature"], "service": g["service"], "demo_tuned": case["demo_tuned"], "title": case["alert"]["title"]}
        for cond in ("A", "B"):
            r = raw[cond]
            entry[cond] = {"ok": r["ok"], "degraded": r.get("degraded"), "latency_s": r["latency_s"], "model_used": r.get("model_used") or r.get("models_used")}
            if r["ok"] and r["response"]:
                structured = r.get("structured") if cond == "B" else None
                s = scoring.score_condition(r["response"], structured, g, seed_ids, team_names)
                entry[cond]["scores"] = s
                entry[cond]["composite"] = round(scoring.composite(s), 4)
            if cond == "B":
                entry[cond]["memory_state"] = (r.get("structured") or {}).get("memory_state")
                entry[cond]["template_fallback"] = r.get("template_fallback")
                entry[cond]["live_bank_evidence"] = [e["incident_id"] for e in (r.get("structured") or {}).get("evidence", []) if e.get("source_bank") == "recallops-live"]
        if "composite" in entry["A"] and "composite" in entry["B"]:
            entry["verdict"] = scoring.verdict(entry["A"]["composite"], entry["B"]["composite"])
        else:
            entry["verdict"] = "excluded_failure"
        per_case.append(entry)

    def agg(cond: str, getter, applicable=lambda s: True):
        vals = []
        for e in per_case:
            s = e[cond].get("scores")
            if s is None:
                continue
            v = getter(s)
            if v is None or v == "N/A":
                continue
            vals.append(v)
        return {"n": len(vals), "sum": sum(vals), "mean": round(sum(vals) / len(vals), 4) if vals else None}

    def both(getter):
        return {c: agg(c, getter) for c in ("A", "B")}

    metrics = {
        "root_cause_generic": both(lambda s: s["root_cause"]["generic"]),
        "root_cause_specific_known": both(lambda s: s["root_cause"]["specific"]),
        "worked_fix_any_of_3_actions": both(lambda s: s["worked_fix"]["any_of_actions"]),
        "worked_fix_first_action": both(lambda s: s["worked_fix"]["first_action"]),
        "failed_fix_avoided": both(lambda s: None if s["failed_fix_avoidance"] is None else s["failed_fix_avoidance"]["avoided"]),
        "unsupported_claims_total_count": both(lambda s: s["unsupported_claims"]["count"]),
        "responses_with_unsupported_claim": both(lambda s: 1 - s["unsupported_claims"]["clean"]),
        "actionability_0_3": both(lambda s: s["actionability"]["score"]),
        "failed_fix_warning_B_only": {"A": "N/A", "B": agg("B", lambda s: None if s["failed_fix_warning"] in (None, "N/A") else s["failed_fix_warning"]["warned"])},
        "failed_fix_warning_structured_only_B": {"A": "N/A", "B": agg("B", lambda s: None if s["failed_fix_warning"] in (None, "N/A") else s["failed_fix_warning"]["structured_warning"])},
        "evidence_recall_B_only": {"A": "N/A", "B": agg("B", lambda s: s["evidence_retrieval"]["recall"])},
        "evidence_precision_B_only": {"A": "N/A", "B": agg("B", lambda s: s["evidence_retrieval"]["precision"])},
        "evidence_top1_expected_B_only": {"A": "N/A", "B": agg("B", lambda s: s["evidence_retrieval"]["top1_expected"])},
        "resolver_knowledge_any_B_only": {"A": "N/A", "B": agg("B", lambda s: s["resolver_knowledge"]["any"])},
        "resolver_team_hint_correct_B_only": {"A": "N/A", "B": agg("B", lambda s: s["resolver_knowledge"]["team_hint_correct"])},
        "recurrence_detected_B_only": {"A": "N/A", "B": agg("B", lambda s: s["recurrence_detection"]["detected"])},
        "recurrence_occurrence_number_exact_B_only": {"A": "N/A", "B": agg("B", lambda s: s["recurrence_detection"]["occurrence_number_exact"])},
        "composite_shared_metrics": both(lambda s: None),  # replaced below
    }
    metrics["composite_shared_metrics"] = {
        c: {"n": sum(1 for e in per_case if "composite" in e[c]), "mean": round(statistics.mean([e[c]["composite"] for e in per_case if "composite" in e[c]]), 4)} for c in ("A", "B")
    }
    incidental = [e["A"]["scores"]["incidental_failed_fix_warning_unscored"] for e in per_case if e["A"].get("scores") and e["A"]["scores"].get("incidental_failed_fix_warning_unscored") is not None]

    lat = {c: [e[c]["latency_s"] for e in per_case if e[c]["ok"]] for c in ("A", "B")}
    latency = {c: {"n": len(v), "median_s": round(statistics.median(v), 3) if v else None, "p95_s": pct(v, 0.95) if v else None, "mean_s": round(statistics.mean(v), 3) if v else None, "max_s": max(v) if v else None} for c, v in lat.items()}
    verdicts = [e["verdict"] for e in per_case]
    health = {
        c: {"successful": sum(1 for e in per_case if e[c]["ok"] and not e[c]["degraded"]),
            "degraded": sum(1 for e in per_case if e[c]["ok"] and e[c]["degraded"]),
            "failures": sum(1 for e in per_case if not e[c]["ok"])} for c in ("A", "B")
    }
    health["B"]["template_fallbacks"] = sum(1 for e in per_case if e["B"].get("template_fallback"))
    health["B"]["memory_state_counts"] = {st: sum(1 for e in per_case if e["B"].get("memory_state") == st) for st in ("matched", "no_match", "empty")}
    health["B"]["weak_or_no_match_case_ids"] = [e["case_id"] for e in per_case if e["B"].get("memory_state") != "matched" or (e["B"].get("scores") and e["B"]["scores"]["evidence_retrieval"]["any_expected"] == 0)]
    health["B"]["cases_with_live_bank_evidence"] = {e["case_id"]: e["B"]["live_bank_evidence"] for e in per_case if e["B"].get("live_bank_evidence")}

    results = {
        "head_sha": meta["head_sha"], "head_sha_at_collect": meta["head_sha_at_collect"], "model_primary": meta["model_primary"], "model_fallback": meta["model_fallback"],
        "n_cases": len(cases), "patterns": sorted({g["pattern_signature"] for g in gt.values()}),
        "collect_started": meta["collect_started"], "collect_finished": meta["collect_finished"], "frozen_at": frozen["frozen_at"],
        "scored_at": datetime.now(timezone.utc).isoformat(), "hindsight_ping": meta["hindsight_ping"],
        "request_health": health, "metrics": metrics, "latency": latency,
        "wins": {"recallops": verdicts.count("recallops"), "tie": verdicts.count("tie"), "stateless": verdicts.count("stateless"), "excluded_failure": verdicts.count("excluded_failure")},
        "stateless_incidental_failed_fix_warnings_unscored": {"n_applicable": len(incidental), "n_warned": sum(incidental)},
        "tie_margin": scoring.TIE_MARGIN, "per_case": per_case,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({k: results[k] for k in ("wins", "latency", "request_health")}, indent=2))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "collect":
        asyncio.run(collect())
    elif cmd == "score":
        score()
    else:
        sys.exit(__doc__)

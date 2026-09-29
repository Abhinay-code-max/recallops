"""Deterministic scoring for the memory-vs-stateless benchmark. FROZEN before any model output
was observed (hash recorded in frozen.json by freeze.py; run.py refuses to score if it changed).

A "response" is a dict:
  root_cause: str, blast_radius: str, first_actions: list[str], last_fixed_by: str|None
  (B additionally carries structured pipeline output: evidence, ranked_fixes, warnings,
   team_hint, recurrence, memory_state -- passed separately as `structured`.)

Metric applicability
  Applicable to BOTH conditions: root_cause (generic + specific), worked_fix, failed_fix_avoidance,
    unsupported_claims, actionability, latency.
  History-only (Stateless = N/A, never 0): failed_fix_warning, evidence_retrieval,
    resolver_knowledge, recurrence_detection.
  A metric is also None ("not applicable to this case") when the seed data has nothing to test,
  e.g. failed_fix_avoidance on a pattern with no historically failed fix.

Composite (win/tie/loss): mean of the metrics that are applicable to BOTH conditions on the case,
  each scaled 0..1: root_cause_specific, worked_fix_any, failed_fix_avoidance, claims_clean
  (1 if zero unsupported claims else 0), actionability/3.  |A-B| <= TIE_MARGIN => tie.
"""
from __future__ import annotations

import re
from typing import Any

TIE_MARGIN = 0.10
INC_RE = re.compile(r"\bINC-\d{3,}\b")
NEGATION_RE = re.compile(r"\b(do not|don't|dont|do n't|avoid|never|not|instead of|rather than|without|skip|no need to|shouldn't|should not)\b", re.I)
HISTORY_PHRASE_RE = re.compile(
    r"\b(last time|previously (seen|occurred|happened|resolved|fixed)|in (a |an )?(previous|prior|past|earlier) incidents?|"
    r"prior incidents?|past incidents?|we('ve| have) seen this|has happened before|happened before|"
    r"(previous|prior|past) (occurrences?|outages?)|historical(ly)?|(was|were) (previously )?(resolved|fixed) by)\b", re.I)
RECURRENCE_TEXT_RE = re.compile(r"\b(recur(s|red|rence|ring)?|again|repeat(ed)?|occurrence #?\d+|#\d+ (of|occurrence)|(\d+)(st|nd|rd|th) (time|occurrence)|third time|fourth time|fifth time|second time|previous (incidents?|occurrences?)|pattern)\b", re.I)
DIAGNOSTIC_START_RE = re.compile(
    r"^\W*(immediately[, ]+|first[, ]+|then[, ]+)?(check|review|look|investigate|gather|monitor|examine|inspect|verify|confirm|assess|identify|notify|page|escalate|open|declare|collect|analy[sz]e|determine|ask|find|start by (checking|reviewing|looking))\b", re.I)
SPECIFIC_ARTIFACT_RE = re.compile(
    r"`[^`]+`|\b[a-z][a-z0-9]*[_\-.][a-z0-9_\-.]+\b|\b\d+(\.\d+)?\s?(%|ms|s|min|gb|mb|x|replicas|connections|partitions)\b|--\w+|\bkubectl\b|\bpg_\w+|\bredis-cli\b|\bcert-manager\b", re.I)
VERIFY_RE = re.compile(r"\b(verify|confirm|until|expected|should (drop|return|recover|fall|stabili[sz]e)|monitor.{0,60}(return|drop|recover|baseline|normal|stabili[sz]e)|watch.{0,40}(drop|recover|baseline|normal)|validate)\b", re.I)

# resolver names present in backend/data/seed_team.json (loaded lazily by caller and passed in)


def _flags(rx: str) -> int:
    return re.I | re.S


def _match(rx: str, text: str) -> bool:
    return re.search(rx, text, _flags(rx)) is not None


def response_text(resp: dict[str, Any]) -> str:
    return " \n".join([
        str(resp.get("root_cause") or ""), str(resp.get("blast_radius") or ""),
        " \n".join(str(a) for a in (resp.get("first_actions") or [])), str(resp.get("last_fixed_by") or ""),
    ])


# ---------------------------------------------------------------- root cause
def score_root_cause(resp: dict[str, Any], gt: dict[str, Any]) -> dict[str, Any]:
    text = str(resp.get("root_cause") or "")
    generic = _match(gt["root_cause_generic"], text)
    spec = gt["root_cause_specific"]
    matched = [i for i, rx in enumerate(spec["groups"]) if _match(rx, text)]
    specific = all(r in matched for r in spec["required"]) and len(matched) >= spec["min_groups"]
    return {"generic": int(generic), "specific": int(specific), "groups_matched": matched}


# ---------------------------------------------------------------- fixes
def _action_recommends(action: str, rx: str) -> bool:
    """True if `action` recommends the fix described by `rx` (a negated mention like
    "do not roll back" does not count as recommending it)."""
    for m in re.finditer(rx, action, _flags(rx)):
        window = action[max(0, m.start() - 45): m.start()]
        if NEGATION_RE.search(window):
            continue
        return True
    return False


def _action_warns_against(text: str, rx: str) -> bool:
    for m in re.finditer(rx, text, _flags(rx)):
        window = text[max(0, m.start() - 60): m.start()]
        if NEGATION_RE.search(window) or re.search(r"\b(fail(ed|s)?|ineffective|did not (help|work)|didn't (help|work)|won't (help|work)|no effect|risky)\b", text[max(0, m.start() - 80): m.end() + 120], re.I):
            return True
    return False


def score_worked_fix(resp: dict[str, Any], gt: dict[str, Any]) -> dict[str, Any]:
    actions = [str(a) for a in (resp.get("first_actions") or [])]
    hit_any = [t for t, rx in gt["worked_fixes"].items() if any(_action_recommends(a, rx) for a in actions)]
    first = [t for t, rx in gt["worked_fixes"].items() if actions and _action_recommends(actions[0], rx)]
    return {"any_of_actions": int(bool(hit_any)), "first_action": int(bool(first)), "matched_fix_types": hit_any}


def score_failed_fix_avoidance(resp: dict[str, Any], gt: dict[str, Any]) -> dict[str, Any] | None:
    if not gt["failed_fixes"]:
        return None
    actions = [str(a) for a in (resp.get("first_actions") or [])]
    recommended = [t for t, rx in gt["failed_fixes"].items() if any(_action_recommends(a, rx) for a in actions)]
    return {"avoided": int(not recommended), "recommended_failed_fixes": recommended}


def score_failed_fix_warning(resp: dict[str, Any], structured: dict[str, Any] | None, gt: dict[str, Any]) -> dict[str, Any] | None:
    """History-only; caller passes structured=None for Stateless -> N/A."""
    if not gt["failed_fixes"] or structured is None:
        return None
    warn_msgs = " \n".join(w.get("message", "") for w in (structured.get("warnings") or []) if w.get("kind") == "failed_fix")
    structured_hit = bool(warn_msgs) and any(_match(rx, warn_msgs) for rx in gt["failed_fixes"].values())
    text = response_text(resp)
    text_hit = any(_action_warns_against(text, rx) for rx in gt["failed_fixes"].values())
    return {"structured_warning": int(structured_hit), "text_warning": int(text_hit), "warned": int(structured_hit or text_hit)}


def incidental_failed_fix_warning(resp: dict[str, Any], gt: dict[str, Any]) -> int | None:
    """Recorded for Stateless for transparency ONLY (never scored): did it happen to warn against the fix?"""
    if not gt["failed_fixes"]:
        return None
    return int(any(_action_warns_against(response_text(resp), rx) for rx in gt["failed_fixes"].values()))


# ---------------------------------------------------------------- history-only metrics (B)
def score_evidence(structured: dict[str, Any], resp: dict[str, Any], gt: dict[str, Any]) -> dict[str, Any]:
    ev_ids = [e["incident_id"] for e in (structured.get("evidence") or [])]
    expected = set(gt["expected_incident_ids"])
    ok = expected | set(gt["related_incident_ids"])
    cited = set(INC_RE.findall(response_text(resp)))
    return {
        "retrieved_ids": ev_ids,
        "recall": (len(expected & set(ev_ids)) / len(expected)) if expected else None,
        "precision": (len(ok & set(ev_ids)) / len(ev_ids)) if ev_ids else 0.0,
        "top1_expected": int(bool(ev_ids) and ev_ids[0] in expected),
        "any_expected": int(bool(expected & set(ev_ids))),
        "briefing_cited_expected_recall": len(expected & cited) / len(expected) if expected else None,
    }


def score_resolver(structured: dict[str, Any], resp: dict[str, Any], gt: dict[str, Any]) -> dict[str, Any]:
    names = set(gt["resolvers_with_worked_fix"])
    hint = (structured.get("team_hint") or {}).get("person")
    text = response_text(resp)
    in_hint = hint in names if hint else False
    in_text = any(n in text for n in names)
    return {"team_hint_correct": int(in_hint), "briefing_names_resolver": int(in_text),
            "primary_resolver_identified": int(hint == gt["primary_resolver"] or gt["primary_resolver"] in text),
            "any": int(in_hint or in_text)}


def score_recurrence(structured: dict[str, Any], resp: dict[str, Any], gt: dict[str, Any]) -> dict[str, Any]:
    rec = structured.get("recurrence")
    struct_flag = rec is not None
    exact = struct_flag and rec.get("occurrence_number") == gt["expected_occurrence_number"]
    text_flag = bool(RECURRENCE_TEXT_RE.search(response_text(resp)))
    return {"structured_flag": int(struct_flag), "occurrence_number_exact": int(bool(exact)),
            "text_mentions_recurrence": int(text_flag), "detected": int(struct_flag or text_flag)}


# ---------------------------------------------------------------- unsupported historical claims
def score_unsupported(resp: dict[str, Any], structured: dict[str, Any] | None, gt: dict[str, Any],
                      seed_ids: set[str], team_names: set[str]) -> dict[str, Any]:
    text = response_text(resp)
    claims: list[str] = []
    cited = set(INC_RE.findall(text))
    evidence_ids = {e["incident_id"] for e in (structured or {}).get("evidence", [])}
    for cid in sorted(cited):
        if structured is None:
            claims.append(f"cites {cid} with no history available")
        elif cid not in seed_ids:
            claims.append(f"cites non-existent incident {cid}")
        elif cid not in evidence_ids:
            claims.append(f"cites {cid} which was not returned by recall")
    # history phrases with no incident id support
    for m in HISTORY_PHRASE_RE.finditer(text):
        if structured is None or not evidence_ids:
            claims.append(f"unsupported history phrase: '{m.group(0)}'")
    # numeric recurrence claims
    for m in re.finditer(r"(\d+|two|three|four|five)\s+(prior|previous|earlier|past)\s+(incidents?|times|occurrences?)", text, re.I):
        words = {"two": 2, "three": 3, "four": 4, "five": 5}
        n = int(m.group(1)) if m.group(1).isdigit() else words[m.group(1).lower()]
        if structured is None or n != gt["prior_occurrences"]:
            claims.append(f"wrong/unsupported prior count '{m.group(0)}' (seed: {gt['prior_occurrences']})")
    # named people claimed as prior resolvers
    pool_resolvers = set(gt["resolvers_with_worked_fix"])
    for name in sorted(team_names):
        if name in text and (structured is None or name not in pool_resolvers):
            claims.append(f"names {name} as resolver but they did not resolve this pattern in seed data")
    return {"count": len(claims), "clean": int(not claims), "claims": claims}


# ---------------------------------------------------------------- actionability 0..3
def score_actionability(resp: dict[str, Any]) -> dict[str, Any]:
    actions = [str(a) for a in (resp.get("first_actions") or []) if str(a).strip()]
    a1 = int(bool(actions) and not DIAGNOSTIC_START_RE.search(actions[0]))
    a2 = int(sum(1 for a in actions if SPECIFIC_ARTIFACT_RE.search(a)) >= 2)
    a3 = int(bool(VERIFY_RE.search(response_text(resp))))
    return {"score": a1 + a2 + a3, "concrete_first_action": a1, "specific_artifacts": a2, "verification_criterion": a3}


# ---------------------------------------------------------------- per-condition + composite
def score_condition(resp: dict[str, Any], structured: dict[str, Any] | None, gt: dict[str, Any],
                    seed_ids: set[str], team_names: set[str]) -> dict[str, Any]:
    has_memory = structured is not None
    out: dict[str, Any] = {
        "root_cause": score_root_cause(resp, gt),
        "worked_fix": score_worked_fix(resp, gt),
        "failed_fix_avoidance": score_failed_fix_avoidance(resp, gt),
        "unsupported_claims": score_unsupported(resp, structured, gt, seed_ids, team_names),
        "actionability": score_actionability(resp),
        "failed_fix_warning": score_failed_fix_warning(resp, structured, gt) if has_memory else "N/A",
        "evidence_retrieval": score_evidence(structured, resp, gt) if has_memory else "N/A",
        "resolver_knowledge": score_resolver(structured, resp, gt) if has_memory else "N/A",
        "recurrence_detection": score_recurrence(structured, resp, gt) if has_memory else "N/A",
    }
    if not has_memory:
        out["incidental_failed_fix_warning_unscored"] = incidental_failed_fix_warning(resp, gt)
    return out


def composite(s: dict[str, Any]) -> float:
    parts = [float(s["root_cause"]["specific"]), float(s["worked_fix"]["any_of_actions"]),
             float(s["unsupported_claims"]["clean"]), s["actionability"]["score"] / 3.0]
    if s["failed_fix_avoidance"] is not None:
        parts.append(float(s["failed_fix_avoidance"]["avoided"]))
    return sum(parts) / len(parts)


def verdict(a: float, b: float) -> str:
    if abs(a - b) <= TIE_MARGIN:
        return "tie"
    return "recallops" if b > a else "stateless"

"""Sanity checks of scoring.py on hand-written synthetic strings (no model output involved)."""
import json
import scoring as S

gt = json.load(open("ground_truth.json"))
seed_ids = {f"INC-{i:03d}" for i in range(1, 23)}
team = {"Priya Nair", "Rahul Mehta", "Ananya Iyer", "Emily Chen", "Sofia Martinez", "David Kim", "Arjun Verma"}

# pool case
g = gt["C01"]
good = {"root_cause": "The retry path leaks DB sessions and never releases them, exhausting the pool.", "blast_radius": "checkout", "first_actions": ["Increase the Postgres max pool size from 20 to 60 and force-close stale sessions.", "Do not roll back the deploy; it failed in INC-002.", "Monitor until error rate returns to baseline."], "last_fixed_by": "Priya Nair"}
assert S.score_root_cause(good, g)["specific"] == 1
assert S.score_worked_fix(good, g)["first_action"] == 1
assert S.score_failed_fix_avoidance(good, g)["avoided"] == 1, S.score_failed_fix_avoidance(good, g)
bad = {"root_cause": "Database connection pool exhausted after the deploy.", "blast_radius": "x", "first_actions": ["Roll back the v2.6.0 deploy immediately.", "Check logs.", "Restart pods."], "last_fixed_by": None}
assert S.score_root_cause(bad, g) == {"generic": 1, "specific": 0, "groups_matched": []}
assert S.score_failed_fix_avoidance(bad, g)["avoided"] == 0
assert S.score_worked_fix(bad, g)["any_of_actions"] == 0
assert S.score_actionability(bad)["concrete_first_action"] == 1
diag = {"first_actions": ["Check the logs for errors.", "Review recent deploys.", "Investigate."], "root_cause": ""}
assert S.score_actionability(diag)["score"] == 0
# unsupported claims
assert S.score_unsupported({"root_cause": "As in INC-002 last time", "first_actions": []}, None, g, seed_ids, team)["count"] >= 2
st = {"evidence": [{"incident_id": "INC-002"}]}
assert S.score_unsupported({"root_cause": "As in INC-002.", "first_actions": []}, st, g, seed_ids, team)["clean"] == 1
assert S.score_unsupported({"root_cause": "As in INC-009.", "first_actions": []}, st, g, seed_ids, team)["clean"] == 0
assert S.score_unsupported({"root_cause": "As in INC-099.", "first_actions": []}, st, g, seed_ids, team)["clean"] == 0
assert S.score_unsupported({"root_cause": "Ask Rahul Mehta.", "first_actions": []}, st, g, seed_ids, team)["clean"] == 0
assert S.score_unsupported({"root_cause": "Ask Priya Nair.", "first_actions": []}, st, g, seed_ids, team)["clean"] == 1
# warnings / recurrence / resolver / evidence
sB = {"warnings": [{"kind": "failed_fix", "message": "Rollback to previous deploy failed 2 of 2 time(s) for this pattern -- try another fix first."}], "recurrence": {"occurrence_number": 5}, "team_hint": {"person": "Priya Nair"}, "evidence": [{"incident_id": "INC-021"}, {"incident_id": "INC-002"}]}
assert S.score_failed_fix_warning(bad, sB, g)["structured_warning"] == 1
assert S.score_failed_fix_warning(bad, None, g) is None
assert S.score_recurrence(sB, bad, g)["occurrence_number_exact"] == 1
assert S.score_resolver(sB, bad, g)["team_hint_correct"] == 1
ev = S.score_evidence(sB, bad, g); assert ev["recall"] == 0.5 and ev["precision"] == 1.0
# N/A handling
assert S.score_failed_fix_avoidance(good, gt["C03"]) is None
sc = S.score_condition(good, None, g, seed_ids, team)
assert sc["failed_fix_warning"] == "N/A" and sc["evidence_retrieval"] == "N/A" and sc["recurrence_detection"] == "N/A"
# other specifics
assert S.score_root_cause({"root_cause": "Redis has no TTL on dead-letter keys with a prefix mismatch"}, gt["C03"])["specific"] == 1
assert S.score_root_cause({"root_cause": "Redis hit maxmemory"}, gt["C03"])["specific"] == 0
assert S.score_root_cause({"root_cause": "cert-manager renewal failed because the DNS-01 API token expired"}, gt["C09"])["specific"] == 1
assert S.score_worked_fix({"first_actions": ["Scale the consumer group from 3 to 8 replicas."]}, gt["C04"])["first_action"] == 1
assert S.score_failed_fix_avoidance({"first_actions": ["Add partitions to the topic."]}, gt["C04"])["avoided"] == 0
assert S.verdict(0.5, 0.55) == "tie" and S.verdict(0.3, 0.7) == "recallops" and S.verdict(0.7, 0.3) == "stateless"
print("synthetic scoring checks passed")

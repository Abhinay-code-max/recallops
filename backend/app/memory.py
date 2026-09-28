"""Hindsight memory layer: banks, retain/recall/reflect wrappers, secret masking.

Scaffold only — implemented in Prompt 2 (docs/PROMPTS.md). Confirmed against the
installed hindsight-client package (see scripts/hindsight_smoke.py):
client = hindsight_client.Hindsight(base_url=..., api_key=...); client.create_bank(...),
client.retain(...), client.recall(...), client.reflect(...).

Banks per docs/SPEC.md section 4: incidents, fix-outcomes, team, baseline (empty).
"""
